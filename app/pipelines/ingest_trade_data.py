"""Small, transactional trade-ingestion service built from existing pipeline parts."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import models as db
from app.pipelines.observation_identity import (
    ObservationIdentity,
    build_dataset_identity,
    canonical_json,
    identify_observation,
)
from app.pipelines.trade_models import NormalizedTradeObservation
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.data_models import ParsedObservation
from app.sdmx.data_parser import parse_comtrade_response
from app.validation.context import ValidationContext
from app.validation.engine import ValidationEngine, get_trade_validation_rules
from app.validation.models import (
    ValidationResult,
    ValidationSeverity,
    ValidationSummary,
)


ResponseFetcher = Callable[[str, dict[str, str]], Mapping[str, Any]]

REVISION_UPDATE_FIELDS = (
    "primary_value",
    "quantity",
    "net_weight",
    "gross_weight",
    "cif_value",
    "fob_value",
    "source_attributes",
    "source_fields",
    "observation_content_hash",
)


class TradeIngestionError(RuntimeError):
    """Fatal ingestion failure whose batch has already been finalized."""

    def __init__(self, batch_id: int, message: str) -> None:
        super().__init__(message)
        self.batch_id = batch_id


@dataclass(frozen=True)
class TradeQuery:
    type_code: str
    frequency_code: str
    classification_code: str
    periods: tuple[str, ...]
    reporter_code: str
    flow_code: str
    partner_code: str
    partner2_code: str
    commodity_code: str
    max_records: int = 1
    breakdown_mode: str = "classic"
    include_descriptions: bool = True
    response_format: str = "JSON"

    def __post_init__(self) -> None:
        if not self.periods or any(not period for period in self.periods):
            raise ValueError("At least one non-empty period is required")
        if not 1 <= self.max_records <= 500:
            raise ValueError("Comtrade preview max_records must be between 1 and 500")

    def batch_parameters(self) -> dict[str, object]:
        return {
            "breakdownMode": self.breakdown_mode,
            "classificationCode": self.classification_code,
            "cmdCode": self.commodity_code,
            "flowCode": self.flow_code,
            "format": self.response_format,
            "freqCode": self.frequency_code,
            "includeDesc": self.include_descriptions,
            "maxRecords": self.max_records,
            "partner2Code": self.partner2_code,
            "partnerCode": self.partner_code,
            "period": list(self.periods),
            "reporterCode": self.reporter_code,
            "typeCode": self.type_code,
        }

    def request_parameters(self, period: str) -> dict[str, str]:
        if period not in self.periods:
            raise ValueError(f"Unexpected period for this query: {period!r}")
        return {
            "breakdownMode": self.breakdown_mode,
            "cmdCode": self.commodity_code,
            "flowCode": self.flow_code,
            "format": self.response_format,
            "includeDesc": str(self.include_descriptions).lower(),
            "maxRecords": str(self.max_records),
            "partner2Code": self.partner2_code,
            "partnerCode": self.partner_code,
            "period": period,
            "reporterCode": self.reporter_code,
        }


@dataclass
class _Counters:
    received: int = 0
    parsed: int = 0
    accepted: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    rejected: int = 0


def aggregate_batch_checksum(period_checksums: list[tuple[str, str]]) -> str | None:
    """Hash a period-ordered canonical list of per-response checksums."""
    if not period_checksums:
        return None
    entries = [
        {"checksum": checksum, "period": period}
        for period, checksum in sorted(period_checksums)
    ]
    return hashlib.sha256(canonical_json(entries).encode("utf-8")).hexdigest()


def _apply_counts(batch: db.IngestionBatch, counters: _Counters) -> None:
    batch.observations_received = counters.received
    batch.observations_parsed = counters.parsed
    batch.observations_accepted = counters.accepted
    batch.observations_inserted = counters.inserted
    batch.observations_updated = counters.updated
    batch.observations_skipped = counters.skipped
    batch.observations_rejected = counters.rejected


def _safe_error(exc: Exception) -> str:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    return message[:2000]


def _scope_mismatch(
    observation: ParsedObservation, period: str, query: TradeQuery
) -> tuple[str, str, object | None] | None:
    expected = {
        "period": period,
        "freqCode": query.frequency_code,
        "reporterCode": query.reporter_code,
        "flowCode": query.flow_code,
        "partnerCode": query.partner_code,
        "partner2Code": query.partner2_code,
        "classificationCode": query.classification_code,
        "cmdCode": query.commodity_code,
    }
    for field, wanted in expected.items():
        actual = observation.source_fields.get(field)
        if str(actual) != str(wanted):
            return field, str(wanted), actual
    return None


def _identity_if_possible(
    observation: NormalizedTradeObservation | None, dataset_identity: str
) -> ObservationIdentity | None:
    if observation is None:
        return None
    try:
        return identify_observation(
            observation, dataset_identity=dataset_identity
        )
    except (TypeError, ValueError):
        return None


def _reject(
    session: Session,
    *,
    batch_id: int,
    parsed: ParsedObservation,
    reason: db.RejectionReasonCode,
    message: str,
    identity: ObservationIdentity | None = None,
    concept_id: str | None = None,
    invalid_value: object | None = None,
) -> db.ObservationRejection:
    rejection = db.ObservationRejection(
        ingestion_batch_id=batch_id,
        source_key=identity.source_key if identity else None,
        source_key_hash=identity.source_key_hash if identity else None,
        concept_id=concept_id,
        invalid_value=None if invalid_value is None else str(invalid_value),
        reason_code=reason,
        severity=db.RejectionSeverity.ERROR,
        message=message,
        raw_observation=parsed.source_fields,
    )
    session.add(rejection)
    session.flush()
    return rejection


def _rejection_reason(result: ValidationResult) -> db.RejectionReasonCode:
    if result.rule_id == "MANDATORY_DIMENSION_PRESENT":
        return db.RejectionReasonCode.MISSING_DIMENSION
    if result.rule_id == "VALID_REFERENCE_AREA":
        return db.RejectionReasonCode.UNMAPPED_REFERENCE_AREA
    if result.rule_id == "REFERENCE_AREA_IS_AU_MEMBER":
        return db.RejectionReasonCode.REFERENCE_AREA_NOT_AU_MEMBER
    if result.rule_id == "VALID_TIME_PERIOD" and result.invalid_value is None:
        return db.RejectionReasonCode.MISSING_TIME_PERIOD
    if result.rule_id == "PRIMARY_VALUE_PRESENT":
        return db.RejectionReasonCode.MISSING_PRIMARY_VALUE
    if result.category.value == "CODELIST":
        return db.RejectionReasonCode.INVALID_CODE
    if result.category.value == "VALUE":
        return db.RejectionReasonCode.INVALID_VALUE
    return db.RejectionReasonCode.NORMALIZATION_ERROR


def _persist_validation_results(
    session: Session,
    *,
    batch_id: int,
    summary: ValidationSummary,
    observation_id: int | None = None,
    rejection_id: int | None = None,
) -> None:
    session.add_all(
        db.ValidationFinding(
            ingestion_batch_id=batch_id,
            observation_id=observation_id,
            observation_rejection_id=rejection_id,
            source_key_hash=result.source_key_hash,
            rule_id=result.rule_id,
            category=result.category.value,
            severity=result.severity.value,
            concept_id=result.concept_id,
            invalid_value=result.invalid_value,
            message=result.message,
            metadata_json=result.metadata,
        )
        for result in summary.results
    )


def _observation_values(
    observation: NormalizedTradeObservation,
    identity: ObservationIdentity,
    *,
    dataset_id: int,
) -> dict[str, object]:
    return {
        "dataset_id": dataset_id,
        "reference_area_source_code": observation.reference_area_source_code,
        "reference_geo_id": observation.reference_geo_id,
        "counterpart_area_source_code": observation.counterpart_area_source_code,
        "counterpart_geo_id": observation.counterpart_geo_id,
        "trade_flow_code": observation.trade_flow_code,
        "frequency_code": observation.frequency_code,
        "commodity_code": observation.commodity_code,
        "commodity_classification": observation.commodity_classification,
        "commodity_sdmx_code": observation.commodity_sdmx_code,
        "time_period": observation.time_period,
        "primary_value": observation.primary_value,
        "quantity": observation.quantity,
        "net_weight": observation.net_weight,
        "gross_weight": observation.gross_weight,
        "cif_value": observation.cif_value,
        "fob_value": observation.fob_value,
        "source_dimensions": observation.source_dimensions,
        "source_attributes": observation.source_attributes,
        "source_fields": observation.source_fields,
        "source_key": identity.source_key,
        "source_key_hash": identity.source_key_hash,
        "observation_content_hash": identity.observation_content_hash,
    }


def _store_observation(
    session: Session,
    *,
    dataset_id: int,
    batch_id: int,
    observation: NormalizedTradeObservation,
    identity: ObservationIdentity,
) -> tuple[str, db.TradeObservation]:
    existing = session.scalar(
        select(db.TradeObservation).where(
            db.TradeObservation.dataset_id == dataset_id,
            db.TradeObservation.source_key_hash == identity.source_key_hash,
        )
    )
    values = _observation_values(
        observation, identity, dataset_id=dataset_id
    )
    if existing is None:
        try:
            with session.begin_nested():
                inserted = db.TradeObservation(
                    **values,
                    first_ingestion_batch_id=batch_id,
                    last_ingestion_batch_id=batch_id,
                )
                session.add(inserted)
                session.flush()
            return "INSERTED", inserted
        except IntegrityError as exc:
            constraint_name = getattr(
                getattr(exc.orig, "diag", None), "constraint_name", None
            )
            sqlite_identity_conflict = (
                "trade_observation.dataset_id, "
                "trade_observation.source_key_hash"
            ) in str(exc)
            if (
                constraint_name
                != "uq_trade_observation_dataset_source_key_hash"
                and not sqlite_identity_conflict
            ):
                raise
            existing = session.scalar(
                select(db.TradeObservation).where(
                    db.TradeObservation.dataset_id == dataset_id,
                    db.TradeObservation.source_key_hash == identity.source_key_hash,
                )
            )
            if existing is None:
                raise
    if existing.observation_content_hash == identity.observation_content_hash:
        # ``last_ingestion_batch_id`` means the last successful batch in which
        # the source observation was seen, even when its content was unchanged.
        existing.last_ingestion_batch_id = batch_id
        return "SKIPPED", existing
    for field in REVISION_UPDATE_FIELDS:
        setattr(existing, field, values[field])
    existing.last_ingestion_batch_id = batch_id
    return "UPDATED", existing


def ingest_trade_query(
    session: Session,
    *,
    dataset_id: int,
    query: TradeQuery,
    fetch_response: ResponseFetcher,
) -> db.IngestionBatch:
    """Fetch, normalize, scope-check, and store one deliberately bounded query."""
    dataset = session.get(db.StatDataset, dataset_id)
    if dataset is None:
        raise ValueError(f"Statistical dataset {dataset_id} does not exist")
    dataset_identity = build_dataset_identity(
        dataset.agency, dataset.dataflow_id, dataset.dataflow_version
    )
    query_parameters = query.batch_parameters()
    batch = db.IngestionBatch(
        dataset_id=dataset.id,
        source_system=dataset.source_system,
        query_key=canonical_json(query_parameters),
        query_parameters=query_parameters,
        start_period=min(query.periods),
        end_period=max(query.periods),
        status=db.IngestionBatchStatus.RUNNING,
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)
    batch_id = batch.id

    counters = _Counters()
    raw_checksums: list[tuple[str, str]] = []
    content_checksums: list[tuple[str, str]] = []
    try:
        validation_context = ValidationContext.from_session(session, dataset)
        validation_engine = ValidationEngine(get_trade_validation_rules())
        for period in query.periods:
            payload = fetch_response(period, query.request_parameters(period))
            records = payload.get("data") if isinstance(payload, Mapping) else None
            if not isinstance(records, list):
                raise ValueError(f"Provider response for {period} has no data list")
            if payload.get("count") != len(records):
                raise ValueError(
                    f"Provider count mismatch for {period}: "
                    f"declared {payload.get('count')}, received {len(records)}"
                )
            counters.received += len(records)
            parsed_response = parse_comtrade_response(payload)
            counters.parsed += parsed_response.record_count
            raw_checksums.append((period, parsed_response.raw_response_checksum))
            content_checksums.append(
                (period, parsed_response.statistical_content_checksum)
            )

            for parsed in parsed_response.observations:
                try:
                    result = normalize_trade_observation(parsed, session)
                except Exception as exc:
                    _reject(
                        session,
                        batch_id=batch_id,
                        parsed=parsed,
                        reason=db.RejectionReasonCode.NORMALIZATION_ERROR,
                        message=f"Observation normalization failed: {_safe_error(exc)}",
                    )
                    counters.rejected += 1
                    continue

                if result.observation is None:
                    _reject(
                        session,
                        batch_id=batch_id,
                        parsed=parsed,
                        reason=db.RejectionReasonCode.NORMALIZATION_ERROR,
                        message="Normalizer returned no validation candidate",
                    )
                    counters.rejected += 1
                    continue

                observation = result.observation
                summary = validation_engine.validate(
                    observation, validation_context
                )
                identity = _identity_if_possible(observation, dataset_identity)
                if summary.should_reject:
                    primary_result = next(
                        finding
                        for finding in summary.results
                        if finding.severity
                        in (ValidationSeverity.ERROR, ValidationSeverity.FATAL)
                    )
                    rejection = _reject(
                        session,
                        batch_id=batch_id,
                        parsed=parsed,
                        identity=identity,
                        reason=_rejection_reason(primary_result),
                        concept_id=primary_result.concept_id,
                        invalid_value=primary_result.invalid_value,
                        message=primary_result.message,
                    )
                    _persist_validation_results(
                        session,
                        batch_id=batch_id,
                        summary=summary,
                        rejection_id=rejection.id,
                    )
                    counters.rejected += 1
                    continue

                mismatch = _scope_mismatch(parsed, period, query)
                if mismatch is not None:
                    field, wanted, actual = mismatch
                    rejection = _reject(
                        session,
                        batch_id=batch_id,
                        parsed=parsed,
                        identity=identity,
                        reason=db.RejectionReasonCode.INVALID_VALUE,
                        concept_id=field,
                        invalid_value=actual,
                        message=(
                            f"Provider record is outside the controlled query: "
                            f"expected {field}={wanted!r}, received {actual!r}"
                        ),
                    )
                    _persist_validation_results(
                        session,
                        batch_id=batch_id,
                        summary=summary,
                        rejection_id=rejection.id,
                    )
                    counters.rejected += 1
                    continue
                if identity is None:
                    _reject(
                        session,
                        batch_id=batch_id,
                        parsed=parsed,
                        reason=db.RejectionReasonCode.NORMALIZATION_ERROR,
                        message="Observation identity could not be generated",
                    )
                    counters.rejected += 1
                    continue

                counters.accepted += 1
                action, stored = _store_observation(
                    session,
                    dataset_id=dataset.id,
                    batch_id=batch_id,
                    observation=observation,
                    identity=identity,
                )
                _persist_validation_results(
                    session,
                    batch_id=batch_id,
                    summary=summary,
                    observation_id=stored.id,
                )
                if action == "INSERTED":
                    counters.inserted += 1
                elif action == "UPDATED":
                    counters.updated += 1
                else:
                    counters.skipped += 1

        batch.raw_response_checksum = aggregate_batch_checksum(raw_checksums)
        batch.statistical_content_checksum = aggregate_batch_checksum(
            content_checksums
        )
        _apply_counts(batch, counters)
        batch.finished_at = datetime.now(timezone.utc)
        if counters.accepted == 0:
            batch.status = db.IngestionBatchStatus.FAILED
            batch.error_message = "No observations were accepted"
        elif counters.rejected:
            batch.status = db.IngestionBatchStatus.PARTIAL
        else:
            batch.status = db.IngestionBatchStatus.SUCCESS
        session.commit()
        session.refresh(batch)
        return batch
    except Exception as exc:
        message = _safe_error(exc)
        session.rollback()
        failed_batch = session.get(db.IngestionBatch, batch_id)
        if failed_batch is not None:
            _apply_counts(failed_batch, counters)
            failed_batch.raw_response_checksum = aggregate_batch_checksum(raw_checksums)
            failed_batch.statistical_content_checksum = aggregate_batch_checksum(
                content_checksums
            )
            failed_batch.status = db.IngestionBatchStatus.FAILED
            failed_batch.finished_at = datetime.now(timezone.utc)
            failed_batch.error_message = message
            session.commit()
        raise TradeIngestionError(batch_id, message) from exc

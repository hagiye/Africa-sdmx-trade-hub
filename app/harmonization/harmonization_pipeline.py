"""Persist only target-valid AFR_TRADE observations with complete lineage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as db
from app.harmonization.afr_trade_models import (
    HarmonizationIssueCode,
    HarmonizationResult,
    HarmonizationStatus,
)
from app.harmonization.afr_trade_transformer import (
    MAPPING_DEFINITION_ID,
    MAPPING_VERSION,
    TARGET_STRUCTURE,
    transform_to_afr_trade,
)
from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.context import ValidationContext
from app.validation.engine import ValidationEngine, get_trade_validation_rules


TARGET_DATAFLOW = ("AFRSTAT", "AFR_TRADE", "1.0")
PersistenceAction = Literal["INSERT", "SKIP", "UPDATE", "VERSION_CONFLICT"]


@dataclass(frozen=True)
class PersistenceDecision:
    action: PersistenceAction
    observation: db.AfrTradeObservation | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_target_dataset(session: Session) -> db.StatDataset:
    agency, dataflow_id, version = TARGET_DATAFLOW
    row = session.scalar(
        select(db.StatDataset).where(
            db.StatDataset.agency == agency,
            db.StatDataset.dataflow_id == dataflow_id,
            db.StatDataset.dataflow_version == version,
        )
    )
    if row is not None:
        return row
    dataflow = session.scalar(
        select(db.Dataflow).where(
            db.Dataflow.agency_id == agency,
            db.Dataflow.dataflow_id == dataflow_id,
            db.Dataflow.version == version,
        )
    )
    if dataflow is None:
        raise ValueError("Target dataflow AFRSTAT:AFR_TRADE(1.0) is not loaded")
    row = db.StatDataset(
        agency=agency,
        dataflow_id=dataflow_id,
        dataflow_version=version,
        dsd_agency=TARGET_STRUCTURE.agency,
        dsd_id=TARGET_STRUCTURE.structure_id,
        dsd_version=TARGET_STRUCTURE.version,
        name=dataflow.name,
        source_system="HARMONIZED_AFR_TRADE",
        source_url=None,
    )
    session.add(row)
    session.flush()
    return row


def normalized_from_warehouse(
    session: Session,
    dataset: db.StatDataset,
    row: db.TradeObservation,
) -> NormalizedTradeObservation:
    reference = session.get(db.GeoArea, row.reference_geo_id)
    counterpart = (
        session.get(db.GeoArea, row.counterpart_geo_id)
        if row.counterpart_geo_id is not None
        else None
    )
    return NormalizedTradeObservation(
        source_agency=dataset.agency,
        source_system=dataset.source_system,
        source_dataflow=dataset.dataflow_id,
        source_dataflow_version=dataset.dataflow_version,
        source_dsd=dataset.dsd_id,
        source_dsd_version=dataset.dsd_version,
        reference_area_source_code=row.reference_area_source_code,
        reference_geo_id=row.reference_geo_id,
        reference_iso2=reference.iso2 if reference else None,
        reference_iso3=reference.iso3 if reference else None,
        reference_name=reference.name_en if reference else None,
        reference_area_type=reference.area_type if reference else None,
        reference_is_au_member=reference.au_member if reference else None,
        counterpart_area_source_code=row.counterpart_area_source_code,
        counterpart_geo_id=row.counterpart_geo_id,
        counterpart_iso2=counterpart.iso2 if counterpart else None,
        counterpart_iso3=counterpart.iso3 if counterpart else None,
        counterpart_name=counterpart.name_en if counterpart else None,
        counterpart_area_type=counterpart.area_type if counterpart else None,
        counterpart_is_au_member=counterpart.au_member if counterpart else None,
        trade_flow_code=row.trade_flow_code,
        frequency_code=row.frequency_code,
        commodity_code=row.commodity_code,
        commodity_classification=row.commodity_classification,
        commodity_sdmx_code=row.commodity_sdmx_code,
        time_period=row.time_period,
        primary_value=row.primary_value,
        quantity=row.quantity,
        net_weight=row.net_weight,
        gross_weight=row.gross_weight,
        cif_value=row.cif_value,
        fob_value=row.fob_value,
        source_dimensions=dict(row.source_dimensions),
        source_attributes=dict(row.source_attributes),
        source_fields=dict(row.source_fields),
    )


def _trace_json(result: HarmonizationResult) -> dict[str, object]:
    return {
        "mappings": [row.model_dump(mode="json") for row in result.mapping_results],
        "dropped_concepts": result.dropped_concepts,
        "deferred_concepts": result.deferred_concepts,
        "warnings": [row.model_dump(mode="json") for row in result.warnings],
        "errors": [row.model_dump(mode="json") for row in result.errors],
    }


def _target_values(result: HarmonizationResult) -> dict[str, object]:
    target = result.target_observation
    identity = result.target_identity
    if target is None or identity is None:
        raise ValueError("Only complete identified targets can be persisted")
    return {
        "target_dsd_agency": TARGET_STRUCTURE.agency,
        "target_dsd_id": TARGET_STRUCTURE.structure_id,
        "target_dsd_version": TARGET_STRUCTURE.version,
        "freq": target.freq,
        "ref_area": target.ref_area,
        "counterpart_area": target.counterpart_area,
        "trade_flow": target.trade_flow,
        "product_scheme": target.product_scheme,
        "product": target.product,
        "unit_measure": target.unit_measure,
        "time_period": target.time_period,
        "obs_value": target.obs_value,
        "obs_status": target.obs_status,
        "conf_status": target.conf_status,
        "unit_mult": target.unit_mult,
        "decimals": target.decimals,
        "source": target.source,
        "target_key": identity.target_key,
        "target_key_hash": identity.target_key_hash,
        "target_content_hash": identity.target_content_hash,
        "mapping_trace": _trace_json(result),
    }


def persist_validated_target(
    session: Session,
    *,
    batch: db.HarmonizationBatch,
    target_dataset: db.StatDataset,
    source_row: db.TradeObservation,
    result: HarmonizationResult,
    mapping_definition_id: str = MAPPING_DEFINITION_ID,
    mapping_version: str = MAPPING_VERSION,
    allow_mapping_version_revision: bool = False,
) -> PersistenceDecision:
    """Apply INSERT/SKIP/UPDATE after successful target validation."""

    if (
        result.status is not HarmonizationStatus.SUCCESS
        or result.target_validation is None
        or not result.target_validation.is_valid
        or result.target_identity is None
    ):
        raise ValueError("Refusing to persist a non-successful target result")
    values = _target_values(result)
    existing = session.scalar(
        select(db.AfrTradeObservation).where(
            db.AfrTradeObservation.target_dataset_id == target_dataset.id,
            db.AfrTradeObservation.target_key_hash
            == result.target_identity.target_key_hash,
        )
    )
    if existing is None:
        row = db.AfrTradeObservation(
            target_dataset_id=target_dataset.id,
            mapping_definition_id=mapping_definition_id,
            mapping_version=mapping_version,
            source_trade_observation_id=source_row.id,
            first_harmonization_batch_id=batch.id,
            last_harmonization_batch_id=batch.id,
            **values,
        )
        session.add(row)
        session.flush()
        return PersistenceDecision("INSERT", row)
    if (
        (existing.mapping_definition_id, existing.mapping_version)
        != (mapping_definition_id, mapping_version)
        and not allow_mapping_version_revision
    ):
        return PersistenceDecision("VERSION_CONFLICT", existing)
    existing.last_harmonization_batch_id = batch.id
    existing.source_trade_observation_id = source_row.id
    if existing.target_content_hash == result.target_identity.target_content_hash:
        session.flush()
        return PersistenceDecision("SKIP", existing)
    for key, value in values.items():
        setattr(existing, key, value)
    existing.mapping_definition_id = mapping_definition_id
    existing.mapping_version = mapping_version
    session.flush()
    return PersistenceDecision("UPDATE", existing)


def _reason(value: str) -> db.HarmonizationRejectionReason:
    try:
        return db.HarmonizationRejectionReason(value)
    except ValueError:
        return db.HarmonizationRejectionReason.TARGET_VALIDATION_FAILED


def _reject_result(
    session: Session,
    batch: db.HarmonizationBatch,
    source_row: db.TradeObservation,
    result: HarmonizationResult,
) -> None:
    trace = _trace_json(result)
    target_hash = (
        result.target_identity.target_key_hash if result.target_identity else None
    )
    mapping_issues = [
        issue
        for issue in result.errors
        if issue.code is not HarmonizationIssueCode.TARGET_VALIDATION_FAILED
    ]
    batch.mapping_errors += len(mapping_issues)
    for issue in mapping_issues:
        reason = _reason(issue.code.value)
        if issue.target_concept == "UNIT_MEASURE":
            reason = db.HarmonizationRejectionReason.MISSING_TARGET_UNIT
        session.add(
            db.HarmonizationRejection(
                harmonization_batch_id=batch.id,
                source_trade_observation_id=source_row.id,
                source_key_hash=source_row.source_key_hash,
                target_key_hash=target_hash,
                reason_code=reason,
                severity="ERROR",
                concept_id=issue.target_concept or issue.source_concept,
                source_value=(
                    None if issue.source_value is None else str(issue.source_value)
                ),
                message=issue.message,
                mapping_trace=trace,
            )
        )
    findings = (
        result.target_validation.findings if result.target_validation else []
    )
    batch.target_validation_errors += len(findings)
    for finding in findings:
        reason = _reason(finding.code.value)
        if finding.concept_id == "UNIT_MEASURE" and finding.invalid_value is None:
            reason = db.HarmonizationRejectionReason.MISSING_TARGET_UNIT
        session.add(
            db.HarmonizationRejection(
                harmonization_batch_id=batch.id,
                source_trade_observation_id=source_row.id,
                source_key_hash=source_row.source_key_hash,
                target_key_hash=target_hash,
                reason_code=reason,
                severity="ERROR",
                concept_id=finding.concept_id,
                target_value=(
                    None
                    if finding.invalid_value is None
                    else str(finding.invalid_value)
                ),
                message=finding.message,
                mapping_trace=trace,
            )
        )
    if not mapping_issues and not findings:
        session.add(
            db.HarmonizationRejection(
                harmonization_batch_id=batch.id,
                source_trade_observation_id=source_row.id,
                source_key_hash=source_row.source_key_hash,
                target_key_hash=target_hash,
                reason_code=db.HarmonizationRejectionReason.TARGET_VALIDATION_FAILED,
                severity="ERROR",
                message="Harmonization result was not eligible for persistence.",
                mapping_trace=trace,
            )
        )


def _mapping_checksum(session: Session) -> str | None:
    return session.scalar(
        select(db.SdmxConceptMapping.definition_checksum).where(
            db.SdmxConceptMapping.mapping_definition_id == MAPPING_DEFINITION_ID,
            db.SdmxConceptMapping.mapping_version == MAPPING_VERSION,
        ).limit(1)
    )


def harmonize_source_warehouse(
    session: Session,
    *,
    source_dataset_id: int,
    source_batch_id: int | None = None,
    source_observation_ids: list[int] | None = None,
    mapping_definition_id: str = MAPPING_DEFINITION_ID,
    mapping_version: str = MAPPING_VERSION,
    allow_mapping_version_revision: bool = False,
) -> db.HarmonizationBatch:
    """Run source validation, transformation, target validation, and persistence."""

    if (mapping_definition_id, mapping_version) != (
        MAPPING_DEFINITION_ID,
        MAPPING_VERSION,
    ):
        raise ValueError(
            "The transformer implements only "
            f"{MAPPING_DEFINITION_ID}({MAPPING_VERSION}); refusing to label "
            "output with a different mapping definition or version."
        )

    source_dataset = session.get(db.StatDataset, source_dataset_id)
    if source_dataset is None:
        raise ValueError(f"Source dataset {source_dataset_id} does not exist")
    target_dataset = ensure_target_dataset(session)
    target_dsd = session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == TARGET_STRUCTURE.agency,
            db.DSD.dsd_id == TARGET_STRUCTURE.structure_id,
            db.DSD.version == TARGET_STRUCTURE.version,
        )
    )
    if target_dsd is None:
        raise ValueError("Target DSD AFRSTAT:AFR_TRADE(1.0) is not loaded")
    batch = db.HarmonizationBatch(
        source_dataset_id=source_dataset.id,
        target_dataset_id=target_dataset.id,
        target_dataflow_agency=TARGET_DATAFLOW[0],
        target_dataflow_id=TARGET_DATAFLOW[1],
        target_dataflow_version=TARGET_DATAFLOW[2],
        target_dsd_agency=TARGET_STRUCTURE.agency,
        target_dsd_id=TARGET_STRUCTURE.structure_id,
        target_dsd_version=TARGET_STRUCTURE.version,
        mapping_definition_id=mapping_definition_id,
        mapping_version=mapping_version,
        source_batch_id=source_batch_id,
        mapping_checksum=_mapping_checksum(session),
        target_structure_checksum=target_dsd.checksum,
        status=db.HarmonizationBatchStatus.RUNNING,
    )
    session.add(batch)
    session.commit()

    try:
        query = (
            select(db.TradeObservation)
            .where(db.TradeObservation.dataset_id == source_dataset.id)
            .order_by(db.TradeObservation.time_period, db.TradeObservation.id)
        )
        if source_observation_ids is not None:
            query = query.where(db.TradeObservation.id.in_(source_observation_ids))
        source_rows = list(session.scalars(query))
        context = ValidationContext.from_session(session, source_dataset)
        engine = ValidationEngine(get_trade_validation_rules())
        batch = session.get(db.HarmonizationBatch, batch.id)
        batch.source_observations_received = len(source_rows)
        for source_row in source_rows:
            normalized = normalized_from_warehouse(
                session, source_dataset, source_row
            )
            source_validation = engine.validate(normalized, context)
            if source_validation.is_valid:
                batch.source_observations_valid += 1
            result = transform_to_afr_trade(
                normalized, session, source_validation=source_validation
            )
            if result.target_observation is not None:
                batch.observations_transformed += 1
            if (
                result.status is not HarmonizationStatus.SUCCESS
                or result.target_validation is None
                or not result.target_validation.is_valid
                or result.target_identity is None
            ):
                batch.observations_rejected += 1
                _reject_result(session, batch, source_row, result)
                continue
            decision = persist_validated_target(
                session,
                batch=batch,
                target_dataset=target_dataset,
                source_row=source_row,
                result=result,
                mapping_definition_id=mapping_definition_id,
                mapping_version=mapping_version,
                allow_mapping_version_revision=allow_mapping_version_revision,
            )
            if decision.action == "INSERT":
                batch.observations_inserted += 1
            elif decision.action == "UPDATE":
                batch.observations_updated += 1
            elif decision.action == "SKIP":
                batch.observations_skipped += 1
            else:
                batch.observations_rejected += 1
                session.add(
                    db.HarmonizationRejection(
                        harmonization_batch_id=batch.id,
                        source_trade_observation_id=source_row.id,
                        source_key_hash=source_row.source_key_hash,
                        target_key_hash=result.target_identity.target_key_hash,
                        reason_code=db.HarmonizationRejectionReason.MAPPING_VERSION_CONFLICT,
                        severity="ERROR",
                        message=(
                            "Existing target was produced by a different mapping "
                            "version; explicit revision authorization is required."
                        ),
                        mapping_trace=_trace_json(result),
                    )
                )
        batch.finished_at = _now()
        batch.status = (
            db.HarmonizationBatchStatus.PARTIAL
            if batch.observations_rejected
            else db.HarmonizationBatchStatus.SUCCESS
        )
        session.commit()
        return batch
    except Exception as exc:
        session.rollback()
        failed = session.get(db.HarmonizationBatch, batch.id)
        if failed is not None:
            failed.finished_at = _now()
            failed.status = db.HarmonizationBatchStatus.FAILED
            failed.error_message = str(exc)[:4000]
            session.commit()
        raise

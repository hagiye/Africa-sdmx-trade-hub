"""SDMX-aware trade validation rules, decisions, and persistence."""

from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.pipelines.ingest_trade_data import ingest_trade_query
from app.pipelines.trade_models import NormalizedTradeObservation
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.data_parser import parse_comtrade_response
from app.validation.base import ValidationRule
from app.validation.context import ValidationContext
from app.validation.engine import ValidationEngine, get_trade_validation_rules
from app.validation.models import (
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
    ValidationSummary,
)
from tests.test_trade_ingestion import FIXTURES, QUERY, ingestion_database


def _normalize(session: Session, payload: dict) -> NormalizedTradeObservation:
    parsed = parse_comtrade_response(payload).observations[0]
    result = normalize_trade_observation(parsed, session)
    assert result.observation is not None
    return result.observation


def _validate(
    session: Session,
    dataset: db.StatDataset,
    observation: NormalizedTradeObservation,
    *,
    context: ValidationContext | None = None,
) -> ValidationSummary:
    return ValidationEngine(get_trade_validation_rules()).validate(
        observation,
        context or ValidationContext.from_session(session, dataset),
    )


def _changed_payload(**changes: object) -> dict:
    payload = copy.deepcopy(FIXTURES["2022"])
    payload["data"][0].update(changes)
    return payload


def test_validation_summary_counts_and_serializes() -> None:
    summary = ValidationSummary(
        results=[
            ValidationResult(
                rule_id="INFO_TEST",
                category=ValidationCategory.QUALITY,
                severity=ValidationSeverity.INFO,
                message="information",
            ),
            ValidationResult(
                rule_id="WARNING_TEST",
                category=ValidationCategory.QUALITY,
                severity=ValidationSeverity.WARNING,
                message="review",
            ),
            ValidationResult(
                rule_id="ERROR_TEST",
                category=ValidationCategory.VALUE,
                severity=ValidationSeverity.ERROR,
                message="reject",
            ),
        ]
    )

    assert (summary.info_count, summary.warning_count) == (1, 1)
    assert (summary.error_count, summary.fatal_count) == (1, 0)
    assert summary.should_reject is True
    assert summary.is_valid is False
    serialized = summary.model_dump(mode="json")
    assert serialized["results"][1]["severity"] == "WARNING"
    assert serialized["should_reject"] is True


def test_all_three_real_tunisia_fixtures_are_accepted(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    context = ValidationContext.from_session(session, dataset)
    summaries = [
        _validate(session, dataset, _normalize(session, FIXTURES[period]), context=context)
        for period in ("2022", "2023", "2024")
    ]

    assert all(summary.is_valid for summary in summaries)
    assert all(summary.results == [] for summary in summaries)


def test_invalid_frequency_is_codelist_error(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    summary = _validate(
        session,
        dataset,
        _normalize(session, _changed_payload(freqCode="INVALID_CODE")),
    )

    assert summary.should_reject is True
    assert [(result.rule_id, result.category, result.severity) for result in summary.results] == [
        (
            "VALID_FREQUENCY_CODE",
            ValidationCategory.CODELIST,
            ValidationSeverity.ERROR,
        )
    ]


def test_invalid_trade_flow_is_codelist_error(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    summary = _validate(
        session,
        dataset,
        _normalize(session, _changed_payload(flowCode="INVALID_CODE")),
    )

    assert summary.should_reject is True
    assert [result.rule_id for result in summary.results] == [
        "VALID_TRADE_FLOW_CODE"
    ]


def test_registry_frequency_and_period_strategy_are_not_annual_only(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    annual = _normalize(session, FIXTURES["2022"])
    quarterly = annual.model_copy(
        update={
            "frequency_code": "Q",
            "time_period": "2022-Q1",
            "source_dimensions": {
                **annual.source_dimensions,
                "FREQ": "Q",
            },
        }
    )

    assert _validate(session, dataset, quarterly).results == []


def test_unresolved_commodity_classification_is_codelist_error(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(session, FIXTURES["2022"]).model_copy(
        update={
            "commodity_code": "SYNTHETIC",
            "commodity_classification": "ZZ",
            "commodity_sdmx_code": None,
        }
    )
    summary = _validate(session, dataset, observation)

    assert [result.rule_id for result in summary.results] == [
        "VALID_COMMODITY_CODE"
    ]
    assert summary.should_reject is True


def test_unmapped_reporter_has_one_geography_error_without_scope_noise(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(
        session,
        _changed_payload(
            reporterCode=999999,
            reporterDesc="Synthetic unknown reporter",
            reporterISO="ZZZ",
        ),
    )
    summary = _validate(session, dataset, observation)

    assert observation.reference_geo_id is None
    assert [result.rule_id for result in summary.results] == [
        "VALID_REFERENCE_AREA"
    ]
    assert summary.error_count == 1


def test_known_non_au_reporter_is_valid_geography_but_fails_application_scope(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(
        session,
        _changed_payload(
            reporterCode=124,
            reporterDesc="Canada",
            reporterISO="CAN",
        ),
    )
    summary = _validate(session, dataset, observation)

    assert observation.reference_name == "Canada"
    assert [result.rule_id for result in summary.results] == [
        "REFERENCE_AREA_IS_AU_MEMBER"
    ]
    assert summary.results[0].category is ValidationCategory.APPLICATION_SCOPE


def test_known_kenya_reporter_passes_application_scope(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(
        session,
        _changed_payload(
            reporterCode=404,
            reporterDesc="Kenya",
            reporterISO="KEN",
        ),
    )
    summary = _validate(session, dataset, observation)

    assert observation.reference_name == "Kenya"
    assert observation.reference_is_au_member is True
    assert summary.results == []


def test_world_reporter_resolves_but_fails_application_scope(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(
        session,
        _changed_payload(
            reporterCode=0,
            reporterDesc="World",
            reporterISO="W00",
        ),
    )
    summary = _validate(session, dataset, observation)

    assert observation.reference_area_type is db.AreaType.AGGREGATE
    assert [result.rule_id for result in summary.results] == [
        "REFERENCE_AREA_IS_AU_MEMBER"
    ]


def test_world_counterpart_is_valid_for_tunisia_reporter(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(session, FIXTURES["2022"])
    summary = _validate(session, dataset, observation)

    assert observation.counterpart_name == "World"
    assert observation.counterpart_area_type is db.AreaType.AGGREGATE
    assert summary.results == []


def test_unmapped_counterpart_is_warning_and_does_not_reject(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(
        session,
        _changed_payload(
            partnerCode=999999,
            partnerDesc="Synthetic unknown counterpart",
            partnerISO="ZZZ",
        ),
    )
    summary = _validate(session, dataset, observation)

    assert observation.counterpart_geo_id is None
    assert summary.should_reject is False
    assert summary.warning_count == 1
    assert summary.results[0].rule_id == "VALID_COUNTERPART_AREA"


def test_missing_time_period_is_structural_and_value_error(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(session, _changed_payload(period=None))
    summary = _validate(session, dataset, observation)

    assert summary.should_reject is True
    assert {result.rule_id for result in summary.results} == {
        "MANDATORY_DIMENSION_PRESENT",
        "VALID_TIME_PERIOD",
    }


def test_missing_primary_value_is_error_and_never_zero(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(session, _changed_payload(primaryValue=None))
    summary = _validate(session, dataset, observation)

    assert observation.primary_value is None
    assert [result.rule_id for result in summary.results] == [
        "PRIMARY_VALUE_PRESENT"
    ]
    assert summary.should_reject is True


def test_malformed_normalized_value_is_error(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    valid = _normalize(session, FIXTURES["2022"])
    malformed = valid.model_copy(update={"primary_value": "not numeric"})
    summary = _validate(session, dataset, malformed)

    assert [result.rule_id for result in summary.results] == [
        "VALID_OBSERVATION_VALUE"
    ]
    assert summary.should_reject is True


def test_negative_trade_value_is_review_warning_not_global_rejection(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(session, FIXTURES["2022"]).model_copy(
        update={"primary_value": Decimal("-1")}
    )
    summary = _validate(session, dataset, observation)

    assert [result.rule_id for result in summary.results] == [
        "NON_NEGATIVE_TRADE_VALUE"
    ]
    assert summary.warning_count == 1
    assert summary.should_reject is False


def test_duplicate_within_batch_is_warning_but_existing_warehouse_is_not_checked(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(session, FIXTURES["2022"])
    context = ValidationContext.from_session(session, dataset)

    first = _validate(session, dataset, observation, context=context)
    second = _validate(session, dataset, observation, context=context)

    assert first.results == []
    assert [result.rule_id for result in second.results] == [
        "DUPLICATE_OBSERVATION_IN_BATCH"
    ]
    assert second.warning_count == 1
    assert second.should_reject is False


class _ExplodingRule(ValidationRule):
    rule_id = "SYNTHETIC_EXPLODING_RULE"
    category = ValidationCategory.QUALITY

    def validate(self, observation, context):
        raise RuntimeError("sensitive implementation detail")


def test_unexpected_rule_exception_becomes_safe_fatal_result(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    observation = _normalize(session, FIXTURES["2022"])
    summary = ValidationEngine([_ExplodingRule()]).validate(
        observation, ValidationContext.from_session(session, dataset)
    )

    assert summary.fatal_count == 1
    assert summary.should_reject is True
    assert summary.results[0].rule_id == "VALIDATION_RULE_EXCEPTION"
    assert "sensitive" not in summary.results[0].message


def test_validation_error_is_persisted_and_linked_to_rejection(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    payload = _changed_payload(freqCode="INVALID_CODE")
    query = replace(
        QUERY,
        frequency_code="INVALID_CODE",
        periods=("2022",),
    )

    batch = ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=lambda _period, _parameters: payload,
    )
    finding = session.scalar(select(db.ValidationFinding))
    rejection = session.scalar(select(db.ObservationRejection))

    assert batch.observations_rejected == 1
    assert batch.observations_accepted == 0
    assert finding is not None and rejection is not None
    assert finding.rule_id == "VALID_FREQUENCY_CODE"
    assert finding.severity == "ERROR"
    assert finding.observation_id is None
    assert finding.observation_rejection_id == rejection.id
    assert finding.message == rejection.message


def test_accepted_warning_is_persisted_and_linked_to_observation(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    payload = _changed_payload(
        partnerCode=999999,
        partnerDesc="Synthetic unknown counterpart",
        partnerISO="ZZZ",
    )
    query = replace(QUERY, partner_code="999999", periods=("2022",))

    batch = ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=lambda _period, _parameters: payload,
    )
    finding = session.scalar(select(db.ValidationFinding))
    observation = session.scalar(select(db.TradeObservation))

    assert batch.observations_accepted == 1
    assert batch.observations_rejected == 0
    assert finding is not None and observation is not None
    assert finding.rule_id == "VALID_COUNTERPART_AREA"
    assert finding.severity == "WARNING"
    assert finding.observation_id == observation.id
    assert finding.observation_rejection_id is None
    assert session.scalar(select(func.count()).select_from(db.ObservationRejection)) == 0

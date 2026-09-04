"""End-to-end source validation, harmonization, and target validation tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.harmonization.afr_trade_models import (
    AfrTradeObservation,
    HarmonizationIssueCode,
    HarmonizationStatus,
    TargetValidationStatus,
    identify_target_observation,
)
from app.harmonization.afr_trade_transformer import transform_to_afr_trade
from app.harmonization.afr_trade_validation import (
    TargetValidationContext,
    validate_afr_trade_observation,
)
from app.mappings.sdmx_mapping_loader import load_sdmx_mappings
from app.pipelines.afr_trade_structure import load_afr_trade_structure
from app.pipelines.trade_models import NormalizedTradeObservation
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.data_parser import parse_comtrade_response
from app.validation.context import ValidationContext
from app.validation.engine import ValidationEngine, get_trade_validation_rules
from app.validation.models import ValidationSummary
from tests.test_trade_ingestion import (
    EXPECTED_VALUES,
    FIXTURES,
    ingestion_database,
)


SOURCE_DIMENSIONS = (
    "FREQ",
    "REF_AREA",
    "TRADE_FLOW",
    "COMMODITY_1",
    "COMMODITY_1_CONF",
    "COMMODITY_2",
    "COMMODITY_2_CONF",
    "COMMODITY_CUSTOM_BREAKDOWN",
    "COUNTERPART_AREA_1",
    "COUNTERPART_AREA_1_CONF",
    "COUNTERPART_AREA_2",
    "COUNTERPART_AREA_2_CONF",
    "TRANSPORT_MODE_BORDER",
    "TRANSPORT_MODE_BORDER_CONF",
    "CUSTOMS_PROC",
    "ACTIVITY",
    "TRANSFORMATION",
    "MEASURE",
    "TIME_PERIOD",
)
SOURCE_ATTRIBUTES = (
    "COMMENT_OBS",
    "COMMODITY_CUSTOM_CODE",
    "COMMODITY_CUSTOM_DESC",
    "COUNTERPART_AREA_1_ANNOTATION",
    "COUNTERPART_AREA_1_TYPE",
    "COUNTERPART_AREA_2_ANNOTATION",
    "COUNTERPART_AREA_2_TYPE",
    "OBS_STATUS",
    "TRADE_SYSTEM",
    "UNIT_MEASURE",
    "UNIT_MULT",
)


@pytest.fixture
def harmonization_database(
    ingestion_database: tuple[Session, db.StatDataset],
) -> tuple[Session, db.StatDataset]:
    session, dataset = ingestion_database
    dsd = session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == "UNSD",
            db.DSD.dsd_id == "IMTS",
            db.DSD.version == "1.2",
        )
    )
    assert dsd is not None
    existing = {row.concept_id for row in dsd.dimensions}
    for position, concept_id in enumerate(SOURCE_DIMENSIONS, start=1):
        if concept_id not in existing:
            dsd.dimensions.append(
                db.Dimension(
                    concept_id=concept_id,
                    position=position,
                    role="time" if concept_id == "TIME_PERIOD" else "dimension",
                )
            )
    dsd.attributes.extend(
        db.Attribute(concept_id=concept_id, attachment_level="Observation")
        for concept_id in SOURCE_ATTRIBUTES
    )
    dsd.measures.append(db.Measure(concept_id="OBS_VALUE"))
    unit_multiplier = db.Codelist(
        agency_id="SDMX",
        codelist_id="CL_UNIT_MULT",
        version="1.1",
        name="CL_UNIT_MULT",
        source_url="https://fixtures.invalid/CL_UNIT_MULT",
        retrieved_at=datetime.now(timezone.utc),
        checksum="e" * 64,
    )
    session.add(unit_multiplier)
    session.flush()
    session.add(db.Code(codelist_id=unit_multiplier.id, code="0"))
    session.commit()
    load_afr_trade_structure(session)
    load_sdmx_mappings(session)
    return session, dataset


def _normalized(session: Session, period: str) -> NormalizedTradeObservation:
    parsed = parse_comtrade_response(FIXTURES[period]).observations[0]
    result = normalize_trade_observation(parsed, session)
    assert result.observation is not None
    return result.observation


def _source_validation(
    session: Session,
    dataset: db.StatDataset,
    observation: NormalizedTradeObservation,
) -> ValidationSummary:
    return ValidationEngine(get_trade_validation_rules()).validate(
        observation, ValidationContext.from_session(session, dataset)
    )


def _transform(
    session: Session, dataset: db.StatDataset, period: str
):
    observation = _normalized(session, period)
    validation = _source_validation(session, dataset, observation)
    return transform_to_afr_trade(
        observation, session, source_validation=validation
    )


@pytest.mark.parametrize("period", ("2022", "2023", "2024"))
def test_real_observation_maps_confirmed_target(
    harmonization_database: tuple[Session, db.StatDataset],
    period: str,
) -> None:
    session, dataset = harmonization_database
    result = _transform(session, dataset, period)
    target = result.target_observation

    assert result.source_validation.is_valid
    assert result.status is HarmonizationStatus.SUCCESS
    assert target is not None
    assert (
        target.freq,
        target.ref_area,
        target.counterpart_area,
        target.trade_flow,
        target.product_scheme,
        target.product,
        target.time_period,
        target.obs_value,
    ) == (
        "A",
        "TN",
        "AFR_WORLD",
        "IMPORT",
        "SITC4",
        "TOTAL",
        period,
        EXPECTED_VALUES[period],
    )
    assert (target.unit_measure, target.unit_mult, target.source) == (
        "USD", "0", "UN_COMTRADE"
    )
    assert result.target_validation is not None
    assert result.target_validation.status is TargetValidationStatus.VALID
    assert result.target_validation.findings == []
    assert result.target_identity is not None


def test_mapping_trace_records_registry_decisions(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = harmonization_database
    result = _transform(session, dataset, "2023")
    resolved = {
        (row.target_concept, row.source_concept): row
        for row in result.mapping_results
        if row.outcome == "RESOLVED"
    }

    assert resolved[("FREQ", "FREQ")].target_value == "A"
    assert resolved[("REF_AREA", "REF_AREA")].target_value == "TN"
    assert (
        resolved[("COUNTERPART_AREA", "COUNTERPART_AREA_1")].target_value
        == "AFR_WORLD"
    )
    assert resolved[("TRADE_FLOW", "TRADE_FLOW")].target_value == "IMPORT"
    assert resolved[("PRODUCT", "COMMODITY_1")].target_value == "TOTAL"
    assert resolved[("UNIT_MEASURE", "MEASURE")].source_value == "V_CIF"
    assert resolved[("UNIT_MEASURE", "MEASURE")].target_value == "USD"
    assert resolved[("UNIT_MULT", "UNIT_MULT")].target_value == "0"
    assert resolved[("SOURCE", "SOURCE_SYSTEM")].target_value == "UN_COMTRADE"
    assert all(
        row.mapping_status is db.SdmxMappingStatus.CONFIRMED
        for row in resolved.values()
    )
    assert "COMMODITY_2" in result.dropped_concepts
    assert "UNIT_MEASURE" in result.deferred_concepts


def test_canonical_json_is_deterministic_and_not_labeled_sdmx_json() -> None:
    observation = _complete_target()
    first = observation.canonical_json()

    assert first == observation.canonical_json()
    assert first.startswith('{"CONF_STATUS":')
    assert '"OBS_VALUE":"10"' in first


def test_unsupported_product_fails_without_passthrough(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = harmonization_database
    codelist = session.scalar(
        select(db.Codelist).where(
            db.Codelist.agency_id == "UNSD",
            db.Codelist.codelist_id == "CL_COMMODITY",
            db.Codelist.version == "1.0",
        )
    )
    assert codelist is not None
    session.add(db.Code(codelist_id=codelist.id, code="SITC4_9999"))
    session.commit()
    observation = _normalized(session, "2023").model_copy(
        update={
            "commodity_code": "9999",
            "commodity_sdmx_code": "SITC4_9999",
            "source_dimensions": {
                **_normalized(session, "2023").source_dimensions,
                "COMMODITY_1": "SITC4_9999",
            },
        }
    )
    source_validation = _source_validation(session, dataset, observation)
    result = transform_to_afr_trade(
        observation, session, source_validation=source_validation
    )

    assert source_validation.is_valid
    assert result.status is HarmonizationStatus.FAILED
    assert result.target_observation is not None
    assert result.target_observation.product is None
    assert any(
        issue.code is HarmonizationIssueCode.MISSING_CODE_MAPPING
        and issue.target_concept == "PRODUCT"
        for issue in result.errors
    )


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (db.SdmxMappingStatus.DRAFT, HarmonizationIssueCode.UNCONFIRMED_MAPPING),
        (
            db.SdmxMappingStatus.DEPRECATED,
            HarmonizationIssueCode.DEPRECATED_MAPPING,
        ),
    ],
)
def test_production_transformer_refuses_nonconfirmed_concept_mapping(
    harmonization_database: tuple[Session, db.StatDataset],
    status: db.SdmxMappingStatus,
    expected_code: HarmonizationIssueCode,
) -> None:
    session, dataset = harmonization_database
    mapping = session.scalar(
        select(db.SdmxConceptMapping).where(
            db.SdmxConceptMapping.source_concept_id == "FREQ",
            db.SdmxConceptMapping.target_concept_id == "FREQ",
        )
    )
    assert mapping is not None
    mapping.status = status
    session.commit()

    result = _transform(session, dataset, "2023")

    assert result.status is HarmonizationStatus.FAILED
    assert result.target_observation is not None
    assert result.target_observation.freq is None
    assert any(issue.code is expected_code for issue in result.errors)


def test_deferred_unit_mapping_is_explicit(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = harmonization_database
    mapping = session.scalar(
        select(db.SdmxConceptMapping).where(
            db.SdmxConceptMapping.source_concept_id == "MEASURE",
            db.SdmxConceptMapping.target_concept_id == "UNIT_MEASURE",
        )
    )
    assert mapping is not None
    mapping.mapping_type = db.SdmxMappingType.DEFER
    mapping.status = db.SdmxMappingStatus.DRAFT
    session.commit()
    result = _transform(session, dataset, "2023")

    assert any(
        issue.code is HarmonizationIssueCode.DEFERRED_MAPPING
        and issue.target_concept == "UNIT_MEASURE"
        for issue in result.errors
    )
    assert any(
        row.target_concept == "UNIT_MEASURE" and row.outcome == "DEFERRED"
        for row in result.mapping_results
    )


def test_ambiguous_primary_value_still_fails_with_missing_target_unit(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = harmonization_database
    observation = _normalized(session, "2023").model_copy(
        update={"cif_value": Decimal("1")}
    )
    result = transform_to_afr_trade(
        observation,
        session,
        source_validation=_source_validation(session, dataset, observation),
    )

    assert result.status is HarmonizationStatus.PARTIAL
    assert result.target_observation is not None
    assert result.target_observation.unit_measure is None
    assert any(
        issue.code is HarmonizationIssueCode.MISSING_CODE_MAPPING
        and issue.target_concept == "UNIT_MEASURE"
        for issue in result.errors
    )
    assert result.target_validation is not None
    assert any(
        finding.concept_id == "UNIT_MEASURE"
        for finding in result.target_validation.findings
    )


def test_missing_source_mapping_still_fails_safely(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = harmonization_database
    mapping = session.scalar(
        select(db.SdmxConceptMapping).where(
            db.SdmxConceptMapping.source_concept_id == "SOURCE_SYSTEM",
            db.SdmxConceptMapping.target_concept_id == "SOURCE",
        )
    )
    assert mapping is not None
    session.delete(mapping)
    session.commit()

    result = _transform(session, dataset, "2023")

    assert result.status is HarmonizationStatus.PARTIAL
    assert result.target_observation is not None
    assert result.target_observation.source is None
    assert any(
        issue.code is HarmonizationIssueCode.MISSING_CONCEPT_MAPPING
        and issue.target_concept == "SOURCE"
        for issue in result.errors
    )


def test_invalid_mapped_target_code_is_rejected_by_target_validation(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = harmonization_database
    mapping = session.scalar(
        select(db.SdmxCodeMapping)
        .join(db.SdmxConceptMapping)
        .where(
            db.SdmxConceptMapping.source_concept_id == "TRADE_FLOW",
            db.SdmxCodeMapping.source_code == "M",
        )
    )
    assert mapping is not None
    mapping.target_code = "INVALID_TARGET_FLOW"
    session.commit()

    result = _transform(session, dataset, "2023")

    assert result.target_observation is not None
    assert result.target_observation.trade_flow == "INVALID_TARGET_FLOW"
    assert result.target_validation is not None
    assert any(
        row.code is HarmonizationIssueCode.INVALID_TARGET_CODE
        and row.concept_id == "TRADE_FLOW"
        for row in result.target_validation.findings
    )


def _complete_target(**changes: object) -> AfrTradeObservation:
    values = {
        "freq": "A",
        "ref_area": "TN",
        "counterpart_area": "AFR_WORLD",
        "trade_flow": "IMPORT",
        "product_scheme": "SITC4",
        "product": "TOTAL",
        "unit_measure": "USD",
        "time_period": "2023",
        "obs_value": Decimal("10.00"),
        "unit_mult": "0",
        "source": "UN_COMTRADE",
    }
    values.update(changes)
    return AfrTradeObservation(**values)


def test_complete_target_candidate_passes_metadata_validation(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, _ = harmonization_database
    result = validate_afr_trade_observation(
        _complete_target(), TargetValidationContext.from_session(session)
    )

    assert result.status is TargetValidationStatus.VALID
    assert result.findings == []


def test_target_identity_and_content_hash_semantics() -> None:
    base = identify_target_observation(_complete_target())
    equivalent = identify_target_observation(
        _complete_target(obs_value=Decimal("10"))
    )
    changed_value = identify_target_observation(
        _complete_target(obs_value=Decimal("11"))
    )
    changed_period = identify_target_observation(
        _complete_target(time_period="2024")
    )
    changed_counterpart = identify_target_observation(
        _complete_target(counterpart_area="TN")
    )

    assert equivalent == base
    assert changed_value.target_key_hash == base.target_key_hash
    assert changed_value.target_content_hash != base.target_content_hash
    assert changed_period.target_key_hash != base.target_key_hash
    assert changed_counterpart.target_key_hash != base.target_key_hash


def test_source_rejection_stops_before_target_transformation(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = harmonization_database
    observation = _normalized(session, "2023").model_copy(
        update={"frequency_code": "BAD"}
    )
    source_validation = _source_validation(session, dataset, observation)
    result = transform_to_afr_trade(
        observation, session, source_validation=source_validation
    )

    assert source_validation.should_reject
    assert result.status is HarmonizationStatus.FAILED
    assert result.target_observation is None
    assert result.errors[0].code is HarmonizationIssueCode.SOURCE_VALIDATION_FAILED


def test_harmonization_is_in_memory_only(
    harmonization_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = harmonization_database
    before = session.scalar(select(func.count()).select_from(db.TradeObservation))
    _transform(session, dataset, "2023")
    after = session.scalar(select(func.count()).select_from(db.TradeObservation))

    assert before == after == 0
    assert session.scalar(
        select(func.count()).select_from(db.AfrTradeObservation)
    ) == 0

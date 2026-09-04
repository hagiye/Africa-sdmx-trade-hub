"""Transform validated UNSD IMTS candidates using registry metadata only."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as db
from app.harmonization.afr_trade_models import (
    AfrTradeObservation,
    HarmonizationIssue,
    HarmonizationIssueCode,
    HarmonizationResult,
    HarmonizationStatus,
    MappingTrace,
    identify_target_observation,
)
from app.harmonization.afr_trade_validation import (
    TargetValidationContext,
    validate_afr_trade_observation,
)
from app.mappings.geo import SOURCE_CODELIST
from app.mappings.sdmx_mapping_models import StructureIdentity
from app.mappings.sdmx_mapping_service import (
    get_canonical_geography,
    get_code_mapping,
    get_concept_mapping,
)
from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.models import ValidationSummary


MAPPING_DEFINITION_ID = "UNSD_IMTS_TO_AFR_TRADE"
MAPPING_VERSION = "1.0"
SOURCE_STRUCTURE = StructureIdentity("UNSD", "IMTS", "1.2")
TARGET_STRUCTURE = StructureIdentity("AFRSTAT", "AFR_TRADE", "1.0")
CORE_TARGET_CONCEPTS = frozenset(
    {
        "FREQ",
        "REF_AREA",
        "COUNTERPART_AREA",
        "TRADE_FLOW",
        "PRODUCT_SCHEME",
        "PRODUCT",
        "TIME_PERIOD",
        "OBS_VALUE",
    }
)


def _source_value(
    observation: NormalizedTradeObservation, concept_id: str
) -> object | None:
    explicit = {
        "FREQ": observation.frequency_code,
        "REF_AREA": observation.source_dimensions.get("REF_AREA"),
        "TRADE_FLOW": observation.trade_flow_code,
        "COMMODITY_1": observation.commodity_sdmx_code,
        "COUNTERPART_AREA_1": observation.source_dimensions.get(
            "COUNTERPART_AREA_1"
        ),
        "TIME_PERIOD": observation.time_period,
        "OBS_VALUE": observation.primary_value,
        "SOURCE_SYSTEM": observation.source_system,
    }
    if concept_id in explicit:
        return explicit[concept_id]
    if concept_id in observation.source_dimensions:
        return observation.source_dimensions[concept_id]
    return observation.source_attributes.get(concept_id)


def _all_decisions(
    session: Session,
    source_concept: str | None = None,
    target_concept: str | None = None,
) -> list[db.SdmxConceptMapping]:
    model = db.SdmxConceptMapping
    today = date.today()
    query = select(model).where(
        model.mapping_definition_id == MAPPING_DEFINITION_ID,
        model.mapping_version == MAPPING_VERSION,
        model.source_agency == SOURCE_STRUCTURE.agency,
        model.source_structure_id == SOURCE_STRUCTURE.structure_id,
        model.source_structure_version == SOURCE_STRUCTURE.version,
        model.target_agency == TARGET_STRUCTURE.agency,
        model.target_structure_id == TARGET_STRUCTURE.structure_id,
        model.target_structure_version == TARGET_STRUCTURE.version,
        (model.valid_from.is_(None) | (model.valid_from <= today)),
        (model.valid_to.is_(None) | (model.valid_to >= today)),
    )
    if source_concept is not None:
        query = query.where(model.source_concept_id == source_concept)
    if target_concept is not None:
        query = query.where(model.target_concept_id == target_concept)
    return list(session.scalars(query.order_by(model.id)))


def _issue_for_decision(
    source_concept: str,
    target_concept: str,
    source_value: object | None,
    decisions: list[db.SdmxConceptMapping],
) -> HarmonizationIssue:
    if any(row.mapping_type is db.SdmxMappingType.DEFER for row in decisions):
        code = HarmonizationIssueCode.DEFERRED_MAPPING
        detail = "is explicitly deferred"
    elif any(row.status is db.SdmxMappingStatus.DEPRECATED for row in decisions):
        code = HarmonizationIssueCode.DEPRECATED_MAPPING
        detail = "has only a deprecated mapping"
    elif decisions:
        code = HarmonizationIssueCode.UNCONFIRMED_MAPPING
        detail = "has no confirmed mapping"
    else:
        code = HarmonizationIssueCode.MISSING_CONCEPT_MAPPING
        detail = "has no mapping definition"
    return HarmonizationIssue(
        code=code,
        source_concept=source_concept,
        target_concept=target_concept,
        source_value=source_value,
        message=f"{source_concept} -> {target_concept} {detail}.",
    )


def _confirmed_concept(
    session: Session,
    observation: NormalizedTradeObservation,
    source_concept: str,
    target_concept: str,
    errors: list[HarmonizationIssue],
) -> db.SdmxConceptMapping | None:
    result = get_concept_mapping(
        session,
        SOURCE_STRUCTURE,
        TARGET_STRUCTURE,
        source_concept,
        target_concept=target_concept,
        mapping_definition_id=MAPPING_DEFINITION_ID,
        mapping_version=MAPPING_VERSION,
        confirmed_only=True,
    )
    if not result.resolved or result.value is None:
        errors.append(
            _issue_for_decision(
                source_concept,
                target_concept,
                _source_value(observation, source_concept),
                _all_decisions(session, source_concept, target_concept),
            )
        )
        return None
    if result.value.mapping_type in {
        db.SdmxMappingType.DEFER,
        db.SdmxMappingType.DROP,
    }:
        errors.append(
            _issue_for_decision(
                source_concept,
                target_concept,
                _source_value(observation, source_concept),
                [result.value],
            )
        )
        return None
    if result.value.transformation_id is not None:
        transformation = session.scalar(
            select(db.SdmxTransformationDefinition).where(
                db.SdmxTransformationDefinition.transformation_id
                == result.value.transformation_id,
                db.SdmxTransformationDefinition.version == MAPPING_VERSION,
            )
        )
        if transformation is None:
            errors.append(
                HarmonizationIssue(
                    code=HarmonizationIssueCode.MISSING_CONCEPT_MAPPING,
                    source_concept=source_concept,
                    target_concept=target_concept,
                    message=(
                        f"Transformation metadata "
                        f"{result.value.transformation_id!r} is unavailable."
                    ),
                )
            )
            return None
    return result.value


def _trace(
    mapping: db.SdmxConceptMapping,
    source_value: object | None,
    target_value: object | None,
    *,
    outcome: str,
    message: str | None = None,
) -> MappingTrace:
    return MappingTrace(
        target_concept=mapping.target_concept_id,
        source_concept=mapping.source_concept_id,
        source_value=source_value,
        target_value=target_value,
        mapping_type=mapping.mapping_type,
        mapping_status=mapping.status,
        transformation_id=mapping.transformation_id,
        outcome=outcome,
        message=message,
    )


def _map_direct(
    session: Session,
    observation: NormalizedTradeObservation,
    source_concept: str,
    target_concept: str,
    source_value: object | None,
    traces: list[MappingTrace],
    errors: list[HarmonizationIssue],
) -> object | None:
    mapping = _confirmed_concept(
        session, observation, source_concept, target_concept, errors
    )
    if mapping is None:
        return None
    if source_value is None:
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.MISSING_SOURCE_VALUE,
                source_concept=source_concept,
                target_concept=target_concept,
                message=f"Source value for {source_concept} is missing.",
            )
        )
        traces.append(_trace(mapping, source_value, None, outcome="UNRESOLVED"))
        return None
    traces.append(_trace(mapping, source_value, source_value, outcome="RESOLVED"))
    return source_value


def _map_code(
    session: Session,
    observation: NormalizedTradeObservation,
    source_concept: str,
    target_concept: str,
    source_value: str | None,
    traces: list[MappingTrace],
    errors: list[HarmonizationIssue],
) -> str | None:
    mapping = _confirmed_concept(
        session, observation, source_concept, target_concept, errors
    )
    if mapping is None:
        return None
    if source_value is None:
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.MISSING_SOURCE_VALUE,
                source_concept=source_concept,
                target_concept=target_concept,
                message=f"Source code for {source_concept} is missing.",
            )
        )
        traces.append(_trace(mapping, None, None, outcome="UNRESOLVED"))
        return None
    result = get_code_mapping(session, mapping, source_value, confirmed_only=True)
    if not result.resolved or result.value is None:
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.MISSING_CODE_MAPPING,
                source_concept=source_concept,
                target_concept=target_concept,
                source_value=source_value,
                message=(
                    f"No confirmed code mapping resolves {source_concept} "
                    f"value {source_value!r} for {target_concept}."
                ),
            )
        )
        traces.append(_trace(mapping, source_value, None, outcome="UNRESOLVED"))
        return None
    target_value = result.value.target_code
    traces.append(_trace(mapping, source_value, target_value, outcome="RESOLVED"))
    return target_value


def _map_area(
    session: Session,
    observation: NormalizedTradeObservation,
    *,
    source_concept: str,
    target_concept: str,
    provider_code: str | None,
    structural_code: str | None,
    expected_geo_id: int | None,
    traces: list[MappingTrace],
    errors: list[HarmonizationIssue],
) -> str | None:
    if provider_code is None:
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.UNMAPPED_TARGET_AREA,
                source_concept=source_concept,
                target_concept=target_concept,
                message=f"Provider geography for {source_concept} is missing.",
            )
        )
        return None
    geography = get_canonical_geography(
        session,
        source_agency=observation.source_agency,
        source_system=observation.source_system,
        source_codelist=SOURCE_CODELIST,
        source_code=provider_code,
        confirmed_only=True,
    )
    if (
        not geography.resolved
        or geography.value is None
        or expected_geo_id != geography.value.id
    ):
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.UNMAPPED_TARGET_AREA,
                source_concept=source_concept,
                target_concept=target_concept,
                source_value=provider_code,
                message=(
                    f"Provider geography {provider_code!r} does not resolve "
                    "consistently through canonical geo_area."
                ),
            )
        )
        return None
    return _map_code(
        session,
        observation,
        source_concept,
        target_concept,
        structural_code,
        traces,
        errors,
    )


def _map_primary_value_unit(
    session: Session,
    observation: NormalizedTradeObservation,
    traces: list[MappingTrace],
    errors: list[HarmonizationIssue],
) -> str | None:
    """Resolve USD only for the evidenced Comtrade CIF import-value path."""

    mapping = _confirmed_concept(
        session, observation, "MEASURE", "UNIT_MEASURE", errors
    )
    if mapping is None:
        return None
    is_supported_cif_value = (
        observation.source_system == "UN_COMTRADE"
        and observation.trade_flow_code == "M"
        and observation.primary_value is not None
        and observation.cif_value is not None
        and observation.primary_value == observation.cif_value
    )
    if not is_supported_cif_value:
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.MISSING_CODE_MAPPING,
                source_concept="MEASURE",
                target_concept="UNIT_MEASURE",
                source_value=None,
                message=(
                    "UNIT_MEASURE can be derived only when a UN Comtrade import "
                    "primaryValue is evidenced by the same-record cifvalue."
                ),
            )
        )
        traces.append(
            _trace(
                mapping,
                None,
                None,
                outcome="UNRESOLVED",
                message="Primary trade-value semantics are outside the confirmed MVP path.",
            )
        )
        return None
    traces.append(
        _trace(
            mapping,
            "V_CIF",
            "USD",
            outcome="RESOLVED",
            message=(
                "primaryValue equals cifvalue; official UN Comtrade documentation "
                "defines published trade values as current US-dollar values."
            ),
        )
    )
    return "USD"


def _map_source(
    session: Session,
    observation: NormalizedTradeObservation,
    traces: list[MappingTrace],
    errors: list[HarmonizationIssue],
) -> str | None:
    mapping = _confirmed_concept(
        session, observation, "SOURCE_SYSTEM", "SOURCE", errors
    )
    if mapping is None:
        return None
    if observation.source_system != "UN_COMTRADE":
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.MISSING_CODE_MAPPING,
                source_concept="SOURCE_SYSTEM",
                target_concept="SOURCE",
                source_value=observation.source_system,
                message=(
                    "No confirmed target SOURCE derivation exists for provider "
                    f"{observation.source_system!r}."
                ),
            )
        )
        traces.append(
            _trace(
                mapping,
                observation.source_system,
                None,
                outcome="UNRESOLVED",
            )
        )
        return None
    traces.append(
        _trace(
            mapping,
            observation.source_system,
            "UN_COMTRADE",
            outcome="RESOLVED",
        )
    )
    return "UN_COMTRADE"


def _classification_traces(
    session: Session,
    observation: NormalizedTradeObservation,
    traces: list[MappingTrace],
    warnings: list[HarmonizationIssue],
) -> tuple[list[str], list[str]]:
    dropped: list[str] = []
    deferred: list[str] = []
    existing = {(row.source_concept, row.target_concept) for row in traces}
    for mapping in _all_decisions(session):
        if mapping.mapping_type not in {
            db.SdmxMappingType.DROP,
            db.SdmxMappingType.DEFER,
        }:
            continue
        source_value = _source_value(observation, mapping.source_concept_id)
        if mapping.mapping_type is db.SdmxMappingType.DROP:
            if mapping.source_concept_id not in dropped:
                dropped.append(mapping.source_concept_id)
            outcome = "DROPPED"
        else:
            if mapping.source_concept_id not in deferred:
                deferred.append(mapping.source_concept_id)
            outcome = "DEFERRED"
            if source_value is not None:
                warnings.append(
                    HarmonizationIssue(
                        code=HarmonizationIssueCode.DEFERRED_MAPPING,
                        source_concept=mapping.source_concept_id,
                        target_concept=mapping.target_concept_id,
                        source_value=source_value,
                        message=(
                            f"{mapping.source_concept_id} is intentionally "
                            "unharmonised in AFR_TRADE 1.0."
                        ),
                    )
                )
        key = (mapping.source_concept_id, mapping.target_concept_id)
        if key not in existing:
            traces.append(
                _trace(
                    mapping,
                    source_value,
                    None,
                    outcome=outcome,
                    message=mapping.notes,
                )
            )
    return dropped, deferred


def transform_to_afr_trade(
    observation: NormalizedTradeObservation,
    session: Session,
    *,
    source_validation: ValidationSummary,
    target_context: TargetValidationContext | None = None,
) -> HarmonizationResult:
    """Map one already source-validated observation without persistence."""

    if source_validation.should_reject:
        return HarmonizationResult(
            source_observation=observation,
            source_validation=source_validation,
            errors=[
                HarmonizationIssue(
                    code=HarmonizationIssueCode.SOURCE_VALIDATION_FAILED,
                    message="Source validation rejected the UNSD observation.",
                )
            ],
            status=HarmonizationStatus.FAILED,
        )

    traces: list[MappingTrace] = []
    warnings: list[HarmonizationIssue] = []
    errors: list[HarmonizationIssue] = []
    freq = _map_code(
        session,
        observation,
        "FREQ",
        "FREQ",
        observation.frequency_code,
        traces,
        errors,
    )
    ref_area = _map_area(
        session,
        observation,
        source_concept="REF_AREA",
        target_concept="REF_AREA",
        provider_code=observation.reference_area_source_code,
        structural_code=observation.source_dimensions.get("REF_AREA"),
        expected_geo_id=observation.reference_geo_id,
        traces=traces,
        errors=errors,
    )
    counterpart_area = _map_area(
        session,
        observation,
        source_concept="COUNTERPART_AREA_1",
        target_concept="COUNTERPART_AREA",
        provider_code=observation.counterpart_area_source_code,
        structural_code=observation.source_dimensions.get("COUNTERPART_AREA_1"),
        expected_geo_id=observation.counterpart_geo_id,
        traces=traces,
        errors=errors,
    )
    trade_flow = _map_code(
        session,
        observation,
        "TRADE_FLOW",
        "TRADE_FLOW",
        observation.trade_flow_code,
        traces,
        errors,
    )
    product_scheme = _map_code(
        session,
        observation,
        "COMMODITY_1",
        "PRODUCT_SCHEME",
        observation.commodity_sdmx_code,
        traces,
        errors,
    )
    product = _map_code(
        session,
        observation,
        "COMMODITY_1",
        "PRODUCT",
        observation.commodity_sdmx_code,
        traces,
        errors,
    )
    time_period = _map_direct(
        session,
        observation,
        "TIME_PERIOD",
        "TIME_PERIOD",
        observation.time_period,
        traces,
        errors,
    )
    obs_value = _map_direct(
        session,
        observation,
        "OBS_VALUE",
        "OBS_VALUE",
        observation.primary_value,
        traces,
        errors,
    )

    unit_measure = _map_primary_value_unit(session, observation, traces, errors)
    unit_mult = _map_code(
        session,
        observation,
        "UNIT_MULT",
        "UNIT_MULT",
        "0" if unit_measure is not None else None,
        traces,
        errors,
    )
    source = _map_source(session, observation, traces, errors)

    target = AfrTradeObservation(
        freq=freq,
        ref_area=ref_area,
        counterpart_area=counterpart_area,
        trade_flow=trade_flow,
        product_scheme=product_scheme,
        product=product,
        unit_measure=unit_measure,
        time_period=time_period,
        obs_value=obs_value,
        unit_mult=unit_mult,
        source=source,
    )
    dropped, deferred = _classification_traces(
        session, observation, traces, warnings
    )
    try:
        validation_context = target_context or TargetValidationContext.from_session(
            session, TARGET_STRUCTURE
        )
        target_validation = validate_afr_trade_observation(
            target, validation_context
        )
    except (TypeError, ValueError):
        target_validation = None
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.TARGET_VALIDATION_FAILED,
                message="Target validation metadata could not be loaded safely.",
            )
        )
    if target_validation is not None and not target_validation.is_valid:
        errors.append(
            HarmonizationIssue(
                code=HarmonizationIssueCode.TARGET_VALIDATION_FAILED,
                message=(
                    f"AFR_TRADE target validation produced "
                    f"{len(target_validation.findings)} finding(s)."
                ),
            )
        )

    core_values = {
        "FREQ": target.freq,
        "REF_AREA": target.ref_area,
        "COUNTERPART_AREA": target.counterpart_area,
        "TRADE_FLOW": target.trade_flow,
        "PRODUCT_SCHEME": target.product_scheme,
        "PRODUCT": target.product,
        "TIME_PERIOD": target.time_period,
        "OBS_VALUE": target.obs_value,
    }
    if any(core_values[concept] is None for concept in CORE_TARGET_CONCEPTS):
        status = HarmonizationStatus.FAILED
    elif target_validation is None or not target_validation.is_valid or errors:
        status = HarmonizationStatus.PARTIAL
    else:
        status = HarmonizationStatus.SUCCESS
    try:
        identity = identify_target_observation(target)
    except ValueError:
        identity = None

    return HarmonizationResult(
        source_observation=observation,
        source_validation=source_validation,
        target_observation=target,
        mapping_results=traces,
        dropped_concepts=dropped,
        deferred_concepts=deferred,
        warnings=warnings,
        errors=errors,
        target_validation=target_validation,
        target_identity=identity,
        status=status,
    )

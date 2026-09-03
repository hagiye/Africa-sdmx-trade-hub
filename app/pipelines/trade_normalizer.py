"""Normalize parsed UN Comtrade records without persisting or filtering them."""

from __future__ import annotations

import copy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Dataflow, GeoArea
from app.mappings.geo import SOURCE_AGENCY, SOURCE_SYSTEM, resolve_source_area
from app.pipelines.trade_concept_mapping import (
    parsed_concept_value,
    provider_field_value,
)
from app.pipelines.trade_models import (
    NormalizationIssue,
    NormalizationIssueCode,
    NormalizationResult,
    NormalizedTradeObservation,
)
from app.sdmx.data_models import ParsedObservation


def _text(value: object | None) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _source_code(observation: ParsedObservation, concept_id: str) -> str | None:
    return _text(provider_field_value(observation, concept_id))


def _code_or_concept(observation: ParsedObservation, concept_id: str) -> str | None:
    return _source_code(observation, concept_id) or parsed_concept_value(
        observation, concept_id
    )


def _source_dsd_identity(
    session: Session, observation: ParsedObservation
) -> tuple[str | None, str | None]:
    if not all(
        (
            observation.dataflow_agency,
            observation.dataflow_id,
            observation.dataflow_version,
        )
    ):
        return None, None
    dataflow = session.scalar(
        select(Dataflow).where(
            Dataflow.agency_id == observation.dataflow_agency,
            Dataflow.dataflow_id == observation.dataflow_id,
            Dataflow.version == observation.dataflow_version,
        )
    )
    if dataflow is None:
        return None, None
    return dataflow.dsd_id, dataflow.dsd_version


def _unmapped_area_issue(
    *, concept_id: str, source_code: str | None, fatal: bool
) -> NormalizationIssue:
    role = "reference" if concept_id == "REF_AREA" else "counterpart"
    issue_code = (
        NormalizationIssueCode.UNMAPPED_REFERENCE_AREA
        if fatal
        else NormalizationIssueCode.UNMAPPED_COUNTERPART_AREA
    )
    return NormalizationIssue(
        code=issue_code,
        message=f"Source {role} area code {source_code!r} has no canonical mapping",
        concept_id=concept_id,
        source_code=source_code,
        fatal=fatal,
    )


def _resolve_area(
    session: Session,
    *,
    source_agency: str,
    source_system: str,
    source_code: str | None,
) -> GeoArea | None:
    if source_code is None:
        return None
    return resolve_source_area(
        session, source_agency, source_system, source_code
    )


def normalize_trade_observation(
    observation: ParsedObservation,
    session: Session,
    *,
    source_system: str = SOURCE_SYSTEM,
) -> NormalizationResult:
    """Interpret one parsed record and return data-quality issues alongside it."""
    source_agency = observation.dataflow_agency or SOURCE_AGENCY
    reference_source_code = _source_code(observation, "REF_AREA")
    counterpart_source_code = _source_code(observation, "COUNTERPART_AREA_1")
    reference = _resolve_area(
        session,
        source_agency=source_agency,
        source_system=source_system,
        source_code=reference_source_code,
    )
    counterpart = _resolve_area(
        session,
        source_agency=source_agency,
        source_system=source_system,
        source_code=counterpart_source_code,
    )

    issues: list[NormalizationIssue] = []
    if reference is None:
        issues.append(
            _unmapped_area_issue(
                concept_id="REF_AREA",
                source_code=reference_source_code,
                fatal=True,
            )
        )
    if counterpart is None:
        issues.append(
            _unmapped_area_issue(
                concept_id="COUNTERPART_AREA_1",
                source_code=counterpart_source_code,
                fatal=False,
            )
        )

    trade_flow_code = _code_or_concept(observation, "TRADE_FLOW")
    frequency_code = _code_or_concept(observation, "FREQ")
    time_period = parsed_concept_value(observation, "TIME_PERIOD")
    primary_value = observation.get_primary_value()
    if trade_flow_code is None:
        issues.append(
            NormalizationIssue(
                code=NormalizationIssueCode.MISSING_TRADE_FLOW,
                message="TRADE_FLOW is absent from the parsed observation",
                concept_id="TRADE_FLOW",
            )
        )
    if time_period is None:
        issues.append(
            NormalizationIssue(
                code=NormalizationIssueCode.MISSING_TIME_PERIOD,
                message="TIME_PERIOD is absent from the parsed observation",
                concept_id="TIME_PERIOD",
            )
        )
    if primary_value is None:
        issues.append(
            NormalizationIssue(
                code=NormalizationIssueCode.MISSING_PRIMARY_VALUE,
                message="primaryValue is absent or null",
            )
        )

    source_dsd, source_dsd_version = _source_dsd_identity(session, observation)
    normalized = NormalizedTradeObservation(
        source_agency=source_agency,
        source_system=source_system,
        source_dataflow=observation.dataflow_id,
        source_dataflow_version=observation.dataflow_version,
        source_dsd=source_dsd,
        source_dsd_version=source_dsd_version,
        reference_area_source_code=reference_source_code,
        reference_geo_id=reference.id if reference else None,
        reference_iso2=reference.iso2 if reference else None,
        reference_iso3=reference.iso3 if reference else None,
        reference_name=reference.name_en if reference else None,
        reference_area_type=reference.area_type if reference else None,
        reference_is_au_member=reference.au_member if reference else None,
        counterpart_area_source_code=counterpart_source_code,
        counterpart_geo_id=counterpart.id if counterpart else None,
        counterpart_iso2=counterpart.iso2 if counterpart else None,
        counterpart_iso3=counterpart.iso3 if counterpart else None,
        counterpart_name=counterpart.name_en if counterpart else None,
        counterpart_area_type=counterpart.area_type if counterpart else None,
        counterpart_is_au_member=counterpart.au_member if counterpart else None,
        trade_flow_code=trade_flow_code,
        trade_flow_label=_text(provider_field_value(observation, "TRADE_FLOW", "label")),
        frequency_code=frequency_code,
        commodity_code=_code_or_concept(observation, "COMMODITY_1"),
        commodity_classification=_text(
            provider_field_value(observation, "COMMODITY_1", "classification")
        ),
        commodity_sdmx_code=parsed_concept_value(observation, "COMMODITY_1"),
        commodity_description=_text(
            provider_field_value(observation, "COMMODITY_1", "label")
        ),
        time_period=time_period,
        primary_value=primary_value,
        quantity=observation.observation_values.get("qty"),
        net_weight=observation.observation_values.get("netWgt"),
        gross_weight=observation.observation_values.get("grossWgt"),
        cif_value=observation.observation_values.get("cifvalue"),
        fob_value=observation.observation_values.get("fobvalue"),
        source_dimensions=copy.deepcopy(observation.dimension_values),
        source_attributes=copy.deepcopy(observation.attributes),
        source_fields=copy.deepcopy(observation.source_fields),
    )
    return NormalizationResult(observation=normalized, issues=issues)

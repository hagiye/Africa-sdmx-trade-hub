"""Declarative SDMX-concept interpretation for trade normalization."""

from __future__ import annotations

from dataclasses import dataclass

from app.sdmx.comtrade_field_mapping import REAL_DSD_CONCEPTS
from app.sdmx.data_models import ParsedObservation


@dataclass(frozen=True)
class TradeConceptRule:
    normalized_field: str | None
    provider_code_field: str | None = None
    provider_label_field: str | None = None
    provider_classification_field: str | None = None
    exposed_by_parser: bool = True


TRADE_CONCEPT_MAPPING = {
    "REF_AREA": TradeConceptRule(
        "reference_area_source_code",
        provider_code_field="reporterCode",
        provider_label_field="reporterDesc",
    ),
    "COUNTERPART_AREA_1": TradeConceptRule(
        "counterpart_area_source_code",
        provider_code_field="partnerCode",
        provider_label_field="partnerDesc",
    ),
    "TRADE_FLOW": TradeConceptRule(
        "trade_flow_code",
        provider_code_field="flowCode",
        provider_label_field="flowDesc",
    ),
    "FREQ": TradeConceptRule(
        "frequency_code",
        provider_code_field="freqCode",
    ),
    "COMMODITY_1": TradeConceptRule(
        "commodity_code",
        provider_code_field="cmdCode",
        provider_label_field="cmdDesc",
        provider_classification_field="classificationCode",
    ),
    "TIME_PERIOD": TradeConceptRule(
        "time_period",
        provider_code_field="period",
    ),
    # The real DSD contains MEASURE, but these simplified records do not expose
    # its dimension code. Numeric columns must not be treated as that code.
    "MEASURE": TradeConceptRule(None, exposed_by_parser=False),
}

if not set(TRADE_CONCEPT_MAPPING) <= REAL_DSD_CONCEPTS:
    raise RuntimeError("Trade normalization references a concept absent from the real DSD")


def parsed_concept_value(
    observation: ParsedObservation, concept_id: str
) -> str | None:
    """Read a concept from the parser's representation without fabricating it."""
    if concept_id == "TIME_PERIOD":
        return observation.time_period
    return observation.dimension_values.get(concept_id)


def provider_field_value(
    observation: ParsedObservation,
    concept_id: str,
    role: str = "code",
) -> object | None:
    """Read the original provider field declared for a concept and role."""
    rule = TRADE_CONCEPT_MAPPING[concept_id]
    field = {
        "code": rule.provider_code_field,
        "label": rule.provider_label_field,
        "classification": rule.provider_classification_field,
    }.get(role)
    if field is None:
        return None
    return observation.source_fields.get(field)

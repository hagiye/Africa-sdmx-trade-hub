"""Structural rules for dimensions exposed by the current source mapping."""

from __future__ import annotations

from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.base import ValidationRule
from app.validation.context import ValidationContext
from app.validation.models import (
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
)


def _dimension_value(
    observation: NormalizedTradeObservation, concept_id: str
) -> object | None:
    return {
        "FREQ": observation.frequency_code,
        "REF_AREA": observation.reference_area_source_code,
        "TRADE_FLOW": observation.trade_flow_code,
        "COMMODITY_1": observation.commodity_code,
        "COUNTERPART_AREA_1": observation.counterpart_area_source_code,
        "COUNTERPART_AREA_2": observation.source_fields.get("partner2Code"),
        "TIME_PERIOD": observation.time_period,
    }.get(concept_id, observation.source_dimensions.get(concept_id))


class MandatoryDimensionPresentRule(ValidationRule):
    rule_id = "MANDATORY_DIMENSION_PRESENT"
    category = ValidationCategory.STRUCTURE

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        results = []
        for concept_id in context.required_dimensions:
            value = _dimension_value(observation, concept_id)
            if value is None or (isinstance(value, str) and not value.strip()):
                results.append(
                    ValidationResult(
                        rule_id=self.rule_id,
                        category=self.category,
                        severity=ValidationSeverity.ERROR,
                        concept_id=concept_id,
                        message=(
                            f"Required {concept_id} is absent from the current "
                            "UN Comtrade application mapping."
                        ),
                    )
                )
        return results

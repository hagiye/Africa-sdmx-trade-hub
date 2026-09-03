"""Rules backed by codelists associated with the selected DSD."""

from __future__ import annotations

from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.base import ValidationRule
from app.validation.context import ValidationContext
from app.validation.models import (
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
)


class _CodelistRule(ValidationRule):
    category = ValidationCategory.CODELIST
    concept_id: str

    def value(self, observation: NormalizedTradeObservation) -> str | None:
        raise NotImplementedError

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        value = self.value(observation)
        if value is None or not str(value).strip():
            return []
        codes = context.codes_for(self.concept_id)
        if not codes:
            return [
                ValidationResult(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=ValidationSeverity.FATAL,
                    concept_id=self.concept_id,
                    invalid_value=str(value),
                    message=(
                        f"The DSD-associated codelist for {self.concept_id} "
                        "is unavailable in the metadata registry."
                    ),
                )
            ]
        if str(value) not in codes:
            return [
                ValidationResult(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=ValidationSeverity.ERROR,
                    concept_id=self.concept_id,
                    invalid_value=str(value),
                    message=(
                        f"Code {value!r} is not present in the SDMX codelist "
                        f"associated with {self.concept_id}."
                    ),
                )
            ]
        return []


class ValidFrequencyCodeRule(_CodelistRule):
    rule_id = "VALID_FREQUENCY_CODE"
    concept_id = "FREQ"

    def value(self, observation: NormalizedTradeObservation) -> str | None:
        return observation.frequency_code


class ValidTradeFlowCodeRule(_CodelistRule):
    rule_id = "VALID_TRADE_FLOW_CODE"
    concept_id = "TRADE_FLOW"

    def value(self, observation: NormalizedTradeObservation) -> str | None:
        return observation.trade_flow_code


class ValidCommodityCodeRule(_CodelistRule):
    rule_id = "VALID_COMMODITY_CODE"
    concept_id = "COMMODITY_1"

    def value(self, observation: NormalizedTradeObservation) -> str | None:
        return observation.commodity_sdmx_code

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        if observation.commodity_code and not observation.commodity_sdmx_code:
            classification = observation.commodity_classification or "unknown"
            return [
                ValidationResult(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=ValidationSeverity.ERROR,
                    concept_id=self.concept_id,
                    invalid_value=(
                        f"{classification}:{observation.commodity_code}"
                    ),
                    message=(
                        "The source commodity and classification do not resolve "
                        "to an authoritative COMMODITY_1 code."
                    ),
                )
            ]
        return super().validate(observation, context)

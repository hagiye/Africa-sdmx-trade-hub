"""Time-period and statistical-value validation rules."""

from __future__ import annotations

import re
from decimal import Decimal

from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.base import ValidationRule
from app.validation.context import ValidationContext
from app.validation.models import (
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
)


TIME_PATTERNS = {
    "A": re.compile(r"^[0-9]{4}$"),
    "Q": re.compile(r"^[0-9]{4}-Q[1-4]$"),
    "M": re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$"),
}


class ValidTimePeriodRule(ValidationRule):
    rule_id = "VALID_TIME_PERIOD"
    category = ValidationCategory.VALUE

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        period = observation.time_period
        if period is None or not str(period).strip():
            return [
                ValidationResult(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=ValidationSeverity.ERROR,
                    concept_id="TIME_PERIOD",
                    message="TIME_PERIOD is required for a trade observation.",
                )
            ]
        pattern = TIME_PATTERNS.get(observation.frequency_code or "")
        if pattern is None:
            # Frequency validity is owned by VALID_FREQUENCY_CODE. Future
            # frequencies can add a format strategy without annual-only logic.
            return []
        if pattern.fullmatch(str(period)):
            return []
        return [
            ValidationResult(
                rule_id=self.rule_id,
                category=self.category,
                severity=ValidationSeverity.ERROR,
                concept_id="TIME_PERIOD",
                invalid_value=str(period),
                message=(
                    f"TIME_PERIOD {period!r} is not valid for frequency "
                    f"{observation.frequency_code!r}."
                ),
            )
        ]


class PrimaryValuePresentRule(ValidationRule):
    rule_id = "PRIMARY_VALUE_PRESENT"
    category = ValidationCategory.VALUE

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        if observation.primary_value is not None:
            return []
        return [
            ValidationResult(
                rule_id=self.rule_id,
                category=self.category,
                severity=ValidationSeverity.ERROR,
                concept_id="OBS_VALUE",
                message=(
                    "The current trade-ingestion policy requires primaryValue; "
                    "missing values are never converted to zero."
                ),
            )
        ]


class ValidObservationValueRule(ValidationRule):
    rule_id = "VALID_OBSERVATION_VALUE"
    category = ValidationCategory.VALUE

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        value = observation.primary_value
        if value is None:
            return []
        if isinstance(value, Decimal) and value.is_finite():
            return []
        return [
            ValidationResult(
                rule_id=self.rule_id,
                category=self.category,
                severity=ValidationSeverity.ERROR,
                concept_id="OBS_VALUE",
                invalid_value=str(value),
                message="The primary statistical value must be a finite Decimal.",
            )
        ]


class NonNegativeTradeValueRule(ValidationRule):
    rule_id = "NON_NEGATIVE_TRADE_VALUE"
    category = ValidationCategory.VALUE

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        value = observation.primary_value
        if not isinstance(value, Decimal) or value >= 0:
            return []
        return [
            ValidationResult(
                rule_id=self.rule_id,
                category=self.category,
                severity=ValidationSeverity.WARNING,
                concept_id="OBS_VALUE",
                invalid_value=str(value),
                message=(
                    "Negative merchandise trade value requires review; it is "
                    "not globally rejected without measure-specific metadata."
                ),
            )
        ]

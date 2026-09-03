"""Deterministic validation orchestration and the current trade ruleset."""

from __future__ import annotations

from collections.abc import Sequence

from app.pipelines.observation_identity import identify_observation
from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.base import ValidationRule
from app.validation.context import ValidationContext
from app.validation.models import (
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
    ValidationSummary,
)
from app.validation.rules import (
    DuplicateObservationInBatchRule,
    MandatoryDimensionPresentRule,
    NonNegativeTradeValueRule,
    PrimaryValuePresentRule,
    ReferenceAreaIsAUMemberRule,
    ValidCommodityCodeRule,
    ValidCounterpartAreaRule,
    ValidFrequencyCodeRule,
    ValidObservationValueRule,
    ValidReferenceAreaRule,
    ValidTimePeriodRule,
    ValidTradeFlowCodeRule,
)


def get_trade_validation_rules() -> tuple[ValidationRule, ...]:
    """Return the rules specific to current UN Comtrade ingestion."""
    return (
        MandatoryDimensionPresentRule(),
        ValidFrequencyCodeRule(),
        ValidTradeFlowCodeRule(),
        ValidReferenceAreaRule(),
        ReferenceAreaIsAUMemberRule(),
        ValidCounterpartAreaRule(),
        ValidTimePeriodRule(),
        PrimaryValuePresentRule(),
        ValidObservationValueRule(),
        NonNegativeTradeValueRule(),
        ValidCommodityCodeRule(),
        DuplicateObservationInBatchRule(),
    )


class ValidationEngine:
    """Execute isolated rules and turn unexpected rule failures into FATALs."""

    def __init__(self, rules: Sequence[ValidationRule]) -> None:
        self.rules = tuple(rules)

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> ValidationSummary:
        results: list[ValidationResult] = []
        for rule in self.rules:
            try:
                results.extend(rule.validate(observation, context))
            except Exception:
                results.append(
                    ValidationResult(
                        rule_id="VALIDATION_RULE_EXCEPTION",
                        category=ValidationCategory.QUALITY,
                        severity=ValidationSeverity.FATAL,
                        message=(
                            f"Validation rule {rule.rule_id} could not complete "
                            "safely."
                        ),
                        metadata={"failed_rule_id": rule.rule_id},
                    )
                )

        try:
            identity = identify_observation(
                observation, dataset_identity=context.dataset_identity
            )
        except (TypeError, ValueError):
            identity = None
        if identity is not None:
            results = [
                result.model_copy(
                    update={
                        "source_key": result.source_key or identity.source_key,
                        "source_key_hash": (
                            result.source_key_hash or identity.source_key_hash
                        ),
                    }
                )
                for result in results
            ]
        return ValidationSummary(results=results)

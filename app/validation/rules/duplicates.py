"""Incoming-batch duplicate quality rule, separate from warehouse identity."""

from __future__ import annotations

from app.pipelines.observation_identity import identify_observation
from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.base import ValidationRule
from app.validation.context import ValidationContext
from app.validation.models import (
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
)


class DuplicateObservationInBatchRule(ValidationRule):
    rule_id = "DUPLICATE_OBSERVATION_IN_BATCH"
    category = ValidationCategory.QUALITY

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        try:
            identity = identify_observation(
                observation, dataset_identity=context.dataset_identity
            )
        except (TypeError, ValueError):
            # Structural/value rules own incomplete identities.
            return []
        if identity.source_key_hash not in context.seen_source_key_hashes:
            context.seen_source_key_hashes.add(identity.source_key_hash)
            return []
        return [
            ValidationResult(
                rule_id=self.rule_id,
                category=self.category,
                severity=ValidationSeverity.WARNING,
                message=(
                    "The same source observation identity appears more than "
                    "once in this incoming batch."
                ),
                source_key=identity.source_key,
                source_key_hash=identity.source_key_hash,
            )
        ]

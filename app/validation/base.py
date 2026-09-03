"""Interface shared by independently testable validation rules."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.context import ValidationContext
from app.validation.models import ValidationCategory, ValidationResult


class ValidationRule(ABC):
    """One deterministic validation responsibility."""

    rule_id: str
    category: ValidationCategory

    @abstractmethod
    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        """Return findings; an empty list means this rule passed."""

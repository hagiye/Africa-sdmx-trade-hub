"""Canonical-geography and application-scope validation rules."""

from __future__ import annotations

from app.database.models import AreaType
from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.base import ValidationRule
from app.validation.context import ValidationContext
from app.validation.models import (
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
)


class ValidReferenceAreaRule(ValidationRule):
    rule_id = "VALID_REFERENCE_AREA"
    category = ValidationCategory.GEOGRAPHY

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        code = observation.reference_area_source_code
        if not code:
            return []
        mapping = context.geographies.get(code)
        if mapping is not None and mapping.geo_area_id is not None:
            return []
        return [
            ValidationResult(
                rule_id=self.rule_id,
                category=self.category,
                severity=ValidationSeverity.ERROR,
                concept_id="REF_AREA",
                invalid_value=code,
                message=(
                    f"Reference area source code {code!r} does not resolve "
                    "through source_geo_mapping to canonical geography."
                ),
            )
        ]


class ReferenceAreaIsAUMemberRule(ValidationRule):
    rule_id = "REFERENCE_AREA_IS_AU_MEMBER"
    category = ValidationCategory.APPLICATION_SCOPE

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        code = observation.reference_area_source_code
        mapping = context.geographies.get(code) if code else None
        # VALID_REFERENCE_AREA owns unresolved geography; avoid a second noisy
        # scope finding when canonical membership cannot yet be evaluated.
        if mapping is None or mapping.geo_area_id is None:
            return []
        if mapping.area_type is AreaType.COUNTRY and mapping.au_member is True:
            return []
        return [
            ValidationResult(
                rule_id=self.rule_id,
                category=self.category,
                severity=ValidationSeverity.ERROR,
                concept_id="REF_AREA",
                invalid_value=code,
                message=(
                    "Reference area is structurally resolvable but is not a "
                    "canonical African Union Member State country."
                ),
                metadata={
                    "area_name": mapping.name,
                    "area_type": mapping.area_type.value if mapping.area_type else None,
                },
            )
        ]


class ValidCounterpartAreaRule(ValidationRule):
    rule_id = "VALID_COUNTERPART_AREA"
    category = ValidationCategory.GEOGRAPHY

    def validate(
        self,
        observation: NormalizedTradeObservation,
        context: ValidationContext,
    ) -> list[ValidationResult]:
        code = observation.counterpart_area_source_code
        if not code:
            return []
        mapping = context.geographies.get(code)
        if mapping is not None and mapping.geo_area_id is not None:
            return []
        return [
            ValidationResult(
                rule_id=self.rule_id,
                category=self.category,
                severity=ValidationSeverity.WARNING,
                concept_id="COUNTERPART_AREA_1",
                invalid_value=code,
                message=(
                    f"Counterpart source code {code!r} is not mapped to "
                    "canonical geography; source evidence is retained."
                ),
            )
        ]

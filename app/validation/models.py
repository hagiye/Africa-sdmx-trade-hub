"""Serializable validation findings and aggregate decisions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class ValidationSeverity(StrEnum):
    """Impact of a validation finding on observation processing.

    INFO records useful context. WARNING permits processing but merits review.
    ERROR rejects the observation. FATAL means validation cannot continue
    safely for that observation and also rejects it.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


class ValidationCategory(StrEnum):
    STRUCTURE = "STRUCTURE"
    CODELIST = "CODELIST"
    VALUE = "VALUE"
    GEOGRAPHY = "GEOGRAPHY"
    APPLICATION_SCOPE = "APPLICATION_SCOPE"
    QUALITY = "QUALITY"


class ValidationResult(BaseModel):
    """One safe, serializable rule finding without implementation details."""

    rule_id: str
    category: ValidationCategory
    severity: ValidationSeverity
    concept_id: str | None = None
    invalid_value: str | None = None
    message: str
    source_key: str | None = None
    source_key_hash: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ValidationSummary(BaseModel):
    """Combined findings and the resulting accept/reject decision."""

    results: list[ValidationResult] = Field(default_factory=list)

    def _count(self, severity: ValidationSeverity) -> int:
        return sum(result.severity is severity for result in self.results)

    @computed_field
    @property
    def info_count(self) -> int:
        return self._count(ValidationSeverity.INFO)

    @computed_field
    @property
    def warning_count(self) -> int:
        return self._count(ValidationSeverity.WARNING)

    @computed_field
    @property
    def error_count(self) -> int:
        return self._count(ValidationSeverity.ERROR)

    @computed_field
    @property
    def fatal_count(self) -> int:
        return self._count(ValidationSeverity.FATAL)

    @computed_field
    @property
    def should_reject(self) -> bool:
        return bool(self.error_count or self.fatal_count)

    @computed_field
    @property
    def is_valid(self) -> bool:
        return not self.should_reject

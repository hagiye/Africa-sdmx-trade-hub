"""Generic parsed statistical-data models."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class ParsedObservation(BaseModel):
    """One provider observation represented without warehouse assumptions."""

    dataflow_agency: str | None = None
    dataflow_id: str | None = None
    dataflow_version: str | None = None
    dimension_values: dict[str, str | None] = Field(default_factory=dict)
    time_period: str | None = None
    observation_values: dict[str, Decimal | None] = Field(default_factory=dict)
    attributes: dict[str, object] = Field(default_factory=dict)
    source_fields: dict[str, object] = Field(default_factory=dict)
    source_record_index: int
    source: str

    def get_primary_value(self) -> Decimal | None:
        """Return the provider's primary value without treating it as MEASURE."""
        return self.observation_values.get("primaryValue")


class ParsedDataResponse(BaseModel):
    """Parsed observations plus non-observation response information."""

    provider: str
    dataflow_agency: str | None = None
    dataflow_id: str | None = None
    dataflow_version: str | None = None
    observations: list[ParsedObservation] = Field(default_factory=list)
    record_count: int
    envelope_metadata: dict[str, object] = Field(default_factory=dict)
    raw_response_checksum: str
    statistical_content_checksum: str

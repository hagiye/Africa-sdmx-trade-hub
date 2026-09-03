"""Application-level trade normalization models without persistence concerns."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.database.models import AreaType


class NormalizationIssueCode(StrEnum):
    UNMAPPED_REFERENCE_AREA = "UNMAPPED_REFERENCE_AREA"
    UNMAPPED_COUNTERPART_AREA = "UNMAPPED_COUNTERPART_AREA"
    MISSING_TRADE_FLOW = "MISSING_TRADE_FLOW"
    MISSING_TIME_PERIOD = "MISSING_TIME_PERIOD"
    MISSING_PRIMARY_VALUE = "MISSING_PRIMARY_VALUE"


class NormalizationIssue(BaseModel):
    code: NormalizationIssueCode
    message: str
    concept_id: str | None = None
    source_code: str | None = None
    fatal: bool = False


class NormalizedTradeObservation(BaseModel):
    """One interpreted trade observation; this is not an ORM model."""

    source_agency: str
    source_system: str
    source_dataflow: str | None = None
    source_dataflow_version: str | None = None
    source_dsd: str | None = None
    source_dsd_version: str | None = None

    reference_area_source_code: str | None = None
    reference_geo_id: int | None = None
    reference_iso2: str | None = None
    reference_iso3: str | None = None
    reference_name: str | None = None
    reference_area_type: AreaType | None = None
    reference_is_au_member: bool | None = None

    counterpart_area_source_code: str | None = None
    counterpart_geo_id: int | None = None
    counterpart_iso2: str | None = None
    counterpart_iso3: str | None = None
    counterpart_name: str | None = None
    counterpart_area_type: AreaType | None = None
    counterpart_is_au_member: bool | None = None

    trade_flow_code: str | None = None
    trade_flow_label: str | None = None
    frequency_code: str | None = None
    commodity_code: str | None = None
    commodity_classification: str | None = None
    commodity_sdmx_code: str | None = None
    commodity_description: str | None = None
    time_period: str | None = None

    primary_value: Decimal | None = None
    quantity: Decimal | None = None
    net_weight: Decimal | None = None
    gross_weight: Decimal | None = None
    cif_value: Decimal | None = None
    fob_value: Decimal | None = None

    source_dimensions: dict[str, str | None] = Field(default_factory=dict)
    source_attributes: dict[str, object] = Field(default_factory=dict)
    source_fields: dict[str, object] = Field(default_factory=dict)


class NormalizationResult(BaseModel):
    observation: NormalizedTradeObservation | None
    issues: list[NormalizationIssue] = Field(default_factory=list)

    @property
    def has_fatal_issues(self) -> bool:
        return any(issue.fatal for issue in self.issues)

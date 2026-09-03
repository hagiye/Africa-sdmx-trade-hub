"""Non-persistent models for AFRSTAT:AFR_TRADE(1.0) harmonization."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from app.database.models import SdmxMappingStatus, SdmxMappingType
from app.pipelines.observation_identity import canonical_decimal, canonical_json
from app.pipelines.trade_models import NormalizedTradeObservation
from app.validation.models import ValidationSummary


TARGET_DIMENSIONS = (
    "FREQ",
    "REF_AREA",
    "COUNTERPART_AREA",
    "TRADE_FLOW",
    "PRODUCT_SCHEME",
    "PRODUCT",
    "UNIT_MEASURE",
    "TIME_PERIOD",
)
TARGET_ATTRIBUTES = (
    "OBS_STATUS",
    "CONF_STATUS",
    "UNIT_MULT",
    "DECIMALS",
    "SOURCE",
)


class HarmonizationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class HarmonizationIssueCode(StrEnum):
    SOURCE_VALIDATION_FAILED = "SOURCE_VALIDATION_FAILED"
    MISSING_CONCEPT_MAPPING = "MISSING_CONCEPT_MAPPING"
    MISSING_CODE_MAPPING = "MISSING_CODE_MAPPING"
    UNCONFIRMED_MAPPING = "UNCONFIRMED_MAPPING"
    DEPRECATED_MAPPING = "DEPRECATED_MAPPING"
    DEFERRED_MAPPING = "DEFERRED_MAPPING"
    UNMAPPED_TARGET_AREA = "UNMAPPED_TARGET_AREA"
    MISSING_SOURCE_VALUE = "MISSING_SOURCE_VALUE"
    INVALID_TARGET_CODE = "INVALID_TARGET_CODE"
    TARGET_VALIDATION_FAILED = "TARGET_VALIDATION_FAILED"


class TargetValidationStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"


class MappingTrace(BaseModel):
    target_concept: str | None = None
    source_concept: str
    source_value: object | None = None
    target_value: object | None = None
    mapping_type: SdmxMappingType
    mapping_status: SdmxMappingStatus
    transformation_id: str | None = None
    outcome: str
    message: str | None = None


class HarmonizationIssue(BaseModel):
    code: HarmonizationIssueCode
    message: str
    source_concept: str | None = None
    target_concept: str | None = None
    source_value: object | None = None


class TargetValidationFinding(BaseModel):
    code: HarmonizationIssueCode
    concept_id: str
    invalid_value: object | None = None
    message: str


class TargetValidationResult(BaseModel):
    status: TargetValidationStatus
    findings: list[TargetValidationFinding] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.status is TargetValidationStatus.VALID


class AfrTradeObservation(BaseModel):
    """Canonical target candidate; optional values permit auditable partial results."""

    freq: str | None = None
    ref_area: str | None = None
    counterpart_area: str | None = None
    trade_flow: str | None = None
    product_scheme: str | None = None
    product: str | None = None
    unit_measure: str | None = None
    time_period: str | None = None
    obs_value: Decimal | None = None
    obs_status: str | None = None
    conf_status: str | None = None
    unit_mult: str | None = None
    decimals: int | None = None
    source: str | None = None

    def canonical_dict(self) -> dict[str, object | None]:
        """Return AFR_TRADE canonical JSON fields in DSD component order."""

        return {
            "FREQ": self.freq,
            "REF_AREA": self.ref_area,
            "COUNTERPART_AREA": self.counterpart_area,
            "TRADE_FLOW": self.trade_flow,
            "PRODUCT_SCHEME": self.product_scheme,
            "PRODUCT": self.product,
            "UNIT_MEASURE": self.unit_measure,
            "TIME_PERIOD": self.time_period,
            "OBS_VALUE": (
                canonical_decimal(self.obs_value)
                if isinstance(self.obs_value, Decimal)
                else self.obs_value
            ),
            "OBS_STATUS": self.obs_status,
            "CONF_STATUS": self.conf_status,
            "UNIT_MULT": self.unit_mult,
            "DECIMALS": self.decimals,
            "SOURCE": self.source,
        }

    def canonical_json(self) -> str:
        """Serialize internal AFR_TRADE canonical JSON (not SDMX-JSON)."""

        return canonical_json(self.canonical_dict())


class TargetObservationIdentity(BaseModel):
    target_key: str
    target_key_hash: str
    target_content_hash: str


class HarmonizationResult(BaseModel):
    source_observation: NormalizedTradeObservation
    source_validation: ValidationSummary
    target_observation: AfrTradeObservation | None = None
    mapping_results: list[MappingTrace] = Field(default_factory=list)
    dropped_concepts: list[str] = Field(default_factory=list)
    deferred_concepts: list[str] = Field(default_factory=list)
    warnings: list[HarmonizationIssue] = Field(default_factory=list)
    errors: list[HarmonizationIssue] = Field(default_factory=list)
    target_validation: TargetValidationResult | None = None
    target_identity: TargetObservationIdentity | None = None
    status: HarmonizationStatus


def build_target_key(observation: AfrTradeObservation) -> str:
    values = observation.canonical_dict()
    missing = [concept for concept in TARGET_DIMENSIONS if values[concept] is None]
    if missing:
        raise ValueError(
            "Cannot identify incomplete AFR_TRADE observation; missing: "
            + ", ".join(missing)
        )
    return "|".join(f"{concept}={values[concept]}" for concept in TARGET_DIMENSIONS)


def identify_target_observation(
    observation: AfrTradeObservation,
) -> TargetObservationIdentity:
    """Hash target dimensions for identity and values/attributes for content."""

    target_key = build_target_key(observation)
    identity_input = f"AFRSTAT|AFR_TRADE|1.0|{target_key}"
    content = {
        "OBS_VALUE": observation.obs_value,
        **{
            concept: observation.canonical_dict()[concept]
            for concept in TARGET_ATTRIBUTES
        },
    }
    return TargetObservationIdentity(
        target_key=target_key,
        target_key_hash=hashlib.sha256(identity_input.encode("utf-8")).hexdigest(),
        target_content_hash=hashlib.sha256(
            canonical_json(content).encode("utf-8")
        ).hexdigest(),
    )

"""Deterministic identity and revision hashes for normalized observations."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from app.pipelines.trade_models import NormalizedTradeObservation


CONTENT_ATTRIBUTE_KEYS = frozenset(
    {
        "aggrLevel",
        "altQtyUnitCode",
        "isAggregate",
        "isAltQtyEstimated",
        "isGrossWgtEstimated",
        "isLeaf",
        "isNetWgtEstimated",
        "isOriginalClassification",
        "isQtyEstimated",
        "isReported",
        "legacyEstimationFlag",
        "qtyUnitCode",
    }
)


@dataclass(frozen=True)
class ObservationIdentity:
    source_key: str
    source_key_hash: str
    observation_content_hash: str


def build_dataset_identity(
    agency: str, dataflow_id: str, dataflow_version: str
) -> str:
    """Return ``agency|dataflow_id|version`` using the exact source identifiers."""
    components = (agency, dataflow_id, dataflow_version)
    if any(not component for component in components):
        raise ValueError("Dataset agency, dataflow ID, and version are required")
    if any("|" in component for component in components):
        raise ValueError("Dataset identity components cannot contain '|'")
    return "|".join(components)


def build_source_key(observation: NormalizedTradeObservation) -> str:
    """Serialize populated SDMX dimensions plus TIME_PERIOD in concept-ID order."""
    dimensions = {
        concept_id: value
        for concept_id, value in observation.source_dimensions.items()
        if concept_id != "TIME_PERIOD" and value is not None
    }
    if observation.time_period is None:
        raise ValueError("TIME_PERIOD is required to build observation identity")
    dimensions["TIME_PERIOD"] = observation.time_period

    components: list[str] = []
    for concept_id in sorted(dimensions):
        value = dimensions[concept_id]
        if "=" in concept_id or "|" in concept_id:
            raise ValueError(f"Invalid SDMX concept ID in source key: {concept_id!r}")
        if "|" in value:
            raise ValueError(
                f"SDMX dimension value for {concept_id!r} cannot contain '|'"
            )
        components.append(f"{concept_id}={value}")
    return "|".join(components)


def hash_source_key(dataset_identity: str, source_key: str) -> str:
    """SHA-256 ``dataset_identity + '|' + source_key`` as UTF-8."""
    canonical_input = f"{dataset_identity}|{source_key}"
    return hashlib.sha256(canonical_input.encode("utf-8")).hexdigest()


def canonical_decimal(value: Decimal) -> str:
    """Use numeric equivalence: 1, 1.0, and 1.00 canonicalize to ``"1"``."""
    if not value.is_finite():
        raise ValueError("Non-finite Decimal values cannot be hashed")
    if value.is_zero():
        return "0"
    return format(value.normalize(), "f")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite float values cannot be hashed")
        return canonical_decimal(Decimal(str(value)))
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported value in canonical JSON: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize JSON with recursively sorted keys and stable compact separators."""
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_observation_content(observation: NormalizedTradeObservation) -> str:
    """Build canonical JSON for revision-sensitive values and attributes.

    Source fields and labels are retained in warehouse storage but are excluded
    here. Relevant unit, aggregation, and reported/estimated attributes are
    included because they affect statistical interpretation.
    """
    content = {
        "statistical_values": {
            "cif_value": observation.cif_value,
            "fob_value": observation.fob_value,
            "gross_weight": observation.gross_weight,
            "net_weight": observation.net_weight,
            "primary_value": observation.primary_value,
            "quantity": observation.quantity,
        },
        "source_attributes": {
            key: value
            for key, value in observation.source_attributes.items()
            if key in CONTENT_ATTRIBUTE_KEYS
        },
    }
    return canonical_json(content)


def hash_observation_content(observation: NormalizedTradeObservation) -> str:
    """Hash canonical statistical values and observation attributes as UTF-8."""
    content = build_observation_content(observation)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def identify_observation(
    observation: NormalizedTradeObservation,
    *,
    dataset_identity: str | None = None,
) -> ObservationIdentity:
    """Build all persisted identity fields for one normalized observation."""
    if dataset_identity is None:
        if observation.source_dataflow is None or observation.source_dataflow_version is None:
            raise ValueError("Normalized observation has no complete dataset identity")
        dataset_identity = build_dataset_identity(
            observation.source_agency,
            observation.source_dataflow,
            observation.source_dataflow_version,
        )
    source_key = build_source_key(observation)
    return ObservationIdentity(
        source_key=source_key,
        source_key_hash=hash_source_key(dataset_identity, source_key),
        observation_content_hash=hash_observation_content(observation),
    )

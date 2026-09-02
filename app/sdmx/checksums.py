"""Canonical checksums for UN Comtrade JSON response envelopes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


JsonValue = Mapping[str, Any] | Sequence[Any] | str | bytes


def _as_json(value: JsonValue) -> Any:
    if isinstance(value, bytes):
        return json.loads(value.decode("utf-8"))
    if isinstance(value, str):
        return json.loads(value)
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def raw_response_checksum(response: JsonValue) -> str:
    """Hash the complete JSON response after deterministic canonicalization."""
    return hashlib.sha256(_canonical_json_bytes(_as_json(response))).hexdigest()


def statistical_content_checksum(
    response: JsonValue,
    *,
    observation_container: str = "data",
) -> str:
    """Hash only statistical records, independent of envelope and record order.

    ``count``, ``elapsedTime``, ``error``, and any future top-level fields are API
    envelope metadata. No fields inside an observation record are removed.
    """
    payload = _as_json(response)
    if not isinstance(payload, Mapping):
        raise TypeError("The Comtrade response must be a JSON object")
    if observation_container not in payload:
        raise KeyError(f"Missing observation container: {observation_container}")
    records = payload[observation_container]
    if not isinstance(records, list) or not all(
        isinstance(record, Mapping) for record in records
    ):
        raise TypeError(
            f"The {observation_container!r} observation container must be a list "
            "of JSON objects"
        )

    # The response array is a collection of records. Sorting each complete,
    # canonical record prevents provider result ordering from changing the hash,
    # while preserving every value and every nested structure within each record.
    canonical_records = sorted(_canonical_json_bytes(record) for record in records)
    canonical_content = b"[" + b",".join(canonical_records) + b"]"
    return hashlib.sha256(canonical_content).hexdigest()

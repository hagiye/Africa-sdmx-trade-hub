"""Generic parser for UN Comtrade JSON statistical observations."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from app.sdmx.checksums import raw_response_checksum, statistical_content_checksum
from app.sdmx.comtrade_field_mapping import (
    COMTRADE_ATTRIBUTE_FIELDS,
    COMTRADE_DIMENSION_RULES,
    COMTRADE_OBSERVATION_CONTAINER,
    COMTRADE_STATISTICAL_VALUE_FIELDS,
)
from app.sdmx.data_models import ParsedDataResponse, ParsedObservation
from app.sdmx.exceptions import ComtradeDataParseError


DEFAULT_PROVIDER = "UN Comtrade / UNSD"
DEFAULT_DATAFLOW_AGENCY = "UNSD"
DEFAULT_DATAFLOW_ID = "IMTS_A"
DEFAULT_DATAFLOW_VERSION = "1.0"


def parse_decimal(value: object) -> Decimal | None:
    """Convert one provider numeric value to a finite Decimal."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ComtradeDataParseError(
            f"Boolean is not a valid statistical numeric value: {value!r}"
        )
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(str(value))
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            result = Decimal(stripped)
        except InvalidOperation as exc:
            raise ComtradeDataParseError(
                f"Invalid statistical numeric value: {value!r}"
            ) from exc
    else:
        raise ComtradeDataParseError(
            f"Unsupported statistical numeric type {type(value).__name__}: {value!r}"
        )
    if not result.is_finite():
        raise ComtradeDataParseError(
            f"Statistical numeric value must be finite: {value!r}"
        )
    return result


def _dimension_value(record: Mapping[str, object], rule: Mapping[str, Any]) -> str | None:
    source_fields = rule["source_fields"]
    if not all(field in record and record[field] is not None for field in source_fields):
        return None
    source_values = tuple(str(record[field]) for field in source_fields)
    kind = rule["kind"]
    if kind == "direct":
        return source_values[0]
    if kind == "lookup":
        return rule["translations"].get(source_values[0])
    if kind == "composite_lookup":
        return rule["translations"].get(source_values)
    raise ComtradeDataParseError(f"Unsupported declarative dimension rule: {kind!r}")


def _parse_record(
    record: Mapping[str, object],
    index: int,
    *,
    dataflow_agency: str | None,
    dataflow_id: str | None,
    dataflow_version: str | None,
    source: str,
) -> ParsedObservation:
    dimensions = {}
    for concept, rule in COMTRADE_DIMENSION_RULES.items():
        value = _dimension_value(record, rule)
        if value is not None:
            dimensions[concept] = value

    time_value = record.get("period")
    time_period = None if time_value is None else str(time_value)

    values: dict[str, Decimal | None] = {}
    for field in COMTRADE_STATISTICAL_VALUE_FIELDS:
        if field not in record:
            continue
        try:
            values[field] = parse_decimal(record[field])
        except ComtradeDataParseError as exc:
            raise ComtradeDataParseError(
                f"Invalid value for record {index} field {field!r}: {exc}"
            ) from exc

    attributes = {
        field: copy.deepcopy(record[field])
        for field in COMTRADE_ATTRIBUTE_FIELDS
        if field in record
    }
    return ParsedObservation(
        dataflow_agency=dataflow_agency,
        dataflow_id=dataflow_id,
        dataflow_version=dataflow_version,
        dimension_values=dimensions,
        time_period=time_period,
        observation_values=values,
        attributes=attributes,
        source_fields=copy.deepcopy(dict(record)),
        source_record_index=index,
        source=source,
    )


def parse_comtrade_response(
    response: object,
    *,
    provider: str = DEFAULT_PROVIDER,
    dataflow_agency: str | None = DEFAULT_DATAFLOW_AGENCY,
    dataflow_id: str | None = DEFAULT_DATAFLOW_ID,
    dataflow_version: str | None = DEFAULT_DATAFLOW_VERSION,
) -> ParsedDataResponse:
    """Parse one already-decoded Comtrade response without database access."""
    if not isinstance(response, Mapping):
        raise ComtradeDataParseError(
            f"Comtrade response must be a JSON object, got {type(response).__name__}"
        )
    if COMTRADE_OBSERVATION_CONTAINER not in response:
        raise ComtradeDataParseError(
            f"Comtrade response is missing the "
            f"{COMTRADE_OBSERVATION_CONTAINER!r} observation container"
        )
    records = response[COMTRADE_OBSERVATION_CONTAINER]
    if not isinstance(records, list):
        raise ComtradeDataParseError(
            f"Comtrade {COMTRADE_OBSERVATION_CONTAINER!r} observation container "
            f"must be a list, got {type(records).__name__}"
        )
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ComtradeDataParseError(
                f"Comtrade observation at index {index} must be an object, "
                f"got {type(record).__name__}"
            )

    try:
        raw_checksum = raw_response_checksum(response)
        content_checksum = statistical_content_checksum(
            response, observation_container=COMTRADE_OBSERVATION_CONTAINER
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ComtradeDataParseError(
            f"Comtrade response cannot be checksummed: {exc}"
        ) from exc

    observations = [
        _parse_record(
            record,
            index,
            dataflow_agency=dataflow_agency,
            dataflow_id=dataflow_id,
            dataflow_version=dataflow_version,
            source=provider,
        )
        for index, record in enumerate(records)
    ]
    envelope = {
        field: copy.deepcopy(value)
        for field, value in response.items()
        if field != COMTRADE_OBSERVATION_CONTAINER
    }
    return ParsedDataResponse(
        provider=provider,
        dataflow_agency=dataflow_agency,
        dataflow_id=dataflow_id,
        dataflow_version=dataflow_version,
        observations=observations,
        record_count=len(observations),
        envelope_metadata=envelope,
        raw_response_checksum=raw_checksum,
        statistical_content_checksum=content_checksum,
    )


def canonical_dimension_key(observation: ParsedObservation) -> str:
    """Serialize populated dimensions and time deterministically, without hashing."""
    components = {
        concept: value
        for concept, value in observation.dimension_values.items()
        if value is not None
    }
    if observation.time_period is not None:
        components["TIME_PERIOD"] = observation.time_period
    return "|".join(
        f"{concept}={components[concept]}" for concept in sorted(components)
    )

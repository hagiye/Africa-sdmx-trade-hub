"""Offline tests for the generic UN Comtrade observation parser."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.sdmx.data_parser import (
    canonical_dimension_key,
    parse_comtrade_response,
    parse_decimal,
)
from app.sdmx.exceptions import ComtradeDataParseError


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "data"
FIXTURE_PATHS = sorted(
    FIXTURE_DIRECTORY.glob("un_comtrade_tunisia_imports_world_20*.json")
)
EXPECTED_PRIMARY_VALUES = {
    "2022": Decimal("26672667450.171"),
    "2023": Decimal("25930493874.99"),
    "2024": Decimal("26065070572.389"),
}
EXPECTED_DIMENSIONS = {
    "FREQ": "A",
    "REF_AREA": "TN",
    "TRADE_FLOW": "M",
    "COMMODITY_1": "SITC4_TOTAL",
    "COUNTERPART_AREA_1": "W0",
    "COUNTERPART_AREA_2": "W0",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda path: path.stem[-4:])
def test_each_real_fixture_parses_one_observation(fixture_path: Path) -> None:
    payload = _load(fixture_path)
    parsed = parse_comtrade_response(payload)
    observation = parsed.observations[0]
    period = payload["data"][0]["period"]

    assert parsed.record_count == len(parsed.observations) == 1
    assert observation.time_period == period
    assert isinstance(observation.time_period, str)
    assert observation.dimension_values == EXPECTED_DIMENSIONS
    assert observation.get_primary_value() == EXPECTED_PRIMARY_VALUES[period]
    assert isinstance(observation.get_primary_value(), Decimal)


def test_three_real_fixtures_produce_exactly_three_observations() -> None:
    responses = [parse_comtrade_response(_load(path)) for path in FIXTURE_PATHS]
    observations = [item for response in responses for item in response.observations]

    assert len(observations) == 3
    assert [observation.time_period for observation in observations] == [
        "2022",
        "2023",
        "2024",
    ]


def test_statistical_values_use_decimal_and_preserve_null() -> None:
    observations = [
        parse_comtrade_response(_load(path)).observations[0]
        for path in FIXTURE_PATHS
    ]
    expected_value_fields = {
        "altQty",
        "cifvalue",
        "fobvalue",
        "grossWgt",
        "netWgt",
        "primaryValue",
        "qty",
    }

    assert all(set(item.observation_values) == expected_value_fields for item in observations)
    assert all(item.observation_values["fobvalue"] is None for item in observations)
    assert observations[2].observation_values["netWgt"] is None
    assert all(
        value is None or isinstance(value, Decimal)
        for item in observations
        for value in item.observation_values.values()
    )


def test_attributes_and_complete_original_source_record_are_preserved() -> None:
    payload = _load(FIXTURE_PATHS[0])
    source_record = payload["data"][0]
    observation = parse_comtrade_response(payload).observations[0]

    assert observation.source_fields == source_record
    assert observation.source_fields is not source_record
    assert observation.attributes["aggrLevel"] == 0
    assert observation.attributes["isAggregate"] is True
    assert observation.attributes["qtyUnitAbbr"] == "N/A"
    assert observation.attributes["reporterDesc"] == "Tunisia"
    assert observation.attributes["partnerDesc"] == "World"
    assert observation.attributes["cmdDesc"] == "All Commodities"
    # Explicitly unresolved fields remain auditable rather than disappearing.
    assert observation.source_fields["mosCode"] == "0"
    assert observation.source_fields["typeCode"] == "C"
    assert "elapsedTime" not in observation.source_fields


def test_response_identity_envelope_and_checksums_are_preserved() -> None:
    payload = _load(FIXTURE_PATHS[0])
    first = parse_comtrade_response(payload)
    second = parse_comtrade_response(copy.deepcopy(payload))

    assert (first.dataflow_agency, first.dataflow_id, first.dataflow_version) == (
        "UNSD",
        "IMTS_A",
        "1.0",
    )
    assert first.envelope_metadata == {
        "count": 1,
        "elapsedTime": "0.05 secs",
        "error": "",
    }
    assert first.raw_response_checksum == second.raw_response_checksum
    assert first.statistical_content_checksum == second.statistical_content_checksum


def test_synthetic_multi_record_response_preserves_order_and_associations() -> None:
    """The two-record response is synthetic and derived from the real schema."""
    payload = _load(FIXTURE_PATHS[0])
    second_record = copy.deepcopy(payload["data"][0])
    second_record["period"] = "2023"
    second_record["refYear"] = 2023
    second_record["refPeriodId"] = 20230101
    second_record["primaryValue"] = 12.5
    second_record["cifvalue"] = 12.5
    payload["data"].append(second_record)
    payload["count"] = 2

    parsed = parse_comtrade_response(payload)

    assert parsed.record_count == 2
    assert [item.source_record_index for item in parsed.observations] == [0, 1]
    assert [item.time_period for item in parsed.observations] == ["2022", "2023"]
    assert [item.get_primary_value() for item in parsed.observations] == [
        Decimal("26672667450.171"),
        Decimal("12.5"),
    ]
    assert all(item.dimension_values == EXPECTED_DIMENSIONS for item in parsed.observations)


def test_missing_optional_fields_remain_absent() -> None:
    payload = _load(FIXTURE_PATHS[0])
    record = payload["data"][0]
    del record["fobvalue"]
    del record["cmdDesc"]
    del record["isAggregate"]

    observation = parse_comtrade_response(payload).observations[0]

    assert "fobvalue" not in observation.observation_values
    assert "cmdDesc" not in observation.attributes
    assert "isAggregate" not in observation.attributes
    assert "fobvalue" not in observation.source_fields
    assert observation.dimension_values["COMMODITY_1"] == "SITC4_TOTAL"


def test_missing_untranslated_dimension_source_does_not_create_fake_dimension() -> None:
    payload = _load(FIXTURE_PATHS[0])
    del payload["data"][0]["partner2Code"]

    observation = parse_comtrade_response(payload).observations[0]

    assert "COUNTERPART_AREA_2" not in observation.dimension_values
    assert "partner2Code" not in observation.source_fields


def test_empty_synthetic_dataset_is_valid() -> None:
    payload = {"count": 0, "data": [], "elapsedTime": "0.01 secs", "error": ""}

    parsed = parse_comtrade_response(payload)

    assert parsed.observations == []
    assert parsed.record_count == 0


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "must be a JSON object"),
        ({"count": 0}, "missing the 'data' observation container"),
        ({"data": {}}, "observation container must be a list"),
        ({"data": ["not an object"]}, "observation at index 0 must be an object"),
    ],
)
def test_malformed_response_has_meaningful_error(payload: object, message: str) -> None:
    with pytest.raises(ComtradeDataParseError, match=message):
        parse_comtrade_response(payload)


def test_invalid_numeric_field_has_record_and_field_context() -> None:
    payload = _load(FIXTURE_PATHS[0])
    payload["data"][0]["primaryValue"] = "not numeric"

    with pytest.raises(
        ComtradeDataParseError,
        match="record 0 field 'primaryValue'",
    ):
        parse_comtrade_response(payload)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (42, Decimal("42")),
        (1.25, Decimal("1.25")),
        ("123.450", Decimal("123.450")),
        ("  ", None),
        (Decimal("9.1"), Decimal("9.1")),
    ],
)
def test_parse_decimal(value: object, expected: Decimal | None) -> None:
    assert parse_decimal(value) == expected


@pytest.mark.parametrize("value", ["invalid", True, object(), "NaN", float("inf")])
def test_parse_decimal_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ComtradeDataParseError):
        parse_decimal(value)


def test_canonical_dimension_key_is_deterministic() -> None:
    observation = parse_comtrade_response(_load(FIXTURE_PATHS[0])).observations[0]
    expected = (
        "COMMODITY_1=SITC4_TOTAL|COUNTERPART_AREA_1=W0|"
        "COUNTERPART_AREA_2=W0|FREQ=A|REF_AREA=TN|TIME_PERIOD=2022|TRADE_FLOW=M"
    )

    assert canonical_dimension_key(observation) == expected
    observation.dimension_values = dict(reversed(list(observation.dimension_values.items())))
    assert canonical_dimension_key(observation) == expected


def test_checksum_semantics_through_parser() -> None:
    payload = _load(FIXTURE_PATHS[2])
    envelope_changed = copy.deepcopy(payload)
    envelope_changed["elapsedTime"] = "99.99 secs"
    value_changed = copy.deepcopy(payload)
    value_changed["data"][0]["primaryValue"] += 1

    original = parse_comtrade_response(payload)
    envelope_result = parse_comtrade_response(envelope_changed)
    value_result = parse_comtrade_response(value_changed)

    assert original.raw_response_checksum != envelope_result.raw_response_checksum
    assert (
        original.statistical_content_checksum
        == envelope_result.statistical_content_checksum
    )
    assert original.statistical_content_checksum != value_result.statistical_content_checksum

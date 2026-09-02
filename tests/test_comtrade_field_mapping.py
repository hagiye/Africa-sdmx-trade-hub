"""Offline checks for the real Comtrade field inventory and SDMX mapping."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from lxml import etree

from app.sdmx.checksums import raw_response_checksum, statistical_content_checksum
from app.sdmx.comtrade_field_mapping import (
    COMTRADE_JSON_TO_SDMX,
    DSD_DIMENSIONS,
    NOT_EXPOSED_DSD_DIMENSIONS,
    UNMAPPED_COMTRADE_FIELDS,
    WORLD_PARTNER_CLASSIFICATION,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
FIXTURE_PATHS = sorted(
    FIXTURE_DIRECTORY.glob("un_comtrade_tunisia_imports_world_20*.json")
)
INVENTORY_PATH = ROOT / "data" / "discovery" / "comtrade_trade_record_fields.json"
DSD_PATH = ROOT / "structures" / "raw" / "UNSD_datastructure_IMTS_1.2.xml"


def _fixtures() -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in FIXTURE_PATHS]


def _real_dsd_concepts() -> set[str]:
    root = etree.parse(str(DSD_PATH))
    component_names = {"Dimension", "TimeDimension", "Attribute", "Measure"}
    return {
        element.get("id")
        for element in root.iter()
        if etree.QName(element).localname in component_names and element.get("id")
    }


def test_all_three_fixtures_load_with_observation_container() -> None:
    payloads = _fixtures()
    assert len(payloads) == 3
    assert [payload["data"][0]["period"] for payload in payloads] == [
        "2022",
        "2023",
        "2024",
    ]
    assert all(isinstance(payload["data"], list) for payload in payloads)
    assert all(len(payload["data"]) == 1 for payload in payloads)


def test_real_fields_are_inventoried_and_declaratively_mapped() -> None:
    records = [payload["data"][0] for payload in _fixtures()]
    actual_fields = set().union(*(set(record) for record in records))
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    inventory_fields = {field["name"] for field in inventory["all_observed_fields"]}

    assert actual_fields == inventory_fields == set(COMTRADE_JSON_TO_SDMX)
    assert UNMAPPED_COMTRADE_FIELDS
    assert all(
        COMTRADE_JSON_TO_SDMX[field]["concept"] is None
        or COMTRADE_JSON_TO_SDMX[field]["relationship"] == "UNKNOWN"
        for field in UNMAPPED_COMTRADE_FIELDS
    )


def test_mapping_references_only_concepts_in_real_dsd() -> None:
    real_concepts = _real_dsd_concepts()
    mapped_concepts = {
        metadata["concept"]
        for metadata in COMTRADE_JSON_TO_SDMX.values()
        if metadata["concept"] is not None
    }
    confirmed_concepts = {
        metadata["concept"]
        for metadata in COMTRADE_JSON_TO_SDMX.values()
        if metadata["confidence"] == "CONFIRMED"
    }

    assert mapped_concepts <= real_concepts
    assert confirmed_concepts <= real_concepts
    assert tuple(DSD_DIMENSIONS) == (
        "FREQ", "REF_AREA", "TRADE_FLOW", "COMMODITY_1",
        "COMMODITY_1_CONF", "COMMODITY_2", "COMMODITY_2_CONF",
        "COMMODITY_CUSTOM_BREAKDOWN", "COUNTERPART_AREA_1",
        "COUNTERPART_AREA_1_CONF", "COUNTERPART_AREA_2",
        "COUNTERPART_AREA_2_CONF", "TRANSPORT_MODE_BORDER",
        "TRANSPORT_MODE_BORDER_CONF", "CUSTOMS_PROC", "ACTIVITY",
        "TRANSFORMATION", "MEASURE", "TIME_PERIOD",
    )


def test_evidence_supported_core_dimension_mappings_exist() -> None:
    expected = {
        "reporterCode": "REF_AREA",
        "flowCode": "TRADE_FLOW",
        "period": "TIME_PERIOD",
        "partnerCode": "COUNTERPART_AREA_1",
        "partner2Code": "COUNTERPART_AREA_2",
    }
    assert {
        field: COMTRADE_JSON_TO_SDMX[field]["concept"] for field in expected
    } == expected
    assert "MEASURE" in NOT_EXPOSED_DSD_DIMENSIONS
    assert COMTRADE_JSON_TO_SDMX["primaryValue"]["concept"] == "OBS_VALUE"


def test_world_partner_is_an_aggregate_not_a_country() -> None:
    for payload in _fixtures():
        record = payload["data"][0]
        assert record["partnerCode"] == record["partner2Code"] == 0
        assert record["partnerDesc"] == record["partner2Desc"] == "World"
    assert WORLD_PARTNER_CLASSIFICATION["area_type"] == "AGGREGATE"
    assert WORLD_PARTNER_CLASSIFICATION["is_country"] is False


def test_statistical_content_checksum_is_deterministic_and_order_independent() -> None:
    payload = _fixtures()[0]
    reordered_record = dict(reversed(list(payload["data"][0].items())))
    reordered_payload = dict(reversed(list(payload.items())))
    reordered_payload["data"] = [reordered_record]

    first = statistical_content_checksum(payload)
    assert first == statistical_content_checksum(payload)
    assert first == statistical_content_checksum(reordered_payload)

    two_records = copy.deepcopy(payload)
    second = copy.deepcopy(two_records["data"][0])
    second["period"] = "2021"
    two_records["data"].append(second)
    reversed_records = copy.deepcopy(two_records)
    reversed_records["data"].reverse()
    assert statistical_content_checksum(two_records) == statistical_content_checksum(
        reversed_records
    )


def test_volatile_envelope_changes_only_raw_response_checksum() -> None:
    payload = _fixtures()[2]
    changed = copy.deepcopy(payload)
    changed["elapsedTime"] = "99.99 secs"

    assert raw_response_checksum(payload) != raw_response_checksum(changed)
    assert statistical_content_checksum(payload) == statistical_content_checksum(changed)


def test_statistical_value_change_changes_content_checksum() -> None:
    payload = _fixtures()[2]
    changed = copy.deepcopy(payload)
    changed["data"][0]["primaryValue"] += 1

    assert statistical_content_checksum(payload) != statistical_content_checksum(changed)

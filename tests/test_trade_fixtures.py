"""Offline integrity checks for the controlled real trade fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "data"
MANIFEST_PATH = (
    FIXTURE_DIRECTORY / "un_comtrade_tunisia_imports_world_manifest.json"
)
EXPECTED_PERIODS = [2022, 2023, 2024]


def test_trade_fixture_set_integrity() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["periods"] == EXPECTED_PERIODS
    assert len(manifest["fixtures"]) == len(EXPECTED_PERIODS)
    assert manifest["reporter"] == {
        "label": "Tunisia",
        "provider_code": "788",
        "source_code": "TN",
    }
    assert manifest["partner"] == {
        "area_type": "AGGREGATE",
        "label": "World",
        "provider_code": "0",
        "source_code": "W0",
    }

    total_observations = 0
    for entry in manifest["fixtures"]:
        period = entry["period"]
        assert period in EXPECTED_PERIODS

        fixture_path = FIXTURE_DIRECTORY / entry["file"]
        fixture_bytes = fixture_path.read_bytes()
        assert len(fixture_bytes) == entry["file_bytes"]
        assert hashlib.sha256(fixture_bytes).hexdigest() == entry["sha256"]

        payload = json.loads(fixture_bytes)
        records = payload["data"]
        assert isinstance(records, list)
        assert len(records) >= 1
        assert payload["count"] == len(records) == entry["record_count"]
        total_observations += len(records)

        for record in records:
            assert str(record["period"]) == str(period)
            assert record["reporterCode"] == 788
            assert record["reporterDesc"] == "Tunisia"
            assert record["partnerCode"] == 0
            assert record["partnerDesc"] == "World"
            assert record["flowCode"] == "M"
            assert record["flowDesc"] == "Import"

    assert total_observations == 3

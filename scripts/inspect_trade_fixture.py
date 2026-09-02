"""Inspect the controlled real UN Comtrade JSON fixtures without networking."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.sdmx.checksums import raw_response_checksum, statistical_content_checksum


FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
FIXTURE_PATTERN = "un_comtrade_tunisia_imports_world_20*.json"


def load_fixtures() -> list[tuple[Path, dict[str, Any]]]:
    fixtures = []
    for path in sorted(FIXTURE_DIRECTORY.glob(FIXTURE_PATTERN)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"Expected a top-level object in {path}")
        fixtures.append((path, payload))
    if not fixtures:
        raise FileNotFoundError(f"No fixtures matched {FIXTURE_PATTERN}")
    return fixtures


def find_observation_container(payload: dict[str, Any]) -> str:
    candidates = [
        name
        for name, value in payload.items()
        if isinstance(value, list)
        and (not value or all(isinstance(item, dict) for item in value))
    ]
    if len(candidates) != 1:
        raise ValueError(f"Expected one record-array field, found {candidates}")
    return candidates[0]


def _display(value: Any, limit: int = 38) -> str:
    rendered = repr(value)
    return rendered if len(rendered) <= limit else rendered[: limit - 3] + "..."


def main() -> int:
    fixtures = load_fixtures()
    records_by_period: dict[str, dict[str, Any]] = {}
    containers: set[str] = set()

    for path, payload in fixtures:
        container = find_observation_container(payload)
        containers.add(container)
        records = payload[container]
        period = str(records[0].get("period", "UNKNOWN")) if records else "UNKNOWN"
        print(f"\nFIXTURE: {path.name}")
        print(f"Period: {period}")
        print(f"Top-level JSON keys: {', '.join(sorted(payload))}")
        print(f"Observation container field: {container}")
        print(f"Number of observations: {len(records)}")
        if not records:
            continue
        record = records[0]
        records_by_period[period] = record
        print("\nJSON Field | Python Type | Example Value")
        print("--- | --- | ---")
        for field, value in sorted(record.items()):
            print(f"{field} | {type(value).__name__} | {_display(value)}")

    if len(containers) != 1:
        raise ValueError(f"Observation container differs across fixtures: {containers}")

    periods = sorted(records_by_period)
    all_fields = sorted(
        set().union(*(set(record) for record in records_by_period.values()))
    )
    common_fields = sorted(
        set.intersection(*(set(record) for record in records_by_period.values()))
    )
    missing = {
        field: [period for period in periods if field not in records_by_period[period]]
        for field in all_fields
        if any(field not in records_by_period[period] for period in periods)
    }
    null_fields = sorted(
        field
        for field in all_fields
        if any(records_by_period[period].get(field) is None for period in periods)
    )
    empty_fields = sorted(
        field
        for field in all_fields
        if any(records_by_period[period].get(field) == "" for period in periods)
    )
    nested_objects = sorted(
        field
        for field in all_fields
        if any(isinstance(records_by_period[p].get(field), dict) for p in periods)
    )
    nested_arrays = sorted(
        field
        for field in all_fields
        if any(isinstance(records_by_period[p].get(field), list) for p in periods)
    )
    types_by_field: dict[str, set[str]] = defaultdict(set)
    for field in all_fields:
        for period in periods:
            if field in records_by_period[period]:
                types_by_field[field].add(type(records_by_period[period][field]).__name__)
    varying_types = {
        field: sorted(types)
        for field, types in types_by_field.items()
        if len(types) > 1
    }

    print("\nCROSS-YEAR SUMMARY")
    print("Field | " + " | ".join(periods) + " | Types | Nullable")
    print("--- | " + " | ".join("---" for _ in periods) + " | --- | ---")
    for field in all_fields:
        examples = [
            _display(records_by_period[period].get(field, "<MISSING>"))
            for period in periods
        ]
        print(
            f"{field} | {' | '.join(examples)} | "
            f"{', '.join(sorted(types_by_field[field]))} | "
            f"{'yes' if field in null_fields else 'no'}"
        )

    print(f"\nFields present in all years ({len(common_fields)}): {', '.join(common_fields)}")
    print(f"Fields missing in some years: {missing or 'none'}")
    print(f"Fields containing null: {', '.join(null_fields) or 'none'}")
    print(f"Fields containing empty string: {', '.join(empty_fields) or 'none'}")
    print(f"Fields whose Python types differ: {varying_types or 'none'}")
    print(f"Nested objects: {', '.join(nested_objects) or 'none'}")
    print(f"Nested arrays: {', '.join(nested_arrays) or 'none'}")
    print("Unexpected structural differences: " + (str(varying_types) if varying_types else "none"))

    container = next(iter(containers))
    print("\nENVELOPE VS STATISTICAL CONTENT")
    print(f"Observation container: {container}")
    print(
        "API envelope fields: "
        + ", ".join(sorted(set(fixtures[0][1]) - {container}))
    )
    print("Statistical content: every complete object inside the observation container")
    for path, payload in fixtures:
        period = str(payload[container][0]["period"])
        print(
            f"{period}: raw_response_checksum={raw_response_checksum(payload)} "
            f"statistical_content_checksum={statistical_content_checksum(payload)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

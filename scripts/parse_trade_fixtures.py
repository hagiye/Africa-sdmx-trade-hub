"""Parse the three controlled real UN Comtrade fixtures offline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.sdmx.data_parser import parse_comtrade_response


FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
FIXTURE_PATTERN = "un_comtrade_tunisia_imports_world_20*.json"


def main() -> int:
    paths = sorted(FIXTURE_DIRECTORY.glob(FIXTURE_PATTERN))
    if not paths:
        raise FileNotFoundError(f"No fixtures matched {FIXTURE_PATTERN}")

    responses = [
        parse_comtrade_response(json.loads(path.read_text(encoding="utf-8")))
        for path in paths
    ]
    observations = [
        observation
        for response in responses
        for observation in response.observations
    ]

    print("Dataflow: UNSD:IMTS_A(1.0)")
    print("DSD: UNSD:IMTS(1.2)")
    print(f"Observations parsed: {len(observations)}")
    print("\nPeriod | REF_AREA | TRADE_FLOW | COUNTERPART_AREA_1 | COMMODITY_1 | Primary Value")
    print("--- | --- | --- | --- | --- | ---")
    for observation in observations:
        dimensions = observation.dimension_values
        print(
            f"{observation.time_period} | {dimensions.get('REF_AREA', '-')} | "
            f"{dimensions.get('TRADE_FLOW', '-')} | "
            f"{dimensions.get('COUNTERPART_AREA_1', '-')} | "
            f"{dimensions.get('COMMODITY_1', '-')} | "
            f"{observation.get_primary_value()}"
        )

    print("\nStatistical content checksums:")
    for observation, response in zip(observations, responses, strict=True):
        print(
            f"{observation.time_period}: {response.statistical_content_checksum}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

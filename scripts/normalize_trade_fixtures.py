"""Normalize the controlled real UN Comtrade fixtures without writing data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import SessionLocal
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.data_parser import parse_comtrade_response


FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
FIXTURE_PATTERN = "un_comtrade_tunisia_imports_world_20*.json"


def main() -> int:
    paths = sorted(FIXTURE_DIRECTORY.glob(FIXTURE_PATTERN))
    if not paths:
        raise FileNotFoundError(f"No fixtures matched {FIXTURE_PATTERN}")

    observations = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        observations.extend(parse_comtrade_response(payload).observations)

    with SessionLocal() as session:
        results = [
            normalize_trade_observation(observation, session)
            for observation in observations
        ]

    unresolved = [result for result in results if result.observation is None]
    if unresolved:
        messages = [
            issue.message
            for result in unresolved
            for issue in result.issues
            if issue.fatal
        ]
        raise RuntimeError("Fixture normalization failed: " + "; ".join(messages))

    print(
        "Period | Reporter | ISO3 | AU? | Partner | Partner Type | "
        "Flow | Commodity | Primary Value"
    )
    print("--- | --- | --- | --- | --- | --- | --- | --- | ---")
    for result in results:
        normalized = result.observation
        assert normalized is not None
        if result.issues:
            issue_codes = ", ".join(issue.code.value for issue in result.issues)
            raise RuntimeError(
                f"Fixture {normalized.time_period} has normalization issues: "
                f"{issue_codes}"
            )
        flow = normalized.trade_flow_label or normalized.trade_flow_code or "-"
        commodity = (
            f"{normalized.commodity_classification or '-'}:"
            f"{normalized.commodity_code or '-'}"
        )
        print(
            f"{normalized.time_period or '-'} | {normalized.reference_name} | "
            f"{normalized.reference_iso3 or '-'} | "
            f"{'Yes' if normalized.reference_is_au_member else 'No'} | "
            f"{normalized.counterpart_name or '-'} | "
            f"{normalized.counterpart_area_type.value if normalized.counterpart_area_type else '-'} | "
            f"{flow} | {commodity} | {normalized.primary_value}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Show the complete mapping trace for the controlled 2023 observation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import SessionLocal
from scripts.transform_trade_fixtures import transform_fixtures


def _display(value: object | None) -> str:
    return "-" if value is None else str(value)


def main() -> int:
    with SessionLocal() as session:
        result = next(
            row
            for row in transform_fixtures(session)
            if row.source_observation.time_period == "2023"
        )

    print("Source: UNSD:IMTS(1.2)")
    print("Target: AFRSTAT:AFR_TRADE(1.0)")
    print(f"Harmonization status: {result.status.value}")
    print("\nTarget Concept | Source Concept | Source Value | Target Value | Type | Status | Outcome")
    print("--- | --- | --- | --- | --- | --- | ---")
    for trace in result.mapping_results:
        print(
            f"{_display(trace.target_concept)} | {trace.source_concept} | "
            f"{_display(trace.source_value)} | {_display(trace.target_value)} | "
            f"{trace.mapping_type.value} | {trace.mapping_status.value} | "
            f"{trace.outcome}"
        )
    print(f"\nDropped source concepts: {', '.join(result.dropped_concepts)}")
    print(f"Deferred source concepts: {', '.join(result.deferred_concepts)}")
    print("Errors:")
    for issue in result.errors:
        print(f"- {issue.code.value}: {issue.message}")
    if result.target_validation:
        print(f"Target validation: {result.target_validation.status.value}")
        for finding in result.target_validation.findings:
            print(f"- {finding.concept_id}: {finding.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

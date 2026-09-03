"""Validate the three controlled real trade fixtures without network or writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.data_parser import parse_comtrade_response
from app.validation.context import ValidationContext
from app.validation.engine import ValidationEngine, get_trade_validation_rules


FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
FIXTURE_PATTERN = "un_comtrade_tunisia_imports_world_20*.json"


def main() -> int:
    paths = sorted(FIXTURE_DIRECTORY.glob(FIXTURE_PATTERN))
    if not paths:
        raise FileNotFoundError(f"No fixtures matched {FIXTURE_PATTERN}")

    with SessionLocal() as session:
        dataset = session.scalar(
            select(db.StatDataset).where(
                db.StatDataset.agency == "UNSD",
                db.StatDataset.dataflow_id == "IMTS_A",
                db.StatDataset.dataflow_version == "1.0",
            )
        )
        if dataset is None:
            raise RuntimeError("Seed UNSD:IMTS_A(1.0) before validation")
        context = ValidationContext.from_session(session, dataset)
        engine = ValidationEngine(get_trade_validation_rules())
        rows = []
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            parsed = parse_comtrade_response(payload).observations[0]
            normalized = normalize_trade_observation(parsed, session).observation
            if normalized is None:
                raise RuntimeError(f"Normalizer returned no candidate for {path.name}")
            summary = engine.validate(normalized, context)
            rows.append((normalized, summary))

    print("Period | Reporter | Partner | Validation Status | Warnings | Errors")
    print("--- | --- | --- | --- | ---: | ---:")
    for observation, summary in rows:
        status = "REJECT" if summary.should_reject else "ACCEPT"
        print(
            f"{observation.time_period or '-'} | "
            f"{observation.reference_name or observation.reference_area_source_code or '-'} | "
            f"{observation.counterpart_name or observation.counterpart_area_source_code or '-'} | "
            f"{status} | {summary.warning_count} | "
            f"{summary.error_count + summary.fatal_count}"
        )

    accepted = sum(not summary.should_reject for _, summary in rows)
    rejected = len(rows) - accepted
    warnings = sum(summary.warning_count for _, summary in rows)
    errors = sum(
        summary.error_count + summary.fatal_count for _, summary in rows
    )
    print("\nSummary")
    print(f"Observations validated: {len(rows)}")
    print(f"Accepted: {accepted}")
    print(f"Rejected: {rejected}")
    print(f"Warnings: {warnings}")
    print(f"Errors: {errors}")
    return 0 if rejected == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

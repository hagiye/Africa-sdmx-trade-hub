"""Run the three controlled fixtures through both validation stages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal
from app.harmonization.afr_trade_transformer import transform_to_afr_trade
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.data_parser import parse_comtrade_response
from app.validation.context import ValidationContext
from app.validation.engine import ValidationEngine, get_trade_validation_rules


FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
FIXTURE_PATTERN = "un_comtrade_tunisia_imports_world_20*.json"


def transform_fixtures(session) -> list:
    dataset = session.scalar(
        select(db.StatDataset).where(
            db.StatDataset.agency == "UNSD",
            db.StatDataset.dataflow_id == "IMTS_A",
            db.StatDataset.dataflow_version == "1.0",
        )
    )
    if dataset is None:
        raise RuntimeError("Seed UNSD:IMTS_A(1.0) before harmonization")
    context = ValidationContext.from_session(session, dataset)
    engine = ValidationEngine(get_trade_validation_rules())
    results = []
    for path in sorted(FIXTURE_DIRECTORY.glob(FIXTURE_PATTERN)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_comtrade_response(payload).observations[0]
        normalized = normalize_trade_observation(parsed, session).observation
        if normalized is None:
            raise RuntimeError(f"Normalizer returned no candidate for {path.name}")
        source_validation = engine.validate(normalized, context)
        results.append(
            transform_to_afr_trade(
                normalized,
                session,
                source_validation=source_validation,
            )
        )
    return results


def main() -> int:
    with SessionLocal() as session:
        results = transform_fixtures(session)

    print(
        "Source Period | Source Reporter | Target REF_AREA | Target Counterpart | "
        "Target Flow | Target Product | Target Unit | Target OBS_VALUE | "
        "Target Validation Status"
    )
    print("--- | --- | --- | --- | --- | --- | --- | ---: | ---")
    for result in results:
        target = result.target_observation
        validation = result.target_validation
        print(
            f"{result.source_observation.time_period or '-'} | "
            f"{result.source_observation.reference_name or '-'} | "
            f"{target.ref_area if target else '-'} | "
            f"{target.counterpart_area if target else '-'} | "
            f"{target.trade_flow if target else '-'} | "
            f"{target.product if target else '-'} | "
            f"{target.unit_measure if target and target.unit_measure else 'DEFERRED'} | "
            f"{target.obs_value if target else '-'} | "
            f"{validation.status.value if validation else 'NOT_RUN'} "
            f"({result.status.value})"
        )
    print("\nSummary")
    for status in ("SUCCESS", "PARTIAL", "FAILED"):
        print(f"{status}: {sum(row.status.value == status for row in results)}")
    print(
        "Known target blockers: UNIT_MEASURE and UNIT_MULT are DRAFT/DEFER; "
        "SOURCE has no registry mapping."
    )
    return 1 if any(result.status.value == "FAILED" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

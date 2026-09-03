"""Build identities for the three controlled fixtures without persistence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.models import StatDataset
from app.database.session import SessionLocal
from app.pipelines.observation_identity import (
    build_dataset_identity,
    identify_observation,
)
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.data_parser import parse_comtrade_response


FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
FIXTURE_PATTERN = "un_comtrade_tunisia_imports_world_20*.json"


def main() -> int:
    paths = sorted(FIXTURE_DIRECTORY.glob(FIXTURE_PATTERN))
    if len(paths) != 3:
        raise RuntimeError(f"Expected three trade fixtures, found {len(paths)}")

    with SessionLocal() as session:
        dataset = session.scalar(
            select(StatDataset).where(
                StatDataset.agency == "UNSD",
                StatDataset.dataflow_id == "IMTS_A",
                StatDataset.dataflow_version == "1.0",
            )
        )
        if dataset is None:
            raise RuntimeError("Seed UNSD:IMTS_A(1.0) before building identities")
        dataset_identity = build_dataset_identity(
            dataset.agency, dataset.dataflow_id, dataset.dataflow_version
        )

        rows = []
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            parsed = parse_comtrade_response(payload).observations
            if len(parsed) != 1:
                raise RuntimeError(f"Expected one observation in {path.name}")
            result = normalize_trade_observation(parsed[0], session)
            if result.observation is None or result.issues:
                messages = "; ".join(issue.message for issue in result.issues)
                raise RuntimeError(f"Could not normalize {path.name}: {messages}")
            observation = result.observation
            identity = identify_observation(
                observation, dataset_identity=dataset_identity
            )
            rows.append((observation, identity))

    for observation, identity in rows:
        print(f"Period: {observation.time_period}")
        print(
            "Reporter: "
            f"{observation.reference_area_source_code} ({observation.reference_name})"
        )
        print(
            "Partner: "
            f"{observation.counterpart_area_source_code} "
            f"({observation.counterpart_name or 'unmapped'})"
        )
        print(f"Flow: {observation.trade_flow_code}")
        print(f"Source Key: {identity.source_key}")
        print(f"Source Key Hash: {identity.source_key_hash}")
        print(f"Observation Content Hash: {identity.observation_content_hash}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

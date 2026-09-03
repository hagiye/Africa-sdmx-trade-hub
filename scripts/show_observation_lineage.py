"""Show source and batch lineage for the 2023 AFR_TRADE observation."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal


def main() -> int:
    with SessionLocal() as session:
        target = session.scalar(
            select(db.AfrTradeObservation)
            .where(db.AfrTradeObservation.time_period == "2023")
            .limit(1)
        )
        if target is None:
            rejection = session.scalar(
                select(db.HarmonizationRejection)
                .join(db.TradeObservation)
                .where(db.TradeObservation.time_period == "2023")
                .order_by(db.HarmonizationRejection.id.desc())
                .limit(1)
            )
            print("No target-valid 2023 observation is persisted.")
            if rejection:
                print(
                    "Latest governed lineage ends in rejection: "
                    f"source observation {rejection.source_trade_observation_id} -> "
                    f"harmonization batch {rejection.harmonization_batch_id} -> "
                    f"{rejection.reason_code.value}"
                )
            return 0
        source = session.get(db.TradeObservation, target.source_trade_observation_id)
        print("TARGET: AFRSTAT:AFR_TRADE(1.0)")
        print(f"Target observation: {target.id} ({target.target_key_hash})")
        print(
            "Target values: "
            f"{target.ref_area}/{target.counterpart_area}/{target.trade_flow}/"
            f"{target.product}/{target.unit_measure}/{target.time_period} = "
            f"{target.obs_value}"
        )
        print(f"Last harmonization batch: {target.last_harmonization_batch_id}")
        print(f"Mapping: {target.mapping_definition_id}({target.mapping_version})")
        print(f"Source observation: {source.id} ({source.source_key_hash})")
        print(f"UNSD dimensions: {source.source_dimensions}")
        print(f"Source ingestion batch: {source.last_ingestion_batch_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

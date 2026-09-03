"""Inspect the persisted AFR_TRADE statistical warehouse."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal


def main() -> int:
    with SessionLocal() as session:
        count, reporters, counterparts, first, last = session.execute(
            select(
                func.count(db.AfrTradeObservation.id),
                func.count(func.distinct(db.AfrTradeObservation.ref_area)),
                func.count(func.distinct(db.AfrTradeObservation.counterpart_area)),
                func.min(db.AfrTradeObservation.time_period),
                func.max(db.AfrTradeObservation.time_period),
            )
        ).one()
        batches = session.scalar(
            select(func.count()).select_from(db.HarmonizationBatch)
        )
        rejections = session.scalar(
            select(func.count()).select_from(db.HarmonizationRejection)
        )
        duplicate_groups = session.scalar(
            select(func.count()).select_from(
                select(db.AfrTradeObservation.target_key_hash)
                .group_by(
                    db.AfrTradeObservation.target_dataset_id,
                    db.AfrTradeObservation.target_key_hash,
                )
                .having(func.count() > 1)
                .subquery()
            )
        )
        print("Target: AFRSTAT:AFR_TRADE(1.0)")
        print(f"Observations: {count}")
        print(f"Reporters: {reporters}")
        print(f"Counterparts: {counterparts}")
        print(f"Period range: {first or '-'} to {last or '-'}")
        print(f"Harmonization batches: {batches}")
        print(f"Rejections: {rejections}")
        print(f"Duplicate target-key groups: {duplicate_groups}")
        rows = session.scalars(
            select(db.AfrTradeObservation).order_by(
                db.AfrTradeObservation.time_period,
                db.AfrTradeObservation.id,
            )
        )
        print("\nPeriod | REF_AREA | Counterpart | Flow | Product | Unit | OBS_VALUE")
        print("--- | --- | --- | --- | --- | --- | ---")
        for row in rows:
            print(
                f"{row.time_period} | {row.ref_area} | {row.counterpart_area} | "
                f"{row.trade_flow} | {row.product} | {row.unit_measure} | "
                f"{row.obs_value}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

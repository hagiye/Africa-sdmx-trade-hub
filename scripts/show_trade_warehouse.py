"""Show the bounded trade warehouse and its latest ingestion batch."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import aliased

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal


def main() -> int:
    reference = aliased(db.GeoArea)
    counterpart = aliased(db.GeoArea)
    with SessionLocal() as session:
        dataset = session.scalar(select(db.StatDataset).order_by(db.StatDataset.id))
        if dataset is None:
            print("No statistical dataset is seeded")
            return 0
        scope = db.TradeObservation.dataset_id == dataset.id
        observation_count = session.scalar(
            select(func.count()).select_from(db.TradeObservation).where(scope)
        ) or 0
        au_reporter_count = session.scalar(
            select(func.count(distinct(db.TradeObservation.reference_geo_id)))
            .join(reference, db.TradeObservation.reference_geo_id == reference.id)
            .where(scope, reference.au_member.is_(True))
        ) or 0
        counterpart_count = session.scalar(
            select(func.count(distinct(db.TradeObservation.counterpart_geo_id))).where(
                scope, db.TradeObservation.counterpart_geo_id.is_not(None)
            )
        ) or 0
        earliest, latest = session.execute(
            select(
                func.min(db.TradeObservation.time_period),
                func.max(db.TradeObservation.time_period),
            ).where(scope)
        ).one()
        rows = session.execute(
            select(db.TradeObservation, reference, counterpart)
            .join(reference, db.TradeObservation.reference_geo_id == reference.id)
            .outerjoin(
                counterpart,
                db.TradeObservation.counterpart_geo_id == counterpart.id,
            )
            .where(scope)
            .order_by(db.TradeObservation.time_period)
        ).all()
        batch = session.scalar(
            select(db.IngestionBatch)
            .where(db.IngestionBatch.dataset_id == dataset.id)
            .order_by(db.IngestionBatch.id.desc())
        )

        print(
            f"Dataset: {dataset.agency}:{dataset.dataflow_id}"
            f"({dataset.dataflow_version}) - {dataset.name}"
        )
        print(f"Observation count: {observation_count}")
        print(f"AU reporter count: {au_reporter_count}")
        print(f"Counterpart count: {counterpart_count}")
        print(f"Earliest period: {earliest or '-'}")
        print(f"Latest period: {latest or '-'}")
        print("\nPeriod | Reporter | ISO3 | Counterpart | Type | Flow | Commodity | Primary Value")
        for observation, reporter, partner in rows:
            commodity = (
                f"{observation.commodity_classification or '-'}:"
                f"{observation.commodity_code or '-'}"
            )
            print(
                f"{observation.time_period or '-'} | {reporter.name_en} | "
                f"{reporter.iso3 or '-'} | "
                f"{partner.name_en if partner else observation.counterpart_area_source_code or '-'} | "
                f"{partner.area_type.value if partner else 'UNMAPPED'} | "
                f"{observation.trade_flow_code or '-'} | {commodity} | "
                f"{observation.primary_value}"
            )
        print("\nLatest batch")
        if batch is None:
            print("None")
        else:
            print(f"Batch ID: {batch.id}")
            print(f"Status: {batch.status.value}")
            print(f"Received: {batch.observations_received}")
            print(f"Parsed: {batch.observations_parsed}")
            print(f"Accepted: {batch.observations_accepted}")
            print(f"Inserted: {batch.observations_inserted}")
            print(f"Updated: {batch.observations_updated}")
            print(f"Skipped: {batch.observations_skipped}")
            print(f"Rejected: {batch.observations_rejected}")
            print(f"Started: {batch.started_at.isoformat()}")
            print(f"Finished: {batch.finished_at.isoformat() if batch.finished_at else '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

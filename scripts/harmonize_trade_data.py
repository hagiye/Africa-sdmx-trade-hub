"""Run the governed UNSD IMTS to AFR_TRADE warehouse harmonization."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal
from app.harmonization.harmonization_pipeline import harmonize_source_warehouse


def main() -> int:
    with SessionLocal() as session:
        source = session.scalar(
            select(db.StatDataset).where(
                db.StatDataset.agency == "UNSD",
                db.StatDataset.dataflow_id == "IMTS_A",
                db.StatDataset.dataflow_version == "1.0",
            )
        )
        if source is None:
            raise RuntimeError("Source dataset UNSD:IMTS_A(1.0) is not registered")
        latest_source_batch = session.scalar(
            select(db.IngestionBatch.id)
            .where(db.IngestionBatch.dataset_id == source.id)
            .order_by(db.IngestionBatch.id.desc())
            .limit(1)
        )
        batch = harmonize_source_warehouse(
            session,
            source_dataset_id=source.id,
            source_batch_id=latest_source_batch,
        )
        print(f"Harmonization batch: {batch.id}")
        print(f"Status: {batch.status.value}")
        print(f"Source received: {batch.source_observations_received}")
        print(f"Source valid: {batch.source_observations_valid}")
        print(f"Transformed: {batch.observations_transformed}")
        print(f"Inserted: {batch.observations_inserted}")
        print(f"Updated: {batch.observations_updated}")
        print(f"Skipped: {batch.observations_skipped}")
        print(f"Rejected: {batch.observations_rejected}")
        print(f"Mapping errors: {batch.mapping_errors}")
        print(f"Target validation errors: {batch.target_validation_errors}")
        return 1 if batch.status is db.HarmonizationBatchStatus.FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())

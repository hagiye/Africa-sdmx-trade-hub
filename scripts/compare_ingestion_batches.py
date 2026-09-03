"""Compare the latest two trade batches and detect warehouse duplicates."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal


def _display(value: object | None) -> str:
    return "-" if value is None else str(getattr(value, "value", value))


def main() -> int:
    with SessionLocal() as session:
        batches = list(
            session.scalars(
                select(db.IngestionBatch)
                .order_by(db.IngestionBatch.id.desc())
                .limit(2)
            )
        )
        if len(batches) != 2:
            raise RuntimeError(
                f"Expected at least two ingestion batches, found {len(batches)}"
            )
        second, first = batches
        metrics = (
            ("Status", "status"),
            ("Received", "observations_received"),
            ("Parsed", "observations_parsed"),
            ("Accepted", "observations_accepted"),
            ("Inserted", "observations_inserted"),
            ("Updated", "observations_updated"),
            ("Skipped", "observations_skipped"),
            ("Rejected", "observations_rejected"),
            ("Statistical checksum", "statistical_content_checksum"),
            ("Raw checksum", "raw_response_checksum"),
        )
        print(f"Metric | First Batch {first.id} | Second Batch {second.id}")
        for label, attribute in metrics:
            print(
                f"{label} | {_display(getattr(first, attribute))} | "
                f"{_display(getattr(second, attribute))}"
            )

        rows_after = session.scalar(
            select(func.count()).select_from(db.TradeObservation)
        ) or 0
        # The ingestion service never deletes observations. Inserted is the
        # only second-batch action that can increase the warehouse row count.
        rows_before = rows_after - second.observations_inserted
        duplicate_groups = list(
            session.execute(
                select(
                    db.TradeObservation.dataset_id,
                    db.TradeObservation.source_key_hash,
                    func.count(db.TradeObservation.id).label("row_count"),
                )
                .group_by(
                    db.TradeObservation.dataset_id,
                    db.TradeObservation.source_key_hash,
                )
                .having(func.count(db.TradeObservation.id) > 1)
            )
        )
        print(f"\nWarehouse rows before: {rows_before}")
        print(f"Warehouse rows after: {rows_after}")
        print(f"Duplicate rows detected: {len(duplicate_groups)}")

        print(
            "\nPeriod | Source Key Hash | Content Hash | First Batch | Last Batch"
        )
        for row in session.scalars(
            select(db.TradeObservation).order_by(db.TradeObservation.time_period)
        ):
            print(
                f"{row.time_period or '-'} | {row.source_key_hash} | "
                f"{row.observation_content_hash} | "
                f"{row.first_ingestion_batch_id} | {row.last_ingestion_batch_id}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

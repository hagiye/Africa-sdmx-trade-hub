"""Report the latest AFR_TRADE harmonization batch and rejection evidence."""

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
        batch = session.scalar(
            select(db.HarmonizationBatch)
            .order_by(db.HarmonizationBatch.id.desc())
            .limit(1)
        )
        if batch is None:
            print("No harmonization batch has been run.")
            return 0
        print(f"Batch: {batch.id} ({batch.status.value})")
        print(f"Mapping: {batch.mapping_definition_id}({batch.mapping_version})")
        for label, value in (
            ("source_received", batch.source_observations_received),
            ("source_valid", batch.source_observations_valid),
            ("transformed", batch.observations_transformed),
            ("inserted", batch.observations_inserted),
            ("updated", batch.observations_updated),
            ("skipped", batch.observations_skipped),
            ("rejected", batch.observations_rejected),
            ("mapping_errors", batch.mapping_errors),
            ("target_validation_errors", batch.target_validation_errors),
        ):
            print(f"{label}: {value}")
        print("\nRejection reason | Count")
        print("--- | ---")
        reasons = session.execute(
            select(
                db.HarmonizationRejection.reason_code,
                func.count(db.HarmonizationRejection.id),
            )
            .where(db.HarmonizationRejection.harmonization_batch_id == batch.id)
            .group_by(db.HarmonizationRejection.reason_code)
            .order_by(db.HarmonizationRejection.reason_code)
        )
        for reason, count in reasons:
            print(f"{reason.value} | {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

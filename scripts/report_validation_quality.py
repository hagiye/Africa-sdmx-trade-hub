"""Report persisted validation findings for the latest production batch."""

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
            select(db.IngestionBatch).order_by(db.IngestionBatch.id.desc())
        )
        if batch is None:
            print("No ingestion batch exists")
            return 0

        findings = session.scalar(
            select(func.count())
            .select_from(db.ValidationFinding)
            .where(db.ValidationFinding.ingestion_batch_id == batch.id)
        ) or 0
        print(f"Latest batch: {batch.id} ({batch.status.value})")
        if findings == 0:
            print(
                "No validation results were recorded for this batch; it may "
                "predate validation integration or have passed with no findings."
            )
            return 0

        print("\nRule | Severity | Count")
        print("--- | --- | ---:")
        for rule_id, severity, count in session.execute(
            select(
                db.ValidationFinding.rule_id,
                db.ValidationFinding.severity,
                func.count(db.ValidationFinding.id),
            )
            .where(db.ValidationFinding.ingestion_batch_id == batch.id)
            .group_by(db.ValidationFinding.rule_id, db.ValidationFinding.severity)
            .order_by(db.ValidationFinding.rule_id, db.ValidationFinding.severity)
        ):
            print(f"{rule_id} | {severity} | {count}")

        print("\nConcept | Error Count")
        print("--- | ---:")
        concept_rows = session.execute(
            select(
                db.ValidationFinding.concept_id,
                func.count(db.ValidationFinding.id),
            )
            .where(
                db.ValidationFinding.ingestion_batch_id == batch.id,
                db.ValidationFinding.severity.in_(("ERROR", "FATAL")),
            )
            .group_by(db.ValidationFinding.concept_id)
            .order_by(db.ValidationFinding.concept_id)
        ).all()
        if not concept_rows:
            print("(none) | 0")
        for concept_id, count in concept_rows:
            print(f"{concept_id or '-'} | {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

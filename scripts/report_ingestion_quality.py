"""Report quality counts and geography decisions for the latest trade batch."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal
from app.mappings.geo import is_au_reporter, resolve_source_mapping


def _show_mapping(label: str, mapping: db.SourceGeoMapping | None) -> None:
    if mapping is None or mapping.geo_area is None:
        print(f"{label} mapping: UNMAPPED")
        return
    area = mapping.geo_area
    print(
        f"{label} mapping: {mapping.source_code} -> {area.name_en}; "
        f"type={area.area_type.value}; ISO2={area.iso2 or '-'}; "
        f"ISO3={area.iso3 or '-'}; status={mapping.mapping_status.value}"
    )


def main() -> int:
    with SessionLocal() as session:
        batch = session.scalar(
            select(db.IngestionBatch).order_by(db.IngestionBatch.id.desc())
        )
        if batch is None:
            print("No ingestion batch exists")
            return 0
        print(f"Latest batch: {batch.id} ({batch.status.value})")
        print(f"Received: {batch.observations_received}")
        print(f"Parsed: {batch.observations_parsed}")
        print(f"Accepted: {batch.observations_accepted}")
        print(f"Inserted: {batch.observations_inserted}")
        print(f"Updated: {batch.observations_updated}")
        print(f"Skipped: {batch.observations_skipped}")
        print(f"Rejected: {batch.observations_rejected}")
        if batch.observations_rejected:
            print("\nReason | Count")
            for reason, count in session.execute(
                select(
                    db.ObservationRejection.reason_code,
                    func.count(db.ObservationRejection.id),
                )
                .where(db.ObservationRejection.ingestion_batch_id == batch.id)
                .group_by(db.ObservationRejection.reason_code)
                .order_by(db.ObservationRejection.reason_code)
            ):
                print(f"{reason.value} | {count}")

        parameters = batch.query_parameters or {}
        reporter_code = str(parameters.get("reporterCode", ""))
        counterpart_code = str(parameters.get("partnerCode", ""))
        reporter_mapping = resolve_source_mapping(
            session, "UNSD", batch.source_system, reporter_code
        )
        counterpart_mapping = resolve_source_mapping(
            session, "UNSD", batch.source_system, counterpart_code
        )
        print()
        _show_mapping("Reporter", reporter_mapping)
        _show_mapping("Counterpart", counterpart_mapping)
        accepted = is_au_reporter(
            session, "UNSD", batch.source_system, reporter_code
        )
        print(f"AU reporter result: {'ACCEPTED' if accepted else 'REJECTED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

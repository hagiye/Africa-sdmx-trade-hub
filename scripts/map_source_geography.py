"""Load official UN Comtrade geography codes into source_geo_mapping."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import SessionLocal
from app.mappings.geo import (
    fetch_un_comtrade_partner_areas,
    load_source_geo_mappings,
)


def main() -> int:
    provider_records = fetch_un_comtrade_partner_areas()
    with SessionLocal() as session:
        result = load_source_geo_mappings(session, provider_records)

    print(f"Source codes examined: {result.source_codes_examined}")
    print(f"Inserted: {result.inserted}")
    print(f"Updated: {result.updated}")
    print(f"Unchanged: {result.unchanged}")
    print(f"Mapped: {result.mapped}")
    print(f"Unmapped: {result.unmapped}")
    print(f"Total mappings: {result.total_mappings}")
    print(f"World created: {'yes' if result.world_created else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

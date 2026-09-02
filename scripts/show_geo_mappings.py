"""Inspect UN Comtrade geography mapping coverage and required examples."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.models import AreaType, GeoArea, MappingStatus, SourceGeoMapping
from app.database.session import SessionLocal
from app.mappings.geo import SOURCE_AGENCY, SOURCE_CODELIST, SOURCE_SYSTEM


def main() -> int:
    scope = (
        SourceGeoMapping.source_agency == SOURCE_AGENCY,
        SourceGeoMapping.source_system == SOURCE_SYSTEM,
        SourceGeoMapping.source_codelist == SOURCE_CODELIST,
    )
    with SessionLocal() as session:
        total = session.scalar(
            select(func.count()).select_from(SourceGeoMapping).where(*scope)
        ) or 0
        mapped = session.scalar(
            select(func.count())
            .select_from(SourceGeoMapping)
            .where(*scope, SourceGeoMapping.geo_area_id.is_not(None))
        ) or 0
        unmapped = session.scalar(
            select(func.count())
            .select_from(SourceGeoMapping)
            .where(*scope, SourceGeoMapping.mapping_status == MappingStatus.UNMAPPED)
        ) or 0
        au_members = session.scalar(
            select(func.count())
            .select_from(SourceGeoMapping)
            .join(GeoArea)
            .where(*scope, GeoArea.au_member.is_(True))
        ) or 0
        non_au_countries = session.scalar(
            select(func.count())
            .select_from(SourceGeoMapping)
            .join(GeoArea)
            .where(
                *scope,
                GeoArea.area_type == AreaType.COUNTRY,
                GeoArea.au_member.is_(False),
            )
        ) or 0
        aggregates = session.scalar(
            select(func.count())
            .select_from(SourceGeoMapping)
            .join(GeoArea)
            .where(*scope, GeoArea.area_type == AreaType.AGGREGATE)
        ) or 0
        examples = list(
            session.scalars(
                select(SourceGeoMapping)
                .options(selectinload(SourceGeoMapping.geo_area))
                .where(*scope, SourceGeoMapping.source_code.in_(("788", "404", "0")))
                .order_by(SourceGeoMapping.source_code)
            )
        )

    print("Provider: UN Comtrade")
    print(f"Source codelist: {SOURCE_CODELIST}")
    print(f"Source geography codes: {total}")
    print(f"Mapped: {mapped}")
    print(f"AU Member States mapped: {au_members}")
    print(f"Non-AU countries mapped: {non_au_countries}")
    print(f"Aggregates mapped: {aggregates}")
    print(f"Unmapped: {unmapped}")
    print(
        "\nSource Code | Source Label | Canonical Area | Type | ISO3 | "
        "AU Member | Status"
    )
    print("--- | --- | --- | --- | --- | --- | ---")
    for mapping in examples:
        area = mapping.geo_area
        print(
            f"{mapping.source_code} | {mapping.source_label_en or '-'} | "
            f"{area.name_en if area else '-'} | "
            f"{area.area_type.value if area else '-'} | "
            f"{area.iso3 or '-' if area else '-'} | "
            f"{'yes' if area and area.au_member else 'no'} | "
            f"{mapping.mapping_status.value}"
        )
    found = {mapping.source_code for mapping in examples}
    missing = {"788", "404", "0"} - found
    if missing:
        raise RuntimeError(f"Required mappings are missing: {sorted(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

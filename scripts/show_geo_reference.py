"""Show compact counts and canonical Tunisia/Kenya geography records."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.models import AreaType, GeoArea
from app.database.session import SessionLocal


def _count(session, *criteria) -> int:
    statement = select(func.count()).select_from(GeoArea)
    if criteria:
        statement = statement.where(*criteria)
    return session.scalar(statement) or 0


def main() -> int:
    with SessionLocal() as session:
        total = _count(session)
        countries = _count(session, GeoArea.area_type == AreaType.COUNTRY)
        au_members = _count(session, GeoArea.au_member.is_(True))
        non_au = _count(session, GeoArea.au_member.is_(False))
        sample = list(
            session.scalars(
                select(GeoArea)
                .where(GeoArea.iso2.in_(("TN", "KE")))
                .order_by(GeoArea.iso2)
            )
        )

    print(f"Total geo areas: {total}")
    print(f"Total countries: {countries}")
    print(f"AU Member States: {au_members}")
    print(f"Non-AU areas: {non_au}")
    print("\nISO2 | ISO3 | Numeric | English | French | AU Member")
    print("--- | --- | --- | --- | --- | ---")
    for area in sample:
        print(
            f"{area.iso2} | {area.iso3} | {area.numeric_code} | "
            f"{area.name_en} | {area.name_fr} | "
            f"{'yes' if area.au_member else 'no'}"
        )

    found = {area.iso2 for area in sample}
    missing = {"TN", "KE"} - found
    if missing:
        raise RuntimeError(f"Required canonical rows are missing: {sorted(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

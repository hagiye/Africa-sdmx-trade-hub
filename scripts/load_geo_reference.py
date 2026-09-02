"""Load the versioned African Union geography reference into PostgreSQL."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import SessionLocal
from app.reference.geo import load_geo_reference


def main() -> int:
    with SessionLocal() as session:
        result = load_geo_reference(session)

    print(f"Inserted: {result.inserted}")
    print(f"Updated: {result.updated}")
    print(f"Unchanged: {result.unchanged}")
    print(f"Total rows: {result.total_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

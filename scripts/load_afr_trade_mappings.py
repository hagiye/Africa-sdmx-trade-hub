"""Load the version-controlled UNSD IMTS to AFR_TRADE mapping registry."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import SessionLocal
from app.mappings.sdmx_mapping_loader import load_sdmx_mappings


def main() -> int:
    with SessionLocal() as session:
        result = load_sdmx_mappings(session)
    print(f"Mapping: {result.mapping_id}({result.mapping_version})")
    print(f"Source: {result.source.display()}")
    print(f"Target: {result.target.display()}")
    print(f"Action: {result.action}")
    print(f"Checksum: {result.checksum}")
    print(f"Transformation definitions: {result.transformations}")
    print(f"Concept mappings: {result.concepts}")
    print(f"Code mappings: {result.codes}")
    print(f"Inserted: {result.inserted}")
    print(f"Updated: {result.updated}")
    print(f"Unchanged: {result.unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Load the canonical AFRSTAT:AFR_TRADE(1.0) target into the shared registry."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import SessionLocal
from app.pipelines.afr_trade_structure import load_afr_trade_structure


def main() -> int:
    with SessionLocal() as session:
        result = load_afr_trade_structure(session)
    print("AFRSTAT:AFR_TRADE(1.0)")
    print(f"Action: {result.action}")
    print(f"Checksum: {result.checksum}")
    print(f"Inserted structures: {result.inserted}")
    print(f"Updated structures: {result.updated}")
    print(f"Unchanged structures: {result.unchanged}")
    print(f"Concepts: {result.concepts}")
    print(f"Dimensions: {result.dimensions}")
    print(f"Attributes: {result.attributes}")
    print(f"Measures: {result.measures}")
    print(f"Codelists: {result.codelists}")
    print(f"Codes: {result.codes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

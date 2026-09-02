"""CLI entry point for the SDMX metadata import pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import SessionLocal
from app.pipelines.import_structures import import_structures


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    with SessionLocal() as session:
        summary = import_structures(session)
    print("\nSDMX Structure Import\n")
    print(f"Provider: {summary.provider}")
    print(f"Dataflow: {summary.dataflow}")
    print(f"DSD: {summary.dsd}")
    print(f"Version: {summary.version}\n")
    print(f"Concept schemes: {summary.concept_schemes}")
    print(f"Concepts: {summary.concepts}")
    print(f"Codelists: {summary.codelists}")
    print(f"Codes: {summary.codes}")
    print(f"Dimensions: {summary.dimensions}")
    print(f"Attributes: {summary.attributes}")
    print(f"Measures: {summary.measures}\n")
    print(f"Constraints: {summary.constraints}")
    print(f"Inserted: {summary.inserted}")
    print(f"Updated: {summary.updated}")
    print(f"Unchanged: {summary.unchanged}")
    print(f"Checksum changes: {summary.checksum_changes}\n")
    print(f"Constraint discovery: {summary.constraints_note}")
    print(f"Status: {summary.status}")


if __name__ == "__main__":
    main()

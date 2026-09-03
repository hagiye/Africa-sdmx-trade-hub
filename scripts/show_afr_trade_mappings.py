"""Inspect the loaded UNSD IMTS to AFR_TRADE mapping metadata."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal
from app.mappings.sdmx_mapping_loader import load_mapping_definition


def _target(value: str | None) -> str:
    return value or "-"


def main() -> int:
    definition = load_mapping_definition()
    with SessionLocal() as session:
        concepts = list(
            session.scalars(
                select(db.SdmxConceptMapping)
                .where(
                    db.SdmxConceptMapping.mapping_definition_id
                    == definition.mapping_id,
                    db.SdmxConceptMapping.mapping_version
                    == definition.mapping_version,
                    db.SdmxConceptMapping.source_agency == definition.source.agency,
                    db.SdmxConceptMapping.source_structure_id
                    == definition.source.structure_id,
                    db.SdmxConceptMapping.source_structure_version
                    == definition.source.version,
                    db.SdmxConceptMapping.target_agency == definition.target.agency,
                    db.SdmxConceptMapping.target_structure_id
                    == definition.target.structure_id,
                    db.SdmxConceptMapping.target_structure_version
                    == definition.target.version,
                )
                .order_by(db.SdmxConceptMapping.id)
            )
        )
        concept_ids = [row.id for row in concepts]
        codes = list(
            session.scalars(
                select(db.SdmxCodeMapping)
                .where(db.SdmxCodeMapping.concept_mapping_id.in_(concept_ids))
                .order_by(db.SdmxCodeMapping.id)
            )
        ) if concept_ids else []

    print(f"Source: {definition.source.display()}")
    print(f"Target: {definition.target.display()}")
    print(f"Mapping: {definition.mapping_id}({definition.mapping_version})")
    print(f"Checksum: {definition.checksum}")
    print("\nSource Concept | Target Concept | Type | Status | Transformation")
    print("--- | --- | --- | --- | ---")
    for row in concepts:
        print(
            f"{row.source_concept_id} | {_target(row.target_concept_id)} | "
            f"{row.mapping_type.value} | {row.status.value} | "
            f"{row.transformation_id or '-'}"
        )

    concept_by_id = {row.id: row for row in concepts}
    print("\nConcept | Source Code | Target Code | Status")
    print("--- | --- | --- | ---")
    for row in codes:
        concept = concept_by_id[row.concept_mapping_id]
        label = f"{concept.source_concept_id}->{_target(concept.target_concept_id)}"
        print(f"{label} | {row.source_code} | {_target(row.target_code)} | {row.status.value}")

    types = Counter(row.mapping_type for row in concepts)
    statuses = Counter(row.status for row in concepts)
    print("\nCounts")
    print(f"Concept mappings: {len(concepts)}")
    print(f"Code mappings: {len(codes)}")
    print(f"DROP mappings: {types[db.SdmxMappingType.DROP]}")
    print(f"DEFER mappings: {types[db.SdmxMappingType.DEFER]}")
    print(f"CONFIRMED mappings: {statuses[db.SdmxMappingStatus.CONFIRMED]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Report classification coverage of source UNSD:IMTS(1.2) dimensions."""

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


def main() -> int:
    definition = load_mapping_definition()
    with SessionLocal() as session:
        dsd = session.scalar(
            select(db.DSD).where(
                db.DSD.agency_id == definition.source.agency,
                db.DSD.dsd_id == definition.source.structure_id,
                db.DSD.version == definition.source.version,
            )
        )
        if dsd is None:
            raise RuntimeError(f"Source DSD is not loaded: {definition.source.display()}")
        source_dimensions = [row.concept_id for row in dsd.dimensions]
        mappings = list(
            session.scalars(
                select(db.SdmxConceptMapping).where(
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
            )
        )

    by_source: dict[str, set[db.SdmxMappingType]] = {}
    for row in mappings:
        by_source.setdefault(row.source_concept_id, set()).add(row.mapping_type)
    counts: Counter[db.SdmxMappingType] = Counter()
    unclassified: list[str] = []
    conflicts: list[str] = []
    for concept_id in source_dimensions:
        types = by_source.get(concept_id, set())
        if not types:
            unclassified.append(concept_id)
        elif len(types) == 1:
            counts[next(iter(types))] += 1
        else:
            conflicts.append(concept_id)

    print(f"Source: {definition.source.display()}")
    print(f"Target: {definition.target.display()}")
    print(f"Total source dimensions/concepts considered: {len(source_dimensions)}")
    print(f"Mapped directly: {counts[db.SdmxMappingType.DIRECT]}")
    print(f"Renamed: {counts[db.SdmxMappingType.RENAME]}")
    print(f"Transformed: {counts[db.SdmxMappingType.TRANSFORM]}")
    print(f"Derived: {counts[db.SdmxMappingType.DERIVE]}")
    print(f"Dropped: {counts[db.SdmxMappingType.DROP]}")
    print(f"Deferred: {counts[db.SdmxMappingType.DEFER]}")
    print(f"Unclassified: {len(unclassified)}")
    if unclassified:
        print(f"Unclassified concepts: {', '.join(unclassified)}")
    if conflicts:
        print(f"Conflicting classifications: {', '.join(conflicts)}")
        return 1
    return 1 if unclassified else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Display registry identities, counts, and selected DSD dimension order."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal
from app.sdmx.discovery import TRADE_DSD


def main() -> None:
    with SessionLocal() as session:
        groups = [
            ("Dataflows", db.Dataflow, (db.Dataflow.agency_id, db.Dataflow.dataflow_id, db.Dataflow.version)),
            ("DSDs", db.DSD, (db.DSD.agency_id, db.DSD.dsd_id, db.DSD.version)),
            ("Concept Schemes", db.ConceptScheme, (db.ConceptScheme.agency_id, db.ConceptScheme.scheme_id, db.ConceptScheme.version)),
            ("Codelists", db.Codelist, (db.Codelist.agency_id, db.Codelist.codelist_id, db.Codelist.version)),
        ]
        for title, model, columns in groups:
            print(f"\n{title}")
            for row in session.execute(select(*columns).order_by(*columns)):
                print(f"- {row[0]}:{row[1]}({row[2]})")
        dsd = session.scalar(
            select(db.DSD).where(
                db.DSD.agency_id == TRADE_DSD.agency,
                db.DSD.dsd_id == TRADE_DSD.structure_id,
                db.DSD.version == TRADE_DSD.version,
            )
        )
        if dsd:
            print(f"\nDSD: {dsd.agency_id}:{dsd.dsd_id}({dsd.version})")
            print("# | Concept | Codelist")
            for dimension in dsd.dimensions:
                codelist = (
                    f"{dimension.codelist_agency_id}:{dimension.codelist_id}({dimension.codelist_version})"
                    if dimension.codelist_id
                    else "-"
                )
                print(f"{dimension.position} | {dimension.concept_id} | {codelist}")
        print("\nTable counts")
        for model in (
            db.Dataflow, db.DSD, db.ConceptScheme, db.Concept, db.Codelist,
            db.Code, db.Dimension, db.Attribute, db.Measure,
        ):
            print(f"{model.__tablename__}: {session.scalar(select(func.count()).select_from(model))}")


if __name__ == "__main__":
    main()

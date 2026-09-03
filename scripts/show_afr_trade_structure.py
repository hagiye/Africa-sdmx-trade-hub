"""Inspect the registered AFR_TRADE target alongside its canonical annotations."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.database.session import SessionLocal
from app.pipelines.afr_trade_structure import load_canonical_structure


def _reference(component: dict) -> str:
    reference = component.get("codelist")
    if reference is None:
        return "-"
    return f"{reference['agency']}:{reference['id']}({reference['version']})"


def main() -> int:
    canonical = load_canonical_structure()
    model = canonical.definition
    with SessionLocal() as session:
        agency = session.scalar(
            select(db.Agency).where(db.Agency.agency_id == "AFRSTAT")
        )
        dataflow = session.scalar(
            select(db.Dataflow).where(
                db.Dataflow.agency_id == "AFRSTAT",
                db.Dataflow.dataflow_id == "AFR_TRADE",
                db.Dataflow.version == "1.0",
            )
        )
        dsd = session.scalar(
            select(db.DSD).where(
                db.DSD.agency_id == "AFRSTAT",
                db.DSD.dsd_id == "AFR_TRADE",
                db.DSD.version == "1.0",
            )
        )
        if agency is None or dataflow is None or dsd is None:
            raise RuntimeError("Load AFRSTAT:AFR_TRADE(1.0) before inspection")

        print(f"Agency: {agency.agency_id}")
        print(f"Dataflow: {dataflow.agency_id}:{dataflow.dataflow_id}")
        print(f"DSD: {dsd.agency_id}:{dsd.dsd_id}")
        print(f"Version: {dsd.version}")
        print(f"Checksum: {dsd.checksum}")

        print("\nPosition | Concept | Role | Codelist | Required")
        print("---: | --- | --- | --- | ---")
        for component in model["dsd"]["dimensions"]:
            print(
                f"{component['position']} | {component['id']} | "
                f"{component['role']} | {_reference(component)} | "
                f"{'yes' if component['required'] else 'conditional'}"
            )

        print("\nAttributes")
        print("Concept | Attachment | Codelist | Required")
        print("--- | --- | --- | ---")
        for component in model["dsd"]["attributes"]:
            print(
                f"{component['id']} | {component['attachment_level']} | "
                f"{_reference(component)} | "
                f"{'yes' if component['required'] else 'conditional'}"
            )

        print("\nCodelists")
        print("Codelist | Code count")
        print("--- | ---:")
        for codelist in model["codelists"]:
            count = session.scalar(
                select(func.count(db.Code.id))
                .join(db.Codelist, db.Code.codelist_id == db.Codelist.id)
                .where(
                    db.Codelist.agency_id == "AFRSTAT",
                    db.Codelist.codelist_id == codelist["id"],
                    db.Codelist.version == codelist["version"],
                )
            ) or 0
            print(f"AFRSTAT:{codelist['id']}(1.0) | {count}")

        target_datasets = session.scalar(
            select(func.count())
            .select_from(db.StatDataset)
            .where(
                db.StatDataset.agency == "AFRSTAT",
                db.StatDataset.dataflow_id == "AFR_TRADE",
            )
        ) or 0
        target_observations = session.scalar(
            select(func.count(db.TradeObservation.id))
            .join(
                db.StatDataset,
                db.TradeObservation.dataset_id == db.StatDataset.id,
            )
            .where(
                db.StatDataset.agency == "AFRSTAT",
                db.StatDataset.dataflow_id == "AFR_TRADE",
            )
        ) or 0
        print("\nTarget data scope")
        print(f"AFR_TRADE statistical datasets: {target_datasets}")
        print(f"AFR_TRADE observations: {target_observations}")

    print("\nDISCLAIMER:")
    print(model["disclaimer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

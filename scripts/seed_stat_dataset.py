"""Idempotently seed the UNSD annual merchandise-trade warehouse dataset."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.models import Dataflow, StatDataset
from app.database.session import SessionLocal


DATASET_IDENTITY = ("UNSD", "IMTS_A", "1.0")
EXPECTED_DSD_IDENTITY = ("UNSD", "IMTS", "1.2")
SOURCE_SYSTEM = "UN_COMTRADE"


@dataclass(frozen=True)
class DatasetSeedResult:
    action: str
    dataset_id: int
    name: str


def seed_stat_dataset(session: Session) -> DatasetSeedResult:
    agency, dataflow_id, version = DATASET_IDENTITY
    dataflow = session.scalar(
        select(Dataflow).where(
            Dataflow.agency_id == agency,
            Dataflow.dataflow_id == dataflow_id,
            Dataflow.version == version,
        )
    )
    if dataflow is None:
        raise RuntimeError(
            "Metadata registry does not contain UNSD:IMTS_A(1.0); "
            "import structures before seeding the statistical dataset"
        )
    actual_dsd = (dataflow.dsd_agency_id, dataflow.dsd_id, dataflow.dsd_version)
    if actual_dsd != EXPECTED_DSD_IDENTITY:
        raise RuntimeError(
            f"UNSD:IMTS_A(1.0) references unexpected DSD {actual_dsd!r}"
        )

    dataset = session.scalar(
        select(StatDataset).where(
            StatDataset.agency == agency,
            StatDataset.dataflow_id == dataflow_id,
            StatDataset.dataflow_version == version,
        )
    )
    if dataset is None:
        dataset = StatDataset(
            agency=agency,
            dataflow_id=dataflow_id,
            dataflow_version=version,
            dsd_agency=EXPECTED_DSD_IDENTITY[0],
            dsd_id=EXPECTED_DSD_IDENTITY[1],
            dsd_version=EXPECTED_DSD_IDENTITY[2],
            name=dataflow.name,
            source_system=SOURCE_SYSTEM,
            source_url=dataflow.source_url,
        )
        session.add(dataset)
        action = "INSERTED"
    else:
        action = "EXISTING"
        dataset.dsd_agency = EXPECTED_DSD_IDENTITY[0]
        dataset.dsd_id = EXPECTED_DSD_IDENTITY[1]
        dataset.dsd_version = EXPECTED_DSD_IDENTITY[2]
        dataset.name = dataflow.name
        dataset.source_system = SOURCE_SYSTEM
        dataset.source_url = dataflow.source_url

    session.commit()
    session.refresh(dataset)
    return DatasetSeedResult(action=action, dataset_id=dataset.id, name=dataset.name)


def main() -> int:
    with SessionLocal() as session:
        result = seed_stat_dataset(session)
    print(f"Result: {result.action}")
    print(f"Dataset ID: {result.dataset_id}")
    print(f"Identity: {DATASET_IDENTITY[0]}:{DATASET_IDENTITY[1]}({DATASET_IDENTITY[2]})")
    print(f"Name: {result.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

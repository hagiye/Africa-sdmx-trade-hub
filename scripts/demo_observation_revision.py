"""Demonstrate a synthetic revision in a temporary in-memory database."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import models as db
from app.mappings.geo import CODELIST_IDENTITY, load_source_geo_mappings
from app.pipelines.ingest_trade_data import TradeQuery, ingest_trade_query
from app.reference.geo import load_geo_reference


ORIGINAL_PATH = (
    ROOT / "tests" / "fixtures" / "data"
    / "un_comtrade_tunisia_imports_world_2023.json"
)
REVISED_PATH = (
    ROOT / "tests" / "fixtures" / "data" / "synthetic"
    / "un_comtrade_tunisia_imports_world_2023_revised.json"
)
QUERY = TradeQuery(
    type_code="C",
    frequency_code="A",
    classification_code="S4",
    periods=("2023",),
    reporter_code="788",
    flow_code="M",
    partner_code="0",
    partner2_code="0",
    commodity_code="TOTAL",
)
PROVIDER_AREAS = [
    {
        "PartnerCode": 0,
        "PartnerDesc": "World",
        "PartnerCodeIsoAlpha3": "W00",
        "entryEffectiveDate": "1901-01-01T00:00:00",
        "isGroup": True,
    },
    {
        "PartnerCode": 788,
        "PartnerDesc": "Tunisia",
        "PartnerCodeIsoAlpha2": "TN",
        "PartnerCodeIsoAlpha3": "TUN",
        "entryEffectiveDate": "1900-01-01T00:00:00",
        "isGroup": False,
    },
]


@dataclass(frozen=True)
class ObservationState:
    observation_id: int
    period: str | None
    source_key_hash: str
    content_hash: str
    primary_value: str
    first_batch: int
    last_batch: int


def _seed_temporary_database(session: Session) -> db.StatDataset:
    load_geo_reference(session)
    agency, codelist_id, version = CODELIST_IDENTITY
    session.add(db.Agency(agency_id=agency, name="UNSD"))
    codelist = db.Codelist(
        agency_id=agency,
        codelist_id=codelist_id,
        version=version,
        name="CL_AREA",
        source_url="https://fixtures.invalid/CL_AREA",
        retrieved_at=datetime.now(timezone.utc),
        checksum="a" * 64,
    )
    session.add(codelist)
    session.flush()
    session.add_all(
        db.Code(codelist_id=codelist.id, code=code)
        for code in ("W0", "KE", "TN")
    )
    session.add(
        db.Dataflow(
            agency_id="UNSD",
            dataflow_id="IMTS_A",
            version="1.0",
            name="IMTS Annual",
            source_url="https://fixtures.invalid/IMTS_A",
            retrieved_at=datetime.now(timezone.utc),
            checksum="b" * 64,
            dsd_agency_id="UNSD",
            dsd_id="IMTS",
            dsd_version="1.2",
        )
    )
    dataset = db.StatDataset(
        agency="UNSD",
        dataflow_id="IMTS_A",
        dataflow_version="1.0",
        dsd_agency="UNSD",
        dsd_id="IMTS",
        dsd_version="1.2",
        name="IMTS Annual",
        source_system="UN_COMTRADE",
    )
    session.add(dataset)
    session.commit()
    load_source_geo_mappings(session, PROVIDER_AREAS)
    return dataset


def _state(row: db.TradeObservation) -> ObservationState:
    value = (
        row.primary_value.quantize(Decimal("0.01"))
        if row.primary_value is not None
        else None
    )
    return ObservationState(
        observation_id=row.id,
        period=row.time_period,
        source_key_hash=row.source_key_hash,
        content_hash=row.observation_content_hash,
        primary_value=str(value),
        first_batch=row.first_ingestion_batch_id,
        last_batch=row.last_ingestion_batch_id,
    )


def main() -> int:
    original_payload = json.loads(ORIGINAL_PATH.read_text(encoding="utf-8"))
    revised_payload = json.loads(REVISED_PATH.read_text(encoding="utf-8"))
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            dataset = _seed_temporary_database(session)
            original_batch = ingest_trade_query(
                session,
                dataset_id=dataset.id,
                query=QUERY,
                fetch_response=lambda _period, _parameters: original_payload,
            )
            row = session.scalar(select(db.TradeObservation))
            assert row is not None
            original = _state(row)
            rows_before = session.scalar(
                select(func.count()).select_from(db.TradeObservation)
            ) or 0

            revision_batch = ingest_trade_query(
                session,
                dataset_id=dataset.id,
                query=QUERY,
                fetch_response=lambda _period, _parameters: revised_payload,
            )
            row = session.scalar(select(db.TradeObservation))
            assert row is not None
            revised = _state(row)
            rows_after = session.scalar(
                select(func.count()).select_from(db.TradeObservation)
            ) or 0

            print("SYNTHETIC REVISION TEST - temporary in-memory database")
            print("Metric | Original | Revised")
            for label, field in (
                ("Observation ID", "observation_id"),
                ("Period", "period"),
                ("Source Key Hash", "source_key_hash"),
                ("Content Hash", "content_hash"),
                ("Primary Value", "primary_value"),
                ("First Batch", "first_batch"),
                ("Last Batch", "last_batch"),
            ):
                print(
                    f"{label} | {getattr(original, field)} | "
                    f"{getattr(revised, field)}"
                )
            print(f"\nRows before revision: {rows_before}")
            print(f"Rows after revision: {rows_after}")
            print(f"Inserted: {revision_batch.observations_inserted}")
            print(f"Updated: {revision_batch.observations_updated}")
            print(f"Skipped: {revision_batch.observations_skipped}")
            print(f"Original batch inserted: {original_batch.observations_inserted}")
    finally:
        engine.dispose()
    print("Production warehouse was not opened or modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

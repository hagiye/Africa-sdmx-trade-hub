"""Offline trade-ingestion tests using the controlled real fixtures."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.mappings.geo import CODELIST_IDENTITY, load_source_geo_mappings
from app.pipelines.ingest_trade_data import (
    TradeIngestionError,
    TradeQuery,
    ingest_trade_query,
)
from app.reference.geo import load_geo_reference


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "data"
FIXTURES = {
    period: json.loads(
        (FIXTURE_DIRECTORY / f"un_comtrade_tunisia_imports_world_{period}.json")
        .read_text(encoding="utf-8")
    )
    for period in ("2022", "2023", "2024")
}
QUERY = TradeQuery(
    type_code="C",
    frequency_code="A",
    classification_code="S4",
    periods=("2022", "2023", "2024"),
    reporter_code="788",
    flow_code="M",
    partner_code="0",
    partner2_code="0",
    commodity_code="TOTAL",
)
EXPECTED_VALUES = {
    "2022": Decimal("26672667450.171"),
    "2023": Decimal("25930493874.99"),
    "2024": Decimal("26065070572.389"),
}
PROVIDER_AREAS = [
    {
        "PartnerCode": 0,
        "PartnerDesc": "World",
        "PartnerCodeIsoAlpha3": "W00",
        "entryEffectiveDate": "1901-01-01T00:00:00",
        "isGroup": True,
    },
    {
        "PartnerCode": 124,
        "PartnerDesc": "Canada",
        "PartnerCodeIsoAlpha2": "CA",
        "PartnerCodeIsoAlpha3": "CAN",
        "entryEffectiveDate": "1900-01-01T00:00:00",
        "isGroup": False,
    },
    {
        "PartnerCode": 404,
        "PartnerDesc": "Kenya",
        "PartnerCodeIsoAlpha2": "KE",
        "PartnerCodeIsoAlpha3": "KEN",
        "entryEffectiveDate": "1900-01-01T00:00:00",
        "isGroup": False,
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


@pytest.fixture
def ingestion_database(db_session: Session) -> tuple[Session, db.StatDataset]:
    load_geo_reference(db_session)
    canada = db.GeoArea(
        iso2="CA",
        iso3="CAN",
        numeric_code="124",
        name_en="Canada",
        name_fr="Canada",
        area_type=db.AreaType.COUNTRY,
        au_member=False,
    )
    db_session.add(canada)
    agency, codelist_id, version = CODELIST_IDENTITY
    db_session.add_all(
        [
            db.Agency(agency_id=agency, name="UNSD"),
            db.Agency(agency_id="SDMX", name="SDMX"),
        ]
    )
    codelist = db.Codelist(
        agency_id=agency,
        codelist_id=codelist_id,
        version=version,
        name="CL_AREA",
        source_url="https://fixtures.invalid/CL_AREA",
        retrieved_at=datetime.now(timezone.utc),
        checksum="a" * 64,
    )
    db_session.add(codelist)
    db_session.flush()
    db_session.add_all(
        db.Code(codelist_id=codelist.id, code=code)
        for code in ("W0", "KE", "TN")
    )
    for codelist_agency, validation_id, validation_version, codes in (
        ("SDMX", "CL_FREQ", "2.0", ("A", "Q", "M")),
        ("UNSD", "CL_TRADE_FLOW", "1.0", ("M", "X")),
        ("UNSD", "CL_COMMODITY", "1.0", ("SITC4_TOTAL",)),
    ):
        row = db.Codelist(
            agency_id=codelist_agency,
            codelist_id=validation_id,
            version=validation_version,
            name=validation_id,
            source_url=f"https://fixtures.invalid/{validation_id}",
            retrieved_at=datetime.now(timezone.utc),
            checksum="c" * 64,
        )
        db_session.add(row)
        db_session.flush()
        db_session.add_all(db.Code(codelist_id=row.id, code=code) for code in codes)
    dsd = db.DSD(
        agency_id="UNSD",
        dsd_id="IMTS",
        version="1.2",
        name="International Merchandise Trade Statistics",
        source_url="https://fixtures.invalid/IMTS",
        retrieved_at=datetime.now(timezone.utc),
        checksum="d" * 64,
    )
    db_session.add(dsd)
    db_session.flush()
    for position, concept_id, codelist_identity in (
        (1, "FREQ", ("SDMX", "CL_FREQ", "2.0")),
        (2, "REF_AREA", ("UNSD", "CL_AREA", "1.0")),
        (3, "TRADE_FLOW", ("UNSD", "CL_TRADE_FLOW", "1.0")),
        (4, "COMMODITY_1", ("UNSD", "CL_COMMODITY", "1.0")),
        (9, "COUNTERPART_AREA_1", ("UNSD", "CL_AREA", "1.0")),
        (11, "COUNTERPART_AREA_2", ("UNSD", "CL_AREA", "1.0")),
        (19, "TIME_PERIOD", None),
    ):
        db_session.add(
            db.Dimension(
                dsd_id=dsd.id,
                concept_id=concept_id,
                position=position,
                role="time" if concept_id == "TIME_PERIOD" else "dimension",
                codelist_agency_id=(
                    codelist_identity[0] if codelist_identity else None
                ),
                codelist_id=(codelist_identity[1] if codelist_identity else None),
                codelist_version=(
                    codelist_identity[2] if codelist_identity else None
                ),
            )
        )
    db_session.add(
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
    db_session.add(dataset)
    db_session.commit()
    load_source_geo_mappings(db_session, PROVIDER_AREAS)
    return db_session, dataset


def test_fixture_batch_ingests_three_new_observations_successfully(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    saw_running: list[bool] = []

    def fetch(period: str, parameters: dict[str, str]):
        batch = session.scalar(select(db.IngestionBatch))
        saw_running.append(
            batch is not None
            and batch.status is db.IngestionBatchStatus.RUNNING
            and batch.finished_at is None
        )
        assert parameters["period"] == period
        return copy.deepcopy(FIXTURES[period])

    batch = ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=QUERY,
        fetch_response=fetch,
    )

    assert saw_running == [True, True, True]
    assert batch.status is db.IngestionBatchStatus.SUCCESS
    assert batch.finished_at is not None
    assert (
        batch.observations_received,
        batch.observations_parsed,
        batch.observations_accepted,
        batch.observations_inserted,
        batch.observations_updated,
        batch.observations_skipped,
        batch.observations_rejected,
    ) == (3, 3, 3, 3, 0, 0, 0)
    assert batch.raw_response_checksum is not None
    assert batch.statistical_content_checksum is not None

    observations = list(
        session.scalars(
            select(db.TradeObservation).order_by(db.TradeObservation.time_period)
        )
    )
    assert len(observations) == 3
    assert len({row.source_key_hash for row in observations}) == 3
    assert [row.time_period for row in observations] == ["2022", "2023", "2024"]
    # SQLite's NUMERIC test adapter round-trips through binary floating point;
    # PostgreSQL preserves the unconstrained NUMERIC values exactly.
    assert {
        row.primary_value.quantize(Decimal("0.001")) for row in observations
    } == {
        value.quantize(Decimal("0.001")) for value in EXPECTED_VALUES.values()
    }
    assert all(row.first_ingestion_batch_id == batch.id for row in observations)
    assert all(row.last_ingestion_batch_id == batch.id for row in observations)
    assert all(row.source_key and row.observation_content_hash for row in observations)

    reporters = list(
        session.scalars(
            select(db.GeoArea).where(
                db.GeoArea.id.in_({row.reference_geo_id for row in observations})
            )
        )
    )
    assert len(reporters) == 1
    assert (
        reporters[0].name_en,
        reporters[0].iso2,
        reporters[0].iso3,
        reporters[0].area_type,
        reporters[0].au_member,
    ) == ("Tunisia", "TN", "TUN", db.AreaType.COUNTRY, True)
    counterparts = list(
        session.scalars(
            select(db.GeoArea).where(
                db.GeoArea.id.in_({row.counterpart_geo_id for row in observations})
            )
        )
    )
    assert len(counterparts) == 1
    assert counterparts[0].name_en == "World"
    assert counterparts[0].area_type is db.AreaType.AGGREGATE
    assert counterparts[0].au_member is False


def test_non_au_reporter_creates_rejection(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    payload = copy.deepcopy(FIXTURES["2022"])
    payload["data"][0].update(
        {"reporterCode": 124, "reporterDesc": "Canada", "reporterISO": "CAN"}
    )
    query = replace(QUERY, periods=("2022",), reporter_code="124")

    batch = ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=lambda _period, _parameters: payload,
    )

    assert batch.status is db.IngestionBatchStatus.FAILED
    assert batch.observations_received == 1
    assert batch.observations_parsed == 1
    assert batch.observations_accepted == 0
    assert batch.observations_rejected == 1
    rejection = session.scalar(select(db.ObservationRejection))
    assert rejection is not None
    assert (
        rejection.reason_code
        is db.RejectionReasonCode.REFERENCE_AREA_NOT_AU_MEMBER
    )
    assert rejection.raw_observation["reporterCode"] == 124
    assert session.scalar(select(func.count()).select_from(db.TradeObservation)) == 0


def test_fatal_fetch_error_finalizes_batch_as_failed(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database

    def fail(_period: str, _parameters: dict[str, str]):
        raise RuntimeError("synthetic provider outage")

    with pytest.raises(TradeIngestionError) as error:
        ingest_trade_query(
            session,
            dataset_id=dataset.id,
            query=QUERY,
            fetch_response=fail,
        )

    batch = session.get(db.IngestionBatch, error.value.batch_id)
    assert batch is not None
    assert batch.status is db.IngestionBatchStatus.FAILED
    assert batch.finished_at is not None
    assert batch.error_message == "synthetic provider outage"
    assert session.scalar(select(func.count()).select_from(db.TradeObservation)) == 0


def test_duplicate_record_inside_one_batch_does_not_create_duplicate_row(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    payload = copy.deepcopy(FIXTURES["2022"])
    payload["data"].append(copy.deepcopy(payload["data"][0]))
    payload["count"] = 2
    query = replace(QUERY, periods=("2022",), max_records=2)

    batch = ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=lambda _period, _parameters: payload,
    )

    assert batch.status is db.IngestionBatchStatus.SUCCESS
    assert batch.observations_received == 2
    assert batch.observations_accepted == 2
    assert batch.observations_inserted == 1
    assert batch.observations_skipped == 1
    assert session.scalar(select(func.count()).select_from(db.TradeObservation)) == 1

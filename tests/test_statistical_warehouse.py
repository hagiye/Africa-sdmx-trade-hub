"""Statistical warehouse model and database-constraint tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import models as db
from scripts.seed_stat_dataset import seed_stat_dataset


def _dataset(session: Session) -> db.StatDataset:
    dataset = db.StatDataset(
        agency="UNSD",
        dataflow_id="IMTS_A",
        dataflow_version="1.0",
        dsd_agency="UNSD",
        dsd_id="IMTS",
        dsd_version="1.2",
        name="International Merchandise Trade Statistics, Annual",
        source_system="UN_COMTRADE",
    )
    session.add(dataset)
    session.flush()
    return dataset


def _area(session: Session, code: str, name: str, area_type: db.AreaType) -> db.GeoArea:
    area = db.GeoArea(
        iso2=code if len(code) == 2 else None,
        iso3=None,
        numeric_code=None,
        name_en=name,
        name_fr=name,
        area_type=area_type,
        au_member=area_type is db.AreaType.COUNTRY,
    )
    session.add(area)
    session.flush()
    return area


def _batch(session: Session, dataset: db.StatDataset) -> db.IngestionBatch:
    batch = db.IngestionBatch(
        dataset_id=dataset.id,
        source_system="UN_COMTRADE",
    )
    session.add(batch)
    session.flush()
    return batch


def _trade_observation(
    dataset: db.StatDataset,
    reference: db.GeoArea,
    counterpart: db.GeoArea,
    batch: db.IngestionBatch,
    *,
    source_key_hash: str = "a" * 64,
) -> db.TradeObservation:
    return db.TradeObservation(
        dataset_id=dataset.id,
        reference_area_source_code="788",
        reference_geo_id=reference.id,
        counterpart_area_source_code="0",
        counterpart_geo_id=counterpart.id,
        trade_flow_code="M",
        frequency_code="A",
        commodity_code="TOTAL",
        commodity_classification="S4",
        commodity_sdmx_code="SITC4_TOTAL",
        time_period="2022",
        primary_value=Decimal("100"),
        quantity=Decimal("0"),
        net_weight=Decimal("0"),
        gross_weight=Decimal("0"),
        cif_value=Decimal("100"),
        fob_value=None,
        source_dimensions={"FREQ": "A", "REF_AREA": "TN"},
        source_attributes={"isReported": False},
        source_fields={"reporterCode": 788},
        source_key="FREQ=A|REF_AREA=TN|TIME_PERIOD=2022",
        source_key_hash=source_key_hash,
        observation_content_hash="b" * 64,
        first_ingestion_batch_id=batch.id,
        last_ingestion_batch_id=batch.id,
    )


def test_database_enforces_dataset_source_hash_uniqueness(
    db_session: Session,
) -> None:
    dataset = _dataset(db_session)
    reference = _area(db_session, "TN", "Tunisia", db.AreaType.COUNTRY)
    counterpart = _area(db_session, "W0", "World", db.AreaType.AGGREGATE)
    batch = _batch(db_session, dataset)
    first = _trade_observation(dataset, reference, counterpart, batch)
    db_session.add(first)
    db_session.commit()
    assert first.id is not None

    duplicate = _trade_observation(dataset, reference, counterpart, batch)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    count = db_session.scalar(select(func.count()).select_from(db.TradeObservation))
    assert count == 1


def test_new_batch_defaults_and_success_transition(db_session: Session) -> None:
    dataset = _dataset(db_session)
    batch = _batch(db_session, dataset)

    assert batch.status is db.IngestionBatchStatus.RUNNING
    assert batch.finished_at is None
    assert batch.observations_received == 0
    assert batch.observations_parsed == 0
    assert batch.observations_accepted == 0
    assert batch.observations_inserted == 0
    assert batch.observations_updated == 0
    assert batch.observations_skipped == 0
    assert batch.observations_rejected == 0

    batch.status = db.IngestionBatchStatus.SUCCESS
    batch.finished_at = datetime.now(timezone.utc)
    db_session.commit()
    assert batch.status is db.IngestionBatchStatus.SUCCESS
    assert batch.finished_at is not None


def test_failed_batch_can_record_error_message(db_session: Session) -> None:
    dataset = _dataset(db_session)
    batch = _batch(db_session, dataset)
    batch.status = db.IngestionBatchStatus.FAILED
    batch.error_message = "Synthetic provider failure"
    batch.finished_at = datetime.now(timezone.utc)
    db_session.commit()

    assert batch.status is db.IngestionBatchStatus.FAILED
    assert batch.error_message == "Synthetic provider failure"


def test_rejection_stores_evidence(db_session: Session) -> None:
    dataset = _dataset(db_session)
    batch = _batch(db_session, dataset)
    rejection = db.ObservationRejection(
        ingestion_batch_id=batch.id,
        source_key="REF_AREA=ZZ|TIME_PERIOD=2022",
        source_key_hash="c" * 64,
        concept_id="REF_AREA",
        invalid_value="ZZ",
        reason_code=db.RejectionReasonCode.UNMAPPED_REFERENCE_AREA,
        severity=db.RejectionSeverity.ERROR,
        message="Reporter code has no canonical geography mapping",
        raw_observation={"reporterCode": 999999, "period": "2022"},
    )
    db_session.add(rejection)
    db_session.commit()

    assert rejection.id is not None
    assert rejection.ingestion_batch_id == batch.id
    assert rejection.source_key_hash == "c" * 64
    assert rejection.concept_id == "REF_AREA"
    assert rejection.invalid_value == "ZZ"
    assert rejection.raw_observation["reporterCode"] == 999999


def test_stat_dataset_seed_uses_registry_name_and_is_idempotent(
    db_session: Session,
) -> None:
    db_session.add(db.Agency(agency_id="UNSD", name="UNSD"))
    db_session.add(
        db.Dataflow(
            agency_id="UNSD",
            dataflow_id="IMTS_A",
            version="1.0",
            name="Registry-provided IMTS annual name",
            source_url="https://registry.invalid/IMTS_A",
            retrieved_at=datetime.now(timezone.utc),
            checksum="d" * 64,
            dsd_agency_id="UNSD",
            dsd_id="IMTS",
            dsd_version="1.2",
        )
    )
    db_session.commit()

    first = seed_stat_dataset(db_session)
    second = seed_stat_dataset(db_session)

    assert first.action == "INSERTED"
    assert second.action == "EXISTING"
    assert first.dataset_id == second.dataset_id
    assert second.name == "Registry-provided IMTS annual name"
    count = db_session.scalar(select(func.count()).select_from(db.StatDataset))
    assert count == 1

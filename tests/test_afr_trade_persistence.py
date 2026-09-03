"""AFR_TRADE target warehouse lifecycle and lineage tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import models as db
from app.harmonization.afr_trade_models import (
    HarmonizationResult,
    HarmonizationStatus,
    identify_target_observation,
)
from app.harmonization.afr_trade_validation import (
    TargetValidationContext,
    validate_afr_trade_observation,
)
from app.harmonization.harmonization_pipeline import (
    ensure_target_dataset,
    harmonize_source_warehouse,
    normalized_from_warehouse,
    persist_validated_target,
)
from app.pipelines.ingest_trade_data import ingest_trade_query
from app.validation.models import ValidationSummary
from tests.test_afr_trade_transformer import _complete_target, harmonization_database
from tests.test_trade_ingestion import FIXTURES, QUERY, ingestion_database


@pytest.fixture
def persistence_database(
    harmonization_database: tuple[Session, db.StatDataset],
) -> tuple[Session, db.StatDataset]:
    session, dataset = harmonization_database
    ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=QUERY,
        fetch_response=lambda period, _parameters: FIXTURES[period],
    )
    return session, dataset


def _batch(
    session: Session, source: db.StatDataset, target: db.StatDataset
) -> db.HarmonizationBatch:
    row = db.HarmonizationBatch(
        source_dataset_id=source.id,
        target_dataset_id=target.id,
        target_dataflow_agency="AFRSTAT",
        target_dataflow_id="AFR_TRADE",
        target_dataflow_version="1.0",
        target_dsd_agency="AFRSTAT",
        target_dsd_id="AFR_TRADE",
        target_dsd_version="1.0",
        mapping_definition_id="UNSD_IMTS_TO_AFR_TRADE",
        mapping_version="1.0",
        status=db.HarmonizationBatchStatus.RUNNING,
    )
    session.add(row)
    session.flush()
    return row


def _valid_result(
    session: Session,
    dataset: db.StatDataset,
    source_row: db.TradeObservation,
    *,
    value: Decimal = Decimal("10"),
) -> HarmonizationResult:
    source = normalized_from_warehouse(session, dataset, source_row)
    target = _complete_target(
        time_period=source.time_period,
        obs_value=value,
    )
    validation = validate_afr_trade_observation(
        target, TargetValidationContext.from_session(session)
    )
    return HarmonizationResult(
        source_observation=source,
        source_validation=ValidationSummary(),
        target_observation=target,
        target_validation=validation,
        target_identity=identify_target_observation(target),
        status=HarmonizationStatus.SUCCESS,
    )


def test_insert_skip_update_and_source_lineage(
    persistence_database: tuple[Session, db.StatDataset],
) -> None:
    session, source_dataset = persistence_database
    target_dataset = ensure_target_dataset(session)
    source_row = session.scalar(
        select(db.TradeObservation).order_by(db.TradeObservation.time_period)
    )
    assert source_row is not None
    first_batch = _batch(session, source_dataset, target_dataset)
    inserted = persist_validated_target(
        session,
        batch=first_batch,
        target_dataset=target_dataset,
        source_row=source_row,
        result=_valid_result(session, source_dataset, source_row),
    )
    first_id = inserted.observation.id
    session.commit()

    second_batch = _batch(session, source_dataset, target_dataset)
    skipped = persist_validated_target(
        session,
        batch=second_batch,
        target_dataset=target_dataset,
        source_row=source_row,
        result=_valid_result(session, source_dataset, source_row),
    )
    third_batch = _batch(session, source_dataset, target_dataset)
    updated = persist_validated_target(
        session,
        batch=third_batch,
        target_dataset=target_dataset,
        source_row=source_row,
        result=_valid_result(
            session, source_dataset, source_row, value=Decimal("11")
        ),
    )
    session.commit()

    row = session.get(db.AfrTradeObservation, first_id)
    assert (inserted.action, skipped.action, updated.action) == (
        "INSERT", "SKIP", "UPDATE"
    )
    assert session.scalar(select(func.count()).select_from(db.AfrTradeObservation)) == 1
    assert row is not None and row.obs_value == Decimal("11")
    assert row.source_trade_observation_id == source_row.id
    assert row.first_harmonization_batch_id == first_batch.id
    assert row.last_harmonization_batch_id == third_batch.id


def test_mapping_version_change_requires_explicit_policy(
    persistence_database: tuple[Session, db.StatDataset],
) -> None:
    session, source_dataset = persistence_database
    target_dataset = ensure_target_dataset(session)
    source_row = session.scalar(select(db.TradeObservation))
    assert source_row is not None
    first = _batch(session, source_dataset, target_dataset)
    result = _valid_result(session, source_dataset, source_row)
    persist_validated_target(
        session, batch=first, target_dataset=target_dataset,
        source_row=source_row, result=result,
    )
    second = _batch(session, source_dataset, target_dataset)
    decision = persist_validated_target(
        session, batch=second, target_dataset=target_dataset,
        source_row=source_row, result=result, mapping_version="2.0",
    )

    assert decision.action == "VERSION_CONFLICT"
    assert decision.observation is not None
    assert decision.observation.mapping_version == "1.0"


def test_database_unique_constraint_rejects_duplicate_target_identity(
    persistence_database: tuple[Session, db.StatDataset],
) -> None:
    session, source_dataset = persistence_database
    target_dataset = ensure_target_dataset(session)
    source_row = session.scalar(select(db.TradeObservation))
    assert source_row is not None
    batch = _batch(session, source_dataset, target_dataset)
    decision = persist_validated_target(
        session, batch=batch, target_dataset=target_dataset,
        source_row=source_row, result=_valid_result(session, source_dataset, source_row),
    )
    row = decision.observation
    assert row is not None
    session.add(
        db.AfrTradeObservation(
            **{
                column.name: getattr(row, column.name)
                for column in db.AfrTradeObservation.__table__.columns
                if column.name not in {"id", "created_at", "updated_at"}
            }
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_current_real_observations_are_rejected_not_persisted(
    persistence_database: tuple[Session, db.StatDataset],
) -> None:
    session, source_dataset = persistence_database
    batch = harmonize_source_warehouse(
        session, source_dataset_id=source_dataset.id
    )

    assert batch.status is db.HarmonizationBatchStatus.PARTIAL
    assert (
        batch.source_observations_received,
        batch.source_observations_valid,
        batch.observations_transformed,
        batch.observations_inserted,
        batch.observations_updated,
        batch.observations_skipped,
        batch.observations_rejected,
    ) == (3, 3, 3, 0, 0, 0, 3)
    assert session.scalar(select(func.count()).select_from(db.AfrTradeObservation)) == 0
    assert session.scalar(select(func.count()).select_from(db.HarmonizationRejection)) >= 3

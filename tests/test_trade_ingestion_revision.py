"""Offline source-revision behavior using explicitly synthetic fixture data."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.pipelines.ingest_trade_data import ingest_trade_query
from app.pipelines.observation_identity import identify_observation
from app.pipelines.trade_normalizer import normalize_trade_observation
from app.sdmx.data_parser import parse_comtrade_response
from tests.test_trade_ingestion import FIXTURES, QUERY, ingestion_database


SYNTHETIC_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "data"
    / "synthetic"
    / "un_comtrade_tunisia_imports_world_2023_revised.json"
)
SYNTHETIC_REVISION = json.loads(SYNTHETIC_FIXTURE_PATH.read_text(encoding="utf-8"))
ORIGINAL_VALUE = Decimal("25930493874.99")
REVISED_VALUE = Decimal("25930494874.99")


def _ingest_payload(
    session: Session,
    dataset: db.StatDataset,
    payload: dict,
    *,
    period: str = "2023",
) -> db.IngestionBatch:
    query = replace(QUERY, periods=(period,))
    return ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=lambda _period, _parameters: copy.deepcopy(payload),
    )


def test_synthetic_fixture_changes_only_primary_value() -> None:
    original = copy.deepcopy(FIXTURES["2023"])
    revised = copy.deepcopy(SYNTHETIC_REVISION)
    original_value = Decimal(str(original["data"][0].pop("primaryValue")))
    revised_value = Decimal(str(revised["data"][0].pop("primaryValue")))

    assert original == revised
    assert original_value == ORIGINAL_VALUE
    assert revised_value == REVISED_VALUE
    assert revised_value - original_value == Decimal("1000.00")


def test_revision_identity_is_stable_before_database_update(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, _dataset = ingestion_database
    original_parsed = parse_comtrade_response(FIXTURES["2023"]).observations[0]
    revised_parsed = parse_comtrade_response(SYNTHETIC_REVISION).observations[0]
    original = normalize_trade_observation(original_parsed, session).observation
    revised = normalize_trade_observation(revised_parsed, session).observation

    assert original is not None and revised is not None
    original_identity = identify_observation(original)
    revised_identity = identify_observation(revised)
    assert original_identity.source_key == revised_identity.source_key
    assert original_identity.source_key_hash == revised_identity.source_key_hash
    assert (
        original_identity.observation_content_hash
        != revised_identity.observation_content_hash
    )


def test_changed_primary_value_updates_same_database_row(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    first = _ingest_payload(session, dataset, FIXTURES["2023"])
    original = session.scalar(select(db.TradeObservation))
    assert original is not None
    row_count_before = session.scalar(
        select(func.count()).select_from(db.TradeObservation)
    )
    original_id = original.id
    original_source_key = original.source_key
    original_source_hash = original.source_key_hash
    original_content_hash = original.observation_content_hash
    original_created_at = original.created_at
    original_first_batch = original.first_ingestion_batch_id
    original_source_value = original.source_fields["primaryValue"]

    # SQLite timestamps have one-second resolution. Set a deterministic old
    # value so the ORM on-update behavior can be asserted without sleeping.
    original.updated_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    session.commit()
    original_updated_at = original.updated_at

    second = _ingest_payload(session, dataset, SYNTHETIC_REVISION)
    revised = session.scalar(select(db.TradeObservation))
    row_count_after = session.scalar(
        select(func.count()).select_from(db.TradeObservation)
    )

    assert revised is not None
    assert (
        first.observations_inserted,
        first.observations_updated,
        first.observations_skipped,
    ) == (1, 0, 0)
    assert (
        second.observations_received,
        second.observations_parsed,
        second.observations_accepted,
        second.observations_inserted,
        second.observations_updated,
        second.observations_skipped,
        second.observations_rejected,
    ) == (1, 1, 1, 0, 1, 0, 0)
    assert row_count_before == row_count_after == 1
    assert revised.id == original_id
    assert revised.source_key == original_source_key
    assert revised.source_key_hash == original_source_hash
    assert revised.observation_content_hash != original_content_hash
    assert revised.primary_value.quantize(Decimal("0.01")) == REVISED_VALUE
    assert original_source_value == float(ORIGINAL_VALUE)
    assert revised.source_fields["primaryValue"] == float(REVISED_VALUE)
    assert revised.first_ingestion_batch_id == original_first_batch == first.id
    assert revised.last_ingestion_batch_id == second.id
    assert revised.created_at == original_created_at
    assert revised.updated_at != original_updated_at


def test_changed_time_period_inserts_new_identity(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    first = _ingest_payload(session, dataset, FIXTURES["2023"])
    original = session.scalar(select(db.TradeObservation))
    assert original is not None
    changed_period = copy.deepcopy(FIXTURES["2023"])
    changed_period["data"][0]["period"] = "2099"

    second = _ingest_payload(session, dataset, changed_period, period="2099")
    observations = list(session.scalars(select(db.TradeObservation)))

    assert first.observations_inserted == 1
    assert second.observations_inserted == 1
    assert second.observations_updated == second.observations_skipped == 0
    assert len(observations) == 2
    assert len({row.source_key_hash for row in observations}) == 2
    assert {row.time_period for row in observations} == {"2023", "2099"}


def test_meaningful_attribute_only_change_updates_same_row(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    first = _ingest_payload(session, dataset, FIXTURES["2023"])
    original = session.scalar(select(db.TradeObservation))
    assert original is not None
    original_source_hash = original.source_key_hash
    original_content_hash = original.observation_content_hash
    attribute_revision = copy.deepcopy(FIXTURES["2023"])
    attribute_revision["data"][0]["isReported"] = True

    second = _ingest_payload(session, dataset, attribute_revision)
    revised = session.scalar(select(db.TradeObservation))

    assert revised is not None
    assert first.observations_inserted == 1
    assert second.observations_updated == 1
    assert second.observations_inserted == second.observations_skipped == 0
    assert revised.source_key_hash == original_source_hash
    assert revised.observation_content_hash != original_content_hash
    assert revised.primary_value.quantize(Decimal("0.01")) == ORIGINAL_VALUE
    assert revised.source_attributes["isReported"] is True
    assert revised.source_fields["isReported"] is True
    assert revised.first_ingestion_batch_id == first.id
    assert revised.last_ingestion_batch_id == second.id


def test_volatile_envelope_change_skips_instead_of_updating(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    first = _ingest_payload(session, dataset, FIXTURES["2023"])
    original_hash = session.scalar(
        select(db.TradeObservation.observation_content_hash)
    )
    envelope_change = copy.deepcopy(FIXTURES["2023"])
    envelope_change["elapsedTime"] = "SYNTHETIC VOLATILE CHANGE"

    second = _ingest_payload(session, dataset, envelope_change)

    assert second.observations_inserted == second.observations_updated == 0
    assert second.observations_skipped == 1
    assert first.raw_response_checksum != second.raw_response_checksum
    assert (
        first.statistical_content_checksum
        == second.statistical_content_checksum
    )
    assert (
        session.scalar(select(db.TradeObservation.observation_content_hash))
        == original_hash
    )

"""Offline proof that unchanged trade re-ingestion is idempotent."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import models as db
from app.pipelines.ingest_trade_data import TradeQuery, ingest_trade_query
from tests.test_trade_ingestion import FIXTURES, QUERY, ingestion_database


def _fetch_fixtures(period: str, _parameters: dict[str, str]):
    return copy.deepcopy(FIXTURES[period])


def _ingest(
    session: Session, dataset: db.StatDataset, query: TradeQuery = QUERY
) -> db.IngestionBatch:
    return ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=_fetch_fixtures,
    )


def _observation_state(session: Session) -> dict[str, tuple[str, str, int, int]]:
    return {
        row.time_period: (
            row.source_key_hash,
            row.observation_content_hash,
            row.first_ingestion_batch_id,
            row.last_ingestion_batch_id,
        )
        for row in session.scalars(select(db.TradeObservation))
    }


def _reverse_json_objects(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _reverse_json_objects(item)
            for key, item in reversed(list(value.items()))
        }
    if isinstance(value, list):
        return [_reverse_json_objects(item) for item in value]
    return value


def test_second_identical_fixture_ingestion_skips_without_new_rows(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    first = _ingest(session, dataset)
    before = _observation_state(session)

    second = _ingest(session, dataset)
    after = _observation_state(session)

    assert first.status is db.IngestionBatchStatus.SUCCESS
    assert first.observations_inserted == 3
    assert second.status is db.IngestionBatchStatus.SUCCESS
    assert (
        second.observations_received,
        second.observations_parsed,
        second.observations_accepted,
        second.observations_inserted,
        second.observations_updated,
        second.observations_skipped,
        second.observations_rejected,
    ) == (3, 3, 3, 0, 0, 3, 0)
    assert session.scalar(select(func.count()).select_from(db.TradeObservation)) == 3
    assert set(before) == set(after) == {"2022", "2023", "2024"}
    for period in before:
        before_source, before_content, before_first, before_last = before[period]
        after_source, after_content, after_first, after_last = after[period]
        assert after_source == before_source
        assert after_content == before_content
        assert after_first == before_first == first.id
        assert before_last == first.id
        assert after_last == second.id
    assert (
        first.statistical_content_checksum
        == second.statistical_content_checksum
    )


def test_reordered_json_keys_remain_unchanged_and_skip(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    query = replace(QUERY, periods=("2022",))
    first = _ingest(session, dataset, query)
    original = session.scalar(select(db.TradeObservation))
    assert original is not None
    original_state = (original.source_key_hash, original.observation_content_hash)
    reordered = _reverse_json_objects(copy.deepcopy(FIXTURES["2022"]))

    second = ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=lambda _period, _parameters: reordered,
    )
    stored = session.scalar(select(db.TradeObservation))

    assert stored is not None
    assert second.observations_inserted == 0
    assert second.observations_updated == 0
    assert second.observations_skipped == 1
    assert (stored.source_key_hash, stored.observation_content_hash) == original_state
    assert stored.first_ingestion_batch_id == first.id
    assert stored.last_ingestion_batch_id == second.id
    assert first.raw_response_checksum == second.raw_response_checksum
    assert (
        first.statistical_content_checksum
        == second.statistical_content_checksum
    )


def test_volatile_envelope_change_only_changes_raw_batch_checksum(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    query = replace(QUERY, periods=("2022",))
    first = _ingest(session, dataset, query)
    original_content_hash = session.scalar(
        select(db.TradeObservation.observation_content_hash)
    )
    changed_envelope = copy.deepcopy(FIXTURES["2022"])
    changed_envelope["elapsedTime"] = "synthetic different elapsed time"

    second = ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=lambda _period, _parameters: changed_envelope,
    )

    assert second.observations_skipped == 1
    assert second.observations_inserted == second.observations_updated == 0
    assert first.raw_response_checksum != second.raw_response_checksum
    assert (
        first.statistical_content_checksum
        == second.statistical_content_checksum
    )
    assert (
        session.scalar(select(db.TradeObservation.observation_content_hash))
        == original_content_hash
    )


def test_duplicate_inside_one_response_inserts_once_then_skips(
    ingestion_database: tuple[Session, db.StatDataset],
) -> None:
    session, dataset = ingestion_database
    query = replace(QUERY, periods=("2022",), max_records=2)
    duplicate_payload = copy.deepcopy(FIXTURES["2022"])
    duplicate_payload["data"].append(copy.deepcopy(duplicate_payload["data"][0]))
    duplicate_payload["count"] = 2

    batch = ingest_trade_query(
        session,
        dataset_id=dataset.id,
        query=query,
        fetch_response=lambda _period, _parameters: duplicate_payload,
    )

    assert batch.status is db.IngestionBatchStatus.SUCCESS
    assert batch.observations_received == batch.observations_accepted == 2
    assert batch.observations_inserted == 1
    assert batch.observations_skipped == 1
    assert session.scalar(select(func.count()).select_from(db.TradeObservation)) == 1


def test_unique_constraint_race_is_reloaded_and_skipped(
    ingestion_database: tuple[Session, db.StatDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate a stale SELECT so the unique constraint wins an insert race."""
    session, dataset = ingestion_database
    query = replace(QUERY, periods=("2022",))
    first = _ingest(session, dataset, query)
    real_scalar = session.scalar
    stale_lookup_returned = False

    def stale_once(statement, *args, **kwargs):
        nonlocal stale_lookup_returned
        descriptions = getattr(statement, "column_descriptions", ())
        entity = descriptions[0].get("entity") if descriptions else None
        if entity is db.TradeObservation and not stale_lookup_returned:
            stale_lookup_returned = True
            return None
        return real_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(session, "scalar", stale_once)
    second = _ingest(session, dataset, query)

    assert stale_lookup_returned is True
    assert second.status is db.IngestionBatchStatus.SUCCESS
    assert second.observations_inserted == second.observations_updated == 0
    assert second.observations_skipped == 1
    assert real_scalar(select(func.count()).select_from(db.TradeObservation)) == 1
    stored = real_scalar(select(db.TradeObservation))
    assert stored is not None
    assert stored.first_ingestion_batch_id == first.id
    assert stored.last_ingestion_batch_id == second.id

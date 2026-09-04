"""Recruiter-facing explorer support API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import models as db
from app.database.session import get_db
from app.harmonization.harmonization_pipeline import (
    ensure_target_dataset,
    harmonize_source_warehouse,
    persist_validated_target,
)
from app.main import app
from tests.test_afr_trade_persistence import (
    _batch,
    _valid_result,
    persistence_database,
)
from tests.test_afr_trade_transformer import harmonization_database
from tests.test_trade_ingestion import ingestion_database


def test_explorer_summaries_mappings_findings_and_lineage(
    persistence_database: tuple[Session, db.StatDataset],
) -> None:
    session, source_dataset = persistence_database
    initial_batch = harmonize_source_warehouse(
        session, source_dataset_id=source_dataset.id
    )
    target_dataset = ensure_target_dataset(session)
    source_row = session.scalar(
        select(db.TradeObservation).order_by(db.TradeObservation.time_period)
    )
    assert source_row is not None
    successful_batch = _batch(session, source_dataset, target_dataset)
    decision = persist_validated_target(
        session,
        batch=successful_batch,
        target_dataset=target_dataset,
        source_row=source_row,
        result=_valid_result(session, source_dataset, source_row),
    )
    session.commit()
    assert decision.observation is not None

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            summary = client.get("/api/v1/summary")
            assert summary.status_code == 200
            assert summary.json()["harmonised_observations"] == 3
            assert summary.json()["source_observations"] == 3

            validation = client.get("/api/v1/validation/summary")
            rules = client.get("/api/v1/validation/rules")
            findings = client.get("/api/v1/validation/findings?limit=10")
            assert validation.status_code == rules.status_code == findings.status_code == 200
            assert validation.json()["validated_observations"] == 3
            assert findings.json()["limit"] == 10

            harmonization = client.get("/api/v1/harmonization/summary")
            mappings = client.get("/api/v1/harmonization/mappings")
            assert harmonization.status_code == mappings.status_code == 200
            assert harmonization.json()["latest_batch"]["id"] == successful_batch.id
            assert len(mappings.json()) == 33
            assert {item["mapping_type"] for item in mappings.json()} >= {
                "DIRECT",
                "DROP",
                "DEFER",
            }

            lineage = client.get(
                f"/api/v1/afr-trade/{decision.observation.id}/lineage"
            )
            assert lineage.status_code == 200
            assert lineage.json()["source_observation"]["id"] == source_row.id
            assert lineage.json()["source_ingestion_batch"] is not None
            assert client.get("/api/v1/afr-trade/999999/lineage").status_code == 404
            assert initial_batch.observations_inserted == 3
            assert initial_batch.observations_rejected == 0
    finally:
        app.dependency_overrides.clear()

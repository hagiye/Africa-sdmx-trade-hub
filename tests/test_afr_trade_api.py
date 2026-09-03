"""Read-only AFR_TRADE statistical REST API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import models as db
from app.database.session import get_db
from app.harmonization.harmonization_pipeline import (
    ensure_target_dataset,
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


def test_afr_trade_list_filters_pagination_metadata_and_detail(
    persistence_database: tuple[Session, db.StatDataset],
) -> None:
    session, source_dataset = persistence_database
    target_dataset = ensure_target_dataset(session)
    batch = _batch(session, source_dataset, target_dataset)
    source_rows = session.query(db.TradeObservation).order_by(
        db.TradeObservation.time_period
    ).all()
    for source_row in source_rows:
        persist_validated_target(
            session,
            batch=batch,
            target_dataset=target_dataset,
            source_row=source_row,
            result=_valid_result(session, source_dataset, source_row),
        )
    session.commit()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            page = client.get("/api/v1/afr-trade?limit=2&offset=1")
            assert page.status_code == 200
            assert page.json()["total"] == 3
            assert len(page.json()["items"]) == 2
            assert page.json()["items"][0]["TIME_PERIOD"] == "2023"
            filtered = client.get(
                "/api/v1/afr-trade",
                params={
                    "ref_area": "TN",
                    "product_scheme": "SITC4",
                    "freq": "A",
                    "start_period": "2023",
                    "end_period": "2023",
                },
            )
            assert filtered.status_code == 200
            assert filtered.json()["total"] == 1
            item = filtered.json()["items"][0]
            assert item["REF_AREA"] == "TN"
            assert item["OBS_VALUE"] == "10"
            assert client.get(f"/api/v1/afr-trade/{item['id']}").status_code == 200
            metadata = client.get("/api/v1/afr-trade/metadata")
            assert metadata.status_code == 200
            assert metadata.json()["DSD"] == {
                "agency": "AFRSTAT",
                "id": "AFR_TRADE",
                "version": "1.0",
            }
            assert client.get("/api/v1/afr-trade?limit=1001").status_code == 422
            assert client.get("/api/v1/afr-trade/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()

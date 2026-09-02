"""Read-only metadata API tests, including 404 and pagination behavior."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.main import app
from app.pipelines.import_structures import import_structures


@pytest.fixture
def api_client(db_session: Session, fixture_sdmx_client):
    import_structures(db_session, fixture_sdmx_client)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_dataflow_list_and_detail(api_client: TestClient) -> None:
    listing = api_client.get("/api/v1/dataflows")
    detail = api_client.get("/api/v1/dataflows/UNSD/IMTS_A/1.0")

    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert detail.status_code == 200
    assert detail.json()["labels"]["fr"] == "Commerce international annuel"
    assert detail.json()["dsd"] == {
        "agency": "UNSD",
        "id": "IMTS",
        "version": "1.2",
    }


def test_dsd_and_ordered_dimensions(api_client: TestClient) -> None:
    detail = api_client.get("/api/v1/dsd/UNSD/IMTS/1.2")
    dimensions = api_client.get("/api/v1/dsd/UNSD/IMTS/1.2/dimensions")

    assert detail.status_code == 200
    assert detail.json()["labels"]["fr"].startswith("Statistiques du commerce")
    assert [item["concept"] for item in dimensions.json()] == [
        "FREQ",
        "TIME_PERIOD",
    ]
    assert dimensions.json()[0]["position"] == 1
    assert dimensions.json()[1]["role"] == "time"


def test_codelist_list_detail_and_paginated_codes(api_client: TestClient) -> None:
    listing = api_client.get("/api/v1/codelists")
    detail = api_client.get("/api/v1/codelists/SDMX/CL_FREQ/2.0")
    page = api_client.get(
        "/api/v1/codelists/SDMX/CL_FREQ/2.0/codes?page=2&page_size=1"
    )

    assert listing.status_code == 200
    assert detail.json()["code_count"] == 2
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["pages"] == 2
    assert page.json()["items"][0] == {
        "code": "M",
        "parent_code": "A",
        "labels": {"en": "Monthly", "fr": "Mensuel"},
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dataflows/NOPE/NOPE/1.0",
        "/api/v1/dsd/NOPE/NOPE/1.0",
        "/api/v1/dsd/NOPE/NOPE/1.0/dimensions",
        "/api/v1/codelists/NOPE/NOPE/1.0",
        "/api/v1/codelists/NOPE/NOPE/1.0/codes",
    ],
)
def test_missing_metadata_returns_404(api_client: TestClient, path: str) -> None:
    response = api_client.get(path)

    assert response.status_code == 404

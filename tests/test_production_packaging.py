"""Production configuration and same-origin SPA serving tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.config import Settings
from app.main import app


def test_hosted_postgres_urls_are_normalized_for_psycopg() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:password@db.example/demo?sslmode=require",
    )
    assert settings.sqlalchemy_database_url == (
        "postgresql+psycopg://user:password@db.example/demo?sslmode=require"
    )


def test_production_rejects_wildcard_cors() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        cors_allowed_origins="*",
    )
    with pytest.raises(ValueError, match="cannot contain"):
        _ = settings.allowed_origins


def test_frontend_routes_and_security_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend = tmp_path / "frontend" / "dist"
    frontend.mkdir(parents=True)
    marker = "<html><body>production-spa-marker</body></html>"
    (frontend / "index.html").write_text(marker, encoding="utf-8")
    monkeypatch.setattr(main_module, "FRONTEND_DIST", frontend)

    with TestClient(app) as client:
        for route in (
            "/",
            "/explore",
            "/metadata",
            "/validation",
            "/harmonization",
            "/architecture",
        ):
            response = client.get(route)
            assert response.status_code == 200
            assert "production-spa-marker" in response.text

        api_missing = client.get("/api/v1/does-not-exist")
        assert api_missing.status_code == 404
        assert api_missing.json() == {"detail": "Not Found"}
        assert client.get("/.env").status_code == 404

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {
            "status": "healthy",
            "service": "Pan-African SDMX Trade Data Hub",
        }
        assert health.headers["x-content-type-options"] == "nosniff"
        assert health.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in health.headers["content-security-policy"]

        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200

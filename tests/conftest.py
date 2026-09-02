"""Shared deterministic SDMX and database fixtures."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.sdmx.client import SDMXResponse, sha256_bytes, structure_checksum


FIXTURES = Path(__file__).parent / "fixtures"


class FixtureSDMXClient:
    """Serve the representative SDMX message through the client interface."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, str, str]] = []

    def get_structure(
        self,
        structure_type: str,
        agency: str = "all",
        structure_id: str = "all",
        version: str = "latest",
        **_: str,
    ) -> SDMXResponse:
        self.calls.append((structure_type, agency, structure_id, version))
        url = f"https://fixtures.invalid/{structure_type}/{agency}/{structure_id}/{version}"
        return SDMXResponse(
            content=self.payload,
            url=url,
            status_code=200,
            content_type="application/vnd.sdmx.structure+xml;version=3.0",
            elapsed_seconds=0.01,
            checksum=structure_checksum(self.payload),
            raw_checksum=sha256_bytes(self.payload),
        )


@pytest.fixture
def structure_payload() -> bytes:
    return (FIXTURES / "structures.xml").read_bytes()


@pytest.fixture
def fixture_sdmx_client(structure_payload: bytes) -> FixtureSDMXClient:
    return FixtureSDMXClient(structure_payload)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()

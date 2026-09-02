"""HTTP failure handling and checksum tests for the SDMX client."""

import hashlib

import pytest
import requests

from app.sdmx.client import SDMXClient, sha256_bytes, structure_checksum
from app.sdmx.exceptions import SDMXProviderError, SDMXStructureNotFound


class StubResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"<root/>") -> None:
        self.status_code = status_code
        self.content = content
        self.headers = {"Content-Type": "application/xml"}
        self.url = "https://example.invalid/structure"
        self.ok = status_code < 400


class StubSession:
    def __init__(self, result) -> None:
        self.result = result
        self.request = None

    def mount(self, *_args) -> None:
        pass

    def get(self, url, **kwargs):
        self.request = (url, kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_successful_request_records_headers_and_checksums() -> None:
    session = StubSession(StubResponse(content=b"<root><value>1</value></root>"))
    client = SDMXClient("https://example.invalid/sdmx", session=session)

    response = client.get_structure("dataflow", "UNSD", "IMTS_A", "1.0")

    assert response.status_code == 200
    assert response.raw_checksum == hashlib.sha256(response.content).hexdigest()
    assert session.request[1]["headers"]["User-Agent"].startswith(
        "africa-sdmx-trade-hub/"
    )
    assert "version=3.0" in session.request[1]["headers"]["Accept"]


@pytest.mark.parametrize("status", [429, 500])
def test_provider_http_errors_are_not_hidden(status: int) -> None:
    client = SDMXClient(
        "https://example.invalid", session=StubSession(StubResponse(status))
    )

    with pytest.raises(SDMXProviderError, match=f"HTTP {status}"):
        client.get("structure")


def test_404_raises_structure_not_found() -> None:
    client = SDMXClient(
        "https://example.invalid", session=StubSession(StubResponse(404))
    )

    with pytest.raises(SDMXStructureNotFound):
        client.get("missing")


def test_timeout_has_provider_context() -> None:
    client = SDMXClient(
        "https://example.invalid", session=StubSession(requests.Timeout("late"))
    )

    with pytest.raises(SDMXProviderError, match="timed out"):
        client.get("slow")


def test_empty_response_is_rejected() -> None:
    client = SDMXClient(
        "https://example.invalid", session=StubSession(StubResponse(content=b""))
    )

    with pytest.raises(SDMXProviderError, match="empty response"):
        client.get("empty")


def test_structure_checksum_ignores_volatile_header(structure_payload: bytes) -> None:
    later = structure_payload.replace(
        b"fixture-request-1", b"fixture-request-2"
    ).replace(b"2026-09-02T00:00:00Z", b"2026-09-03T12:00:00Z")

    assert sha256_bytes(structure_payload) != sha256_bytes(later)
    assert structure_checksum(structure_payload) == structure_checksum(later)


def test_structure_checksum_detects_metadata_change(structure_payload: bytes) -> None:
    changed = structure_payload.replace(b"IMTS Annual", b"IMTS Annual revised")

    assert structure_checksum(structure_payload) != structure_checksum(changed)


def test_non_xml_checksum_falls_back_to_raw_bytes() -> None:
    payload = b"not XML"

    assert structure_checksum(payload) == sha256_bytes(payload)

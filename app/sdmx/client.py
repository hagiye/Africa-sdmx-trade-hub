"""Resilient HTTP client for public SDMX structure services."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from urllib.parse import quote

import requests
from lxml import etree
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.sdmx.exceptions import SDMXProviderError, SDMXStructureNotFound

LOGGER = logging.getLogger(__name__)
STRUCTURE_ACCEPT = "application/vnd.sdmx.structure+xml;version=3.0"


def sha256_bytes(payload: bytes) -> str:
    """Return the SHA-256 checksum of the exact provider payload."""
    return hashlib.sha256(payload).hexdigest()


def structure_checksum(payload: bytes) -> str:
    """Hash structure content without volatile SDMX message-header fields."""
    try:
        root = etree.fromstring(
            payload,
            parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True),
        )
        structures = next(
            (
                child
                for child in root
                if etree.QName(child).localname == "Structures"
            ),
            root,
        )
        canonical = etree.tostring(
            structures, method="c14n", exclusive=True, with_comments=False
        )
    except (etree.XMLSyntaxError, ValueError):
        canonical = payload
    return sha256_bytes(canonical)


@dataclass(frozen=True)
class SDMXResponse:
    content: bytes
    url: str
    status_code: int
    content_type: str
    elapsed_seconds: float
    checksum: str
    raw_checksum: str


class SDMXClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
        user_agent: str = "africa-sdmx-trade-hub/0.1 (+independent portfolio project)",
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.session = session or requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.headers = {"Accept": STRUCTURE_ACCEPT, "User-Agent": user_agent}

    def get(self, path: str, params: dict[str, str] | None = None) -> SDMXResponse:
        url = self.base_url + path.lstrip("/")
        started = time.perf_counter()
        LOGGER.info("SDMX request url=%s", url)
        try:
            response = self.session.get(
                url, params=params, headers=self.headers, timeout=self.timeout
            )
        except requests.Timeout as exc:
            raise SDMXProviderError(f"SDMX provider timed out requesting {url}") from exc
        except requests.RequestException as exc:
            raise SDMXProviderError(f"SDMX provider request failed for {url}: {exc}") from exc
        elapsed = time.perf_counter() - started
        content_type = response.headers.get("Content-Type", "")
        LOGGER.info(
            "SDMX response status=%s bytes=%s elapsed=%.3fs content_type=%s",
            response.status_code,
            len(response.content),
            elapsed,
            content_type,
        )
        if response.status_code == 404:
            raise SDMXStructureNotFound(f"SDMX structure not found: {response.url}")
        if not response.ok:
            raise SDMXProviderError(
                f"SDMX provider returned HTTP {response.status_code} for {response.url}"
            )
        if not response.content:
            raise SDMXProviderError(f"SDMX provider returned an empty response for {response.url}")
        raw_checksum = sha256_bytes(response.content)
        checksum = structure_checksum(response.content)
        LOGGER.info(
            "SDMX payload raw_checksum=%s structure_checksum=%s",
            raw_checksum,
            checksum,
        )
        return SDMXResponse(
            response.content,
            response.url,
            response.status_code,
            content_type,
            elapsed,
            checksum,
            raw_checksum,
        )

    def get_structure(
        self,
        structure_type: str,
        agency: str = "all",
        structure_id: str = "all",
        version: str = "latest",
        *,
        references: str | None = None,
        detail: str | None = None,
    ) -> SDMXResponse:
        parts = (structure_type, agency, structure_id, version)
        path = "structure/" + "/".join(quote(part, safe="._-") for part in parts)
        params = {
            key: value
            for key, value in {"references": references, "detail": detail}.items()
            if value is not None
        }
        LOGGER.info(
            "SDMX structure type=%s agency=%s id=%s version=%s",
            structure_type,
            agency,
            structure_id,
            version,
        )
        return self.get(path, params=params)

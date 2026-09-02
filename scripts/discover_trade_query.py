"""Discover the real provider query contract for the selected trade Dataflow.

This is a metadata and capability probe only. It never persists observations.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from lxml import etree
from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.database import models as db
from app.database.session import SessionLocal
from app.sdmx.discovery import PROVIDER_NAME, TRADE_DATAFLOW


API_VERSION = "2.0.0 (SDMX 3.0 structures)"
DATA_ACCEPT = "application/vnd.sdmx.data+csv;version=2.0.0"
START_PERIOD = "2023"
END_PERIOD = "2023"
MAX_PROBE_BYTES = 64 * 1024
USER_AGENT = "africa-sdmx-trade-hub/0.1 (+independent portfolio project)"


@dataclass(frozen=True)
class TradeMetadata:
    dataflow: db.Dataflow
    dsd: db.DSD
    dimensions: tuple[db.Dimension, ...]
    sample_values: dict[str, str]


@dataclass(frozen=True)
class ProbeResult:
    url: str
    status_code: int
    content_type: str
    message: str
    truncated: bool


def _find_code_by_label(
    session: Session, dimension: db.Dimension, english_label: str
) -> str:
    """Resolve a code from the imported codelist rather than guessing its ID."""
    if not all(
        (
            dimension.codelist_agency_id,
            dimension.codelist_id,
            dimension.codelist_version,
        )
    ):
        raise RuntimeError(f"{dimension.concept_id} has no imported codelist")

    codelist = session.scalar(
        select(db.Codelist).where(
            db.Codelist.agency_id == dimension.codelist_agency_id,
            db.Codelist.codelist_id == dimension.codelist_id,
            db.Codelist.version == dimension.codelist_version,
        )
    )
    if codelist is None:
        raise RuntimeError(
            f"Codelist not found for dimension {dimension.concept_id}: "
            f"{dimension.codelist_agency_id}:{dimension.codelist_id}"
            f"({dimension.codelist_version})"
        )

    code = session.scalar(
        select(db.Code.code)
        .join(
            db.LocalizedLabel,
            (db.LocalizedLabel.entity_pk == db.Code.id)
            & (db.LocalizedLabel.entity_type == "code"),
        )
        .where(
            db.Code.codelist_id == codelist.id,
            db.LocalizedLabel.language == "en",
            db.LocalizedLabel.label == english_label,
        )
    )
    if code is None:
        raise RuntimeError(
            f"No English label {english_label!r} in "
            f"{codelist.agency_id}:{codelist.codelist_id}({codelist.version})"
        )
    return code


def load_trade_metadata(session: Session) -> TradeMetadata:
    """Load the selected Dataflow, its DSD, and sample codes from PostgreSQL."""
    flow = session.scalar(
        select(db.Dataflow).where(
            db.Dataflow.agency_id == TRADE_DATAFLOW.agency,
            db.Dataflow.dataflow_id == TRADE_DATAFLOW.structure_id,
            db.Dataflow.version == TRADE_DATAFLOW.version,
        )
    )
    if flow is None:
        raise RuntimeError(
            "Stored trade Dataflow not found; run scripts/import_structures.py first"
        )
    if not all((flow.dsd_agency_id, flow.dsd_id, flow.dsd_version)):
        raise RuntimeError("Stored trade Dataflow has no DSD reference")

    dsd = session.scalar(
        select(db.DSD).where(
            db.DSD.agency_id == flow.dsd_agency_id,
            db.DSD.dsd_id == flow.dsd_id,
            db.DSD.version == flow.dsd_version,
        )
    )
    if dsd is None:
        raise RuntimeError(
            f"Referenced DSD not found: {flow.dsd_agency_id}:"
            f"{flow.dsd_id}({flow.dsd_version})"
        )

    dimensions = tuple(
        session.scalars(
            select(db.Dimension)
            .where(db.Dimension.dsd_id == dsd.id)
            .order_by(db.Dimension.position)
        ).all()
    )
    positions = [dimension.position for dimension in dimensions]
    if positions != list(range(1, len(dimensions) + 1)):
        raise RuntimeError(f"DSD dimensions are not contiguous: {positions}")
    time_dimensions = [dimension for dimension in dimensions if dimension.role == "time"]
    if len(time_dimensions) != 1:
        raise RuntimeError(f"Expected one time dimension, found {len(time_dimensions)}")

    by_id = {dimension.concept_id: dimension for dimension in dimensions}
    sample_values = {
        "FREQ": _find_code_by_label(session, by_id["FREQ"], "Annual"),
        "REF_AREA": _find_code_by_label(session, by_id["REF_AREA"], "Kenya"),
        "TRADE_FLOW": _find_code_by_label(
            session, by_id["TRADE_FLOW"], "Total Imports"
        ),
    }
    return TradeMetadata(flow, dsd, dimensions, sample_values)


def build_sample_key(metadata: TradeMetadata) -> str:
    """Build a positional key in DSD order, excluding the time dimension."""
    values = []
    for dimension in metadata.dimensions:
        if dimension.role == "time":
            continue
        values.append(metadata.sample_values.get(dimension.concept_id, "*"))
    return ".".join(values)


def data_endpoint(source_url: str) -> str:
    """Derive the API-v2 data endpoint from the stored structure source URL."""
    parsed = urlsplit(source_url)
    api_path = parsed.path.split("/structure/", 1)[0].rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, f"{api_path}/data/dataflow", "", ""))


def build_query_url(metadata: TradeMetadata, key: str) -> str:
    endpoint = data_endpoint(metadata.dataflow.source_url)
    identity = "/".join(
        quote(value, safe="._-*")
        for value in (
            metadata.dataflow.agency_id,
            metadata.dataflow.dataflow_id,
            metadata.dataflow.version,
            key,
        )
    )
    request = requests.Request(
        "GET",
        f"{endpoint}/{identity}",
        params={
            "startPeriod": START_PERIOD,
            "endPeriod": END_PERIOD,
            "firstNObservations": "1",
            "max": "1",
        },
    )
    return request.prepare().url


def _provider_message(payload: bytes) -> str:
    if not payload:
        return "empty response"
    try:
        root = etree.fromstring(
            payload,
            parser=etree.XMLParser(resolve_entities=False, no_network=True),
        )
        texts = [
            " ".join(text.split())
            for text in root.itertext()
            if text and text.strip()
        ]
        return " ".join(texts) or "XML response without message text"
    except (etree.XMLSyntaxError, ValueError):
        return " ".join(payload.decode("utf-8", errors="replace").split())[:500]


def probe_query(url: str) -> ProbeResult:
    """Issue a bounded capability probe and retain at most 64 KiB."""
    with requests.get(
        url,
        headers={"Accept": DATA_ACCEPT, "User-Agent": USER_AGENT},
        timeout=(10, settings.sdmx_timeout_seconds),
        stream=True,
    ) as response:
        payload = bytearray()
        for chunk in response.iter_content(8192):
            payload.extend(chunk)
            if len(payload) > MAX_PROBE_BYTES:
                break
        truncated = len(payload) > MAX_PROBE_BYTES
        body = bytes(payload[:MAX_PROBE_BYTES])
        return ProbeResult(
            response.url,
            response.status_code,
            response.headers.get("Content-Type", ""),
            _provider_message(body),
            truncated,
        )


def main() -> int:
    with SessionLocal() as session:
        metadata = load_trade_metadata(session)
        key = build_sample_key(metadata)
        query_url = build_query_url(metadata, key)

    result = probe_query(query_url)
    print(f"Provider: {PROVIDER_NAME}")
    print(f"SDMX API version: {API_VERSION}")
    print(
        "Dataflow: "
        f"{metadata.dataflow.agency_id}:{metadata.dataflow.dataflow_id}"
        f"({metadata.dataflow.version}) - {metadata.dataflow.name}"
    )
    print(
        f"DSD: {metadata.dsd.agency_id}:{metadata.dsd.dsd_id}"
        f"({metadata.dsd.version}) - {metadata.dsd.name}"
    )
    print("Dimension order:")
    for dimension in metadata.dimensions:
        print(f"  {dimension.position}. {dimension.concept_id} [{dimension.role}]")
    print(f"Data endpoint: {data_endpoint(metadata.dataflow.source_url)}")
    print(f"Sample key: {key}")
    print(f"Sample query: {result.url}")
    print(f"Date parameters: startPeriod={START_PERIOD}; endPeriod={END_PERIOD}")
    print(f"Response format requested: {DATA_ACCEPT}")
    print(f"Response format returned: {result.content_type or 'not supplied'}")
    print(f"HTTP status: {result.status_code}")
    print(f"Provider message: {result.message}")
    print(
        "Safety limits: firstNObservations=1; max=1; "
        f"client read cap={MAX_PROBE_BYTES} bytes"
    )
    print("Content constraint: none published for UNSD in prior discovery (HTTP 404)")
    print("Numeric server limit: not disclosed by the provider")
    if result.truncated:
        print("Response body: truncated at the client safety limit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

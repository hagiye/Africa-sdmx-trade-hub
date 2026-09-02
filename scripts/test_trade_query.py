"""Prove that a minimal live trade query returns real observations.

This script reads SDMX identities and codes from the metadata registry, maps
the area codes through UN Comtrade's official reference lists, and requests
one aggregate observation for each of three completed years. It never writes
to PostgreSQL.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.database import models as db
from app.database.session import SessionLocal
from app.sdmx.discovery import TRADE_DATAFLOW


DATA_ENDPOINT = "https://comtradeapi.un.org/public/v1/preview"
REPORTERS_ENDPOINT = (
    "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
)
PARTNERS_ENDPOINT = (
    "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
)
PERIODS = ("2022", "2023", "2024")
REPORTER_LABEL = "Tunisia"
PARTNER_LABEL = "World (all areas, including reference area, including IO)"
FREQUENCY_LABEL = "Annual"
FLOW_LABEL = "Total Imports"
COMMODITY_LABEL = "All commodities"
COMMODITY_PREFIX = "SITC4_"
MAX_RECORDS = 1
MAX_RESPONSE_BYTES = 64 * 1024
REQUEST_INTERVAL_SECONDS = 1.1
USER_AGENT = "africa-sdmx-trade-hub/0.1 (+independent portfolio project)"

# Confirmed from the official provider reference endpoints on 2026-09-02.
# They are provider translations of the stored SDMX codes TN and W0, not
# invented SDMX codes. The returned observations are checked against both.
PROVIDER_REPORTER_CODE = "788"
PROVIDER_PARTNER_CODE = "0"


@dataclass(frozen=True)
class QueryCodes:
    frequency: str
    reporter: str
    flow: str
    commodity: str
    partner: str


@dataclass(frozen=True)
class LiveResult:
    period: str
    url: str
    status_code: int
    content_type: str
    response_size: int
    observation_count: int
    preview: dict[str, Any]


def create_http_session() -> requests.Session:
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": USER_AGENT})
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def _read_bounded(response: requests.Response, byte_limit: int) -> bytes:
    body = bytearray()
    for chunk in response.iter_content(8192):
        body.extend(chunk)
        if len(body) > byte_limit:
            raise RuntimeError(
                f"Response exceeded the {byte_limit}-byte safety limit: "
                f"{response.url}"
            )
    return bytes(body)


def _parse_json(body: bytes, url: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise RuntimeError(f"Provider returned invalid JSON: {url}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected a JSON object from {url}")
    return payload


def _find_code_by_label(
    session: Session,
    dimension: db.Dimension,
    english_label: str,
    *,
    code_prefix: str | None = None,
) -> str:
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
            f"Codelist not found for {dimension.concept_id}: "
            f"{dimension.codelist_agency_id}:{dimension.codelist_id}"
            f"({dimension.codelist_version})"
        )

    candidates = session.execute(
        select(db.Code.code, db.LocalizedLabel.label)
        .join(
            db.LocalizedLabel,
            (db.LocalizedLabel.entity_pk == db.Code.id)
            & (db.LocalizedLabel.entity_type == "code"),
        )
        .where(
            db.Code.codelist_id == codelist.id,
            db.LocalizedLabel.language == "en",
        )
    )
    matches = [
        code
        for code, label in candidates
        if label.casefold() == english_label.casefold()
        and (code_prefix is None or code.startswith(code_prefix))
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one {english_label!r} code for {dimension.concept_id}, "
            f"found {matches}"
        )
    return matches[0]


def load_query_codes(session: Session) -> QueryCodes:
    """Read the chosen codes through the stored Dataflow and referenced DSD."""
    flow = session.scalar(
        select(db.Dataflow).where(
            db.Dataflow.agency_id == TRADE_DATAFLOW.agency,
            db.Dataflow.dataflow_id == TRADE_DATAFLOW.structure_id,
            db.Dataflow.version == TRADE_DATAFLOW.version,
        )
    )
    if flow is None:
        raise RuntimeError("Stored trade Dataflow was not found")
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
        raise RuntimeError("The Dataflow's stored DSD was not found")

    dimensions = {
        dimension.concept_id: dimension
        for dimension in session.scalars(
            select(db.Dimension).where(db.Dimension.dsd_id == dsd.id)
        )
    }
    required = {
        "FREQ",
        "REF_AREA",
        "TRADE_FLOW",
        "COMMODITY_1",
        "COUNTERPART_AREA_1",
    }
    missing = required.difference(dimensions)
    if missing:
        raise RuntimeError(f"Stored DSD is missing dimensions: {sorted(missing)}")

    return QueryCodes(
        frequency=_find_code_by_label(
            session, dimensions["FREQ"], FREQUENCY_LABEL
        ),
        reporter=_find_code_by_label(
            session, dimensions["REF_AREA"], REPORTER_LABEL
        ),
        flow=_find_code_by_label(
            session, dimensions["TRADE_FLOW"], FLOW_LABEL
        ),
        commodity=_find_code_by_label(
            session,
            dimensions["COMMODITY_1"],
            COMMODITY_LABEL,
            code_prefix=COMMODITY_PREFIX,
        ),
        partner=_find_code_by_label(
            session, dimensions["COUNTERPART_AREA_1"], PARTNER_LABEL
        ),
    )


def _provider_classification(sdmx_commodity: str) -> str:
    prefix, separator, _ = sdmx_commodity.partition("_")
    if not separator or not prefix.startswith("SITC") or not prefix[4:].isdigit():
        raise RuntimeError(
            f"Cannot map stored commodity code to Comtrade: {sdmx_commodity}"
        )
    return f"S{prefix[4:]}"


def construct_queries(
    codes: QueryCodes,
    reporter_code: str,
    partner_code: str,
) -> list[tuple[str, requests.PreparedRequest]]:
    classification = _provider_classification(codes.commodity)
    commodity_code = codes.commodity.split("_", 1)[1]
    endpoint = f"{DATA_ENDPOINT}/C/{codes.frequency}/{classification}"
    queries = []
    for period in PERIODS:
        request = requests.Request(
            "GET",
            endpoint,
            params={
                "period": period,
                "reporterCode": reporter_code,
                "flowCode": codes.flow,
                "partnerCode": partner_code,
                "partner2Code": partner_code,
                "cmdCode": commodity_code,
                "maxRecords": str(MAX_RECORDS),
                "breakdownMode": "classic",
                "includeDesc": "true",
                "format": "JSON",
            },
        ).prepare()
        if not request.url:
            raise RuntimeError("Failed to construct provider query")
        lowered_url = request.url.casefold()
        if "subscription-key" in lowered_url or "api-key" in lowered_url:
            raise RuntimeError("Refusing to print a query containing a secret")
        queries.append((period, request))
    return queries


def send_query(
    http: requests.Session,
    period: str,
    request: requests.PreparedRequest,
    codes: QueryCodes,
    reporter_code: str,
    partner_code: str,
) -> LiveResult:
    print(f"Query ({period}): {request.url}")
    try:
        with http.send(
            request,
            timeout=(10, settings.sdmx_timeout_seconds),
            stream=True,
        ) as response:
            body = _read_bounded(response, MAX_RESPONSE_BYTES)
            content_type = response.headers.get("Content-Type", "")
            print(f"HTTP status: {response.status_code}")
            print(f"Content type: {content_type or 'not supplied (JSON requested)'}")
            print(f"Response size: {len(body)} bytes")
            if not response.ok:
                error_preview = " ".join(
                    body.decode("utf-8", errors="replace").split()
                )[:500]
                print(f"Provider error: {error_preview}")
                response.raise_for_status()
            payload = _parse_json(body, response.url)
            url = response.url
            status_code = response.status_code
    except requests.RequestException as exc:
        raise RuntimeError(f"Live request failed for {period}: {exc}") from exc

    provider_error = payload.get("error")
    if provider_error:
        raise RuntimeError(f"Provider error for {period}: {provider_error}")
    records = payload.get("data")
    if not isinstance(records, list):
        raise RuntimeError(f"Provider response for {period} has no data list")
    declared_count = payload.get("count")
    if declared_count != len(records):
        raise RuntimeError(
            f"Provider count mismatch for {period}: "
            f"declared {declared_count}, received {len(records)}"
        )
    print(f"Observations: {len(records)}")
    if len(records) != 1:
        raise RuntimeError(
            f"Expected one observation for {period}, received {len(records)}"
        )

    record = records[0]
    expected = {
        "period": period,
        "freqCode": codes.frequency,
        "reporterCode": reporter_code,
        "reporterDesc": REPORTER_LABEL,
        "flowCode": codes.flow,
        "partnerCode": partner_code,
        "partnerDesc": "World",
        "partner2Code": partner_code,
        "classificationCode": _provider_classification(codes.commodity),
        "cmdCode": codes.commodity.split("_", 1)[1],
    }
    mismatches = {
        field: (wanted, record.get(field))
        for field, wanted in expected.items()
        if str(record.get(field)) != str(wanted)
    }
    if mismatches:
        raise RuntimeError(f"Observation does not match query: {mismatches}")
    if record.get("primaryValue") is None:
        raise RuntimeError(f"Observation for {period} has no primaryValue")

    preview_fields = (
        "period",
        "reporterCode",
        "reporterDesc",
        "flowCode",
        "flowDesc",
        "partnerCode",
        "partnerDesc",
        "classificationCode",
        "cmdCode",
        "cmdDesc",
        "primaryValue",
    )
    preview = {field: record.get(field) for field in preview_fields}
    print(f"Preview: {json.dumps(preview, ensure_ascii=False)}")
    return LiveResult(
        period=period,
        url=url,
        status_code=status_code,
        content_type=content_type,
        response_size=len(body),
        observation_count=len(records),
        preview=preview,
    )


def main() -> int:
    try:
        with SessionLocal() as database:
            codes = load_query_codes(database)

        print(
            f"Confirmed reporter: {codes.reporter} -> "
            f"{PROVIDER_REPORTER_CODE} ({REPORTERS_ENDPOINT})"
        )
        print(
            f"Confirmed partner: {codes.partner} -> "
            f"{PROVIDER_PARTNER_CODE} ({PARTNERS_ENDPOINT})"
        )
        with create_http_session() as http:
            queries = construct_queries(
                codes, PROVIDER_REPORTER_CODE, PROVIDER_PARTNER_CODE
            )
            results = []
            for index, (period, query) in enumerate(queries):
                if index:
                    time.sleep(REQUEST_INTERVAL_SECONDS)
                results.append(
                    send_query(
                        http,
                        period,
                        query,
                        codes,
                        PROVIDER_REPORTER_CODE,
                        PROVIDER_PARTNER_CODE,
                    )
                )

        print(f"Total observations: {sum(item.observation_count for item in results)}")
        return 0
    except (RuntimeError, requests.RequestException) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

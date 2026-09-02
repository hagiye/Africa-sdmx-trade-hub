"""Discover and probe the real trade-observation query contract.

The stored SDMX Dataflow, DSD, and codelists remain the source of truth for
structure and code semantics. The probe reads one observation from UN
Comtrade and never writes observations to PostgreSQL.
"""

from __future__ import annotations

import json
import sys
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
from app.sdmx.discovery import PROVIDER_NAME, TRADE_DATAFLOW


OBSERVATION_PROVIDER = "UN Comtrade"
DATA_ENDPOINT = "https://comtradeapi.un.org/public/v1/preview"
REPORTERS_ENDPOINT = (
    "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
)
PARTNERS_ENDPOINT = (
    "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json"
)
COMTRADE_API_VERSION = "v1"
SDMX_STRUCTURE_API_VERSION = "REST v2 (SDMX 3.0 structure responses)"
START_PERIOD = "2020"
END_PERIOD = "2020"
MAX_RECORDS = 1
MAX_RESPONSE_BYTES = 64 * 1024
MAX_REFERENCE_BYTES = 128 * 1024
USER_AGENT = "africa-sdmx-trade-hub/0.1 (+independent portfolio project)"

# UN Comtrade calls HS 2017 "H5". The stored SDMX-IMTS codelist uses the
# prefix "HS17" for the same edition.
COMTRADE_TO_SDMX_CLASSIFICATION = {
    "H0": "HS92",
    "H1": "HS96",
    "H2": "HS02",
    "H3": "HS07",
    "H4": "HS12",
    "H5": "HS17",
}


@dataclass(frozen=True)
class TradeMetadata:
    dataflow: db.Dataflow
    dsd: db.DSD
    dimensions: tuple[db.Dimension, ...]
    sample_values: dict[str, str]


@dataclass(frozen=True)
class JsonResponse:
    url: str
    status_code: int
    content_type: str
    payload: dict[str, Any]


def _http_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, str] | None = None,
    byte_limit: int,
) -> JsonResponse:
    """GET and parse JSON without retaining an unexpectedly large response."""
    with session.get(
        url,
        params=params,
        timeout=(10, settings.sdmx_timeout_seconds),
        stream=True,
    ) as response:
        body = bytearray()
        for chunk in response.iter_content(8192):
            body.extend(chunk)
            if len(body) > byte_limit:
                raise RuntimeError(
                    f"Response exceeded the {byte_limit}-byte safety limit: "
                    f"{response.url}"
                )
        response.raise_for_status()
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise RuntimeError(f"Provider returned invalid JSON: {response.url}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected a JSON object from {response.url}")
        return JsonResponse(
            url=response.url,
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type", ""),
            payload=payload,
        )


def _find_code_by_label(
    session: Session,
    dimension: db.Dimension,
    english_label: str,
    *,
    code_prefix: str | None = None,
) -> str:
    """Resolve one code from an imported codelist rather than guessing it."""
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


def load_trade_metadata(session: Session) -> TradeMetadata:
    """Load the selected Dataflow, DSD, order, and sample codes from PostgreSQL."""
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
    if sum(dimension.role == "time" for dimension in dimensions) != 1:
        raise RuntimeError("The stored DSD must contain exactly one time dimension")

    by_id = {dimension.concept_id: dimension for dimension in dimensions}
    required_dimensions = {
        "FREQ",
        "REF_AREA",
        "TRADE_FLOW",
        "COMMODITY_1",
        "COUNTERPART_AREA_1",
        "COUNTERPART_AREA_2",
    }
    missing = required_dimensions.difference(by_id)
    if missing:
        raise RuntimeError(f"Stored DSD is missing dimensions: {sorted(missing)}")

    sample_values = {
        "FREQ": _find_code_by_label(session, by_id["FREQ"], "Annual"),
        "REF_AREA": _find_code_by_label(session, by_id["REF_AREA"], "Kenya"),
        "TRADE_FLOW": _find_code_by_label(
            session, by_id["TRADE_FLOW"], "Total Imports"
        ),
        "COMMODITY_1": _find_code_by_label(
            session,
            by_id["COMMODITY_1"],
            "All commodities",
            code_prefix="HS17_",
        ),
        "COUNTERPART_AREA_1": _find_code_by_label(
            session,
            by_id["COUNTERPART_AREA_1"],
            "World (all areas, including reference area, including IO)",
        ),
        "COUNTERPART_AREA_2": _find_code_by_label(
            session,
            by_id["COUNTERPART_AREA_2"],
            "World (all areas, including reference area, including IO)",
        ),
    }
    return TradeMetadata(flow, dsd, dimensions, sample_values)


def build_sample_key(metadata: TradeMetadata) -> str:
    """Build an SDMX REST v2 positional key in the stored DSD order."""
    return ".".join(
        metadata.sample_values.get(dimension.concept_id, "*")
        for dimension in metadata.dimensions
        if dimension.role != "time"
    )


def _reference_results(response: JsonResponse) -> list[dict[str, Any]]:
    results = response.payload.get("results")
    if not isinstance(results, list):
        raise RuntimeError(f"Reference response has no results list: {response.url}")
    return [item for item in results if isinstance(item, dict)]


def _resolve_reporter_code(http: requests.Session, iso_alpha2: str) -> str:
    response = _get_json(
        http, REPORTERS_ENDPOINT, byte_limit=MAX_REFERENCE_BYTES
    )
    matches = [
        item
        for item in _reference_results(response)
        if item.get("reporterCodeIsoAlpha2") == iso_alpha2
        and item.get("isGroup") is False
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one Comtrade reporter for ISO alpha-2 {iso_alpha2}, "
            f"found {len(matches)}"
        )
    return str(matches[0]["reporterCode"])


def _resolve_world_partner_code(http: requests.Session) -> str:
    response = _get_json(
        http, PARTNERS_ENDPOINT, byte_limit=MAX_REFERENCE_BYTES
    )
    matches = [
        item
        for item in _reference_results(response)
        if str(item.get("text", "")).casefold() == "world"
        and item.get("isGroup") is True
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one Comtrade World partner, found {len(matches)}"
        )
    return str(matches[0]["PartnerCode"])


def build_query(
    metadata: TradeMetadata,
    reporter_code: str,
    world_partner_code: str,
) -> requests.PreparedRequest:
    """Translate the supported DSD subset into a bounded Comtrade v1 query."""
    if START_PERIOD != END_PERIOD:
        raise RuntimeError(
            "This bounded discovery probe requires equal start/end periods; "
            "Comtrade v1 uses period rather than startPeriod/endPeriod"
        )
    commodity_code = metadata.sample_values["COMMODITY_1"].split("_", 1)[1]
    endpoint = f"{DATA_ENDPOINT}/C/{metadata.sample_values['FREQ']}/HS"
    return requests.Request(
        "GET",
        endpoint,
        params={
            "period": START_PERIOD,
            "reporterCode": reporter_code,
            "flowCode": metadata.sample_values["TRADE_FLOW"],
            "partnerCode": world_partner_code,
            "partner2Code": world_partner_code,
            "cmdCode": commodity_code,
            "maxRecords": str(MAX_RECORDS),
            "breakdownMode": "classic",
            "includeDesc": "true",
            "format": "JSON",
        },
    ).prepare()


def probe_query(
    http: requests.Session,
    prepared: requests.PreparedRequest,
    metadata: TradeMetadata,
    reporter_code: str,
    world_partner_code: str,
) -> JsonResponse:
    response = _get_json(
        http,
        prepared.url,
        byte_limit=MAX_RESPONSE_BYTES,
    )
    error = response.payload.get("error")
    records = response.payload.get("data")
    if error:
        raise RuntimeError(f"UN Comtrade error: {error}")
    if not isinstance(records, list) or len(records) != 1:
        raise RuntimeError(
            f"Expected exactly one bounded observation, found "
            f"{len(records) if isinstance(records, list) else 'no data list'}"
        )

    record = records[0]
    if not isinstance(record, dict) or record.get("primaryValue") is None:
        raise RuntimeError("The provider response did not contain a trade observation")
    expected = {
        "freqCode": metadata.sample_values["FREQ"],
        "period": START_PERIOD,
        "reporterCode": int(reporter_code),
        "flowCode": metadata.sample_values["TRADE_FLOW"],
        "partnerCode": int(world_partner_code),
        "partner2Code": int(world_partner_code),
        "cmdCode": metadata.sample_values["COMMODITY_1"].split("_", 1)[1],
    }
    mismatches = {
        field: (wanted, record.get(field))
        for field, wanted in expected.items()
        if str(record.get(field)) != str(wanted)
    }
    if mismatches:
        raise RuntimeError(f"Observation does not match the query: {mismatches}")

    returned_classification = str(record.get("classificationCode", ""))
    dsd_prefix = COMTRADE_TO_SDMX_CLASSIFICATION.get(returned_classification)
    if dsd_prefix is None or not metadata.sample_values["COMMODITY_1"].startswith(
        f"{dsd_prefix}_"
    ):
        raise RuntimeError(
            "Returned commodity classification is not represented by the "
            f"stored SDMX code: {returned_classification!r}"
        )
    return response


def main() -> int:
    with SessionLocal() as database:
        metadata = load_trade_metadata(database)
        sample_key = build_sample_key(metadata)

    with _http_session() as http:
        reporter_code = _resolve_reporter_code(
            http, metadata.sample_values["REF_AREA"]
        )
        world_partner_code = _resolve_world_partner_code(http)
        prepared = build_query(metadata, reporter_code, world_partner_code)
        result = probe_query(
            http,
            prepared,
            metadata,
            reporter_code,
            world_partner_code,
        )

    returned_format = "JSON"
    if result.content_type:
        returned_format += f" ({result.content_type})"
    else:
        returned_format += " (parsed; provider supplied no Content-Type header)"

    print(
        f"Provider: {OBSERVATION_PROVIDER} (observations); "
        f"{PROVIDER_NAME} (stored structures)"
    )
    print(
        f"SDMX API version: {SDMX_STRUCTURE_API_VERSION}; "
        f"observation API: UN Comtrade {COMTRADE_API_VERSION} (non-SDMX REST)"
    )
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
    print(
        f"Data endpoint: {DATA_ENDPOINT}/"
        "{typeCode}/{freqCode}/{classificationCode}"
    )
    print(f"Sample key (stored DSD order): {sample_key}")
    print("Provider path key: C/A/HS")
    print(f"Sample query: {result.url}")
    print(
        f"Date parameters: SDMX startPeriod={START_PERIOD}; "
        f"endPeriod={END_PERIOD}; Comtrade equivalent period={START_PERIOD}"
    )
    print(f"Response format: requested JSON; returned {returned_format}")
    print(f"HTTP status: {result.status_code}")
    print(
        "Constraints/server limits: public preview, no authentication, "
        f"500-record provider cap; probe maxRecords={MAX_RECORDS}; "
        f"client response cap={MAX_RESPONSE_BYTES} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fetch the controlled Tunisia trade sample into deterministic JSON fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.database.session import SessionLocal
from test_trade_query import (
    MAX_RECORDS,
    MAX_RESPONSE_BYTES,
    PERIODS,
    PROVIDER_PARTNER_CODE,
    PROVIDER_REPORTER_CODE,
    REQUEST_INTERVAL_SECONDS,
    QueryCodes,
    construct_queries,
    create_http_session,
    load_query_codes,
)


FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "data"
MANIFEST_PATH = (
    FIXTURE_DIRECTORY / "un_comtrade_tunisia_imports_world_manifest.json"
)
FIXTURE_NAME = "un_comtrade_tunisia_imports_world_{period}.json"


@dataclass(frozen=True)
class FetchedFixture:
    period: int
    filename: str
    canonical_json: bytes
    sha256: str
    http_status: int
    response_bytes: int
    record_count: int
    content_type_missing: bool


def canonical_json(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _error_preview(response: requests.Response) -> str:
    return " ".join(response.text.split())[:500]


def _validate_payload(
    payload: Any,
    period: str,
    codes: QueryCodes,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected a JSON object for {period}")
    if payload.get("error"):
        raise RuntimeError(f"Provider error for {period}: {payload['error']}")
    records = payload.get("data")
    if not isinstance(records, list) or not records:
        raise RuntimeError(f"Provider returned no observations for {period}")
    if payload.get("count") != len(records):
        raise RuntimeError(
            f"Provider count mismatch for {period}: "
            f"declared {payload.get('count')}, received {len(records)}"
        )
    if len(records) > MAX_RECORDS:
        raise RuntimeError(
            f"Provider exceeded maxRecords for {period}: {len(records)}"
        )

    classification = f"S{codes.commodity.split('_', 1)[0][4:]}"
    commodity = codes.commodity.split("_", 1)[1]
    expected = {
        "period": period,
        "freqCode": codes.frequency,
        "reporterCode": PROVIDER_REPORTER_CODE,
        "reporterDesc": "Tunisia",
        "flowCode": codes.flow,
        "partnerCode": PROVIDER_PARTNER_CODE,
        "partnerDesc": "World",
        "partner2Code": PROVIDER_PARTNER_CODE,
        "classificationCode": classification,
        "cmdCode": commodity,
    }
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError(f"Provider returned a non-object observation for {period}")
        mismatches = {
            field: (wanted, record.get(field))
            for field, wanted in expected.items()
            if str(record.get(field)) != str(wanted)
        }
        if mismatches:
            raise RuntimeError(
                f"Observation does not match the controlled sample: {mismatches}"
            )
        if record.get("primaryValue") is None:
            raise RuntimeError(f"Observation for {period} has no primaryValue")
    return records


def fetch_fixture(
    http: requests.Session,
    period: str,
    request: requests.PreparedRequest,
    codes: QueryCodes,
) -> FetchedFixture:
    if not request.url:
        raise RuntimeError(f"Query URL is missing for {period}")
    print(f"Query ({period}): {request.url}")
    try:
        with http.send(
            request,
            timeout=(10, settings.sdmx_timeout_seconds),
            verify=True,
        ) as response:
            raw_response = response.content
            status = response.status_code
            content_type = response.headers.get("Content-Type")
            print(f"HTTP status: {status}")
            print(f"Content-Type: {content_type or 'MISSING'}")
            print(f"Response bytes: {len(raw_response)}")
            if len(raw_response) > MAX_RESPONSE_BYTES:
                raise RuntimeError(
                    f"Response exceeded the {MAX_RESPONSE_BYTES}-byte safety limit"
                )
            if not response.ok:
                print(f"Provider error: {_error_preview(response)}")
                response.raise_for_status()
            try:
                payload = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Provider returned invalid JSON for {period}"
                ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Live request failed for {period}: {exc}") from exc

    records = _validate_payload(payload, period, codes)
    content = canonical_json(payload)
    digest = sha256(content)
    print(f"Record count: {len(records)}")
    print(f"SHA-256: {digest}")
    return FetchedFixture(
        period=int(period),
        filename=FIXTURE_NAME.format(period=period),
        canonical_json=content,
        sha256=digest,
        http_status=status,
        response_bytes=len(raw_response),
        record_count=len(records),
        content_type_missing=content_type is None,
    )


def write_deliberately(path: Path, content: bytes, refresh: bool) -> str:
    if not path.exists():
        path.write_bytes(content)
        return "CREATED"

    existing_checksum = sha256(path.read_bytes())
    new_checksum = sha256(content)
    if existing_checksum == new_checksum:
        return "UNCHANGED"
    if refresh:
        path.write_bytes(content)
        return "CHANGED (refreshed)"
    return "CHANGED (not written; rerun with --refresh to replace)"


def fixture_entry(fixture: FetchedFixture) -> dict[str, Any]:
    return {
        "content_type_missing": fixture.content_type_missing,
        "file": fixture.filename,
        "file_bytes": len(fixture.canonical_json),
        "http_status": fixture.http_status,
        "period": fixture.period,
        "record_count": fixture.record_count,
        "response_bytes": fixture.response_bytes,
        "sha256": fixture.sha256,
    }


def build_manifest(
    fixtures: list[FetchedFixture], codes: QueryCodes
) -> dict[str, Any]:
    classification = f"S{codes.commodity.split('_', 1)[0][4:]}"
    return {
        "agency": "UNSD",
        "commodity": {
            "classification_code": classification,
            "provider_query_code": codes.commodity.split("_", 1)[1],
            "source_code": codes.commodity,
            "type_code": "C",
        },
        "dataflow": "IMTS_A",
        "dataflow_version": "1.0",
        "dsd": "IMTS",
        "dsd_version": "1.2",
        "fixtures": [fixture_entry(fixture) for fixture in fixtures],
        "format": "JSON",
        "frequency": {"code": codes.frequency, "label": "Annual"},
        "partner": {
            "area_type": "AGGREGATE",
            "label": "World",
            "provider_code": PROVIDER_PARTNER_CODE,
            "source_code": codes.partner,
        },
        "periods": [int(period) for period in PERIODS],
        "provider": "UN Comtrade",
        "reporter": {
            "label": "Tunisia",
            "provider_code": PROVIDER_REPORTER_CODE,
            "source_code": codes.reporter,
        },
        "trade_flow": {"code": codes.flow, "label": "Imports"},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch or deliberately refresh the controlled trade fixtures."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Replace existing fixtures and manifest when live content changed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with SessionLocal() as database:
            codes = load_query_codes(database)
        queries = construct_queries(
            codes, PROVIDER_REPORTER_CODE, PROVIDER_PARTNER_CODE
        )

        fetched = []
        with create_http_session() as http:
            for index, (period, request) in enumerate(queries):
                if index:
                    time.sleep(REQUEST_INTERVAL_SECONDS)
                fetched.append(fetch_fixture(http, period, request, codes))

        FIXTURE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        for fixture in fetched:
            path = FIXTURE_DIRECTORY / fixture.filename
            result = write_deliberately(path, fixture.canonical_json, args.refresh)
            print(f"{path}: {result}; {path.stat().st_size if path.exists() else 0} bytes")

        manifest_content = canonical_json(build_manifest(fetched, codes))
        manifest_result = write_deliberately(
            MANIFEST_PATH, manifest_content, args.refresh
        )
        print(
            f"{MANIFEST_PATH}: {manifest_result}; "
            f"{MANIFEST_PATH.stat().st_size if MANIFEST_PATH.exists() else 0} bytes"
        )
        print(f"Total observations: {sum(item.record_count for item in fetched)}")
        return 0
    except (RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

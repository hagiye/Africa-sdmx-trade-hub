"""Probe the public structural and statistical endpoints considered by the project."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

USER_AGENT = "africa-sdmx-trade-hub/0.1 (+independent portfolio project)"


@dataclass(frozen=True)
class Probe:
    provider: str
    base_url: str
    endpoint: str
    purpose: str
    accept: str
    required: bool = False


PROBES = [
    Probe(
        "IMF SDMX Central",
        "https://sdmxcentral.imf.org/sdmx/v2/",
        "https://sdmxcentral.imf.org/sdmx/v2/structure/dataflow/UNSD/all/latest",
        "SDMX 3.0 structures",
        "application/vnd.sdmx.structure+xml;version=3.0",
        True,
    ),
    Probe(
        "IMF SDMX Central",
        "https://sdmxcentral.imf.org/sdmx/v2/",
        "https://sdmxcentral.imf.org/sdmx/v2/structure/datastructure/UNSD/IMTS/1.2",
        "SDMX 3.0 DSD",
        "application/vnd.sdmx.structure+xml;version=3.0",
        True,
    ),
    Probe(
        "IMF Data API",
        "https://data.imf.org/",
        "https://data.imf.org/en/Resource-Pages/IMF-API",
        "SDMX 2.1/3.0 data API documentation; Swagger requires portal sign-in",
        "text/html",
    ),
    Probe(
        "IMF DataMapper API",
        "https://www.imf.org/external/datamapper/api/v1/",
        "https://www.imf.org/external/datamapper/api/v1/",
        "Statistical data (non-SDMX; access may be edge-restricted)",
        "application/json",
    ),
]


def determine_sdmx_version(content: bytes) -> str:
    text = content[:1000].decode("utf-8", errors="ignore")
    if "/v3_0/" in text:
        return "3.0"
    if "/v2_1/" in text:
        return "2.1"
    return "not determinable"


def main() -> int:
    failed = False
    for probe in PROBES:
        started = time.perf_counter()
        try:
            response = requests.get(
                probe.endpoint,
                headers={"Accept": probe.accept, "User-Agent": USER_AGENT},
                timeout=(10, 30),
            )
            elapsed = time.perf_counter() - started
            print(f"Provider:     {probe.provider}")
            print(f"Base URL:     {probe.base_url}")
            print(f"Endpoint:     {probe.endpoint}")
            print(f"Purpose:      {probe.purpose}")
            print(f"HTTP status:  {response.status_code}")
            print(f"Content-Type: {response.headers.get('Content-Type', '')}")
            print(f"SDMX version: {determine_sdmx_version(response.content)}")
            print(f"Response:     {len(response.content):,} bytes ({elapsed:.2f}s)\n")
            if probe.required and not response.ok:
                failed = True
        except requests.RequestException as exc:
            failed = failed or probe.required
            print(
                f"Provider: {probe.provider}\nBase URL: {probe.base_url}\n"
                f"Endpoint: {probe.endpoint}\nERROR: {exc}\n"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

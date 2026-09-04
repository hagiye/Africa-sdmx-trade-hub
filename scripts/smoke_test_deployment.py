"""Smoke-test a deployed Pan-African SDMX Trade Data Hub instance."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TIMEOUT_SECONDS = 60


def get(base_url: str, path: str, *, expect_json: bool = False) -> object:
    url = f"{base_url.rstrip('/')}{path}"
    request = Request(url, headers={"Accept": "application/json, text/html"})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            body = response.read()
            content_type = response.headers.get_content_type()
    except HTTPError as exc:
        raise RuntimeError(f"GET {path} returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"GET {path} failed: {exc.reason}") from exc
    if not 200 <= status < 300:
        raise RuntimeError(f"GET {path} returned HTTP {status}")
    print(f"PASS {status} {path}")
    if expect_json:
        if content_type != "application/json":
            raise RuntimeError(f"GET {path} did not return JSON ({content_type})")
        return json.loads(body)
    return body


def smoke_test(base_url: str) -> None:
    get(base_url, "/")
    health = get(base_url, "/health", expect_json=True)
    if not isinstance(health, dict) or health.get("status") != "healthy":
        raise RuntimeError("GET /health returned an unexpected payload")
    get(base_url, "/docs")
    page = get(base_url, "/api/v1/afr-trade", expect_json=True)
    get(base_url, "/api/v1/afr-trade/metadata", expect_json=True)
    if not isinstance(page, dict) or not isinstance(page.get("items"), list):
        raise RuntimeError("AFR_TRADE response is not a result page")
    if not page["items"]:
        raise RuntimeError("AFR_TRADE contains no observations to filter")
    first = page["items"][0]
    query = urlencode(
        {
            "ref_area": first["REF_AREA"],
            "start_period": first["TIME_PERIOD"],
            "end_period": first["TIME_PERIOD"],
            "limit": 1,
        }
    )
    filtered = get(base_url, f"/api/v1/afr-trade?{query}", expect_json=True)
    if not isinstance(filtered, dict) or filtered.get("total", 0) < 1:
        raise RuntimeError("Filtered AFR_TRADE query returned no observations")


def main() -> int:
    base_url = (
        sys.argv[1] if len(sys.argv) > 1 else os.getenv("DEPLOYMENT_BASE_URL", "")
    ).strip()
    if not base_url:
        print(
            "Usage: python scripts/smoke_test_deployment.py <BASE_URL>\n"
            "or set DEPLOYMENT_BASE_URL",
            file=sys.stderr,
        )
        return 2
    try:
        smoke_test(base_url)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("Deployment smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

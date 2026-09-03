"""Bounded HTTP client for UN Comtrade JSON observations."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


COMTRADE_PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview"
DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024
USER_AGENT = "africa-sdmx-trade-hub/0.1 (+independent portfolio project)"


class ComtradeProviderError(RuntimeError):
    """A bounded UN Comtrade request could not produce a usable JSON object."""


class ComtradeClient:
    def __init__(
        self,
        *,
        base_url: str = COMTRADE_PREVIEW_URL,
        timeout_seconds: float = 60.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.session = session or requests.Session()
        self._owns_session = session is None
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
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": USER_AGENT}
        )

    def __enter__(self) -> ComtradeClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def get_trade_data(
        self,
        *,
        type_code: str,
        frequency_code: str,
        classification_code: str,
        parameters: dict[str, str],
    ) -> dict[str, Any]:
        """Return one size-bounded, decoded Comtrade response."""
        if any("key" in name.casefold() for name in parameters):
            raise ValueError("Comtrade query parameters must not contain secrets")
        path = "/".join(
            quote(component, safe="._-")
            for component in (type_code, frequency_code, classification_code)
        )
        url = f"{self.base_url}/{path}"
        try:
            with self.session.get(
                url,
                params=parameters,
                timeout=(10.0, self.timeout_seconds),
                stream=True,
            ) as response:
                body = bytearray()
                for chunk in response.iter_content(8192):
                    body.extend(chunk)
                    if len(body) > self.max_response_bytes:
                        raise ComtradeProviderError(
                            "UN Comtrade response exceeded the configured size limit"
                        )
                if not response.ok:
                    preview = " ".join(
                        bytes(body).decode("utf-8", errors="replace").split()
                    )[:300]
                    raise ComtradeProviderError(
                        f"UN Comtrade returned HTTP {response.status_code}: {preview}"
                    )
        except requests.RequestException as exc:
            raise ComtradeProviderError(
                f"UN Comtrade request failed: {exc}"
            ) from exc

        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComtradeProviderError(
                "UN Comtrade returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ComtradeProviderError("UN Comtrade response is not a JSON object")
        if payload.get("error"):
            raise ComtradeProviderError(
                f"UN Comtrade reported an error: {str(payload['error'])[:500]}"
            )
        return payload

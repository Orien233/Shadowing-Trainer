"""Shared synchronous HTTP transport for remote provider adapters.

The application creates many short sentence-level TTS/ASR requests.  Using a
single process-local ``httpx.Client`` keeps connection pooling and TLS reuse in
one place while adapters remain responsible for their protocol payloads and
authentication headers.
"""

from __future__ import annotations

import threading
from typing import Any

import httpx


class ProviderHTTPTransport:
    def __init__(self) -> None:
        self._client: httpx.Client | None = None
        self._lock = threading.Lock()

    def _get_client(self) -> httpx.Client:
        with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.Client(
                    follow_redirects=True,
                    limits=httpx.Limits(max_connections=100, max_keepalive_connections=30),
                )
            return self._client

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return self._get_client().request(method, url, **kwargs)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None


provider_http = ProviderHTTPTransport()


def close_provider_http_client() -> None:
    provider_http.close()


__all__ = ["ProviderHTTPTransport", "close_provider_http_client", "provider_http"]

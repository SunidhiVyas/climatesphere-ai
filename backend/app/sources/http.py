"""Single gateway for ALL outbound HTTP calls.

Safety properties
  * https only, host allow-list (user input can never choose the destination -> no SSRF)
  * connect/read timeouts, bounded response size
  * retries with exponential backoff + jitter on 429/5xx/network errors, honours Retry-After
  * global outbound rate limiter so we stay inside the free-tier quotas of the public APIs
"""
from __future__ import annotations

import random
import threading
import time
from collections import deque
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings

ALLOWED_HOSTS = {
    "archive-api.open-meteo.com",
    "geocoding-api.open-meteo.com",
    "api.open-meteo.com",
    "air-quality-api.open-meteo.com",
    "climate-api.open-meteo.com",
    "api.worldbank.org",
    "api.anthropic.com",
}
MAX_BYTES = 30 * 1024 * 1024


class UpstreamError(Exception):
    def __init__(self, message: str, status: int = 502, retry_after: int | None = None):
        super().__init__(message)
        self.message, self.status, self.retry_after = message, status, retry_after


class _OutboundLimiter:
    """Blocking sliding-window limiter shared by every thread."""

    def __init__(self) -> None:
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, weight: int = 1) -> None:
        limit, window = max(1, get_settings().upstream_per_minute), 60.0
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] > window:
                    self._calls.popleft()
                if len(self._calls) + weight <= limit:
                    self._calls.extend([now] * weight)
                    return
                wait = window - (now - self._calls[0]) + 0.05
            if wait > 20:  # don't hold a request thread for ages
                raise UpstreamError("Upstream quota is busy, please retry shortly.", 503, int(wait))
            time.sleep(min(wait, 5))


_limiter = _OutboundLimiter()
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=httpx.Timeout(40.0, connect=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={"User-Agent": "ClimateSphere/1.0 (climate hazard analyzer)"},
            follow_redirects=False,
        )
    return _client


def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    method: str = "GET",
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    retries: int = 3,
    weight: int = 1,
) -> Any:
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS:
        raise UpstreamError("Blocked outbound request (host not allow-listed).", 500)

    last = "unknown error"
    for attempt in range(retries + 1):
        _limiter.acquire(weight)
        try:
            resp = _get_client().request(method, url, params=params, json=json_body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = f"network error ({exc.__class__.__name__})"
        else:
            if len(resp.content) > MAX_BYTES:
                raise UpstreamError("Upstream response too large.", 502)
            if resp.status_code == 429 or resp.status_code >= 500:
                last = f"upstream status {resp.status_code}"
                ra = resp.headers.get("Retry-After", "")
                if attempt == retries:
                    raise UpstreamError(f"Upstream busy ({resp.status_code}).", 503 if resp.status_code == 429 else 502,
                                        int(ra) if ra.isdigit() else 30)
                time.sleep(min(float(ra) if ra.isdigit() else 2 ** attempt, 20) + random.random())
                continue
            if resp.status_code >= 400:
                reason = ""
                try:  # Open-Meteo style: {"error": true, "reason": "..."}
                    reason = str(resp.json().get("reason", ""))[:200]
                except Exception:  # noqa: BLE001
                    pass
                raise UpstreamError(reason or f"Upstream rejected the request ({resp.status_code}).", 502)
            try:
                return resp.json()
            except ValueError as exc:
                raise UpstreamError("Upstream returned invalid JSON.", 502) from exc
        if attempt < retries:
            time.sleep(2 ** attempt + random.random())
    raise UpstreamError(f"Upstream unavailable: {last}", 502)

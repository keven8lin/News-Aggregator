"""
transport.py — HTTP transport primitives shared by all providers.

Provides:
  - ArticleFetchError   (raised when all retry attempts are exhausted)
  - HttpClient          (protocol — any object with .get() satisfies this)
  - RateLimiter         (time-based request throttle)
  - RETRIABLE_STATUS_CODES
  - with_retry          (exponential backoff helper)
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

import requests


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ArticleFetchError(Exception):
    """Raised when an HTTP request fails after all retry attempts."""


# ---------------------------------------------------------------------------
# HttpClient protocol — any object with .get() satisfies this
# ---------------------------------------------------------------------------

@runtime_checkable
class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Enforces a minimum delay between successive calls to wait()."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay = delay_seconds
        self._last_call: float | None = None

    def wait(self) -> None:
        if self._last_call is not None:
            elapsed = time.monotonic() - self._last_call
            remaining = self._delay - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_call = time.monotonic()


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def with_retry(
    func,
    *args,
    max_attempts: int = 3,
    backoff_seconds: float = 2.0,
    **kwargs,
) -> Any:
    """Call func(*args, **kwargs) up to max_attempts times with exponential backoff.

    Retriable conditions:
      - requests.Timeout
      - requests.ConnectionError
      - HTTP status codes in RETRIABLE_STATUS_CODES

    Non-retriable conditions (raised immediately):
      - Any other requests.HTTPError (e.g. 404, 400)

    Raises:
        ArticleFetchError: if all attempts are exhausted.
    """
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = func(*args, **kwargs)
            if response.status_code in RETRIABLE_STATUS_CODES:
                raise requests.HTTPError(
                    f"Retriable HTTP {response.status_code}", response=response
                )
            response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
        except requests.HTTPError as exc:
            resp = exc.response
            if resp is not None and resp.status_code not in RETRIABLE_STATUS_CODES:
                raise ArticleFetchError(
                    f"Non-retriable HTTP error {resp.status_code}"
                ) from exc
            last_exc = exc

        if attempt < max_attempts:
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    raise ArticleFetchError(f"Failed after {max_attempts} attempts") from last_exc

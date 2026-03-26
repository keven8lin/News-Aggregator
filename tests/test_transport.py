"""Tests for transport.py — RateLimiter and with_retry."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
import requests

from transport import ArticleFetchError, RateLimiter, with_retry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        http_error = requests.HTTPError(response=resp)
        resp.raise_for_status.side_effect = http_error
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

def test_rate_limiter_first_call_does_not_sleep():
    rl = RateLimiter(delay_seconds=5.0)
    start = time.monotonic()
    rl.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1


def test_rate_limiter_subsequent_call_sleeps():
    rl = RateLimiter(delay_seconds=0.1)
    rl.wait()
    start = time.monotonic()
    rl.wait()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05


def test_rate_limiter_no_extra_sleep_if_already_waited():
    rl = RateLimiter(delay_seconds=0.05)
    rl.wait()
    time.sleep(0.1)
    start = time.monotonic()
    rl.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


# ---------------------------------------------------------------------------
# with_retry
# ---------------------------------------------------------------------------

def test_with_retry_succeeds_on_first_attempt():
    func = MagicMock(return_value=make_mock_response({"ok": True}))
    response = with_retry(func, "url", max_attempts=3, backoff_seconds=0.0)
    assert func.call_count == 1
    assert response.json() == {"ok": True}


def test_with_retry_retries_on_connection_error():
    good = make_mock_response({"ok": True})
    func = MagicMock(side_effect=[
        requests.ConnectionError("conn fail"),
        requests.ConnectionError("conn fail"),
        good,
    ])
    response = with_retry(func, "url", max_attempts=3, backoff_seconds=0.0)
    assert func.call_count == 3
    assert response is good


def test_with_retry_retries_on_503():
    bad = MagicMock()
    bad.status_code = 503
    bad.raise_for_status.return_value = None
    good = make_mock_response({"ok": True})
    func = MagicMock(side_effect=[bad, good])
    response = with_retry(func, "url", max_attempts=3, backoff_seconds=0.0)
    assert func.call_count == 2
    assert response is good


def test_with_retry_raises_after_exhaustion():
    func = MagicMock(side_effect=requests.ConnectionError("always fails"))
    with pytest.raises(ArticleFetchError):
        with_retry(func, "url", max_attempts=3, backoff_seconds=0.0)
    assert func.call_count == 3


def test_with_retry_no_retry_on_404():
    func = MagicMock(return_value=make_mock_response({}, status_code=404))
    with pytest.raises(ArticleFetchError):
        with_retry(func, "url", max_attempts=3, backoff_seconds=0.0)
    assert func.call_count == 1


def test_with_retry_no_retry_on_400():
    func = MagicMock(return_value=make_mock_response({}, status_code=400))
    with pytest.raises(ArticleFetchError):
        with_retry(func, "url", max_attempts=3, backoff_seconds=0.0)
    assert func.call_count == 1

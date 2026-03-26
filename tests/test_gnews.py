"""Tests for providers/gnews.py — all HTTP calls use injected MagicMock."""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest
import requests

from models import NewsQuery
from providers.base import NewsProviderError
from providers.config import FetchConfig
from providers.gnews import GNewsProvider
from transport import RateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


def make_gnews_response(n: int = 2) -> dict:
    return {
        "totalArticles": n,
        "articles": [
            {
                "title": f"GNews Article {i}",
                "description": f"Description {i}",
                "content": f"Content {i}",
                "url": f"https://news.example.com/{i}",
                "image": "",
                "publishedAt": "2026-03-01T12:00:00Z",
                "source": {"name": "Reuters", "url": "https://reuters.com"},
            }
            for i in range(n)
        ],
    }


def make_provider(http_client=None, rate_limiter=None, api_key="test-key") -> GNewsProvider:
    if http_client is None:
        http_client = MagicMock()
    if rate_limiter is None:
        rl = MagicMock(spec=RateLimiter)
        rl.wait.return_value = None
        rate_limiter = rl
    return GNewsProvider(
        api_key=api_key,
        http_client=http_client,
        rate_limiter=rate_limiter,
        fetch_config=FetchConfig(timeout_seconds=5.0, backoff_seconds=0.0),
    )


# ---------------------------------------------------------------------------
# provider_name
# ---------------------------------------------------------------------------

def test_provider_name():
    assert make_provider().provider_name == "gnews"


# ---------------------------------------------------------------------------
# fetch() — HTTP call and result parsing
# ---------------------------------------------------------------------------

def test_fetch_calls_search_endpoint():
    http = MagicMock()
    http.get.return_value = make_mock_response(make_gnews_response(2))
    provider = make_provider(http_client=http)

    articles = provider.fetch(NewsQuery(q="iran", page_size=2))

    call_args = http.get.call_args
    assert "gnews.io" in call_args[0][0]
    assert "/search" in call_args[0][0]
    assert len(articles) == 2


def test_fetch_includes_token_in_params():
    http = MagicMock()
    http.get.return_value = make_mock_response(make_gnews_response(1))
    provider = make_provider(http_client=http, api_key="secret-key")

    provider.fetch(NewsQuery())

    params = http.get.call_args[1]["params"]
    assert params["token"] == "secret-key"


def test_fetch_maps_query_fields_to_params():
    http = MagicMock()
    http.get.return_value = make_mock_response(make_gnews_response(0))
    provider = make_provider(http_client=http)

    provider.fetch(NewsQuery(
        q="iran",
        language="fa",
        country="ir",
        page_size=5,
        sort_by="relevance",
    ))

    params = http.get.call_args[1]["params"]
    assert params["q"] == "iran"
    assert params["lang"] == "fa"
    assert params["country"] == "ir"
    assert params["max"] == 5
    assert params["sortby"] == "relevance"


def test_fetch_omits_empty_optional_params():
    http = MagicMock()
    http.get.return_value = make_mock_response(make_gnews_response(0))
    provider = make_provider(http_client=http)

    provider.fetch(NewsQuery())

    params = http.get.call_args[1]["params"]
    assert "q" not in params
    assert "country" not in params
    assert "from" not in params
    assert "to" not in params


def test_fetch_includes_date_params_when_set():
    http = MagicMock()
    http.get.return_value = make_mock_response(make_gnews_response(0))
    provider = make_provider(http_client=http)

    provider.fetch(NewsQuery(
        from_date=datetime(2026, 1, 1),
        to_date=datetime(2026, 3, 1),
    ))

    params = http.get.call_args[1]["params"]
    assert params["from"] == "2026-01-01T00:00:00Z"
    assert params["to"] == "2026-03-01T00:00:00Z"


def test_fetch_calls_rate_limiter():
    http = MagicMock()
    http.get.return_value = make_mock_response(make_gnews_response(1))
    rl = MagicMock(spec=RateLimiter)
    rl.wait.return_value = None
    provider = make_provider(http_client=http, rate_limiter=rl)

    provider.fetch(NewsQuery())

    rl.wait.assert_called_once()


def test_fetch_returns_empty_list_when_no_articles():
    http = MagicMock()
    http.get.return_value = make_mock_response({"totalArticles": 0, "articles": []})
    provider = make_provider(http_client=http)

    articles = provider.fetch(NewsQuery())
    assert articles == []


# ---------------------------------------------------------------------------
# _parse() — Article field mapping
# ---------------------------------------------------------------------------

def test_parse_maps_gnews_fields_correctly():
    raw = {
        "title": "Iran Strikes",
        "description": "Iran launched strikes.",
        "content": "Full content here.",
        "url": "https://reuters.com/iran-strikes",
        "publishedAt": "2026-03-20T10:30:00Z",
        "source": {"name": "Reuters", "url": "https://reuters.com"},
    }
    provider = make_provider()
    article = provider._parse(raw, language="en")

    assert article.provider == "gnews"
    assert article.provider_article_id == "https://reuters.com/iran-strikes"
    assert article.title == "Iran Strikes"
    assert article.url == "https://reuters.com/iran-strikes"
    assert article.summary == "Iran launched strikes."
    assert article.content == "Full content here."
    assert article.authors == []
    assert article.published_at == "2026-03-20T10:30:00Z"
    assert article.source_name == "Reuters"
    assert article.language == "en"
    assert article.raw == raw


def test_parse_handles_missing_optional_fields():
    raw = {
        "title": "Minimal",
        "url": "https://example.com/minimal",
        "source": {},
    }
    provider = make_provider()
    article = provider._parse(raw)
    assert article.summary == ""
    assert article.content == ""
    assert article.source_name == ""
    assert article.published_at == ""


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_fetch_wraps_transport_error_as_news_provider_error():
    http = MagicMock()
    http.get.side_effect = requests.ConnectionError("network down")
    provider = make_provider(http_client=http)
    with pytest.raises(NewsProviderError):
        provider.fetch(NewsQuery())


def test_fetch_wraps_503_error_as_news_provider_error():
    http = MagicMock()
    http.get.return_value = make_mock_response({}, status_code=503)
    # 503 is retriable — all 3 attempts fail → ArticleFetchError → NewsProviderError
    provider = make_provider(http_client=http)
    with pytest.raises(NewsProviderError):
        provider.fetch(NewsQuery())


def test_fetch_wraps_400_error_as_news_provider_error():
    http = MagicMock()
    http.get.return_value = make_mock_response({}, status_code=400)
    provider = make_provider(http_client=http)
    with pytest.raises(NewsProviderError):
        provider.fetch(NewsQuery())
    assert http.get.call_count == 1  # non-retriable — no retries


# ---------------------------------------------------------------------------
# Integration — live connection (skipped unless GNEWS_API_KEY is set)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("GNEWS_API_KEY"),
    reason="GNEWS_API_KEY not set — skipping live connection test",
)
def test_live_connection_fetches_articles():
    """Integration test: hits the real GNews API and verifies data pulls."""
    import requests as _requests
    from transport import RateLimiter as _RateLimiter

    session = _requests.Session()
    rl = _RateLimiter(delay_seconds=0)
    provider = GNewsProvider(
        api_key=os.environ["GNEWS_API_KEY"],
        http_client=session,
        rate_limiter=rl,
        fetch_config=FetchConfig(max_retry_attempts=1),
    )
    articles = provider.fetch(NewsQuery(q="space", page_size=3))
    assert len(articles) >= 1
    assert all(a.provider == "gnews" for a in articles)
    assert all(a.title for a in articles)
    assert all(a.url.startswith("http") for a in articles)

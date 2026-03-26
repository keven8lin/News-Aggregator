"""Tests for providers/spaceflight.py — all HTTP calls use injected MagicMock."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from models import NewsQuery
from providers.base import NewsProviderError
from providers.config import FetchConfig
from providers.spaceflight import SpaceflightNewsProvider
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


def make_sf_article_response(offset: int = 0) -> dict:
    return {
        "count": 100,
        "results": [
            {
                "id": offset + 1,
                "title": f"Space Article {offset}",
                "url": f"https://spacenews.com/{offset}",
                "summary": "A spaceflight summary.",
                "authors": [{"name": "NASA", "socials": {}}],
                "published_at": "2026-01-01T00:00:00Z",
                "news_site": "SpaceNews",
            }
        ],
    }


def make_provider(http_client=None, rate_limiter=None) -> SpaceflightNewsProvider:
    if http_client is None:
        http_client = MagicMock()
    if rate_limiter is None:
        rl = MagicMock(spec=RateLimiter)
        rl.wait.return_value = None
        rate_limiter = rl
    return SpaceflightNewsProvider(
        http_client=http_client,
        rate_limiter=rate_limiter,
        fetch_config=FetchConfig(timeout_seconds=5.0, backoff_seconds=0.0),
    )


# ---------------------------------------------------------------------------
# provider_name
# ---------------------------------------------------------------------------

def test_provider_name():
    assert make_provider().provider_name == "spaceflight"


# ---------------------------------------------------------------------------
# fetch() with empty query → random sampling
# ---------------------------------------------------------------------------

def test_fetch_empty_query_uses_random_sampling():
    http = MagicMock()
    rl = MagicMock(spec=RateLimiter)
    rl.wait.return_value = None

    def side_effect(url, params=None, timeout=None):
        offset = params.get("offset", 0) if params else 0
        return make_mock_response(make_sf_article_response(offset))

    http.get.side_effect = side_effect
    provider = make_provider(http_client=http, rate_limiter=rl)

    with patch.object(provider, "_fetch_total_count", return_value=1000):
        articles = provider.fetch(NewsQuery(page_size=5))

    assert len(articles) == 5
    assert rl.wait.call_count == 5


def test_fetch_empty_query_articles_have_unique_urls():
    http = MagicMock()
    rl = MagicMock(spec=RateLimiter)
    rl.wait.return_value = None

    call_count = [0]

    def side_effect(url, params=None, timeout=None):
        offset = params.get("offset", call_count[0]) if params else 0
        call_count[0] += 1
        return make_mock_response(make_sf_article_response(offset))

    http.get.side_effect = side_effect
    provider = make_provider(http_client=http, rate_limiter=rl)

    with patch.object(provider, "_fetch_total_count", return_value=1000):
        articles = provider.fetch(NewsQuery(page_size=5))

    urls = [a.url for a in articles]
    assert len(set(urls)) == 5


def test_fetch_raises_when_not_enough_articles():
    provider = make_provider()
    with patch.object(provider, "_fetch_total_count", return_value=3):
        with pytest.raises(NewsProviderError):
            provider.fetch(NewsQuery(page_size=5))


# ---------------------------------------------------------------------------
# fetch() with non-empty query → search endpoint
# ---------------------------------------------------------------------------

def test_fetch_with_query_uses_search_endpoint():
    http = MagicMock()
    search_response = {
        "count": 2,
        "results": [
            {
                "id": 1,
                "title": "Iran space launch",
                "url": "https://spacenews.com/iran-space",
                "summary": "Iran launches satellite.",
                "authors": [],
                "published_at": "2026-01-01T00:00:00Z",
                "news_site": "SpaceNews",
            }
        ],
    }
    http.get.return_value = make_mock_response(search_response)
    provider = make_provider(http_client=http)

    articles = provider.fetch(NewsQuery(q="iran", page_size=10))

    call_kwargs = http.get.call_args
    assert call_kwargs[1]["params"]["search"] == "iran"
    assert call_kwargs[1]["params"]["limit"] == 10
    assert len(articles) == 1
    assert articles[0].title == "Iran space launch"


# ---------------------------------------------------------------------------
# _parse() — Article field mapping
# ---------------------------------------------------------------------------

def test_parse_maps_fields_correctly():
    raw = {
        "id": 42,
        "title": "Test Title",
        "url": "https://example.com/test",
        "summary": "Test summary.",
        "authors": [{"name": "NASA"}, {"name": "ESA"}],
        "published_at": "2026-03-01T12:00:00Z",
        "news_site": "SpaceNews",
    }
    provider = make_provider()
    article = provider._parse(raw)

    assert article.provider == "spaceflight"
    assert article.provider_article_id == "42"
    assert article.title == "Test Title"
    assert article.url == "https://example.com/test"
    assert article.summary == "Test summary."
    assert article.authors == ["NASA", "ESA"]
    assert article.published_at == "2026-03-01T12:00:00Z"
    assert article.source_name == "SpaceNews"
    assert article.language == "en"
    assert article.content == ""
    assert article.raw == raw


def test_parse_handles_empty_authors():
    raw = {
        "id": 1,
        "title": "T",
        "url": "https://x.com",
        "authors": [],
        "published_at": "",
        "news_site": "",
    }
    provider = make_provider()
    article = provider._parse(raw)
    assert article.authors == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_fetch_wraps_transport_error_as_news_provider_error():
    http = MagicMock()
    http.get.side_effect = requests.ConnectionError("always fails")
    provider = make_provider(http_client=http)
    with pytest.raises(NewsProviderError):
        provider.fetch(NewsQuery(q="test"))


def test_fetch_no_retry_on_404():
    http = MagicMock()
    http.get.return_value = make_mock_response({}, status_code=404)
    provider = make_provider(http_client=http)
    with pytest.raises(NewsProviderError):
        provider.fetch(NewsQuery(q="test"))
    assert http.get.call_count == 1

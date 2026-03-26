"""Tests for aggregator.py — NewsAggregator."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aggregator import NewsAggregator
from models import SpaceFlight, NewsQuery
from providers.base import NewsProvider, NewsProviderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(i: int = 1, provider: str = "test") -> SpaceFlight:
    return SpaceFlight(
        provider=provider,
        provider_article_id=str(i),
        title=f"SpaceFlight {i}",
        url=f"https://example.com/{i}",
        summary=f"Summary {i}",
        content="",
        authors=[],
        published_at="2026-01-01T00:00:00Z",
        source_name="TestSite",
        language="en",
        category="",
    )


def make_mock_provider(name: str, articles: list[SpaceFlight]) -> MagicMock:
    provider = MagicMock(spec=NewsProvider)
    provider.provider_name = name
    provider.fetch.return_value = articles
    return provider


def make_failing_provider(name: str) -> MagicMock:
    provider = MagicMock(spec=NewsProvider)
    provider.provider_name = name
    provider.fetch.side_effect = NewsProviderError("network down")
    return provider


# ---------------------------------------------------------------------------
# Basic aggregation
# ---------------------------------------------------------------------------

def test_fetch_all_combines_articles_from_multiple_providers():
    p1 = make_mock_provider("gnews", [make_article(1, "gnews"), make_article(2, "gnews")])
    p2 = make_mock_provider("spaceflight", [make_article(3, "spaceflight")])
    aggregator = NewsAggregator([p1, p2])

    articles = aggregator.fetch_all(NewsQuery())

    assert len(articles) == 3
    providers = [a.provider for a in articles]
    assert "gnews" in providers
    assert "spaceflight" in providers


def test_fetch_all_empty_providers_returns_empty():
    aggregator = NewsAggregator([])
    assert aggregator.fetch_all(NewsQuery()) == []


def test_fetch_all_single_provider():
    p = make_mock_provider("gnews", [make_article(1)])
    aggregator = NewsAggregator([p])
    articles = aggregator.fetch_all(NewsQuery())
    assert len(articles) == 1


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_deduplication_removes_same_url_across_providers():
    shared_url = "https://example.com/1"
    a1 = SpaceFlight(
        provider="gnews", provider_article_id=shared_url,
        title="SpaceFlight 1", url=shared_url, summary="", content="",
        authors=[], published_at="", source_name="", language="en", category="",
    )
    a2 = SpaceFlight(
        provider="spaceflight", provider_article_id="1",
        title="SpaceFlight 1 dupe", url=shared_url, summary="", content="",
        authors=[], published_at="", source_name="", language="en", category="",
    )
    p1 = make_mock_provider("gnews", [a1])
    p2 = make_mock_provider("spaceflight", [a2])
    aggregator = NewsAggregator([p1, p2])

    articles = aggregator.fetch_all(NewsQuery())

    assert len(articles) == 1
    assert articles[0].provider == "gnews"  # first-seen wins


def test_deduplication_preserves_unique_urls():
    articles = [make_article(i) for i in range(5)]
    p = make_mock_provider("test", articles)
    aggregator = NewsAggregator([p])
    result = aggregator.fetch_all(NewsQuery())
    assert len(result) == 5


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------

def test_failing_provider_does_not_abort_other_providers():
    failing = make_failing_provider("gnews")
    working = make_mock_provider("spaceflight", [make_article(1, "spaceflight")])
    aggregator = NewsAggregator([failing, working])

    articles = aggregator.fetch_all(NewsQuery())

    assert len(articles) == 1
    assert articles[0].provider == "spaceflight"


def test_all_providers_fail_returns_empty():
    p1 = make_failing_provider("gnews")
    p2 = make_failing_provider("spaceflight")
    aggregator = NewsAggregator([p1, p2])

    articles = aggregator.fetch_all(NewsQuery())

    assert articles == []


# ---------------------------------------------------------------------------
# per_provider query routing
# ---------------------------------------------------------------------------

def test_per_provider_routes_correct_query():
    p1 = make_mock_provider("gnews", [])
    p2 = make_mock_provider("spaceflight", [])
    aggregator = NewsAggregator([p1, p2])

    iran_query = NewsQuery(q="iran")
    space_query = NewsQuery(q="")

    aggregator.fetch_all(
        default_query=iran_query,
        per_provider={"spaceflight": space_query},
    )

    p1.fetch.assert_called_once_with(iran_query)   # uses default
    p2.fetch.assert_called_once_with(space_query)  # uses override


def test_default_query_used_when_no_per_provider():
    p = make_mock_provider("gnews", [])
    aggregator = NewsAggregator([p])

    query = NewsQuery(q="test")
    aggregator.fetch_all(default_query=query)

    p.fetch.assert_called_once_with(query)

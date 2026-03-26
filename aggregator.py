"""
aggregator.py — Multi-provider article aggregation service.

Responsibilities:
  - Fan out a NewsQuery (or per-provider queries) to all registered providers
  - Isolate provider failures so one bad provider does not abort the pipeline
  - Deduplicate results by URL before returning
"""

from __future__ import annotations

import sys

from models import SpaceFlight, NewsQuery
from providers.base import NewsProvider, NewsProviderError


class NewsAggregator:
    """Orchestrates fetching from multiple providers and merging results.

    Example usage:
        aggregator = NewsAggregator([gnews_provider, spaceflight_provider])
        articles = aggregator.fetch_all(
            default_query=iran_query,
            per_provider={"spaceflight": spaceflight_query},
        )
    """

    def __init__(self, providers: list[NewsProvider]) -> None:
        self._providers = providers

    def fetch_all(
        self,
        default_query: NewsQuery,
        *,
        per_provider: dict[str, NewsQuery] | None = None,
    ) -> list[SpaceFlight]:
        """Fetch from all registered providers and return deduplicated articles.

        Args:
            default_query: Query sent to any provider not listed in per_provider.
            per_provider:  Optional dict mapping provider_name → NewsQuery for
                           providers that need a different query (e.g. different
                           search terms or page sizes).

        Returns:
            Combined, URL-deduplicated list of SpaceFlights. Order: provider
            registration order, with duplicates from later providers dropped.

        Note:
            If a provider raises NewsProviderError, a warning is printed to
            stderr and the pipeline continues with the remaining providers.
        """
        all_articles: list[SpaceFlight] = []
        for provider in self._providers:
            query = (per_provider or {}).get(provider.provider_name, default_query)
            try:
                articles = provider.fetch(query)
                all_articles.extend(articles)
            except NewsProviderError as exc:
                print(
                    f"WARNING [{provider.provider_name}] failed — {exc}",
                    file=sys.stderr,
                )
        return self._deduplicate(all_articles)

    @staticmethod
    def _deduplicate(articles: list[SpaceFlight]) -> list[SpaceFlight]:
        """Remove duplicate articles by URL, preserving first-seen order."""
        seen: set[str] = set()
        unique: list[SpaceFlight] = []
        for article in articles:
            if article.url not in seen:
                seen.add(article.url)
                unique.append(article)
        return unique

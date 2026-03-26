"""
providers/spaceflight.py — Spaceflight News API v4 provider.

API docs: https://api.spaceflightnewsapi.net/v4/docs/
Endpoint: https://api.spaceflightnewsapi.net/v4/articles/

Behaviour:
  - query.q non-empty  → uses the native search parameter (?search=<q>)
  - query.q empty      → random offset sampling (fetches page_size random articles)
"""

from __future__ import annotations

import random
from typing import Any

from models import SpaceFlight, NewsQuery
from transport import ArticleFetchError, HttpClient, RateLimiter, with_retry
from providers.base import ArticleParseError, NewsProvider, NewsProviderError
from providers.config import FetchConfig


class SpaceflightNewsProvider(NewsProvider):
    """Fetches articles from the Spaceflight News API v4."""

    BASE_URL = "https://api.spaceflightnewsapi.net/v4"

    def __init__(
        self,
        http_client: HttpClient,
        rate_limiter: RateLimiter,
        fetch_config: FetchConfig = FetchConfig(),
    ) -> None:
        self._http = http_client
        self._rate_limiter = rate_limiter
        self._timeout = fetch_config.get("timeout_seconds", "spaceflight")
        self._max_attempts = fetch_config.get("max_retry_attempts", "spaceflight")
        self._backoff = fetch_config.get("backoff_seconds", "spaceflight")

    @property
    def provider_name(self) -> str:
        return "spaceflight"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, query: NewsQuery) -> list[SpaceFlight]:
        """Fetch articles matching query.

        If query.q is set, uses the /articles/?search= endpoint.
        Otherwise samples page_size random articles from the full corpus.

        Raises:
            NewsProviderError: on transport failure or unrecoverable parse error.
        """
        try:
            if query.q:
                return self._fetch_by_search(query)
            return self._fetch_random(query.page_size)
        except (ArticleFetchError, ArticleParseError) as exc:
            raise NewsProviderError(
                f"[spaceflight] fetch failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_by_search(self, query: NewsQuery) -> list[SpaceFlight]:
        """GET /articles/?search=<q>&limit=N and return parsed articles."""
        self._rate_limiter.wait()
        url = f"{self.BASE_URL}/articles/"
        params: dict[str, Any] = {"search": query.q, "limit": query.page_size}
        response = with_retry(
            self._http.get,
            url,
            params=params,
            timeout=self._timeout,
            max_attempts=self._max_attempts,
            backoff_seconds=self._backoff,
        )
        data = response.json()
        return [self._parse(raw) for raw in data.get("results", [])]

    def _fetch_random(self, n: int) -> list[SpaceFlight]:
        """Sample n random articles via total-count + offset fetches."""
        total = self._fetch_total_count()
        if total < n:
            raise NewsProviderError(
                f"[spaceflight] only {total} articles available, requested {n}"
            )
        offsets = random.sample(range(total), n)
        articles: list[SpaceFlight] = []
        for i, offset in enumerate(offsets, start=1):
            article = self._fetch_at_offset(offset)
            articles.append(article)
            print(f"  [spaceflight] [{i}/{n}] {article.title[:60]}", flush=True)
        return articles

    def _fetch_total_count(self) -> int:
        """GET /articles/?limit=1 and parse the 'count' field."""
        url = f"{self.BASE_URL}/articles/"
        response = with_retry(
            self._http.get,
            url,
            params={"limit": 1},
            timeout=self._timeout,
            max_attempts=self._max_attempts,
            backoff_seconds=self._backoff,
        )
        data = response.json()
        try:
            return int(data["count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ArticleParseError(
                f"Could not parse 'count' from response: {data}"
            ) from exc

    def _fetch_at_offset(self, offset: int) -> SpaceFlight:
        """GET /articles/?limit=1&offset=N with rate limiting."""
        self._rate_limiter.wait()
        url = f"{self.BASE_URL}/articles/"
        response = with_retry(
            self._http.get,
            url,
            params={"limit": 1, "offset": offset},
            timeout=self._timeout,
            max_attempts=self._max_attempts,
            backoff_seconds=self._backoff,
        )
        data = response.json()
        try:
            results = data["results"]
            if not results:
                raise ArticleParseError(f"Empty results at offset {offset}")
            return self._parse(results[0])
        except (KeyError, TypeError) as exc:
            raise ArticleParseError(
                f"Unexpected response structure at offset {offset}: {data}"
            ) from exc

    def _parse(self, raw: dict) -> SpaceFlight:
        """Map a Spaceflight API result dict into a normalized Article."""
        try:
            authors = [
                a["name"]
                for a in raw.get("authors", [])
                if isinstance(a, dict) and "name" in a
            ]
            return SpaceFlight(
                provider="spaceflight",
                provider_article_id=str(raw["id"]),
                title=raw["title"],
                url=raw["url"],
                summary=raw.get("summary", ""),
                content="",  # Spaceflight API does not provide full article text
                authors=authors,
                published_at=raw.get("published_at", ""),
                source_name=raw.get("news_site", ""),
                language="en",
                category="",
                raw=raw,
            )
        except (KeyError, TypeError) as exc:
            raise ArticleParseError(f"Failed to parse Spaceflight article: {raw}") from exc

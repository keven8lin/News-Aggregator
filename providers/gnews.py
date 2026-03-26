"""
providers/gnews.py — GNews API v4 provider.

API docs: https://gnews.io/docs/v4
Endpoint: https://gnews.io/api/v4/search

Authentication: token query parameter (loaded from GNEWS_API_KEY env var via Settings).

GNews response shape:
  {
    "totalArticles": N,
    "articles": [
      {
        "title": "...",
        "description": "...",      # maps to summary
        "content": "...",          # may be truncated
        "url": "...",
        "image": "...",
        "publishedAt": "...",      # ISO-8601
        "source": { "name": "...", "url": "..." }
      },
      ...
    ]
  }
"""

from __future__ import annotations

from models import SpaceFlight, NewsQuery
from transport import ArticleFetchError, HttpClient, RateLimiter, with_retry
from providers.base import ArticleParseError, NewsProvider, NewsProviderError
from providers.config import FetchConfig


class GNewsProvider(NewsProvider):
    """Fetches articles from GNews API v4 using a search query."""

    BASE_URL = "https://gnews.io/api/v4"

    def __init__(
        self,
        api_key: str,
        http_client: HttpClient,
        rate_limiter: RateLimiter,
        fetch_config: FetchConfig = FetchConfig(),
    ) -> None:
        self._api_key = api_key
        self._http = http_client
        self._rate_limiter = rate_limiter
        self._timeout = fetch_config.get("timeout_seconds", "gnews")
        self._max_attempts = fetch_config.get("max_retry_attempts", "gnews")
        self._backoff = fetch_config.get("backoff_seconds", "gnews")

    @property
    def provider_name(self) -> str:
        return "gnews"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self, query: NewsQuery) -> list[SpaceFlight]:
        """Fetch articles matching query from GNews /search endpoint.

        Raises:
            NewsProviderError: on transport failure or unrecoverable parse error.
        """
        self._rate_limiter.wait()
        url = f"{self.BASE_URL}/search"
        params = self._build_params(query)
        try:
            response = with_retry(
                self._http.get,
                url,
                params=params,
                timeout=self._timeout,
                max_attempts=self._max_attempts,
                backoff_seconds=self._backoff,
            )
            data = response.json()
            articles = [self._parse(raw, query.language) for raw in data.get("articles", [])]
            for i, article in enumerate(articles, start=1):
                print(f"  [gnews] [{i}/{len(articles)}] {article.title[:60]}", flush=True)
            return articles
        except ArticleFetchError as exc:
            raise NewsProviderError(f"[gnews] fetch failed: {exc}") from exc
        except ArticleParseError:
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_params(self, query: NewsQuery) -> dict:
        """Map a NewsQuery into GNews API query parameters."""
        params: dict[str, str | int] = {
            "token": self._api_key,
            "max": query.page_size,
            "lang": query.language or "en",
            "sortby": query.sort_by or "publishedAt",
        }
        if query.q:
            params["q"] = query.q
        if query.country:
            params["country"] = query.country
        if query.from_date:
            params["from"] = query.from_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        if query.to_date:
            params["to"] = query.to_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        return params

    def _parse(self, raw: dict, language: str = "en") -> SpaceFlight:
        """Map a GNews article dict into a normalized Article."""
        try:
            return SpaceFlight(
                provider="gnews",
                provider_article_id=raw["url"],  # GNews has no integer ID; URL is stable
                title=raw["title"],
                url=raw["url"],
                summary=raw.get("description", ""),
                content=raw.get("content", ""),
                authors=[],  # GNews API does not provide author information
                published_at=raw.get("publishedAt", ""),
                source_name=raw.get("source", {}).get("name", ""),
                language=language,
                category="",
                raw=raw,
            )
        except (KeyError, TypeError) as exc:
            raise ArticleParseError(f"Failed to parse GNews article: {raw}") from exc

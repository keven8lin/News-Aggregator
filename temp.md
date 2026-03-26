 Plan: Universal News API Architecture                                                                                                                                                                                                     
                                                                                                                                                                                                                                         
 Context

 The user wants a clean, production-quality, extensible architecture that supports multiple news providers (GNews, Spaceflight, and future APIs), normalizes their responses into a single Article model, fetches Iran-focused news from
 both sources simultaneously, and keeps all provider-specific details isolated from the rest of the pipeline.

 ---
 Why this design is better

 The original code tightly couples the ABC to Spaceflight's offset/pagination model (fetch_total_count, fetch_article_at_offset). That contract cannot be fulfilled by query-based APIs (GNews, NewsAPI.org). The new design flips the
 contract: fetch(query: NewsQuery) -> list[Article] is universally implementable. Provider differences (pagination, authentication, field names) are encapsulated inside each provider class. The rest of the pipeline never needs to
 change when a new source is added.

 ---
 File Structure

 bain_capital/
 ├── models.py              # Article + NewsQuery domain models
 ├── config.py              # Settings, env var + .env loader (no new deps)
 ├── transport.py           # HttpClient, RateLimiter, with_retry, ArticleFetchError
 ├── providers/
 │   ├── __init__.py        # re-exports: NewsProvider, NewsProviderError, ArticleParseError
 │   ├── base.py            # NewsProvider ABC + provider exceptions
 │   ├── spaceflight.py     # SpaceflightNewsProvider
 │   └── gnews.py           # GNewsProvider
 ├── aggregator.py          # NewsAggregator (multi-provider, dedup, failure isolation)
 ├── analyzer.py            # MODIFY: `from models import Article` (was fetcher)
 ├── reporter.py            # MODIFY: `from models import Article`, news_site → source_name
 ├── main.py                # REWRITE: wires all components, two queries, both providers
 ├── fetcher.py             # DELETE
 └── tests/
     ├── __init__.py
     ├── test_transport.py       # RateLimiter + with_retry (moved from test_fetcher.py)
     ├── test_spaceflight.py     # SpaceflightNewsProvider tests
     ├── test_gnews.py           # GNewsProvider tests
     ├── test_aggregator.py      # NewsAggregator tests
     ├── test_analyzer.py        # UPDATE: import Article from models
     ├── test_reporter.py        # UPDATE: import Article from models, source_name
     └── test_fetcher.py         # DELETE

 ---
 Module Details

 models.py (NEW)

 from __future__ import annotations
 from dataclasses import dataclass, field
 from datetime import datetime

 @dataclass
 class NewsQuery:
     q: str = ""
     category: str = ""
     language: str = "en"
     country: str = ""
     from_date: datetime | None = None
     to_date: datetime | None = None
     page: int = 1
     page_size: int = 10
     sort_by: str = "publishedAt"   # "publishedAt" | "relevance" | "popularity"

 @dataclass
 class Article:
     provider: str                  # "gnews" | "spaceflight" | ...
     provider_article_id: str       # stable unique id within that provider
     title: str
     url: str
     summary: str
     content: str                   # full body text (may be empty)
     authors: list[str]
     published_at: str              # ISO-8601 string (provider-native format)
     source_name: str               # publication/outlet name
     language: str
     category: str
     raw: dict = field(default_factory=dict)   # original API payload for debugging

 ---
 config.py (NEW)

 Provides a frozen Settings dataclass. Loads .env manually (no python-dotenv dep) via os.environ.setdefault so existing env vars take priority.

 from __future__ import annotations
 import os
 from dataclasses import dataclass
 from pathlib import Path

 def _load_dotenv(path: Path = Path(".env")) -> None:
     """Minimal .env parser — no extra dependency."""
     if not path.exists():
         return
     with path.open() as fh:
         for line in fh:
             line = line.strip()
             if not line or line.startswith("#") or "=" not in line:
                 continue
             key, _, val = line.partition("=")
             os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

 @dataclass(frozen=True)
 class Settings:
     gnews_api_key: str
     newsapi_key: str = ""          # placeholder for future NewsAPI.org provider

     @classmethod
     def from_env(cls, dotenv_path: Path = Path(".env")) -> "Settings":
         _load_dotenv(dotenv_path)
         return cls(
             gnews_api_key=os.environ.get("GNEWS_API_KEY", ""),
             newsapi_key=os.environ.get("NEWSAPI_KEY", ""),
         )

 ---
 transport.py (NEW — extracted from fetcher.py)

 All transport primitives move here unchanged. Add ArticleFetchError here.

 Contents:
 - HttpClient protocol (unchanged)
 - RateLimiter (unchanged)
 - RETRIABLE_STATUS_CODES (unchanged)
 - with_retry() (unchanged)
 - ArticleFetchError (moved from fetcher.py)

 ---
 providers/base.py (NEW)

 from abc import ABC, abstractmethod
 from models import Article, NewsQuery

 class NewsProviderError(Exception):
     """Provider-level failure after retries / parse errors."""

 class ArticleParseError(NewsProviderError):
     """Provider response could not be mapped to Article."""

 class NewsProvider(ABC):
     @property
     @abstractmethod
     def provider_name(self) -> str:
         """Short identifier: 'gnews', 'spaceflight', 'newsapi', ..."""

     @abstractmethod
     def fetch(self, query: NewsQuery) -> list[Article]:
         """Return articles matching query. Raises NewsProviderError on failure."""

 providers/__init__.py

 from .base import NewsProvider, NewsProviderError, ArticleParseError
 __all__ = ["NewsProvider", "NewsProviderError", "ArticleParseError"]

 ---
 providers/spaceflight.py (NEW)

 class SpaceflightNewsProvider(NewsProvider):
     BASE_URL = "https://api.spaceflightnewsapi.net/v4"
     provider_name = "spaceflight"

     def __init__(self, http_client, rate_limiter, timeout=10.0,
                  max_retry_attempts=3, backoff_seconds=2.0): ...

     def fetch(self, query: NewsQuery) -> list[Article]:
         # Branch on query.q:
         #   non-empty → _fetch_by_search (GET /articles/?search=<q>&limit=N)
         #   empty     → _fetch_random    (random offset sampling)
         # Both raise NewsProviderError on failure.

     def _fetch_by_search(self, query: NewsQuery) -> list[Article]:
         self._rate_limiter.wait()
         url = f"{self.BASE_URL}/articles/"
         params = {"search": query.q, "limit": query.page_size}
         response = with_retry(self._http.get, url, params=params, ...)
         return [self._parse(r) for r in response.json().get("results", [])]

     def _fetch_random(self, n: int) -> list[Article]:
         total = self._fetch_total_count()
         if total < n:
             raise NewsProviderError(f"Only {total} articles available, requested {n}")
         offsets = random.sample(range(total), n)
         articles = []
         for offset in offsets:
             self._rate_limiter.wait()
             articles.append(self._fetch_at_offset(offset))
         return articles

     def _fetch_total_count(self) -> int: ...      # GET /articles/?limit=1 → data["count"]
     def _fetch_at_offset(self, offset: int) -> Article: ...  # GET /articles/?limit=1&offset=N

     def _parse(self, raw: dict) -> Article:
         # Maps Spaceflight fields → Article
         # provider="spaceflight"
         # provider_article_id=str(raw["id"])
         # source_name=raw.get("news_site", "")
         # authors=[a["name"] for a in raw.get("authors", []) if "name" in a]
         # content=""  (SNAPI doesn't provide full text)
         # language="en", category=""
         # raw=raw

 ---
 providers/gnews.py (NEW)

 class GNewsProvider(NewsProvider):
     BASE_URL = "https://gnews.io/api/v4"
     provider_name = "gnews"

     def __init__(self, api_key: str, http_client, rate_limiter,
                  timeout=10.0, max_retry_attempts=3, backoff_seconds=2.0): ...

     def fetch(self, query: NewsQuery) -> list[Article]:
         self._rate_limiter.wait()
         url = f"{self.BASE_URL}/search"
         params = self._build_params(query)
         try:
             response = with_retry(self._http.get, url, params=params, ...)
             return [self._parse(a) for a in response.json().get("articles", [])]
         except ArticleFetchError as exc:
             raise NewsProviderError(f"GNews fetch failed: {exc}") from exc

     def _build_params(self, query: NewsQuery) -> dict:
         params = {
             "token": self._api_key,
             "max": query.page_size,
             "lang": query.language or "en",
             "sortby": query.sort_by or "publishedAt",
         }
         if query.q:        params["q"] = query.q
         if query.country:  params["country"] = query.country
         if query.from_date: params["from"] = query.from_date.strftime("%Y-%m-%dT%H:%M:%SZ")
         if query.to_date:   params["to"]   = query.to_date.strftime("%Y-%m-%dT%H:%M:%SZ")
         return params

     def _parse(self, raw: dict) -> Article:
         # GNews response shape: { title, description, content, url, publishedAt,
         #                         source: {name, url} }
         # provider_article_id = raw["url"]
         # summary = raw.get("description", "")
         # content = raw.get("content", "")
         # source_name = raw.get("source", {}).get("name", "")
         # authors = []   (GNews provides no author field)
         # language = query.language  (not in response; store from query context)

 Note: _parse receives only the raw dict; language not in GNews response, default to "en".

 ---
 aggregator.py (NEW)

 import sys
 from models import Article, NewsQuery
 from providers.base import NewsProvider, NewsProviderError

 class NewsAggregator:
     def __init__(self, providers: list[NewsProvider]) -> None:
         self._providers = providers

     def fetch_all(
         self,
         default_query: NewsQuery,
         *,
         per_provider: dict[str, NewsQuery] | None = None,
     ) -> list[Article]:
         """
         Fetch from all providers. Per-provider query overrides default_query.
         Failure of one provider is logged but does not abort others.
         Results are deduplicated by URL.
         """
         all_articles: list[Article] = []
         for provider in self._providers:
             query = (per_provider or {}).get(provider.provider_name, default_query)
             try:
                 articles = provider.fetch(query)
                 print(f"  [{provider.provider_name}] fetched {len(articles)} articles")
                 all_articles.extend(articles)
             except NewsProviderError as exc:
                 print(f"  WARNING [{provider.provider_name}] failed — {exc}", file=sys.stderr)
         return self._deduplicate(all_articles)

     @staticmethod
     def _deduplicate(articles: list[Article]) -> list[Article]:
         seen: set[str] = set()
         unique: list[Article] = []
         for article in articles:
             if article.url not in seen:
                 seen.add(article.url)
                 unique.append(article)
         return unique

 ---
 main.py (REWRITE)

 import os, sys
 from datetime import datetime, timezone

 import requests

 from config import Settings
 from models import NewsQuery
 from transport import RateLimiter
 from providers.gnews import GNewsProvider
 from providers.spaceflight import SpaceflightNewsProvider
 from aggregator import NewsAggregator
 from analyzer import (authors_appearing_more_than_once, count_authors,
                       extract_text_corpus, least_common_words_containing_letter,
                       tokenize, word_frequency)
 from reporter import ReportWriteError, build_report, output_filename, write_report

 IRAN_QUERY = NewsQuery(
     q="iran AND (attacks OR leader OR damage OR energy OR strikes)",
     language="en",
     page_size=10,
     sort_by="publishedAt",
 )
 SPACEFLIGHT_QUERY = NewsQuery(page_size=10)  # empty q → random space articles
 RATE_LIMIT_SECONDS = 1.0

 def main() -> None:
     settings = Settings.from_env()
     session = requests.Session()
     rate_limiter = RateLimiter(delay_seconds=RATE_LIMIT_SECONDS)

     providers = [
         GNewsProvider(api_key=settings.gnews_api_key, http_client=session, rate_limiter=rate_limiter),
         SpaceflightNewsProvider(http_client=session, rate_limiter=rate_limiter),
     ]
     aggregator = NewsAggregator(providers)

     print("Fetching articles from all providers...")
     articles = aggregator.fetch_all(
         default_query=IRAN_QUERY,
         per_provider={
             "gnews": IRAN_QUERY,
             "spaceflight": SPACEFLIGHT_QUERY,
         },
     )
     # ... rest of pipeline unchanged (analyze → report → print summary)

 ---
 analyzer.py (MODIFY — 1 line)

 Change from fetcher import Article → from models import Article.

 reporter.py (MODIFY — 3 lines)

 - from fetcher import Article → from models import Article
 - a.news_site → a.source_name (in build_report)
 - JSON key "news_site" → "source_name" in the output dict

 ---
 Tests

 tests/test_transport.py (NEW)

 Port test_rate_limiter_* and test_retry_* tests verbatim from test_fetcher.py.
 Update imports to: from transport import RateLimiter, with_retry, ArticleFetchError.

 tests/test_spaceflight.py (NEW)

 Key tests:
 - fetch() with empty query → calls _fetch_random (total count + offset endpoints)
 - fetch() with non-empty query → calls /articles/?search=iran&limit=10
 - _parse() maps raw dict to Article correctly (provider="spaceflight", provider_article_id=str(id))
 - Retry/rate-limit behavior inherited from transport (1 focused test)
 - NewsProviderError raised on 404 and connection failure

 tests/test_gnews.py (NEW)

 Key tests:
 - fetch() calls correct URL with token, max, lang, sortby params
 - _build_params() maps all NewsQuery fields to GNews params (q, country, from/to dates)
 - _parse() maps GNews JSON fields to Article correctly (source_name from source.name, authors=[])
 - Rate limiter called once per fetch (GNews is 1 HTTP call per query, unlike Spaceflight)
 - NewsProviderError raised on transport failure

 tests/test_aggregator.py (NEW)

 Key tests:
 - fetch_all() combines articles from 2 providers
 - Deduplication removes duplicate URLs regardless of provider
 - Provider failure isolation: one provider raises NewsProviderError, other articles still returned
 - per_provider routing passes correct query to each provider
 - Empty providers list returns []

 tests/test_reporter.py (MODIFY)

 - Update make_article() helper: use new Article fields (provider, provider_article_id, source_name, etc.)
 - Update from fetcher import Article → from models import Article
 - Update art["news_site"] assertion → art["source_name"]

 tests/test_analyzer.py (MODIFY)

 - Update from fetcher import Article → from models import Article
 - Update Article(id=..., ...) constructor calls to use new field names

 tests/test_fetcher.py (DELETE)

 Fully replaced by test_transport.py + test_spaceflight.py.

 ---
 Article constructor (test helpers)

 New minimal Article for tests:
 def make_article(i: int = 1, provider: str = "test", authors=None) -> Article:
     return Article(
         provider=provider,
         provider_article_id=str(i),
         title=f"Article {i}",
         url=f"https://example.com/{i}",
         summary=f"Summary {i}",
         content="",
         authors=authors or [],
         published_at="2026-01-01T00:00:00Z",
         source_name="TestSite",
         language="en",
         category="",
     )

 ---
 Adding a new provider (e.g. NewsAPI.org)

 1. Create providers/newsapi.py with class NewsAPIProvider(NewsProvider):
 2. Implement provider_name = "newsapi", fetch(query), _build_params(query), _parse(raw)
 3. Add newsapi_key: str to Settings (already stubbed in config.py)
 4. Add NewsAPIProvider(api_key=settings.newsapi_key, ...) to the providers list in main.py
 5. No other files change.

 ---
 Verification

 # Set env vars (or write to .env file)
 export GNEWS_API_KEY=5442a3edfa3f193b7950dea9a17ee4b8

 python main.py
 # → prints ~20 articles (10 GNews Iran + 10 random Spaceflight)
 # → writes summary_results_quotes_<timestamp>.json

 pytest tests/ -v
 # → all tests pass with no live API calls

 ---
 Optional future improvements

 - article.content full-text indexing (currently empty for most providers)
 - SQLite persistence layer via a ArticleRepository class (no changes to providers needed)
 - CLI flags (argparse) for query, provider selection, output path
 - Article caching by url fingerprint to avoid re-fetching recent articles
 - Async fetching with httpx/asyncio for parallel provider calls
 - NewsAPIProvider (newsapi.org) as a third provider using the stub in Settings
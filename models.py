"""
models.py — Normalized domain models shared across all providers.

These dataclasses are provider-agnostic: every news source maps its
response into Article, and every query is expressed as a NewsQuery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NewsQuery:
    """Provider-agnostic query/request model.

    Each provider translates these fields into its own API parameters.
    Fields left at their defaults are treated as "not set" by providers.
    """

    q: str = ""                          # free-text search query
    category: str = ""                   # topic/category filter (provider-specific values)
    language: str = "en"                 # ISO 639-1 language code
    country: str = ""                    # ISO 3166-1 alpha-2 country code
    from_date: datetime | None = None    # earliest published date (inclusive)
    to_date: datetime | None = None      # latest published date (inclusive)
    page: int = 1                        # page number (1-based)
    page_size: int = 10                  # articles per page / per request
    sort_by: str = "publishedAt"         # "publishedAt" | "relevance" | "popularity"


@dataclass
class SpaceFlight:
    """Normalized article model that works across all news providers.

    Every provider maps its response fields into this shape.
    The `raw` field preserves the original API payload for debugging
    and future field extraction without re-fetching.
    """

    provider: str               # source identifier: "gnews" | "spaceflight" | ...
    provider_article_id: str    # stable unique ID within that provider (URL or int as str)
    title: str
    url: str
    summary: str                # short description / lede
    content: str                # full body text (empty if provider does not supply it)
    authors: list[str]
    published_at: str           # ISO-8601 datetime string (provider-native format)
    source_name: str            # publication or outlet name
    language: str               # ISO 639-1 language code
    category: str               # topic/category (empty if provider does not supply it)
    raw: dict = field(default_factory=dict)  # original API payload for debugging

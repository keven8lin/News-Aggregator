"""
providers/base.py — Abstract base class and exceptions for all news providers.

Adding a new provider requires:
  1. Subclass NewsProvider
  2. Implement provider_name and fetch()
  3. No changes needed anywhere else in the pipeline
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from models import SpaceFlight, NewsQuery


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class NewsProviderError(Exception):
    """Raised when a provider fails to fetch articles (after retries, parse errors, etc.)."""


class ArticleParseError(NewsProviderError):
    """Raised when a provider response cannot be mapped into an Article."""


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class NewsProvider(ABC):
    """Universal interface for any REST-based news provider.

    Contract:
      - fetch(query) returns a (possibly empty) list of normalized Articles.
      - fetch(query) raises NewsProviderError on any unrecoverable failure.
      - The rest of the pipeline only ever calls fetch() — provider internals
        (pagination model, auth, field names) are fully encapsulated.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short, stable identifier: 'gnews' | 'spaceflight' | 'newsapi' | ..."""

    @abstractmethod
    def fetch(self, query: NewsQuery) -> list[SpaceFlight]:
        """Return articles matching query.

        Raises:
            NewsProviderError: on transport failure or unrecoverable parse error.
        """

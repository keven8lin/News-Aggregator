"""
providers/config.py — Fetch configuration with global defaults and per-provider overrides.

Usage:
    # All defaults:
    cfg = FetchConfig()

    # Override globally:
    cfg = FetchConfig(page_size=5, timeout_seconds=30.0)

    # Override per-provider (falls back to global when None):
    cfg = FetchConfig(page_size=10, gnews_page_size=5)

    # Resolve effective value:
    cfg.get("page_size", "gnews")        # → 5
    cfg.get("page_size", "spaceflight")  # → 10
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FetchConfig:
    """Global fetch knobs with optional per-provider overrides.

    For each setting, the provider-specific value is used when non-None;
    otherwise the global default applies.
    """

    # global defaults
    rate_limit_seconds: float = 1.0
    page_size: int = 10
    timeout_seconds: float = 10.0
    max_retry_attempts: int = 3
    backoff_seconds: float = 2.0

    # per-provider overrides (None → fall back to global)
    gnews_rate_limit_seconds: float | None = None
    gnews_page_size: int | None = None
    gnews_timeout_seconds: float | None = None
    gnews_max_retry_attempts: int | None = None
    gnews_backoff_seconds: float | None = None

    spaceflight_rate_limit_seconds: float | None = None
    spaceflight_page_size: int | None = None
    spaceflight_timeout_seconds: float | None = None
    spaceflight_max_retry_attempts: int | None = None
    spaceflight_backoff_seconds: float | None = None

    def get(self, field: str, provider: str) -> object:
        """Return the provider-specific override for field, or the global default."""
        override = getattr(self, f"{provider}_{field}", None)
        return override if override is not None else getattr(self, field)

"""
config.py — Centralized settings and secret management.

Loads secrets from environment variables, with optional .env file support
(no external dependencies — uses a minimal built-in parser).

Usage:
    settings = Settings.from_env()          # reads .env then environment
    settings = Settings.from_env(".env.test")  # override path for tests
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env file parser.

    Reads KEY=VALUE pairs into os.environ using setdefault so that
    pre-existing environment variables always take priority over .env values.
    Supports quoted values and ignores blank lines and # comments.
    """
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment variables.

    Extend this class when adding a new provider that requires an API key.
    """

    gnews_api_key: str                  # GNews API token
    newsapi_key: str = ""               # NewsAPI.org key (stub for future provider)

    @classmethod
    def from_env(cls, dotenv_path: Path = Path(".env")) -> Settings:
        """Build Settings by loading .env (if present) then reading env vars.

        Args:
            dotenv_path: Path to .env file. Defaults to .env in the working directory.

        Returns:
            A frozen Settings instance.
        """
        _load_dotenv(dotenv_path)
        return cls(
            gnews_api_key=os.environ.get("GNEWS_API_KEY", ""),
            newsapi_key=os.environ.get("NEWSAPI_KEY", ""),
        )

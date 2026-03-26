"""
reporter.py — Report assembly and JSON file output.

Provides:
  - build_report()   — assembles the analysis dict
  - output_filename() — generates the timestamped filename
  - write_report()   — serializes to JSON and writes to disk
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from models import SpaceFlight


class ReportWriteError(Exception):
    """Raised when the report file cannot be written."""


def output_filename(timestamp: datetime | None = None) -> str:
    """
    Return the output filename in the format:
      summary_results_quotes_YYYYMMDDHHMMSS.json

    Uses datetime.now(timezone.utc).replace(tzinfo=None) if timestamp is not provided.
    The timestamp parameter is injectable for deterministic testing.
    """
    ts = timestamp if timestamp is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    return f"summary_results_quotes_{ts.strftime('%Y%m%d%H%M%S')}.json"


def build_report(
    articles: list[SpaceFlight],
    least_common_l_words: list[tuple[str, int]],
    repeat_authors: dict[str, int],
    generated_at: datetime | None = None,
) -> dict:
    """
    Assemble the summary report dictionary.

    Structure:
    {
      "generated_at": "2026-03-25T20:00:00",
      "article_count": 10,
      "articles": [
        {"id": ..., "title": ..., "url": ..., "news_site": ...,
         "published_at": ..., "authors": [...]}
      ],
      "analysis": {
        "least_common_words_containing_l": [
          {"word": "orbital", "count": 1}, ...
        ],
        "authors_appearing_more_than_once": [
          {"author": "NASA", "count": 3}, ...
        ]
      }
    }

    generated_at defaults to datetime.now(timezone.utc).replace(tzinfo=None) if not provided (injectable
    for deterministic tests).
    """
    ts = generated_at if generated_at is not None else datetime.now(timezone.utc).replace(tzinfo=None)

    return {
        "generated_at": ts.isoformat(),
        "article_count": len(articles),
        "articles": [
            {
                "provider": a.provider,
                "provider_article_id": a.provider_article_id,
                "title": a.title,
                "url": a.url,
                "source_name": a.source_name,
                "published_at": a.published_at,
                "authors": a.authors,
                "raw": a.raw,
            }
            for a in articles
        ],
        "analysis": {
            "least_common_words_containing_l": [
                {"word": word, "count": count}
                for word, count in least_common_l_words
            ],
            "authors_appearing_more_than_once": [
                {"author": name, "count": count}
                for name, count in repeat_authors.items()
            ],
        },
    }


def write_report(report: dict, filepath: str) -> None:
    """
    Serialize the report dict to a JSON file at filepath.

    Uses indent=2 and ensure_ascii=False for readable output.
    Wraps any OSError in ReportWriteError.
    """
    try:
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
    except OSError as exc:
        raise ReportWriteError(f"Could not write report to '{filepath}': {exc}") from exc

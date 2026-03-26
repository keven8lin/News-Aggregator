"""
main.py — Entry point. Wires concrete dependencies and runs the pipeline.

Usage:
    # With a .env file containing GNEWS_API_KEY=<key>:
    python main.py

    # Or with an environment variable:
    GNEWS_API_KEY=<key> python main.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import requests

from aggregator import NewsAggregator
from analyzer import (
    authors_appearing_more_than_once,
    count_authors,
    extract_text_corpus,
    least_common_words_containing_letter,
    tokenize,
    word_frequency,
)
from config import Settings
from models import NewsQuery
from providers.config import FetchConfig
from providers.gnews import GNewsProvider
from providers.spaceflight import SpaceflightNewsProvider
from reporter import ReportWriteError, build_report, output_filename, write_report
from transport import RateLimiter

# ---------------------------------------------------------------------------
# Query definitions
# ---------------------------------------------------------------------------

FETCH_CONFIG = FetchConfig()

IRAN_QUERY = NewsQuery(
    q="iran AND (attacks OR leader OR damage OR energy OR strikes)",
    language="en",
    page_size=FETCH_CONFIG.get("page_size", "gnews"),
    sort_by="publishedAt",
)

# Empty q → SpaceflightNewsProvider falls back to random article sampling
SPACEFLIGHT_QUERY = NewsQuery(page_size=FETCH_CONFIG.get("page_size", "spaceflight"))


def main() -> None:
    # 1. Load configuration
    settings = Settings.from_env()
    if not settings.gnews_api_key:
        print(
            "ERROR: GNEWS_API_KEY is not set.\n"
            "  Add it to a .env file:  GNEWS_API_KEY=<your-key>\n"
            "  Or export it:           export GNEWS_API_KEY=<your-key>",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Build shared HTTP transport
    session = requests.Session()
    gnews_limiter = RateLimiter(delay_seconds=FETCH_CONFIG.get("rate_limit_seconds", "gnews"))
    spaceflight_limiter = RateLimiter(delay_seconds=FETCH_CONFIG.get("rate_limit_seconds", "spaceflight"))

    # 3. Register providers
    providers = [
        GNewsProvider(
            api_key=settings.gnews_api_key,
            http_client=session,
            rate_limiter=gnews_limiter,
            fetch_config=FETCH_CONFIG,
        ),
        SpaceflightNewsProvider(
            http_client=session,
            rate_limiter=spaceflight_limiter,
            fetch_config=FETCH_CONFIG,
        ),
    ]
    aggregator = NewsAggregator(providers)

    # 4. Fetch — GNews uses the Iran query; Spaceflight returns random space news
    print("Fetching articles from all providers...")
    articles = aggregator.fetch_all(
        default_query=IRAN_QUERY,
        per_provider={
            "gnews": IRAN_QUERY,
            "spaceflight": SPACEFLIGHT_QUERY,
        },
    )
    print(f"Total articles after deduplication: {len(articles)}")

    if not articles:
        print("ERROR: No articles fetched.", file=sys.stderr)
        sys.exit(1)

    # 5. Split articles by provider, analyse each, and write to separate folders
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for provider_name in ("gnews", "spaceflight"):
        provider_articles = [a for a in articles if a.provider == provider_name]
        if not provider_articles:
            print(f"No articles for {provider_name}, skipping.", file=sys.stderr)
            continue

        corpus = extract_text_corpus(provider_articles)
        tokens = tokenize(corpus)
        freq = word_frequency(tokens)
        l_words = least_common_words_containing_letter(freq, letter="l", n=5)
        author_counts = count_authors(provider_articles)
        repeat_authors = authors_appearing_more_than_once(author_counts)

        os.makedirs(provider_name, exist_ok=True)
        filename = os.path.join(provider_name, output_filename(timestamp=now))
        report = build_report(provider_articles, l_words, repeat_authors, generated_at=now)
        try:
            write_report(report, filename)
        except ReportWriteError as exc:
            print(f"ERROR: Could not write {provider_name} report — {exc}", file=sys.stderr)
            sys.exit(2)

        print(f"\nReport written to: {filename}")

        print(f"\n--- [{provider_name}] Top 5 least common words containing 'l' ---")
        for entry in report["analysis"]["least_common_words_containing_l"]:
            print(f"  {entry['word']!r}: {entry['count']}")

        repeated = report["analysis"]["authors_appearing_more_than_once"]
        if repeated:
            print(f"\n--- [{provider_name}] Authors appearing more than once ---")
            for entry in repeated:
                print(f"  {entry['author']}: {entry['count']} articles")
        else:
            print(f"\n[{provider_name}] No authors appeared more than once.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)

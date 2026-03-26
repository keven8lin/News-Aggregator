"""
analyzer.py — Pure text analysis functions.

All functions are stateless and side-effect free — no I/O, no external
dependencies beyond the standard library. This makes every function
trivially testable without mocking.
"""

from __future__ import annotations

import re
from collections import Counter

from models import SpaceFlight


def extract_text_corpus(articles: list[SpaceFlight]) -> str:
    """Concatenate title and summary for every article into a single string."""
    parts = []
    for article in articles:
        if article.title:
            parts.append(article.title)
        if article.summary:
            parts.append(article.summary)
    return " ".join(parts)


def tokenize(text: str) -> list[str]:
    """
    Normalize text into a list of lowercase word tokens.

    Steps:
      1. Lowercase
      2. Strip everything except a-z and whitespace
      3. Split on whitespace
      4. Drop empty strings
    """
    lowered = text.lower()
    cleaned = re.sub(r"[^a-z\s]", "", lowered)
    return [token for token in cleaned.split() if token]


def word_frequency(tokens: list[str]) -> Counter:
    """Return a Counter mapping each token to its occurrence count."""
    return Counter(tokens)


def least_common_words_containing_letter(
    freq: Counter,
    letter: str = "l",
    n: int = 5,
) -> list[tuple[str, int]]:
    """
    Return the n least-common words that contain `letter`.

    Ties are broken alphabetically to ensure deterministic output.
    Words with zero occurrences are not included (only words in freq matter).
    """
    filtered = [(word, count) for word, count in freq.items() if letter in word]
    # Sort ascending by count, then alphabetically for ties
    filtered.sort(key=lambda x: (x[1], x[0]))
    return filtered[:n]


def count_authors(articles: list[SpaceFlight]) -> Counter:
    """Return a Counter of author name → number of articles they appear in."""
    all_authors: list[str] = []
    for article in articles:
        all_authors.extend(article.authors)
    return Counter(all_authors)


def authors_appearing_more_than_once(author_counts: Counter) -> dict[str, int]:
    """
    Filter to authors with more than one article.

    Returns a dict sorted by count descending, then name ascending for ties.
    """
    repeated = {name: count for name, count in author_counts.items() if count > 1}
    return dict(
        sorted(repeated.items(), key=lambda x: (-x[1], x[0]))
    )

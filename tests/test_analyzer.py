"""Tests for analyzer.py — pure functions, no mocking required."""

from __future__ import annotations

from collections import Counter

import pytest

from analyzer import (
    authors_appearing_more_than_once,
    count_authors,
    extract_text_corpus,
    least_common_words_containing_letter,
    tokenize,
    word_frequency,
)
from models import SpaceFlight


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(
    title: str = "Title",
    summary: str = "Summary",
    authors: list[str] | None = None,
) -> SpaceFlight:
    return SpaceFlight(
        provider="test",
        provider_article_id="1",
        title=title,
        url="https://example.com",
        summary=summary,
        content="",
        authors=authors or [],
        published_at="2026-01-01T00:00:00Z",
        source_name="TestSite",
        language="en",
        category="",
    )


# ---------------------------------------------------------------------------
# extract_text_corpus
# ---------------------------------------------------------------------------

def test_extract_text_corpus_joins_title_and_summary():
    articles = [make_article(title="Rocket Launch", summary="A rocket launched.")]
    corpus = extract_text_corpus(articles)
    assert "Rocket Launch" in corpus
    assert "A rocket launched." in corpus


def test_extract_text_corpus_multiple_articles():
    articles = [
        make_article(title="One", summary="Uno"),
        make_article(title="Two", summary="Dos"),
    ]
    corpus = extract_text_corpus(articles)
    assert "One" in corpus
    assert "Dos" in corpus


def test_extract_text_corpus_empty_list():
    assert extract_text_corpus([]) == ""


def test_extract_text_corpus_empty_summary():
    articles = [make_article(title="Title Only", summary="")]
    corpus = extract_text_corpus(articles)
    assert corpus == "Title Only"


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------

def test_tokenize_lowercases():
    assert tokenize("NASA") == ["nasa"]


def test_tokenize_strips_punctuation():
    tokens = tokenize("SpaceX's mission!")
    # Apostrophe is stripped, joining "SpaceX" + "s" → "spacexs"
    assert "spacexs" in tokens
    assert "mission" in tokens
    # No punctuation characters remain
    for t in tokens:
        assert t.isalpha()


def test_tokenize_splits_on_whitespace():
    assert tokenize("hello world") == ["hello", "world"]


def test_tokenize_drops_empty_strings():
    tokens = tokenize("  hello   world  ")
    assert "" not in tokens
    assert tokens == ["hello", "world"]


def test_tokenize_empty_string():
    assert tokenize("") == []


def test_tokenize_numbers_stripped():
    tokens = tokenize("Falcon 9 launched")
    assert "9" not in tokens  # digits stripped
    assert "falcon" in tokens
    assert "launched" in tokens


# ---------------------------------------------------------------------------
# word_frequency
# ---------------------------------------------------------------------------

def test_word_frequency_counts_correctly():
    freq = word_frequency(["a", "b", "a", "a", "b"])
    assert freq["a"] == 3
    assert freq["b"] == 2


def test_word_frequency_empty():
    assert word_frequency([]) == Counter()


def test_word_frequency_single_token():
    freq = word_frequency(["launch"])
    assert freq["launch"] == 1


# ---------------------------------------------------------------------------
# least_common_words_containing_letter
# ---------------------------------------------------------------------------

def test_least_common_filters_to_letter():
    freq = Counter({"orbital": 1, "space": 5, "rocket": 3, "launch": 2})
    result = least_common_words_containing_letter(freq, letter="l", n=5)
    words = [w for w, _ in result]
    assert "orbital" in words   # contains 'l'
    assert "launch" in words    # contains 'l'
    assert "space" not in words  # no 'l'
    assert "rocket" not in words  # no 'l'


def test_least_common_returns_n_results():
    # 10 words containing 'l', all with count 1
    freq = Counter({f"word{i}l": 1 for i in range(10)})
    result = least_common_words_containing_letter(freq, letter="l", n=5)
    assert len(result) == 5


def test_least_common_returns_fewer_when_not_enough():
    freq = Counter({"orbital": 1, "full": 2})
    result = least_common_words_containing_letter(freq, letter="l", n=5)
    assert len(result) == 2


def test_least_common_sorts_ascending_by_count():
    freq = Counter({"all": 10, "orbital": 1, "full": 3, "will": 5})
    result = least_common_words_containing_letter(freq, letter="l", n=4)
    counts = [c for _, c in result]
    assert counts == sorted(counts)


def test_least_common_alphabetical_tiebreaking():
    freq = Counter({"zeal": 1, "ball": 1, "call": 1})
    result = least_common_words_containing_letter(freq, letter="l", n=3)
    words = [w for w, _ in result]
    assert words == ["ball", "call", "zeal"]


def test_least_common_empty_freq():
    result = least_common_words_containing_letter(Counter(), letter="l", n=5)
    assert result == []


def test_least_common_no_words_with_letter():
    freq = Counter({"space": 3, "rocket": 2, "orbit": 1})
    result = least_common_words_containing_letter(freq, letter="l", n=5)
    assert result == []


# ---------------------------------------------------------------------------
# count_authors
# ---------------------------------------------------------------------------

def test_count_authors_counts_correctly():
    articles = [
        make_article(authors=["NASA", "SpaceX"]),
        make_article(authors=["NASA"]),
        make_article(authors=["ESA"]),
    ]
    counts = count_authors(articles)
    assert counts["NASA"] == 2
    assert counts["SpaceX"] == 1
    assert counts["ESA"] == 1


def test_count_authors_empty_articles():
    assert count_authors([]) == Counter()


def test_count_authors_no_authors():
    articles = [make_article(authors=[]), make_article(authors=[])]
    assert count_authors(articles) == Counter()


# ---------------------------------------------------------------------------
# authors_appearing_more_than_once
# ---------------------------------------------------------------------------

def test_authors_more_than_once_excludes_singles():
    counts = Counter({"NASA": 3, "SpaceX": 1, "ESA": 2})
    result = authors_appearing_more_than_once(counts)
    assert "SpaceX" not in result
    assert result["NASA"] == 3
    assert result["ESA"] == 2


def test_authors_more_than_once_empty():
    assert authors_appearing_more_than_once(Counter()) == {}


def test_authors_more_than_once_none_qualify():
    counts = Counter({"A": 1, "B": 1})
    assert authors_appearing_more_than_once(counts) == {}


def test_authors_more_than_once_sorted_by_count_desc():
    counts = Counter({"A": 2, "B": 5, "C": 3})
    result = authors_appearing_more_than_once(counts)
    values = list(result.values())
    assert values == sorted(values, reverse=True)


def test_authors_more_than_once_alphabetical_tiebreaking():
    counts = Counter({"Zebra": 3, "Alpha": 3, "Beta": 3})
    result = authors_appearing_more_than_once(counts)
    keys = list(result.keys())
    assert keys == ["Alpha", "Beta", "Zebra"]

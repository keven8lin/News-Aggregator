"""Tests for reporter.py."""

from __future__ import annotations

import json
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, mock_open, patch

import pytest

from models import SpaceFlight
from reporter import ReportWriteError, build_report, output_filename, write_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(i: int = 1, authors: list[str] | None = None) -> SpaceFlight:
    return SpaceFlight(
        provider="test",
        provider_article_id=str(i),
        title=f"SpaceFlight {i}",
        url=f"https://example.com/{i}",
        summary=f"Summary {i}",
        content="",
        authors=authors or [],
        published_at="2026-01-01T00:00:00Z",
        source_name="TestSite",
        language="en",
        category="",
    )


FIXED_TS = datetime(2026, 3, 25, 20, 0, 0)
FIXED_FILENAME = "summary_results_quotes_20260325200000.json"


# ---------------------------------------------------------------------------
# output_filename
# ---------------------------------------------------------------------------

def test_output_filename_format_with_fixed_timestamp():
    assert output_filename(timestamp=FIXED_TS) == FIXED_FILENAME


def test_output_filename_contains_correct_date_parts():
    ts = datetime(2024, 12, 31, 23, 59, 59)
    filename = output_filename(timestamp=ts)
    assert "20241231235959" in filename
    assert filename.endswith(".json")
    assert filename.startswith("summary_results_quotes_")


def test_output_filename_uses_utcnow_when_no_timestamp():
    # Should not raise — just verify it returns a string ending in .json
    filename = output_filename()
    assert filename.endswith(".json")
    assert filename.startswith("summary_results_quotes_")
    assert len(filename) == len("summary_results_quotes_20260325200000.json")


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------

def test_build_report_top_level_keys():
    articles = [make_article(1), make_article(2)]
    l_words = [("orbital", 1), ("full", 2)]
    repeat = {"NASA": 3}
    report = build_report(articles, l_words, repeat, generated_at=FIXED_TS)
    assert set(report.keys()) == {"generated_at", "article_count", "articles", "analysis"}


def test_build_report_article_count():
    articles = [make_article(i) for i in range(5)]
    report = build_report(articles, [], {}, generated_at=FIXED_TS)
    assert report["article_count"] == 5


def test_build_report_articles_shape():
    articles = [make_article(1, authors=["NASA"])]
    report = build_report(articles, [], {}, generated_at=FIXED_TS)
    art = report["articles"][0]
    assert art["provider_article_id"] == "1"
    assert art["title"] == "SpaceFlight 1"
    assert art["authors"] == ["NASA"]
    assert "url" in art
    assert "source_name" in art
    assert "published_at" in art


def test_build_report_l_words_shape():
    l_words = [("orbital", 1), ("full", 2)]
    report = build_report([], l_words, {}, generated_at=FIXED_TS)
    entries = report["analysis"]["least_common_words_containing_l"]
    assert len(entries) == 2
    assert entries[0] == {"word": "orbital", "count": 1}
    assert entries[1] == {"word": "full", "count": 2}


def test_build_report_repeat_authors_shape():
    repeat = {"NASA": 3, "ESA": 2}
    report = build_report([], [], repeat, generated_at=FIXED_TS)
    entries = report["analysis"]["authors_appearing_more_than_once"]
    assert {"author": "NASA", "count": 3} in entries
    assert {"author": "ESA", "count": 2} in entries


def test_build_report_empty_repeat_authors():
    report = build_report([], [], {}, generated_at=FIXED_TS)
    assert report["analysis"]["authors_appearing_more_than_once"] == []


def test_build_report_generated_at_format():
    report = build_report([], [], {}, generated_at=FIXED_TS)
    assert report["generated_at"] == "2026-03-25T20:00:00"


def test_build_report_uses_utcnow_when_no_timestamp():
    # Should not raise; generated_at should be a non-empty ISO string
    report = build_report([], [], {})
    assert isinstance(report["generated_at"], str)
    assert "T" in report["generated_at"]  # ISO format


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

def test_write_report_creates_valid_json(tmp_path):
    filepath = str(tmp_path / "test_report.json")
    report = {"key": "value", "number": 42}
    write_report(report, filepath)
    with open(filepath, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded == report


def test_write_report_uses_indent(tmp_path):
    filepath = str(tmp_path / "test_report.json")
    report = {"key": "value"}
    write_report(report, filepath)
    with open(filepath, encoding="utf-8") as fh:
        raw = fh.read()
    # Indented JSON contains newlines
    assert "\n" in raw


def test_write_report_raises_report_write_error_on_os_error():
    with patch("builtins.open", side_effect=OSError("disk full")):
        with pytest.raises(ReportWriteError) as exc_info:
            write_report({"key": "value"}, "/fake/path/report.json")
    assert "disk full" in str(exc_info.value)


def test_write_report_wraps_os_error_not_bare_exception():
    with patch("builtins.open", side_effect=OSError("no space")):
        with pytest.raises(ReportWriteError):
            write_report({}, "/bad/path.json")

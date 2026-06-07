"""Tests for review_engine.py."""
from unittest.mock import Mock, patch

import pytest

from src.analyzers.base import Finding
from src.diff_parser import ChangedFile
from src.review_engine import (
    _DEFAULT_MAX_DIFF_BYTES,
    _MAX_DIFF_BYTES_HARD_CAP,
    _get_max_diff_bytes,
    ReviewService,
)


def test_review_filters_analyzer_findings_to_changed_python_lines():
    analyzer = Mock()
    analyzer.analyze.return_value = [
        Finding("warning", "src/app.py", 2, "F401", "unused", source="ruff"),
        Finding("warning", "src/app.py", 9, "E501", "long", source="ruff"),
    ]
    service = ReviewService()
    service.analyzers = [analyzer]

    with patch("src.review_engine.parse_diff", return_value=[
        ChangedFile("src/app.py", added_lines={2}),
        ChangedFile("README.md", added_lines={1}),
    ]), patch("src.review_engine.legacy_review", return_value=[]):
        findings = service.review("diff")

    assert [f.rule for f in findings] == ["F401"]
    analyzer.analyze.assert_called_once_with("src/app.py")


def test_review_ignores_analyzer_errors_and_adds_legacy_findings():
    analyzer = Mock()
    analyzer.analyze.side_effect = RuntimeError("ruff failed")
    service = ReviewService()
    service.analyzers = [analyzer]

    with patch("src.review_engine.parse_diff", return_value=[
        ChangedFile("src/app.py", added_lines={2}),
    ]), patch("src.review_engine.legacy_review", return_value=[
        {
            "severity": "error",
            "line": 2,
            "rule": "no-bare-except",
            "message": "Bare except clause",
            "file": "src/app.py",
        }
    ]):
        findings = service.review("diff")

    assert len(findings) == 1
    assert findings[0].rule == "no-bare-except"
    assert findings[0].source == "regex"


def test_review_service_handles_missing_ruff_analyzer():
    with patch("src.review_engine.RuffAnalyzer", side_effect=RuntimeError("missing")):
        service = ReviewService()

    assert service.analyzers == []


def test_review_rejects_diff_larger_than_500kb(monkeypatch):
    monkeypatch.setenv("GITHUB_REVIEW_MAX_DIFF_BYTES", "1024")  # 1KB limit
    assert _get_max_diff_bytes() == 1024

    service = ReviewService()
    huge_diff = "x" * 2048  # 2KB
    findings = service.review(huge_diff)
    assert len(findings) == 1
    assert findings[0].rule == "diff-too-large"
    assert findings[0].severity == "error"


def test_review_processes_diff_exactly_at_size_limit(monkeypatch):
    monkeypatch.setenv("GITHUB_REVIEW_MAX_DIFF_BYTES", str(_DEFAULT_MAX_DIFF_BYTES))
    service = ReviewService()
    boundary_diff = "x" * _DEFAULT_MAX_DIFF_BYTES

    with patch("src.review_engine.parse_diff", return_value=[]) as parse, \
         patch("src.review_engine.legacy_review", return_value=[]) as legacy:
        findings = service.review(boundary_diff)

    assert findings == []
    parse.assert_called_once_with(boundary_diff)
    legacy.assert_called_once_with(boundary_diff)


def test_review_rejects_diff_one_byte_over_default_limit(monkeypatch):
    monkeypatch.delenv("GITHUB_REVIEW_MAX_DIFF_BYTES", raising=False)
    service = ReviewService()
    oversized_diff = "x" * (_DEFAULT_MAX_DIFF_BYTES + 1)

    with patch("src.review_engine.parse_diff") as parse, \
         patch("src.review_engine.legacy_review") as legacy:
        findings = service.review(oversized_diff)

    assert len(findings) == 1
    assert findings[0].rule == "diff-too-large"
    assert findings[0].severity == "error"
    assert findings[0].source == "review_engine"
    parse.assert_not_called()
    legacy.assert_not_called()


def test_review_allows_empty_diff():
    service = ReviewService()

    with patch("src.review_engine.parse_diff", return_value=[]) as parse, \
         patch("src.review_engine.legacy_review", return_value=[]) as legacy:
        findings = service.review("")

    assert findings == []
    parse.assert_called_once_with("")
    legacy.assert_called_once_with("")


def test_review_handles_binary_like_decoded_diff_text(monkeypatch):
    monkeypatch.setenv("GITHUB_REVIEW_MAX_DIFF_BYTES", "1024")
    service = ReviewService()
    binary_like_diff = "diff --git a/blob b/blob\n+\x00\x80\xff"

    with patch("src.review_engine.parse_diff", return_value=[]) as parse, \
         patch("src.review_engine.legacy_review", return_value=[]) as legacy:
        findings = service.review(binary_like_diff)

    assert findings == []
    parse.assert_called_once_with(binary_like_diff)
    legacy.assert_called_once_with(binary_like_diff)


@pytest.mark.xfail(
    raises=UnicodeEncodeError,
    reason="ReviewService.review accepts str and currently crashes on unpaired surrogates.",
)
def test_review_current_gap_non_utf8_surrogateescape_text():
    ReviewService().review("\udcff")


def test_invalid_max_diff_size_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GITHUB_REVIEW_MAX_DIFF_BYTES", "abc")

    assert _get_max_diff_bytes() == _DEFAULT_MAX_DIFF_BYTES


def test_large_max_diff_size_env_override_is_clamped_to_hard_cap(monkeypatch, caplog):
    ten_gib = 10 * 1024 * 1024 * 1024
    monkeypatch.setenv("GITHUB_REVIEW_MAX_DIFF_BYTES", str(ten_gib))

    assert _get_max_diff_bytes() == _MAX_DIFF_BYTES_HARD_CAP
    assert "exceeds hard cap" in caplog.text


def test_review_allows_diff_under_limit():
    service = ReviewService()
    with patch("src.review_engine.parse_diff", return_value=[]), \
         patch("src.review_engine.legacy_review", return_value=[]):
        findings = service.review("small diff")
    assert all(f.rule != "diff-too-large" for f in findings)

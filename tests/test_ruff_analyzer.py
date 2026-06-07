"""Tests for analyzers/ruff.py."""
import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from src.analyzers.ruff import RuffAnalyzer


def test_ruff_analyzer_skips_non_python_files():
    with patch("src.analyzers.ruff.subprocess.run") as mock_run:
        assert RuffAnalyzer().analyze("README.md") == []
    mock_run.assert_not_called()


def test_ruff_analyzer_parses_json_findings():
    payload = [
        {
            "filename": "src/app.py",
            "location": {"row": 3},
            "code": "F401",
            "message": "unused import",
            "fix": {"message": "Remove import"},
        },
        {
            "filename": "src/app.py",
            "location": {"row": 5},
            "code": "E501",
            "message": "line too long",
        },
    ]
    completed = SimpleNamespace(returncode=1, stdout=json.dumps(payload))

    with patch("src.analyzers.ruff.subprocess.run", return_value=completed) as mock_run:
        findings = RuffAnalyzer("custom-ruff").analyze("src/app.py")

    assert [f.rule for f in findings] == ["F401", "E501"]
    assert findings[0].severity == "error"
    assert findings[0].suggestion == "Remove import"
    assert findings[1].severity == "warning"
    mock_run.assert_called_once_with(
        ["custom-ruff", "check", "--output-format", "json", "src/app.py"],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_ruff_analyzer_returns_empty_for_clean_output_and_failures():
    with patch(
        "src.analyzers.ruff.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=""),
    ):
        assert RuffAnalyzer().analyze("src/app.py") == []

    with patch(
        "src.analyzers.ruff.subprocess.run",
        return_value=SimpleNamespace(returncode=2, stdout="[]"),
    ):
        assert RuffAnalyzer().analyze("src/app.py") == []

    with patch(
        "src.analyzers.ruff.subprocess.run",
        return_value=SimpleNamespace(returncode=1, stdout="not-json"),
    ):
        assert RuffAnalyzer().analyze("src/app.py") == []

    with patch(
        "src.analyzers.ruff.subprocess.run",
        side_effect=FileNotFoundError,
    ):
        assert RuffAnalyzer().analyze("src/app.py") == []

    with patch(
        "src.analyzers.ruff.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ruff", 30),
    ):
        assert RuffAnalyzer().analyze("src/app.py") == []

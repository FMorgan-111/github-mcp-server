"""Ruff subprocess analyzer — run ruff check as JSON, return Findings."""
import json
import subprocess
from pathlib import Path

from .base import Finding


class RuffAnalyzer:
    """Run ruff check on a file, return structured findings."""

    def __init__(self, ruff_cmd: str = "ruff"):
        self.cmd = ruff_cmd

    def analyze(self, file_path: str) -> list[Finding]:
        path = Path(file_path)
        if path.suffix != ".py":
            return []

        try:
            result = subprocess.run(
                [self.cmd, "check", "--output-format", "json", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        if result.returncode not in (0, 1):
            return []  # ruff crash / config error? skip

        try:
            violations = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return []

        findings = []
        for v in violations:
            findings.append(Finding(
                severity="error" if v.get("fix") else "warning",
                file=v.get("filename", str(path)),
                line=v.get("location", {}).get("row", 0),
                rule=v.get("code", ""),
                message=v.get("message", ""),
                suggestion=v.get("fix", {}).get("message", ""),
                source="ruff",
            ))
        return findings

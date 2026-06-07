"""Analyzer protocol — pluggable code analysis backends."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Finding:
    severity: str       # "error" | "warning" | "info"
    file: str
    line: int
    rule: str           # e.g. "F401", "E501"
    message: str
    suggestion: str = ""
    source: str = ""    # "ruff", "bandit", "regex"


class Analyzer(Protocol):
    """Any backend that takes file path → list of Findings."""

    def analyze(self, file_path: str) -> list[Finding]:
        ...

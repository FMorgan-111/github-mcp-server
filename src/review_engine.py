"""ReviewService — orchestrate diff parsing + analyzers + old regex fallback."""
import logging
import os
from .diff_parser import parse_diff
from .analyzers.base import Finding
from .analyzers.ruff import RuffAnalyzer
from .review import review_diff as legacy_review

# 500KB default; override with GITHUB_REVIEW_MAX_DIFF_BYTES env var
_DEFAULT_MAX_DIFF_BYTES = 500 * 1024
# GitHub's PR diff API limit is 1MB; keep this stdio server safely below
# unbounded memory use even if the env var is misconfigured.
_MAX_DIFF_BYTES_HARD_CAP = 1024 * 1024

logger = logging.getLogger(__name__)


def _get_max_diff_bytes() -> int:
    val = os.environ.get("GITHUB_REVIEW_MAX_DIFF_BYTES", "")
    try:
        max_bytes = int(val) if val else _DEFAULT_MAX_DIFF_BYTES
    except ValueError:
        return _DEFAULT_MAX_DIFF_BYTES
    if max_bytes > _MAX_DIFF_BYTES_HARD_CAP:
        logger.warning(
            "GITHUB_REVIEW_MAX_DIFF_BYTES=%s exceeds hard cap of %s bytes; clamping.",
            max_bytes,
            _MAX_DIFF_BYTES_HARD_CAP,
        )
        return _MAX_DIFF_BYTES_HARD_CAP
    return max_bytes


class ReviewService:
    def __init__(self) -> None:
        self.analyzers = []
        try:
            self.analyzers.append(RuffAnalyzer())
        except Exception:
            pass

    def review(self, diff_text: str) -> list[Finding]:
        # Guard against oversized diffs that could OOM the process
        max_bytes = _get_max_diff_bytes()
        diff_bytes = len(diff_text.encode("utf-8"))
        if diff_bytes > max_bytes:
            return [Finding(
                severity="error",
                file="",
                line=0,
                rule="diff-too-large",
                message=f"Diff too large ({diff_bytes // 1024} KB, limit {max_bytes // 1024} KB). "
                        f"Review skipped to avoid OOM.",
                source="review_engine",
            )]

        findings: list[Finding] = []
        changed = parse_diff(diff_text)

        # Ruff on changed Python files
        for cf in changed:
            if cf.path.endswith(".py"):
                for a in self.analyzers:
                    try:
                        raw = a.analyze(cf.path)
                        # Filter: only changed lines
                        findings.extend(f for f in raw if f.line in cf.added_lines)
                    except Exception:
                        pass

        # Legacy regex fallback
        legacy_issues = legacy_review(diff_text)
        for li in legacy_issues:
            findings.append(Finding(
                severity=li["severity"],
                file=li.get("file", ""),
                line=li["line"],
                rule=li["rule"],
                message=li["message"],
                source="regex",
            ))

        return findings

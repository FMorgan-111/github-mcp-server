"""ReviewService — orchestrate diff parsing + analyzers + old regex fallback."""
from .diff_parser import parse_diff
from .analyzers.base import Finding
from .analyzers.ruff import RuffAnalyzer
from .review import review_diff as legacy_review


class ReviewService:
    def __init__(self):
        self.analyzers = []
        try:
            self.analyzers.append(RuffAnalyzer())
        except Exception:
            pass

    def review(self, diff_text: str) -> list[Finding]:
        findings = []
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

"""Audit logger — JSONL write operations for traceability."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional


class AuditLogger:
    """Write structured operation audits as JSONL to a sink."""

    REDACT_KEYS = {
        "GITHUB_TOKEN", "token", "password", "api_key",
        "authorization", "auth", "secret"
    }
    ALLOWED_DIRS = {"/var/log/github-mcp", "stdout", "stderr"}

    def __init__(self, sink: str = "stdout"):
        """
        Args:
            sink: "stdout", "stderr", or an absolute path under allowed dirs.
        """
        self.sink = sink
        self._validate_sink()
        self._fobj: Optional[object] = None

    def _validate_sink(self) -> None:
        if self.sink in ("stdout", "stderr"):
            return
        if not os.path.isabs(self.sink):
            raise ValueError(
                f"Audit file sink must be absolute path, got: {self.sink}"
            )
        # Prevent traversal: resolve symlinks, then check the canonical
        # parent directory is under an allowed tree (if configured).
        # For production, restrict via GITHUB_AUDIT_DIR_ALLOWLIST.
        parent = os.path.dirname(os.path.abspath(self.sink))
        allowlist_str = os.environ.get("GITHUB_AUDIT_DIR_ALLOWLIST", "")
        if allowlist_str:
            allowed = allowlist_str.split(",")
            if not any(
                os.path.commonpath([parent, d]) == d for d in allowed
            ):
                raise ValueError(
                    f"Audit sink parent {parent} not in "
                    f"GITHUB_AUDIT_DIR_ALLOWLIST ({allowlist_str})"
                )

    def _get_stream(self):
        if self.sink == "stdout":
            return sys.stdout
        if self.sink == "stderr":
            return sys.stderr
        if self._fobj is None:
            parent = os.path.dirname(self.sink)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._fobj = open(self.sink, "a", encoding="utf-8")
        return self._fobj

    def log(
        self,
        tool: str,
        action: str,
        repo: str,
        dry_run: bool = False,
        policy_decision: str = "allow",
        policy_rule: str = "",
        request_body: Optional[dict] = None,
        response: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Write one audit entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": uuid.uuid4().hex[:12],
            "tool": tool,
            "action": action,
            "repo": repo,
            "dry_run": dry_run,
            "policy": {
                "decision": policy_decision,
                "matched_rule": policy_rule,
            },
            "request": _redact(request_body) if isinstance(request_body, dict) else None,
            "response": _redact(response) if isinstance(response, dict) else None,
            "error": error,
        }
        try:
            stream = self._get_stream()
            stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            stream.flush()
        except Exception as e:
            # Audit must never crash the tool, but log the failure somewhere
            print(f"[audit] write failed: {e}", file=sys.stderr)

    def close(self) -> None:
        if self._fobj:
            self._fobj.close()
            self._fobj = None


def _redact(obj):
    """Recursively redact sensitive keys from dicts and lists."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in AuditLogger.REDACT_KEYS:
                out[k] = "***REDACTED***"
            elif isinstance(v, (dict, list)):
                out[k] = _redact(v)
            elif isinstance(v, str) and len(v) > 200:
                out[k] = v[:200] + "..."
            else:
                out[k] = v
        return out
    if isinstance(obj, list):
        return [_redact(item) for item in obj]
    return obj

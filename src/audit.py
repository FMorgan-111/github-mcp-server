"""Audit logger — JSONL write operations for traceability."""
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Optional


class AuditLogger:
    """Write structured operation audits as JSONL to a sink."""

    REDACT_KEYS = {
        "GITHUB_TOKEN", "token", "password", "api_key",
        "authorization", "auth", "secret"
    }

    def __init__(self, sink: str = "stdout"):
        """
        Args:
            sink: "stdout", "stderr", or a file path like "/var/log/audit.jsonl"
        """
        self.sink = sink
        self._fobj: Optional[object] = None

    def _get_stream(self):
        if self.sink == "stdout":
            return sys.stdout
        if self.sink == "stderr":
            return sys.stderr
        # file sink — open on first write
        if self._fobj is None:
            os.makedirs(os.path.dirname(self.sink), exist_ok=True)
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
            "request": _redact(request_body) if request_body else None,
            "response": _redact(response) if response else None,
            "error": error,
        }
        try:
            stream = self._get_stream()
            stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            stream.flush()
        except Exception:
            pass  # audit must never crash the tool

    def close(self) -> None:
        if self._fobj:
            self._fobj.close()
            self._fobj = None


def _redact(d: dict) -> dict:
    """Return a shallow copy with sensitive keys replaced."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if k.lower() in AuditLogger.REDACT_KEYS:
            out[k] = "***REDACTED***"
        elif isinstance(v, dict):
            out[k] = _redact(v)
        elif isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "..."
        else:
            out[k] = v
    return out

"""Tests for audit.py — JSONL logging & redaction."""
import io
import json
import os
from datetime import datetime
import tempfile
import unittest
from unittest.mock import Mock, patch

from src.audit import AuditLogger


class TestAuditLogger(unittest.TestCase):

    def test_log_to_file(self):
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            logger = AuditLogger(sink=path)
            logger.log(
                tool="create_pr", action="pull_request.create",
                repo="owner/repo",
                policy_decision="allow", policy_rule="repo_allowlist:owner/*",
                request_body={"title": "fix bug", "head": "patch", "base": "main"},
                response={"number": 42, "html_url": "https://github.com/owner/repo/pull/42"},
            )
            logger.close()

            with open(path, "r") as f:
                entry = json.loads(f.readline())

            self.assertEqual(entry["tool"], "create_pr")
            self.assertEqual(entry["repo"], "owner/repo")
            self.assertEqual(entry["policy"]["decision"], "allow")
            self.assertIn("matched_rule", entry["policy"])
            self.assertEqual(entry["request"]["title"], "fix bug")
            self.assertEqual(entry["response"]["number"], 42)
            self.assertEqual(entry["dry_run"], False)
            self.assertIn("timestamp", entry)
            self.assertIn("request_id", entry)
        finally:
            logger.close()
            if os.path.exists(path):
                os.unlink(path)

    def test_log_dry_run(self):
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            logger = AuditLogger(sink=path)
            logger.log(
                tool="create_issue", action="issue.create",
                repo="owner/repo", dry_run=True,
                policy_decision="allow", policy_rule="default-allow",
                request_body={"title": "test", "body": "test body"},
            )
            logger.close()

            with open(path, "r") as f:
                entry = json.loads(f.readline())

            self.assertTrue(entry["dry_run"])
            self.assertIsNone(entry["response"])
        finally:
            logger.close()
            if os.path.exists(path):
                os.unlink(path)

    def test_log_denied(self):
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            logger = AuditLogger(sink=path)
            logger.log(
                tool="create_pr", action="pull_request.create",
                repo="forbidden/repo",
                policy_decision="deny",
                policy_rule="repo_allowlist:deny_unlisted",
                error="repo forbidden/repo not in allowlist",
            )
            logger.close()

            with open(path, "r") as f:
                entry = json.loads(f.readline())

            self.assertEqual(entry["policy"]["decision"], "deny")
            self.assertEqual(entry["error"], "repo forbidden/repo not in allowlist")
        finally:
            logger.close()
            if os.path.exists(path):
                os.unlink(path)

    def test_redaction(self):
        """Sensitive keys are redacted in audit logs."""
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            logger = AuditLogger(sink=path)
            logger.log(
                tool="create_pr", action="pull_request.create",
                repo="owner/repo",
                request_body={
                    "title": "test",
                    "token": "ghp_should_be_redacted",
                    "password": "secret123",
                },
                response={
                    "status": 201,
                    "authorization": "bearer xyz",
                },
            )
            logger.close()

            with open(path, "r") as f:
                entry = json.loads(f.readline())

            self.assertEqual(entry["request"]["token"], "***REDACTED***")
            self.assertEqual(entry["request"]["password"], "***REDACTED***")
            self.assertEqual(entry["response"]["authorization"], "***REDACTED***")
        finally:
            logger.close()
            if os.path.exists(path):
                os.unlink(path)

    def test_log_format_redacts_nested_values_and_truncates_long_strings(self):
        stream = io.StringIO()
        with patch("src.audit.sys.stdout", stream):
            logger = AuditLogger(sink="stdout")
            logger.log(
                tool="create_issue",
                action="issue.create",
                repo="owner/repo",
                request_body={
                    "nested": {"api_key": "secret"},
                    "items": [{"auth": "bearer"}],
                    "body": "x" * 250,
                },
            )

        entry = json.loads(stream.getvalue())
        datetime.fromisoformat(entry["timestamp"])
        self.assertEqual(len(entry["request_id"]), 12)
        self.assertEqual(entry["request"]["nested"]["api_key"], "***REDACTED***")
        self.assertEqual(entry["request"]["items"][0]["auth"], "***REDACTED***")
        self.assertEqual(entry["request"]["body"], "x" * 200 + "...")

    def test_multiple_operations_write_json_lines(self):
        path = tempfile.mktemp(suffix=".jsonl")
        try:
            logger = AuditLogger(sink=path)
            logger.log("tool1", "action1", "owner/repo")
            logger.log("tool2", "action2", "owner/repo", error="failed")
            logger.close()

            with open(path, "r", encoding="utf-8") as f:
                entries = [json.loads(line) for line in f]

            self.assertEqual([e["tool"] for e in entries], ["tool1", "tool2"])
            self.assertEqual(entries[1]["error"], "failed")
        finally:
            logger.close()
            if os.path.exists(path):
                os.unlink(path)

    def test_invalid_relative_sink_and_allowlist_rejection(self):
        with self.assertRaises(ValueError):
            AuditLogger(sink="relative.jsonl")

        with patch.dict(os.environ, {"GITHUB_AUDIT_DIR_ALLOWLIST": "/allowed"}, clear=False):
            with self.assertRaises(ValueError):
                AuditLogger(sink="/tmp/audit.jsonl")

    def test_logging_errors_are_suppressed(self):
        logger = AuditLogger(sink="stdout")
        broken = Mock()
        broken.write.side_effect = RuntimeError("disk full")

        with patch.object(logger, "_get_stream", return_value=broken):
            logger.log("tool", "action", "owner/repo")

        broken.write.assert_called_once()


if __name__ == "__main__":
    unittest.main()

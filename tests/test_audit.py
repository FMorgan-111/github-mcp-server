"""Tests for audit.py — JSONL logging & redaction."""
import io
import json
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()

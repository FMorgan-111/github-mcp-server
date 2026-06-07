"""Tests for GitHub MCP tools"""
import unittest
from unittest.mock import patch, Mock
from src.analyzers.base import Finding
from src.policy import PolicyDecision
from src.tools import (
    search_code,
    list_issues,
    get_pr_diff,
    review_pr_diff,
    comment_pr_review,
    create_issue,
    create_pr,
)
from src.review import review_diff


class TestTools(unittest.TestCase):

    def _allow_policy(self):
        policy = Mock()
        policy.check_repo.return_value = PolicyDecision(
            "allow", "repo allowed", "repo_allowlist:owner/*"
        )
        policy.check_branch_for_pr.return_value = PolicyDecision(
            "allow", "branch allowed", "branch_unprotected"
        )
        return policy

    def _audit(self):
        audit = Mock()
        audit.log.return_value = None
        return audit

    @patch('src.tools.GitHubClient')
    def test_search_code(self, mock_client_class):
        """Test search_code tool with mocked httpx response"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.search_code.return_value = {
            "items": [
                {
                    'path': 'src/main.py',
                    'repo': 'owner/test-repo',
                    'url': 'https://github.com/owner/test-repo/blob/main/src/main.py'
                }
            ]
        }

        # Call function
        result = search_code("def main", "owner/test-repo")

        # Verify
        self.assertIn("Found 1 results", result)
        self.assertIn("src/main.py in owner/test-repo", result)
        self.assertIn("https://github.com/owner/test-repo", result)
        mock_client.search_code.assert_called_once_with("def main", "owner/test-repo")

    def test_review_diff(self):
        """Test review_diff catches print statement"""
        diff_text = """diff --git a/src/test.py b/src/test.py
index 1234567..abcdefg 100644
--- a/src/test.py
+++ b/src/test.py
@@ -1,3 +1,4 @@
 def hello():
+    print("Debug message")
     return "world"
"""

        issues = review_diff(diff_text)

        # Should find the print statement
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['severity'], 'warning')
        self.assertEqual(issues[0]['rule'], 'no-print')
        self.assertIn('Print statement found', issues[0]['message'])


    def test_search_empty_results(self):
        """Test search_code returns proper message for no results"""
        from unittest.mock import patch, Mock
        with patch('src.tools.GitHubClient') as mock_cls:
            mock_cls.return_value.search_code.return_value = {"items": []}
            result = search_code("nonexistent", "owner/repo")
            self.assertIn("No results", result)

    def test_search_error(self):
        """Test search_code handles API errors gracefully"""
        from unittest.mock import patch, Mock
        with patch('src.tools.GitHubClient') as mock_cls:
            mock_cls.return_value.search_code.return_value = {"error": "API rate limit exceeded"}
            result = search_code("test", "owner/repo")
            self.assertIn("Error", result)
            self.assertIn("rate limit", result)

    def test_list_issues_success(self):
        with patch('src.tools.GitHubClient') as mock_cls:
            mock_cls.return_value.list_issues.return_value = [
                {"number": 1, "title": "Bug", "html_url": "https://example/1"}
            ]
            result = list_issues("owner/repo", "closed")
            self.assertIn("Issues in owner/repo (closed)", result)
            self.assertIn("#1: Bug", result)
            mock_cls.return_value.list_issues.assert_called_once_with("owner/repo", "closed")

    def test_list_issues_empty_and_error(self):
        with patch('src.tools.GitHubClient') as mock_cls:
            mock_cls.return_value.list_issues.return_value = []
            self.assertIn("No open issues", list_issues("owner/repo"))

            mock_cls.return_value.list_issues.return_value = {"error": "bad credentials"}
            self.assertEqual(list_issues("owner/repo"), "Error: bad credentials")

    def test_get_pr_diff_success_and_error(self):
        with patch('src.tools.GitHubClient') as mock_cls:
            mock_cls.return_value.get_pr_diff.return_value = {"diff": "+change"}
            self.assertIn("PR #7 diff:\n\n+change", get_pr_diff("owner/repo", 7))

            mock_cls.return_value.get_pr_diff.return_value = {"error": "not found"}
            self.assertEqual(get_pr_diff("owner/repo", 7), "Error: not found")

    def test_review_pr_diff_formats_findings(self):
        finding = Finding(
            severity="error", file="src/app.py", line=3, rule="F401",
            message="unused import", source="ruff"
        )
        with patch('src.tools.GitHubClient') as mock_cls, \
                patch('src.tools.ReviewService') as mock_review:
            mock_cls.return_value.get_pr_diff.return_value = {"diff": "diff"}
            mock_review.return_value.review.return_value = [finding]
            result = review_pr_diff("owner/repo", 8)
            self.assertIn("Code review for PR #8 (1 issues)", result)
            self.assertIn("src/app.py:3", result)
            self.assertIn("[F401/ruff]", result)

    def test_review_pr_diff_handles_error_and_no_findings(self):
        with patch('src.tools.GitHubClient') as mock_cls, \
                patch('src.tools.ReviewService') as mock_review:
            mock_cls.return_value.get_pr_diff.return_value = {"error": "rate limited"}
            self.assertEqual(review_pr_diff("owner/repo", 8), "Error: rate limited")

            mock_cls.return_value.get_pr_diff.return_value = {"diff": "diff"}
            mock_review.return_value.review.side_effect = RuntimeError("ruff crashed")
            self.assertIn("looks good", review_pr_diff("owner/repo", 8))

    def test_review_pr_diff_returns_diff_too_large_finding(self):
        with patch.dict(
            "os.environ",
            {"GITHUB_REVIEW_MAX_DIFF_BYTES": "1024"},
            clear=False,
        ), patch('src.tools.GitHubClient') as mock_cls:
            mock_cls.return_value.get_pr_diff.return_value = {"diff": "x" * 1025}

            result = review_pr_diff("owner/repo", 8)

        self.assertIn("Code review for PR #8 (1 issues)", result)
        self.assertIn("Diff too large (1 KB, limit 1 KB)", result)
        self.assertIn("[diff-too-large/review_engine]", result)
        self.assertIn(":0", result)

    def test_comment_pr_review_posts_top_findings(self):
        findings = [
            Finding("warning", f"src/{i}.py", i, "R", f"message {i}", source="regex")
            for i in range(1, 12)
        ]
        with patch('src.tools.GitHubClient') as mock_cls, \
                patch('src.tools.ReviewService') as mock_review:
            client = mock_cls.return_value
            client.get_pr_diff.return_value = {"diff": "diff"}
            client.create_review_comment.side_effect = [{"id": i} for i in range(10)]
            mock_review.return_value.review.return_value = findings

            result = comment_pr_review("owner/repo", 9)

            self.assertIn("Posted 10 review comments", result)
            self.assertIn("11 total issues", result)
            self.assertEqual(client.create_review_comment.call_count, 10)

    def test_comment_pr_review_counts_failed_posts_and_empty_review(self):
        finding = Finding("warning", "src/app.py", 5, "R", "message", source="regex")
        with patch('src.tools.GitHubClient') as mock_cls, \
                patch('src.tools.ReviewService') as mock_review:
            client = mock_cls.return_value
            client.get_pr_diff.return_value = {"error": "missing diff"}
            self.assertEqual(comment_pr_review("owner/repo", 9), "Error: missing diff")

            client.get_pr_diff.return_value = {"diff": "diff"}
            mock_review.return_value.review.return_value = []
            self.assertIn("looks good", comment_pr_review("owner/repo", 9))

            mock_review.return_value.review.return_value = [finding]
            client.create_review_comment.return_value = {"error": "validation failed"}
            self.assertIn("Posted 0 review comments", comment_pr_review("owner/repo", 9))

    def test_create_issue_success(self):
        """Test create_issue tool formats success response"""
        with patch('src.tools.GitHubClient') as mock_cls, \
                patch('src.tools._get_policy', return_value=self._allow_policy()), \
                patch('src.tools._get_audit', return_value=self._audit()):
            mock_cls.return_value.create_issue.return_value = {
                "number": 42, "title": "Test Issue", "html_url": "https://github.com/owner/repo/issues/42"
            }
            result = create_issue("owner/repo", "Test Issue", "Body text")
            self.assertIn("42", result)
            self.assertIn("Test Issue", result)

    def test_create_issue_error(self):
        """Test create_issue handles errors"""
        with patch('src.tools.GitHubClient') as mock_cls, \
                patch('src.tools._get_policy', return_value=self._allow_policy()), \
                patch('src.tools._get_audit', return_value=self._audit()):
            mock_cls.return_value.create_issue.return_value = {"error": "Not authorized"}
            result = create_issue("owner/repo", "Test", "Body")
            self.assertIn("Error", result)

    def test_create_issue_policy_denied_and_dry_run(self):
        denied_policy = self._allow_policy()
        denied_policy.check_repo.return_value = PolicyDecision(
            "deny", "repo blocked", "repo_allowlist:deny_unlisted"
        )
        audit = self._audit()
        with patch('src.tools._get_policy', return_value=denied_policy), \
                patch('src.tools._get_audit', return_value=audit), \
                patch('src.tools.GitHubClient') as mock_cls:
            result = create_issue("owner/repo", "Title", "Body")
            self.assertIn("Policy Denied: repo blocked", result)
            mock_cls.assert_not_called()
            audit.log.assert_called_once()

        with patch('src.tools._get_policy', return_value=self._allow_policy()), \
                patch('src.tools._get_audit', return_value=self._audit()), \
                patch('src.tools.GitHubClient') as mock_cls:
            result = create_issue("owner/repo", "Title", "x" * 130, dry_run=True)
            self.assertIn("[DRY RUN] Would create issue", result)
            self.assertIn("...", result)
            mock_cls.assert_not_called()

    def test_create_pr_success_and_error(self):
        with patch('src.tools.GitHubClient') as mock_cls, \
                patch('src.tools._get_policy', return_value=self._allow_policy()), \
                patch('src.tools._get_audit', return_value=self._audit()):
            mock_cls.return_value.create_pr.return_value = {
                "number": 5, "title": "Fix", "html_url": "https://example/pr/5"
            }
            result = create_pr("owner/repo", "Fix", "Body", "feature", "develop")
            self.assertIn("PR created: #5: Fix", result)
            mock_cls.return_value.create_pr.assert_called_once_with(
                "owner/repo", "Fix", "Body", "feature", "develop"
            )

            mock_cls.return_value.create_pr.return_value = {"error": "branch missing"}
            self.assertEqual(
                create_pr("owner/repo", "Fix", "Body", "feature", "develop"),
                "Error: branch missing",
            )

    def test_create_pr_policy_denials_and_dry_run(self):
        repo_denied = self._allow_policy()
        repo_denied.check_repo.return_value = PolicyDecision(
            "deny", "repo blocked", "repo_allowlist:deny_unlisted"
        )
        branch_denied = self._allow_policy()
        branch_denied.check_branch_for_pr.return_value = PolicyDecision(
            "deny", "main blocked", "protected_branch:main"
        )

        with patch('src.tools._get_policy', return_value=repo_denied), \
                patch('src.tools._get_audit', return_value=self._audit()), \
                patch('src.tools.GitHubClient') as mock_cls:
            self.assertIn(
                "Policy Denied: repo blocked",
                create_pr("owner/repo", "Fix", "Body", "feature", "main"),
            )
            mock_cls.assert_not_called()

        with patch('src.tools._get_policy', return_value=branch_denied), \
                patch('src.tools._get_audit', return_value=self._audit()), \
                patch('src.tools.GitHubClient') as mock_cls:
            self.assertIn(
                "Policy Denied: main blocked",
                create_pr("owner/repo", "Fix", "Body", "feature", "main"),
            )
            mock_cls.assert_not_called()

        with patch('src.tools._get_policy', return_value=self._allow_policy()), \
                patch('src.tools._get_audit', return_value=self._audit()), \
                patch('src.tools.GitHubClient') as mock_cls:
            result = create_pr(
                "owner/repo", "Fix", "Body", "feature", "develop", dry_run=True
            )
            self.assertIn("[DRY RUN] Would create PR", result)
            self.assertIn("Head:   feature", result)
            mock_cls.assert_not_called()

    def test_review_diff_multiple_issues(self):
        """Test review_diff catches multiple rule violations"""
        diff = """diff --git a/src/app.py b/src/app.py
@@ -1,8 +1,12 @@
 def process():
+    password = "secret123"
     data = get_data()
+    print(data)
+    # TODO: fix this later
     return data
+except:
+    pass
"""
        issues = review_diff(diff)
        self.assertGreaterEqual(len(issues), 3)
        rules = [i['rule'] for i in issues]
        self.assertIn('no-print', rules)
        self.assertIn('no-hardcoded-secrets', rules)
        self.assertIn('no-todo-comments', rules)

    def test_review_diff_clean(self):
        """Test review_diff returns empty for clean code"""
        diff = """diff --git a/src/app.py b/src/app.py
@@ -1,3 +1,4 @@
 def hello():
+    logger.info("Starting")
     return True
"""
        issues = review_diff(diff)
        self.assertEqual(len(issues), 0)

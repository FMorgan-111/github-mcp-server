"""Tests for GitHub MCP tools"""
import unittest
from unittest.mock import patch, Mock
from src.tools import search_code, create_issue
from src.review import review_diff


class TestTools(unittest.TestCase):

    @patch('src.tools.GitHubClient')
    def test_search_code(self, mock_client_class):
        """Test search_code tool with mocked httpx response"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.search_code.return_value = [
            {
                'path': 'src/main.py',
                'repo': 'owner/test-repo',
                'url': 'https://github.com/owner/test-repo/blob/main/src/main.py'
            }
        ]

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
            mock_cls.return_value.search_code.return_value = []
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

    def test_create_issue_success(self):
        """Test create_issue tool formats success response"""
        from unittest.mock import patch, Mock
        with patch('src.tools.GitHubClient') as mock_cls:
            mock_cls.return_value.create_issue.return_value = {
                "number": 42, "title": "Test Issue", "html_url": "https://github.com/owner/repo/issues/42"
            }
            result = create_issue("owner/repo", "Test Issue", "Body text")
            self.assertIn("42", result)
            self.assertIn("Test Issue", result)

    def test_create_issue_error(self):
        """Test create_issue handles errors"""
        from unittest.mock import patch, Mock
        with patch('src.tools.GitHubClient') as mock_cls:
            mock_cls.return_value.create_issue.return_value = {"error": "Not authorized"}
            result = create_issue("owner/repo", "Test", "Body")
            self.assertIn("Error", result)

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
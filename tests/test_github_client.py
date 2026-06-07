"""Tests for github_client.py."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.github_client import GitHubClient


class FakeHttpxClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.get_calls = []
        self.post_calls = []

    def __enter__(self):
        if self.error:
            raise self.error
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, *args, **kwargs):
        self.get_calls.append((args, kwargs))
        return self.response

    def post(self, *args, **kwargs):
        self.post_calls.append((args, kwargs))
        return self.response


def test_client_initializes_headers_and_base_url():
    client = GitHubClient("token", "https://api.example/")
    assert client.base_url == "https://api.example"
    assert client.headers["Authorization"] == "Bearer token"
    assert client.headers["Accept"] == "application/vnd.github+json"


def test_search_code_formats_items_and_query_scope():
    response = Mock()
    response.json.return_value = {
        "items": [
            {
                "path": "src/app.py",
                "repository": {"full_name": "owner/repo"},
                "html_url": "https://example/blob/src/app.py",
            }
        ]
    }
    fake = FakeHttpxClient(response=response)

    with patch("src.github_client.httpx.Client", return_value=fake):
        result = GitHubClient("token", "https://api.example").search_code("def main", "owner/repo")

    assert result == {
        "items": [
            {
                "path": "src/app.py",
                "repo": "owner/repo",
                "url": "https://example/blob/src/app.py",
            }
        ]
    }
    args, kwargs = fake.get_calls[0]
    assert args[0] == "https://api.example/search/code"
    assert kwargs["params"] == {"q": "repo:owner/repo def main"}
    response.raise_for_status.assert_called_once()


def test_list_issues_success_and_error():
    response = Mock()
    response.json.return_value = [{"number": 1}]
    fake = FakeHttpxClient(response=response)

    with patch("src.github_client.httpx.Client", return_value=fake):
        result = GitHubClient("token").list_issues("owner/repo", "closed")

    assert result == [{"number": 1}]
    assert fake.get_calls[0][1]["params"] == {"state": "closed"}

    response.raise_for_status.side_effect = RuntimeError("401 Unauthorized")
    with patch("src.github_client.httpx.Client", return_value=FakeHttpxClient(response=response)):
        error = GitHubClient("token").list_issues("owner/repo")
    assert error["error"].startswith("List issues failed: 401 Unauthorized")


def test_create_issue_posts_payload_and_handles_error():
    response = Mock()
    response.json.return_value = {"number": 2}
    fake = FakeHttpxClient(response=response)

    with patch("src.github_client.httpx.Client", return_value=fake):
        result = GitHubClient("token").create_issue("owner/repo", "Title", "Body")

    assert result == {"number": 2}
    assert fake.post_calls[0][1]["json"] == {"title": "Title", "body": "Body"}

    with patch("src.github_client.httpx.Client", return_value=FakeHttpxClient(error=RuntimeError("down"))):
        error = GitHubClient("token").create_issue("owner/repo", "Title", "Body")
    assert error == {"error": "Create issue failed: down"}


def test_get_pr_diff_uses_diff_accept_header_and_handles_error():
    response = Mock()
    response.text = "diff text"
    fake = FakeHttpxClient(response=response)

    with patch("src.github_client.httpx.Client", return_value=fake):
        result = GitHubClient("token", "https://api.example").get_pr_diff("owner/repo", 3)

    assert result == {"diff": "diff text"}
    args, kwargs = fake.get_calls[0]
    assert args[0] == "https://api.example/repos/owner/repo/pulls/3"
    assert kwargs["headers"]["Accept"] == "application/vnd.github.v3.diff"

    response.raise_for_status.side_effect = RuntimeError("404")
    with patch("src.github_client.httpx.Client", return_value=FakeHttpxClient(response=response)):
        error = GitHubClient("token").get_pr_diff("owner/repo", 3)
    assert error == {"error": "Get PR diff failed: 404"}


def test_create_pr_posts_payload_and_handles_error():
    response = Mock()
    response.json.return_value = {"number": 4}
    fake = FakeHttpxClient(response=response)

    with patch("src.github_client.httpx.Client", return_value=fake):
        result = GitHubClient("token").create_pr(
            "owner/repo", "Title", "Body", "feature", "main"
        )

    assert result == {"number": 4}
    assert fake.post_calls[0][1]["json"] == {
        "title": "Title",
        "body": "Body",
        "head": "feature",
        "base": "main",
    }

    with patch("src.github_client.httpx.Client", return_value=FakeHttpxClient(error=RuntimeError("403"))):
        error = GitHubClient("token").create_pr("owner/repo", "Title", "Body", "h", "b")
    assert error == {"error": "Create PR failed: 403"}


def test_create_review_comment_payload_variants_and_error():
    response = Mock()
    response.json.return_value = {"id": 10}
    fake = FakeHttpxClient(response=response)

    with patch("src.github_client.httpx.Client", return_value=fake):
        result = GitHubClient("token").create_review_comment(
            "owner/repo", 5, "body", commit_id="abc", path="src/app.py", line=7
        )

    assert result == {"id": 10}
    assert fake.post_calls[0][1]["json"] == {
        "body": "body",
        "commit_id": "abc",
        "path": "src/app.py",
        "line": 7,
    }

    response2 = Mock()
    response2.json.return_value = {"id": 11}
    fake2 = FakeHttpxClient(response=response2)
    with patch("src.github_client.httpx.Client", return_value=fake2):
        GitHubClient("token").create_review_comment("owner/repo", 5, "body")
    assert fake2.post_calls[0][1]["json"] == {"body": "body"}

    response2.raise_for_status.side_effect = RuntimeError("validation")
    with patch("src.github_client.httpx.Client", return_value=FakeHttpxClient(response=response2)):
        error = GitHubClient("token").create_review_comment("owner/repo", 5, "body")
    assert error == {"error": "Review comment failed: validation"}

"""GitHub API client wrapper using httpx"""
import httpx
from typing import Optional, Dict, Any, List


class GitHubClient:
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def search_code(self, query: str, repo: Optional[str] = None) -> Dict[str, Any]:
        try:
            q = f"repo:{repo} {query}" if repo else query
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    f"{self.base_url}/search/code",
                    headers=self.headers,
                    params={"q": q}
                )
                response.raise_for_status()
                data = response.json()
                return [
                    {
                        "path": item["path"],
                        "repo": item["repository"]["full_name"],
                        "url": item["html_url"]
                    }
                    for item in data.get("items", [])
                ]
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    def list_issues(self, repo: str, state: str = "open") -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    f"{self.base_url}/repos/{repo}/issues",
                    headers=self.headers,
                    params={"state": state}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": f"List issues failed: {str(e)}"}

    def create_issue(self, repo: str, title: str, body: str) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(
                    f"{self.base_url}/repos/{repo}/issues",
                    headers=self.headers,
                    json={"title": title, "body": body}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": f"Create issue failed: {str(e)}"}

    def get_pr_diff(self, repo: str, pr_number: int) -> Dict[str, Any]:
        try:
            headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    f"{self.base_url}/repos/{repo}/pulls/{pr_number}",
                    headers=headers
                )
                response.raise_for_status()
                return {"diff": response.text}
        except Exception as e:
            return {"error": f"Get PR diff failed: {str(e)}"}

    def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(
                    f"{self.base_url}/repos/{repo}/pulls",
                    headers=self.headers,
                    json={"title": title, "body": body, "head": head, "base": base}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": f"Create PR failed: {str(e)}"}
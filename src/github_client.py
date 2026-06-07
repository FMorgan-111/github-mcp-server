"""GitHub API client wrapper using httpx"""
import httpx
from typing import Any


class GitHubClient:
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def search_code(self, query: str, repo: str | None = None) -> dict[str, Any]:
        try:
            q = f"repo:{repo} {query}" if repo else query
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    f"{self.base_url}/search/code",
                    headers=self.headers,
                    params={"q": q}
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                return {
                    "items": [
                        {
                            "path": item["path"],
                            "repo": item["repository"]["full_name"],
                            "url": item["html_url"]
                        }
                        for item in data.get("items", [])
                    ]
                }
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}

    def list_issues(self, repo: str, state: str = "open") -> dict[str, Any]:
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    f"{self.base_url}/repos/{repo}/issues",
                    headers=self.headers,
                    params={"state": state}
                )
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
        except Exception as e:
            return {"error": f"List issues failed: {str(e)}"}

    def create_issue(self, repo: str, title: str, body: str) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(
                    f"{self.base_url}/repos/{repo}/issues",
                    headers=self.headers,
                    json={"title": title, "body": body}
                )
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
        except Exception as e:
            return {"error": f"Create issue failed: {str(e)}"}

    def get_pr_diff(self, repo: str, pr_number: int) -> dict[str, Any]:
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

    def create_pr(self, repo: str, title: str, body: str, head: str, base: str) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(
                    f"{self.base_url}/repos/{repo}/pulls",
                    headers=self.headers,
                    json={"title": title, "body": body, "head": head, "base": base}
                )
                response.raise_for_status()
                result: dict[str, Any] = response.json()
                return result
        except Exception as e:
            return {"error": f"Create PR failed: {str(e)}"}

    def create_review_comment(
        self, repo: str, pr_number: int, body: str,
        commit_id: str = "", path: str = "", line: int = 0
    ) -> dict[str, Any]:
        """Post a review comment on a PR line."""
        try:
            payload: dict[str, Any] = {"body": body}
            if commit_id and path and line > 0:
                payload["commit_id"] = commit_id
                payload["path"] = path
                payload["line"] = line
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    f"{self.base_url}/repos/{repo}/pulls/{pr_number}/reviews",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
        except Exception as e:
            return {"error": f"Review comment failed: {str(e)}"}

    # ── File operations ─────────────────────────────────

    def get_file_contents(
        self, repo: str, path: str, ref: str = ""
    ) -> dict[str, Any]:
        """Read a file from a repository.

        Returns decoded UTF-8 text content, sha, size, and path.
        """
        try:
            url = f"{self.base_url}/repos/{repo}/contents/{path}"
            params: dict[str, str] = {}
            if ref:
                params["ref"] = ref
            with httpx.Client(timeout=20) as client:
                resp = client.get(
                    url, headers=self.headers, params=params,
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()

                # GitHub API may return a list for directories
                if isinstance(data, list):
                    return {"error": f"'{path}' is a directory, not a file"}

                content = data.get("content", "")
                encoding = data.get("encoding", "base64")
                if encoding == "base64" and content:
                    import base64
                    decoded = base64.b64decode(content).decode("utf-8")
                else:
                    decoded = content

                return {
                    "path": data.get("path", path),
                    "sha": data.get("sha", ""),
                    "size": data.get("size", 0),
                    "content": decoded,
                }
        except Exception as e:
            return {"error": f"Get file contents failed: {str(e)}"}

    def create_or_update_file(
        self, repo: str, path: str, message: str, content: str,
        sha: str = "", branch: str = "",
    ) -> dict[str, Any]:
        """Create or update a single file in a repository.

        If branch is specified and doesn't exist, it will be auto-created
        from the repository's default branch.
        """
        try:
            import base64
            payload: dict[str, Any] = {
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            }
            if sha:
                payload["sha"] = sha
            if branch:
                payload["branch"] = branch
            with httpx.Client(timeout=20) as client:
                resp = client.put(
                    f"{self.base_url}/repos/{repo}/contents/{path}",
                    headers=self.headers,
                    json=payload,
                )
                # If branch doesn't exist, auto-create it and retry
                if resp.status_code == 404 and branch:
                    self._ensure_branch(client, repo, branch)
                    resp = client.put(
                        f"{self.base_url}/repos/{repo}/contents/{path}",
                        headers=self.headers,
                        json=payload,
                    )
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return {
                    "commit_sha": result.get("commit", {}).get("sha", ""),
                    "content_sha": result.get("content", {}).get("sha", ""),
                    "path": result.get("content", {}).get("path", path),
                    "html_url": result.get("content", {}).get("html_url", ""),
                }
        except Exception as e:
            return {"error": f"Create/update file failed: {str(e)}"}

    def _ensure_branch(
        self, client: "httpx.Client", repo: str, branch: str,
    ) -> None:
        """Create a branch from main if it doesn't exist."""
        # Get main SHA
        ref_resp = client.get(
            f"{self.base_url}/repos/{repo}/git/ref/heads/main",
            headers=self.headers,
        )
        ref_resp.raise_for_status()
        main_sha = ref_resp.json()["object"]["sha"]

        # Create branch
        client.post(
            f"{self.base_url}/repos/{repo}/git/refs",
            headers=self.headers,
            json={"ref": f"refs/heads/{branch}", "sha": main_sha},
        )

    def push_files(
        self, repo: str, branch: str, message: str,
        files: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Push multiple files as a single commit via Git Data API.

        Args:
            repo: 'owner/repo'.
            branch: Branch name to commit to.
            message: Commit message.
            files: [{"path": "src/a.py", "content": "..."}, ...]
        """
        try:
            with httpx.Client(timeout=30) as client:
                # 1. Get the current branch ref
                ref_resp = client.get(
                    f"{self.base_url}/repos/{repo}/git/ref/heads/{branch}",
                    headers=self.headers,
                )
                ref_resp.raise_for_status()
                ref_data: dict[str, Any] = ref_resp.json()
                base_sha = ref_data["object"]["sha"]

                # 2. Get the base tree sha from the parent commit
                commit_resp = client.get(
                    f"{self.base_url}/repos/{repo}/git/commits/{base_sha}",
                    headers=self.headers,
                )
                commit_resp.raise_for_status()
                commit_data: dict[str, Any] = commit_resp.json()
                base_tree_sha = commit_data["tree"]["sha"]

                # 3. Create blobs for each file, then build tree entries
                tree_entries: list[dict[str, Any]] = []
                for f in files:
                    blob_resp = client.post(
                        f"{self.base_url}/repos/{repo}/git/blobs",
                        headers=self.headers,
                        json={
                            "content": f["content"],
                            "encoding": "utf-8",
                        },
                    )
                    blob_resp.raise_for_status()
                    blob_sha = blob_resp.json()["sha"]
                    tree_entries.append({
                        "path": f["path"],
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_sha,
                    })

                # 4. Create a new tree
                tree_resp = client.post(
                    f"{self.base_url}/repos/{repo}/git/trees",
                    headers=self.headers,
                    json={
                        "base_tree": base_tree_sha,
                        "tree": tree_entries,
                    },
                )
                tree_resp.raise_for_status()
                new_tree_sha = tree_resp.json()["sha"]

                # 5. Create a commit pointing to the new tree
                new_commit_resp = client.post(
                    f"{self.base_url}/repos/{repo}/git/commits",
                    headers=self.headers,
                    json={
                        "message": message,
                        "tree": new_tree_sha,
                        "parents": [base_sha],
                    },
                )
                new_commit_resp.raise_for_status()
                new_commit_sha = new_commit_resp.json()["sha"]

                # 6. Update the branch ref
                update_resp = client.patch(
                    f"{self.base_url}/repos/{repo}/git/refs/heads/{branch}",
                    headers=self.headers,
                    json={
                        "sha": new_commit_sha,
                        "force": False,
                    },
                )
                update_resp.raise_for_status()

                return {
                    "commit_sha": new_commit_sha,
                    "branch": branch,
                    "files_changed": len(files),
                    "files": [f["path"] for f in files],
                }
        except Exception as e:
            return {"error": f"Push files failed: {str(e)}"}

    # ── Issue & PR lifecycle ────────────────────────────

    def add_issue_comment(
        self, repo: str, issue_number: int, body: str,
    ) -> dict[str, Any]:
        """Comment on an issue (works for PRs too — they share the same API)."""
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    f"{self.base_url}/repos/{repo}/issues/{issue_number}/comments",
                    headers=self.headers,
                    json={"body": body},
                )
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
        except Exception as e:
            return {"error": f"Add issue comment failed: {str(e)}"}

    def merge_pull_request(
        self, repo: str, pr_number: int,
        commit_title: str = "", merge_method: str = "merge",
    ) -> dict[str, Any]:
        """Merge a pull request."""
        try:
            payload: dict[str, Any] = {"merge_method": merge_method}
            if commit_title:
                payload["commit_title"] = commit_title
            with httpx.Client(timeout=20) as client:
                resp = client.put(
                    f"{self.base_url}/repos/{repo}/pulls/{pr_number}/merge",
                    headers=self.headers,
                    json=payload,
                )
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
        except Exception as e:
            return {"error": f"Merge PR failed: {str(e)}"}

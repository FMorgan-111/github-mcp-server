"""MCP tools for GitHub operations — with policy guard & audit logging."""
from typing import Any, cast

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import (
    get_github_token, get_github_api_base,
    get_policy_path, get_policy_required,
    get_audit_sink, get_dry_run_enabled,
    get_policy_no_watch,
)
from .github_client import GitHubClient
from .review_engine import ReviewService
from .policy import PolicyConfig, resolve_dry_run
from .audit import AuditLogger


mcp = FastMCP("GitHub MCP Agent Server")

# ── Custom HTTP routes (available in HTTP transport mode) ──


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for HTTP transport mode."""
    return JSONResponse({"status": "ok"})

# Lazy-init singletons — created on first access
_policy: PolicyConfig | None = None
_audit: AuditLogger | None = None


def _get_policy() -> PolicyConfig:
    global _policy
    if _policy is None:
        _policy = PolicyConfig().load(
            path=get_policy_path(),
            required=get_policy_required(),
        )
        if not get_policy_no_watch():
            _policy.start_watching(get_policy_path())
    return _policy


def _stop_policy_watcher() -> None:
    """Shutdown hook: stop the policy file watcher if active."""
    global _policy
    if _policy is not None:
        _policy.stop_watching()


def _get_audit() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger(sink=get_audit_sink())
    return _audit


# ── Read tools (no guard needed) ───────────────────────
@mcp.tool()
def search_code(query: str, repo: str | None = None) -> str:
    """Search for code in GitHub repositories."""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.search_code(query, repo)

    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"

    items = result.get("items", [])
    if not items:
        return "No results found"

    output = []
    for item in items[:10]:
        output.append(f"• {item['path']} in {item['repo']}\n  {item['url']}")

    return f"Found {len(items)} results:\n" + "\n\n".join(output)


@mcp.tool()
def list_issues(repo: str, state: str = "open") -> str:
    """List issues in a GitHub repository."""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.list_issues(repo, state)

    if "error" in result:
        return f"Error: {result['error']}"

    # GitHub API returns a list; cast for mypy since return type is dict
    issues = cast(list[dict[str, Any]], result)
    if not issues:
        return f"No {state} issues found in {repo}"

    output = []
    for issue in issues[:10]:
        output.append(f"#{issue['number']}: {issue['title']}\n  {issue['html_url']}")

    return f"Issues in {repo} ({state}):\n" + "\n\n".join(output)


@mcp.tool()
def get_pr_diff(repo: str, pr_number: int) -> str:
    """Get the diff for a pull request."""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.get_pr_diff(repo, pr_number)

    if "error" in result:
        return f"Error: {result['error']}"

    return f"PR #{pr_number} diff:\n\n{result['diff']}"


@mcp.tool()
def review_pr_diff(repo: str, pr_number: int) -> str:
    """Review a PR diff using ruff + legacy regex rules. Returns structured findings."""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.get_pr_diff(repo, pr_number)

    if "error" in result:
        return f"Error: {result['error']}"

    # Use new review engine (ruff + regex fallback)
    try:
        review = ReviewService()
        findings = review.review(result["diff"])
    except Exception:
        findings = []

    if not findings:
        return f"PR #{pr_number} looks good - no issues found!"

    output = [f"Code review for PR #{pr_number} ({len(findings)} issues):"]
    for f in findings:
        icon = "❌" if f.severity == "error" else "⚠️"
        output.append(
            f"{icon} {f.file}:{f.line} — {f.message} "
            f"[{f.rule}/{f.source}]"
        )

    return "\n".join(output)


@mcp.tool()
def comment_pr_review(repo: str, pr_number: int) -> str:
    """Fetch PR diff, run code review, and post findings as review comments."""
    client = GitHubClient(get_github_token(), get_github_api_base())
    diff_result = client.get_pr_diff(repo, pr_number)

    if "error" in diff_result:
        return f"Error: {diff_result['error']}"

    try:
        review = ReviewService()
        findings = review.review(diff_result["diff"])
    except Exception:
        findings = []

    if not findings:
        return f"PR #{pr_number} looks good - no issues found!"

    # Limit to top 10 findings to avoid spam
    posted = 0
    for f in findings[:10]:
        body = f"{f.message}\n\nRule: `{f.rule}` | Source: {f.source}"
        r = client.create_review_comment(repo, pr_number, body, path=f.file, line=f.line)
        if "error" not in r:
            posted += 1

    return (
        f"Posted {posted} review comments on PR #{pr_number} "
        f"({len(findings)} total issues found, top 10 posted)"
    )


@mcp.tool()
def get_file_contents(repo: str, path: str, ref: str = "") -> str:
    """Read a file from a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format.
        path: File path (e.g. 'src/main.py').
        ref: Branch, tag, or commit SHA (default: default branch).
    """
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.get_file_contents(repo, path, ref)

    if "error" in result:
        return f"Error: {result['error']}"

    return (
        f"File: {result['path']} ({result['size']} bytes, sha: {result['sha'][:7]})\n"
        f"---\n{result['content']}"
    )


# ── Write tools (guarded) ──────────────────────────────
@mcp.tool()
def create_issue(repo: str, title: str, body: str, dry_run: bool = False) -> str:
    """Create a new issue in a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format.
        title: Issue title.
        body: Issue body text.
        dry_run: If True, preview the operation without executing.
    """
    dry = resolve_dry_run(dry_run, get_dry_run_enabled())
    policy = _get_policy()
    audit = _get_audit()

    # Guard: repo allowlist check
    repo_decision = policy.check_repo(repo)
    if repo_decision.action == "deny":
        audit.log(
            tool="create_issue", action="issue.create", repo=repo,
            dry_run=dry, policy_decision="deny",
            policy_rule=repo_decision.matched_rule,
            request_body={"title": title, "body": body},
            error=repo_decision.reason,
        )
        return f"❌ Policy Denied: {repo_decision.reason}"

    if dry:
        audit.log(
            tool="create_issue", action="issue.create", repo=repo,
            dry_run=True, policy_decision="allow",
            policy_rule=repo_decision.matched_rule,
            request_body={"title": title, "body": body},
        )
        return (
            f"[DRY RUN] Would create issue in {repo}:\n"
            f"  Title: {title}\n"
            f"  Body:  {body[:120]}{'...' if len(body) > 120 else ''}\n"
            f"  Policy: {repo_decision.reason}"
        )

    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.create_issue(repo, title, body)

    if "error" in result:
        audit.log(
            tool="create_issue", action="issue.create", repo=repo,
            policy_decision="allow", policy_rule=repo_decision.matched_rule,
            request_body={"title": title, "body": body},
            error=result["error"],
        )
        return f"Error: {result['error']}"

    audit.log(
        tool="create_issue", action="issue.create", repo=repo,
        policy_decision="allow", policy_rule=repo_decision.matched_rule,
        request_body={"title": title, "body": body},
        response=result,
    )
    return f"Issue created: #{result['number']}: {result['title']}\n{result['html_url']}"


@mcp.tool()
def create_pr(repo: str, title: str, body: str, head: str, base: str,
              dry_run: bool = False) -> str:
    """Create a new pull request.

    Args:
        repo: Repository in 'owner/repo' format.
        title: PR title.
        body: PR description.
        head: Source branch name.
        base: Target branch name (e.g. 'main').
        dry_run: If True, preview the operation without executing.
    """
    dry = resolve_dry_run(dry_run, get_dry_run_enabled())
    policy = _get_policy()
    audit = _get_audit()

    # Guard: repo allowlist
    repo_decision = policy.check_repo(repo)
    if repo_decision.action == "deny":
        audit.log(
            tool="create_pr", action="pull_request.create", repo=repo,
            dry_run=dry, policy_decision="deny",
            policy_rule=repo_decision.matched_rule,
            request_body={"title": title, "head": head, "base": base},
            error=repo_decision.reason,
        )
        return f"❌ Policy Denied: {repo_decision.reason}"

    # Guard: branch protection
    branch_decision = policy.check_branch_for_pr(base)
    if branch_decision.action == "deny":
        audit.log(
            tool="create_pr", action="pull_request.create", repo=repo,
            dry_run=dry, policy_decision="deny",
            policy_rule=branch_decision.matched_rule,
            request_body={"title": title, "head": head, "base": base},
            error=branch_decision.reason,
        )
        return f"❌ Policy Denied: {branch_decision.reason}"

    if dry:
        audit.log(
            tool="create_pr", action="pull_request.create", repo=repo,
            dry_run=True, policy_decision="allow",
            policy_rule=f"{repo_decision.matched_rule}, {branch_decision.matched_rule}",
            request_body={"title": title, "head": head, "base": base},
        )
        return (
            f"[DRY RUN] Would create PR in {repo}:\n"
            f"  Title:  {title}\n"
            f"  Head:   {head} → Base: {base}\n"
            f"  Policy: {repo_decision.reason} · {branch_decision.reason}"
        )

    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.create_pr(repo, title, body, head, base)

    if "error" in result:
        audit.log(
            tool="create_pr", action="pull_request.create", repo=repo,
            policy_decision="allow",
            policy_rule=f"{repo_decision.matched_rule}, {branch_decision.matched_rule}",
            request_body={"title": title, "head": head, "base": base},
            error=result["error"],
        )
        return f"Error: {result['error']}"

    audit.log(
        tool="create_pr", action="pull_request.create", repo=repo,
        policy_decision="allow",
        policy_rule=f"{repo_decision.matched_rule}, {branch_decision.matched_rule}",
        request_body={"title": title, "head": head, "base": base},
        response=result,
    )
    return f"PR created: #{result['number']}: {result['title']}\n{result['html_url']}"


@mcp.tool()
def create_or_update_file(
    repo: str, path: str, content: str,
    message: str = "", branch: str = "",
    sha: str = "", dry_run: bool = False,
) -> str:
    """Create or update a single file in a GitHub repository.

    Args:
        repo: Repository in 'owner/repo' format.
        path: File path to create/update.
        content: New file content.
        message: Commit message (default: auto-generated).
        branch: Branch to commit to (default: repo default branch).
        sha: Blob SHA of file being replaced (required for updates).
        dry_run: If True, preview the operation without executing.
    """
    dry = resolve_dry_run(dry_run, get_dry_run_enabled())
    policy = _get_policy()
    audit = _get_audit()

    repo_decision = policy.check_repo(repo)
    if repo_decision.action == "deny":
        audit.log(
            tool="create_or_update_file", action="file.upsert", repo=repo,
            dry_run=dry, policy_decision="deny",
            policy_rule=repo_decision.matched_rule,
            request_body={"path": path, "branch": branch},
            error=repo_decision.reason,
        )
        return f"❌ Policy Denied: {repo_decision.reason}"

    commit_msg = message or f"Update {path}"

    if dry:
        audit.log(
            tool="create_or_update_file", action="file.upsert", repo=repo,
            dry_run=True, policy_decision="allow",
            policy_rule=repo_decision.matched_rule,
            request_body={"path": path, "message": commit_msg, "branch": branch},
        )
        return (
            f"[DRY RUN] Would write to {repo}/{path}:\\n"
            f"  Branch:  {branch or '(default)'}\\n"
            f"  Message: {commit_msg}\\n"
            f"  Content: {content[:120]}{'...' if len(content) > 120 else ''}\\n"
            f"  Policy:  {repo_decision.reason}"
        )

    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.create_or_update_file(repo, path, commit_msg, content, sha, branch)

    if "error" in result:
        audit.log(
            tool="create_or_update_file", action="file.upsert", repo=repo,
            policy_decision="allow", policy_rule=repo_decision.matched_rule,
            request_body={"path": path, "message": commit_msg, "branch": branch},
            error=result["error"],
        )
        return f"Error: {result['error']}"

    audit.log(
        tool="create_or_update_file", action="file.upsert", repo=repo,
        policy_decision="allow", policy_rule=repo_decision.matched_rule,
        request_body={"path": path, "message": commit_msg, "branch": branch},
        response=result,
    )
    return (
        f"File written: {result['path']}\\n"
        f"  Commit:  {result['commit_sha'][:7]}\\n"
        f"  URL:     {result['html_url']}"
    )


@mcp.tool()
def push_files(
    repo: str, branch: str, message: str,
    files_json: str, dry_run: bool = False,
) -> str:
    """Push multiple files as a single commit.

    Args:
        repo: Repository in 'owner/repo' format.
        branch: Branch name to commit to.
        message: Commit message.
        files_json: JSON string of [{\"path\": \"...\", \"content\": \"...\"}, ...].
        dry_run: If True, preview without executing.
    """
    import json as _json

    dry = resolve_dry_run(dry_run, get_dry_run_enabled())
    policy = _get_policy()
    audit = _get_audit()

    repo_decision = policy.check_repo(repo)
    if repo_decision.action == "deny":
        audit.log(
            tool="push_files", action="files.push", repo=repo,
            dry_run=dry, policy_decision="deny",
            policy_rule=repo_decision.matched_rule,
            request_body={"branch": branch, "message": message},
            error=repo_decision.reason,
        )
        return f"❌ Policy Denied: {repo_decision.reason}"

    try:
        files = _json.loads(files_json)
    except _json.JSONDecodeError as e:
        return f"Error: Invalid files_json: {e}"

    if not isinstance(files, list) or len(files) == 0:
        return "Error: files_json must be a non-empty list of {path, content} objects"

    if dry:
        audit.log(
            tool="push_files", action="files.push", repo=repo,
            dry_run=True, policy_decision="allow",
            policy_rule=repo_decision.matched_rule,
            request_body={"branch": branch, "message": message, "count": len(files)},
        )
        paths = [f.get("path", "?") for f in files]
        return (
            f"[DRY RUN] Would push {len(files)} file(s) to {repo} on {branch}:\\n"
            + "\\n".join(f"  • {p}" for p in paths)
            + f"\\n  Message: {message}\\n"
            f"  Policy:  {repo_decision.reason}"
        )

    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.push_files(repo, branch, message, files)

    if "error" in result:
        audit.log(
            tool="push_files", action="files.push", repo=repo,
            policy_decision="allow", policy_rule=repo_decision.matched_rule,
            request_body={"branch": branch, "message": message, "count": len(files)},
            error=result["error"],
        )
        return f"Error: {result['error']}"

    audit.log(
        tool="push_files", action="files.push", repo=repo,
        policy_decision="allow", policy_rule=repo_decision.matched_rule,
        request_body={"branch": branch, "message": message, "count": len(files)},
        response=result,
    )
    file_list = "\\n".join(f"  • {p}" for p in result["files"])
    return (
        f"Pushed {result['files_changed']} file(s) to {repo} [{branch}]:\\n"
        f"{file_list}\\n"
        f"Commit: {result['commit_sha'][:7]}\\n"
        f"Message: {message}"
    )


@mcp.tool()
def add_issue_comment(repo: str, issue_number: int, body: str,
                     dry_run: bool = False) -> str:
    """Add a comment to a GitHub issue or pull request.

    Args:
        repo: Repository in 'owner/repo' format.
        issue_number: Issue or PR number.
        body: Comment text (markdown supported).
        dry_run: If True, preview without executing.
    """
    dry = resolve_dry_run(dry_run, get_dry_run_enabled())
    policy = _get_policy()
    audit = _get_audit()

    repo_decision = policy.check_repo(repo)
    if repo_decision.action == "deny":
        audit.log(
            tool="add_issue_comment", action="issue.comment", repo=repo,
            dry_run=dry, policy_decision="deny",
            policy_rule=repo_decision.matched_rule,
            request_body={"issue_number": issue_number},
            error=repo_decision.reason,
        )
        return f"❌ Policy Denied: {repo_decision.reason}"

    if dry:
        audit.log(
            tool="add_issue_comment", action="issue.comment", repo=repo,
            dry_run=True, policy_decision="allow",
            policy_rule=repo_decision.matched_rule,
            request_body={"issue_number": issue_number},
        )
        preview = body[:200] + ("..." if len(body) > 200 else "")
        return (
            f"[DRY RUN] Would comment on #{issue_number} in {repo}:\\n"
            f"  {preview}\\n"
            f"  Policy: {repo_decision.reason}"
        )

    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.add_issue_comment(repo, issue_number, body)

    if "error" in result:
        audit.log(
            tool="add_issue_comment", action="issue.comment", repo=repo,
            policy_decision="allow", policy_rule=repo_decision.matched_rule,
            request_body={"issue_number": issue_number},
            error=result["error"],
        )
        return f"Error: {result['error']}"

    audit.log(
        tool="add_issue_comment", action="issue.comment", repo=repo,
        policy_decision="allow", policy_rule=repo_decision.matched_rule,
        request_body={"issue_number": issue_number},
        response=result,
    )
    return f"Comment added: {result.get('html_url', '')}"


@mcp.tool()
def merge_pull_request(
    repo: str, pr_number: int,
    commit_title: str = "", merge_method: str = "merge",
    dry_run: bool = False,
) -> str:
    """Merge a pull request.

    Args:
        repo: Repository in 'owner/repo' format.
        pr_number: Pull request number.
        commit_title: Custom merge commit title.
        merge_method: 'merge', 'squash', or 'rebase' (default: 'merge').
        dry_run: If True, preview without executing.
    """
    dry = resolve_dry_run(dry_run, get_dry_run_enabled())
    policy = _get_policy()
    audit = _get_audit()

    repo_decision = policy.check_repo(repo)
    if repo_decision.action == "deny":
        audit.log(
            tool="merge_pull_request", action="pull_request.merge", repo=repo,
            dry_run=dry, policy_decision="deny",
            policy_rule=repo_decision.matched_rule,
            request_body={"pr_number": pr_number, "merge_method": merge_method},
            error=repo_decision.reason,
        )
        return f"❌ Policy Denied: {repo_decision.reason}"

    if dry:
        audit.log(
            tool="merge_pull_request", action="pull_request.merge", repo=repo,
            dry_run=True, policy_decision="allow",
            policy_rule=repo_decision.matched_rule,
            request_body={"pr_number": pr_number, "merge_method": merge_method},
        )
        return (
            f"[DRY RUN] Would merge PR #{pr_number} in {repo}\\n"
            f"  Method: {merge_method}\\n"
            f"  Policy: {repo_decision.reason}"
        )

    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.merge_pull_request(repo, pr_number, commit_title, merge_method)

    if "error" in result:
        audit.log(
            tool="merge_pull_request", action="pull_request.merge", repo=repo,
            policy_decision="allow", policy_rule=repo_decision.matched_rule,
            request_body={"pr_number": pr_number, "merge_method": merge_method},
            error=result["error"],
        )
        return f"Error: {result['error']}"

    audit.log(
        tool="merge_pull_request", action="pull_request.merge", repo=repo,
        policy_decision="allow", policy_rule=repo_decision.matched_rule,
        request_body={"pr_number": pr_number, "merge_method": merge_method},
        response=result,
    )
    merged = result.get("merged", False)
    sha = result.get("sha", "")[:7]
    msg = result.get("message", "")
    return (
        f"PR #{pr_number} {'merged' if merged else 'not merged'}: {msg}\\n"
        f"  SHA: {sha}"
    )

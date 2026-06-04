"""MCP tools for GitHub operations"""
from fastmcp import FastMCP
from .github_client import GitHubClient
from .review import review_diff
from .config import get_github_token, get_github_api_base


mcp = FastMCP("GitHub MCP Server")


@mcp.tool()
def search_code(query: str, repo: str = None) -> str:
    """Search for code in GitHub repositories"""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.search_code(query, repo)

    if "error" in result:
        return f"Error: {result['error']}"

    if not result:
        return "No results found"

    output = []
    for item in result[:10]:  # Limit to first 10 results
        output.append(f"• {item['path']} in {item['repo']}\n  {item['url']}")

    return f"Found {len(result)} results:\n" + "\n\n".join(output)


@mcp.tool()
def list_issues(repo: str, state: str = "open") -> str:
    """List issues in a GitHub repository"""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.list_issues(repo, state)

    if "error" in result:
        return f"Error: {result['error']}"

    if not result:
        return f"No {state} issues found in {repo}"

    output = []
    for issue in result[:10]:  # Limit to first 10
        output.append(f"#{issue['number']}: {issue['title']}\n  {issue['html_url']}")

    return f"Issues in {repo} ({state}):\n" + "\n\n".join(output)


@mcp.tool()
def create_issue(repo: str, title: str, body: str) -> str:
    """Create a new issue in a GitHub repository"""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.create_issue(repo, title, body)

    if "error" in result:
        return f"Error: {result['error']}"

    return f"Issue created: #{result['number']}: {result['title']}\n{result['html_url']}"


@mcp.tool()
def get_pr_diff(repo: str, pr_number: int) -> str:
    """Get the diff for a pull request"""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.get_pr_diff(repo, pr_number)

    if "error" in result:
        return f"Error: {result['error']}"

    return f"PR #{pr_number} diff:\n\n{result['diff']}"


@mcp.tool()
def create_pr(repo: str, title: str, body: str, head: str, base: str) -> str:
    """Create a new pull request"""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.create_pr(repo, title, body, head, base)

    if "error" in result:
        return f"Error: {result['error']}"

    return f"PR created: #{result['number']}: {result['title']}\n{result['html_url']}"


@mcp.tool()
def review_pr_diff(repo: str, pr_number: int) -> str:
    """Review a pull request diff and return code review feedback"""
    client = GitHubClient(get_github_token(), get_github_api_base())
    result = client.get_pr_diff(repo, pr_number)

    if "error" in result:
        return f"Error: {result['error']}"

    issues = review_diff(result['diff'])

    if not issues:
        return f"PR #{pr_number} looks good - no issues found!"

    output = [f"Code review for PR #{pr_number}:"]
    for issue in issues:
        severity_icon = "⚠️" if issue['severity'] == 'warning' else "❌"
        output.append(f"{severity_icon} Line {issue['line']}: {issue['message']} ({issue['rule']})")

    return "\n".join(output)
# GitHub MCP Agent Server

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![CI](https://github.com/FMorgan-111/github-mcp-server/actions/workflows/ci.yml/badge.svg)]()

> **MCP (Model Context Protocol) server** that exposes GitHub operations as tools for AI agents — Claude Code, Codex, and any MCP-compatible client.

## Features

| Tool | Description |
|------|-------------|
| `search_code` | Search GitHub repositories for code |
| `list_issues` | List open/closed issues in a repository |
| `create_issue` | Create a new GitHub issue |
| `get_pr_diff` | Fetch the raw diff of any pull request |
| `create_pr` | Create a pull request between branches |
| `review_pr_diff` | Automated code review via local rules (no API call) |

## Quick Start

### 1. Prerequisites

- Python 3.10+
- A [GitHub personal access token](https://github.com/settings/tokens) with `repo` scope

### 2. Install

```bash
pip install fastmcp httpx python-dotenv
```

### 3. Configure

```bash
git clone https://github.com/FMorgan-111/github-mcp-server.git
cd github-mcp-server
echo "GITHUB_TOKEN=ghp_your_token_here" > .env
```

### 4. Run

```bash
python -m src.main
```

### 5. Connect to your AI agent

**Claude Code:**
```bash
claude mcp add github-agent -- python3 /path/to/github-mcp-server/src/main.py
```

**Or via Claude Desktop / Cursor config:**
```json
{
  "mcpServers": {
    "github-agent": {
      "command": "python3",
      "args": ["/path/to/github-mcp-server/src/main.py"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

Then ask your AI:
> *"List open issues in FMorgan-111/github-mcp-server"*
> *"Search for 'FastMCP' in my repo"*
> *"Review PR #1 in this repo"*

## Tool Reference

### `search_code(query, repo)`

Search code within a GitHub repository.

**Parameters:**
- `query` (str, required) — Search query
- `repo` (str, optional) — Repository in `owner/repo` format

**Returns:** Formatted list of matching files with paths and URLs.

### `list_issues(repo, state)`

List issues in a repository.

**Parameters:**
- `repo` (str, required) — Repository in `owner/repo` format
- `state` (str, optional) — `"open"` (default) or `"closed"`

### `create_issue(repo, title, body)`

Create a new issue.

**Parameters:**
- `repo` (str, required) — Repository in `owner/repo` format
- `title` (str, required) — Issue title
- `body` (str, required) — Issue body text

### `get_pr_diff(repo, pr_number)`

Fetch the raw diff of a pull request.

**Parameters:**
- `repo` (str, required) — Repository in `owner/repo` format
- `pr_number` (int, required) — Pull request number

### `create_pr(repo, title, body, head, base)`

Create a pull request.

**Parameters:**
- `repo` (str, required) — Repository in `owner/repo` format
- `title` (str, required) — PR title
- `body` (str, required) — PR description
- `head` (str, required) — Source branch name
- `base` (str, required) — Target branch name (e.g. `"main"`)

### `review_pr_diff(repo, pr_number)`

Fetch a PR diff and run local code review rules. No API call — all analysis is local.

**Rules checked:**
- ⚠️ `print()` statements in non-test files
- ⚠️ `TODO` / `FIXME` / `HACK` comments
- ❌ Hardcoded secrets (passwords, API keys, tokens)
- ❌ Bare `except:` clauses (should specify exception type)
- ⚠️ Functions over 80 lines

## Architecture

```
┌─────────────────┐     MCP stdio transport     ┌──────────────────────┐
│  Claude Code    │ ◄─────────────────────────► │  GitHub MCP Server   │
│  Codex          │     JSON-RPC 2.0 messages    │                      │
│  Any MCP client │                              │  ┌────────────────┐ │
└─────────────────┘                              │  │  github_client │ │
                                                 │  │  (httpx)       │ │
                                                 │  │  → GitHub API  │ │
                                                 │  └────────────────┘ │
                                                 │  ┌────────────────┐ │
                                                 │  │  review.py     │ │
                                                 │  │  local rules   │ │
                                                 │  └────────────────┘ │
                                                 │  ┌────────────────┐ │
                                                 │  │  config.py     │ │
                                                 │  │  .env / env    │ │
                                                 │  └────────────────┘ │
                                                 └──────────────────────┘
```

## Development

```bash
# Clone and install
git clone https://github.com/FMorgan-111/github-mcp-server.git
cd github-mcp-server
pip install -e . --break-system-packages

# Run tests
python -m pytest tests/ -v

# Start MCP server (stdio mode)
python -m src.main

# Test with MCP Inspector
# https://github.com/modelcontextprotocol/inspector
```

## Deployment

### Docker

```bash
docker build -t github-mcp-server .
docker run -e GITHUB_TOKEN=ghp_your_token_here -i github-mcp-server
```

### Smithery (MCP Registry)

Deploy to [Smithery](https://smithery.ai) for one-click install into any MCP client.

## License

MIT

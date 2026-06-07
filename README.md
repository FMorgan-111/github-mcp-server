# GitHub MCP Agent Server

[![CI](https://github.com/FMorgan-111/github-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/FMorgan-111/github-mcp-server/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/release/python-3100/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> MCP server giving AI agents controlled GitHub access with policy guard and audit trail.

---

## Architecture

```
   ┌───────────────┐        MCP stdio         ┌───────────────────┐
   │   AI Agent    │ ◄──────────────────────► │ GitHub MCP Server │
   │ (Claude, Codex│      JSON-RPC 2.0        │                   │
   │   or any MCP  │                         ┌─┴───────────────┐   │
   │    client)    │                         │ Policy Guard    │   │
   └───────────────┘                         ├─────────────────┤   │
                                             │ Audit Log       │   │
                                             └─────────────────┘   │
           ┌──────────────────────────────────────────────┐      │
           │                 github_client.py               │      │
           │                    (httpx)                     │      │
           │                   GitHub API                   │      │
           └──────────────────────────────────────────────┘      │
           ┌──────────────────────────────────────────────┐      │
           │          Review Engine (ruff + regex)          │      │
           └──────────────────────────────────────────────┘      │
                                                                └───┘
```

---

## Features & Tools

| Tool              | Description                                | Example Input                                                                 | Example Output                              |
|-------------------|--------------------------------------------|-------------------------------------------------------------------------------|---------------------------------------------|
| `search_code`     | Search GitHub repo code by query            | `search_code("def main", "owner/repo")`                                       | List of matching files with paths & URLs    |
| `list_issues`     | List open or closed issues                   | `list_issues("owner/repo", state="open")`                                     | Formatted list of issues                    |
| `create_issue`    | Create a new issue (policy-guarded)          | `create_issue("owner/repo", "Bug: timeout", "Steps to reproduce...")`         | Confirmation with issue URL                 |
| `get_pr_diff`     | Fetch raw diff of a pull request             | `get_pr_diff("owner/repo", pr_number=7)`                                      | Unified diff as text                        |
| `create_pr`       | Create a pull request between branches       | `create_pr("owner/repo", "Add feature", "Details...", head="feat", base="main")` | Confirmation with PR URL                   |
| `review_pr_diff`  | Run local automated code review rules        | `review_pr_diff("owner/repo", pr_number=7)`                                   | List of warnings and errors found           |
| `comment_pr_review`| Post review findings as PR comments         | `comment_pr_review("owner/repo", pr_number=7)`                                | Number of comments posted                   |
| `get_file_contents`| Read a file from a repository               | `get_file_contents("owner/repo", "src/main.py", ref="main")`                   | Decoded file content with metadata          |
| `create_or_update_file`| Create or update a single file (guarded) | `create_or_update_file("owner/repo", "src/app.py", content="print(1)", message="Add app.py")` | Commit SHA and URL                         |
| `push_files`      | Push multiple files as a single commit       | `push_files("owner/repo", "main", "feat: add modules", '[{"path":"a.py","content":"..."}]')` | Commit SHA and file list                   |
| `add_issue_comment`| Comment on an issue or pull request          | `add_issue_comment("owner/repo", 1, "Looks good!")`                           | Comment URL                                |
| `merge_pull_request`| Merge a pull request                        | `merge_pull_request("owner/repo", 42, merge_method="squash")`                  | Merge status and SHA                       |

---

## Security Model

- **Repository Allowlist:** Only repositories explicitly allowed by policy can be accessed.
- **Branch Protection:** PRs to protected branches are subject to branch protection rules before merging.
- **Dry-Run Mode:** Execute operations without side effects for safe testing and auditing.
- **Audit Logging:** All actions logged in JSONL format with precise timestamps to maintain traceability.
- **Policy Configuration:** Start from `policy.example.json` to configure repository allowlists and protected branches.

---

## FAQ

**Why not call the GitHub API directly?**  
Direct API calls lack centralized policy enforcement, audit logging, and uniform tooling support for AI agents. This MCP server adds a controlled, auditable layer for safer automation.

**What MCP clients work with this?**  
Agents like Claude Code, OpenAI Codex, and any client supporting the MCP JSON-RPC 2.0 transport can connect to this server.

**How is this different from the official GitHub MCP server?**  
This project's key differentiator is policy enforcement. Repository allowlists prevent agents from touching unauthorized repos, branch protection blocks accidental PRs to sensitive branches, dry-run mode supports safe validation, and write actions are audit-logged with timestamps.

---

## Quick Start

### Prerequisites

- Python 3.10+
- GitHub personal access token with `repo` scope

### Install

```bash
pip install fastmcp httpx python-dotenv
```

### Configure and Run

```bash
git clone https://github.com/FMorgan-111/github-mcp-server.git
cd github-mcp-server
cp .env.example .env && nano .env
python3 -m src.main
```

### Connect with Claude Code

```bash
claude mcp add github-agent -- python3 /path/to/github-mcp-server/src/main.py
```

---

## Development

```bash
pip install -e . --break-system-packages
python3 -m pytest tests/ -v
python3 -m src.main
```

106 tests, all passing.

---

## Docker Deployment

```bash
docker build -t github-mcp-server .
docker run \
  -e GITHUB_TOKEN=ghp_your_token_here \
  -i github-mcp-server
```

The `-e GITHUB_TOKEN=...` flag passes the token into the container because
the local `.env` file is not copied into the image.

---

## License

MIT

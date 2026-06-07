# GitHub MCP Agent Server

## Project Structure
```
src/
├── main.py          # Entry point — mcp.run(transport="stdio" or "http")
├── tools.py         # MCP tool definitions (12 tools via @mcp.tool())
├── github_client.py # GitHub API client (httpx, 12 API methods)
├── policy.py        # Policy engine — repo allowlist + branch protection + hot-reload
├── audit.py         # Audit logger — JSONL structured + redaction
├── review.py        # Legacy regex review rules (print/TODO/secrets/bare-except)
├── review_engine.py # Review orchestration (ruff + regex fallback)
├── diff_parser.py   # Unified diff parser → ChangedFile {path, added_lines}
├── config.py        # Env config via python-dotenv
└── analyzers/
    ├── base.py      # Analyzer protocol + Finding dataclass
    └── ruff.py      # Ruff subprocess analyzer
tests/
├── test_tools.py    # 33 tool tests
├── test_github_client.py  # 14 client tests
├── test_policy.py   # 14 policy tests (allowlist + branch + hot-reload)
├── test_audit.py    # 8 audit tests (JSONL + redaction)
├── test_review_engine.py  # 10 review engine tests
├── test_edge_cases.py     # 5 edge case tests
├── test_diff_parser.py    # 5 diff parser tests
├── test_ruff_analyzer.py  # 3 ruff analyzer tests
├── test_config.py   # 3 config tests
├── test_main.py     # 4 main entry tests
├── test_http_transport.py  # 3 HTTP transport tests
└── workflow_test.py # Gray-box workflow (real GitHub API)
```

## Commands
- `python3 -m src.main` — Start MCP server (stdio mode)
- `python3 -m src.main --transport http --port 8000` — HTTP mode
- `python3 -m pytest tests/ -v` — Run all tests (107 tests, 1 xfail)
- `docker build -t github-mcp-server . && docker run -e GITHUB_TOKEN=xxx -i github-mcp-server` — Docker

## Key Architecture
- Each MCP tool creates a **new GitHubClient instance** per call (thread-safe, no shared state)
- Write tools pass through **policy guard** (repo allowlist + branch protection) + **audit logging**
- Policy supports **hot-reload** — file watcher thread polls mtime every 500ms
- Code review uses **ruff + regex dual-engine** architecture
- `GITHUB_TOKEN` is read from `.env` file via `python-dotenv`, or from environment variable
- The server supports **stdio and HTTP** transports via FastMCP

## Adding a New Tool
1. Add a method to `GitHubClient` in `github_client.py`
2. Add a `@mcp.tool()` function in `tools.py`
3. If write tool: add policy guard + audit logging (copy pattern from existing)
4. Add tests in `tests/test_tools.py` (and `tests/test_github_client.py` for API methods)

## Code Style
- Python 3.10+ type hints, mypy strict mode
- httpx, not requests
- Tools return human-readable `str`, not raw JSON
- Error responses always start with "Error: "
- ruff linting, no black (ruff handles formatting)

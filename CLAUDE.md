# GitHub MCP Agent Server

## Project Structure
```
src/
├── main.py          # Entry point — mcp.run(transport="stdio")
├── tools.py         # MCP tool definitions (6 tools via @mcp.tool())
├── github_client.py # GitHub API client (httpx)
├── review.py        # Local code review rules (no API call)
└── config.py        # Env config via python-dotenv
tests/
└── test_tools.py    # 8 tests (pytest)
```

## Commands
- `python3 -m src.main` — Start MCP server (stdio mode)
- `python3 -m pytest tests/ -v` — Run all tests
- `docker build -t github-mcp-server . && docker run -e GITHUB_TOKEN=xxx -i github-mcp-server` — Docker

## Key Architecture
- Each MCP tool creates a **new GitHubClient instance** per call (thread-safe, no shared state)
- The `GITHUB_TOKEN` is read from `.env` file via `python-dotenv`, or from environment variable
- `review.py` is **fully local** — no API calls, just regex-based diff analysis
- The server uses **stdio transport** — an AI agent spawns it as a subprocess and communicates via stdin/stdout

## Adding a New Tool
1. Add a method to `GitHubClient` in `github_client.py`
2. Add a `@mcp.tool()` function in `tools.py`
3. Add tests in `tests/test_tools.py`

## Code Style
- Python 3.10+ type hints
- httpx, not requests
- Tools return human-readable `str`, not raw JSON
- Error responses always start with "Error: "

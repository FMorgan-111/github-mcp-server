# Contributing to GitHub MCP Server

Thank you for your interest in contributing! This document will guide you through setting up your development environment, running tests, following code style guidelines, and submitting quality pull requests.

---

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/FMorgan-111/github-mcp-server.git
   cd github-mcp-server
   ```

2. Create and activate a virtual environment (Python 3.10+ required):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the package in editable mode along with dependencies:
   ```bash
   pip install -e .
   pip install black ruff mypy
   ```

---

## Running Tests

Run all tests with verbose output using:
```bash
python3 -m pytest tests/ -v
```

---

## Code Style

We use the following tools and configurations:

- [Black](https://black.readthedocs.io/en/stable/) with max line length 120:
  ```bash
  black --line-length=120 .
  ```
- [ruff](https://github.com/charliermarsh/ruff) linter for Python code style compliance.
- [mypy](https://mypy-lang.org/) with strict type checking:
  ```bash
  mypy --strict src/
  ```

Please ensure these pass before submitting PRs.

---

## Pull Request Checklist

Before submitting your PR, please verify:

- All tests pass (`pytest`).
- New features/changes have corresponding tests.
- Code passes `ruff` linting with no errors.
- Code passes `mypy` type checks with no errors.
- The changelog or documentation is updated if applicable.

---

## Commit Message Conventions

Please use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) style for commit messages:

- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `test:` for adding or modifying tests
- `ci:` for continuous integration or tooling changes

Example:
```
feat: add new GitHub API method to fetch repo metadata
```

---

## Adding a New MCP Tool

To add a new MCP tool:

1. Implement a new method in `src/github_client.py` for the GitHub API interaction if needed.
2. Define a new tool function in `src/tools.py` decorated with `@mcp.tool()`.
3. If the tool performs any write/change operations, add the required policy guard checks for allowlist or branch protection.
4. Add new test cases for this tool in `tests/test_tools.py` to cover expected inputs and outputs.
5. Ensure all tests pass and linters succeed before submitting the PR.

---

## Troubleshooting

**pip install fails?**  
Upgrade packaging tools first with `python3 -m pip install --upgrade pip setuptools wheel`, then rerun `pip install -e .` from the repository root.

**Token permission errors?**  
Check that `GITHUB_TOKEN` is set in `.env` or your shell and that the token has access to the target repository with the required `repo` permissions.

**How to test with MCP Inspector?**  
Run MCP Inspector against the stdio server command: `npx @modelcontextprotocol/inspector python3 -m src.main`.

---

Thank you for helping improve the GitHub MCP Server project!

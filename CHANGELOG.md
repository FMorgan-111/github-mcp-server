# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- 5 new MCP tools: get_file_contents, create_or_update_file, push_files, add_issue_comment, merge_pull_request
- File read/write: base64-decoded repository file reading with directory detection
- Batch commit: push_files uses Git Data API (blobs → tree → commit → ref update) for multi-file atomic commits
- PR lifecycle: merge support with merge/squash/rebase strategies
- Issue interaction: comment on issues and pull requests
- All new write tools are policy-guarded with full audit logging
- 34 new tests (106 total), all passing

## [0.1.0] — 2026-06-07

### Added
- 7 MCP tools: search_code, list_issues, get_pr_diff, create_issue, create_pr, review_pr_diff, comment_pr_review
- Policy enforcement layer: repo allowlist, branch protection, dry-run mode
- Audit logging: JSONL-structured write operation tracking with timestamps
- Code review engine: ruff-based analyzer + regex fallback rules
- Diff size protection: 500KB default limit, 1MB hard cap with env override (`GITHUB_REVIEW_MAX_DIFF_BYTES`)
- Multi-Python CI: 3.10, 3.11, 3.12 with ruff lint, mypy type check, and pytest coverage
- Comprehensive test suite: 72 tests covering tools, policy, audit, review engine, GitHub client

### Security
- Write tools require policy approval before execution (repo allowlist + branch protection)
- Invalid/missing policy: invalid JSON defaults to deny (fail-safe); missing policy defaults to allow when GITHUB_POLICY_REQUIRED=false
- Audit log write failures are reported to stderr (not silently dropped)
- Oversized diffs (>hard cap) are rejected to prevent OOM

### Changed
- Policy: invalid JSON now defaults to deny instead of allow
- Audit: write failures now emit a warning to stderr
- CI: expanded from basic pytest to ruff + mypy + coverage matrix

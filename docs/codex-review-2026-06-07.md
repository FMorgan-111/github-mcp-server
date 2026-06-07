# Codex Review: CONTRIBUTING.md + README.md

> 2026-06-07 | Reviewer: Codex (gpt-5.5) | Project: github-mcp-server

## CRITICAL — Must Fix

### 1. python vs python3 命令不一致
- **文件:** README.md L87, L102, CONTRIBUTING.md L32
- **问题:** README 和 CONTRIBUTING 的测试命令写的是 `python -m pytest`，但系统 PATH 上只有 `python3`（`python` 不存在）
- **修法:** 统一改成 `python3 -m pytest tests/ -v`
- **备注:** CONTRIBUTING.md 的 venv 创建用了 `python3`（正确），但测试命令用了 `python`（错误）

### 2. black/ruff/mypy 未安装，命令不可执行
- **文件:** CONTRIBUTING.md L41-49
- **问题:** 文档要求 black --line-length=120、ruff、mypy --strict，但 pyproject.toml 的 dependencies 里没有这三者。新贡献者跑这些命令必报 `command not found`
- **修法:** 要么把三者加入 dev dependencies，要么在 CONTRIBUTING 里明确写 `pip install black ruff mypy` 后再跑

## HIGH — Credibility Gaps

### 3. 测试状态未在 README 体现
- **实测:** 23 tests passed in 0.71s（全部通过）
- **问题:** README 没有任何测试覆盖率的 badge 或说明。面试官扫一眼看不到质量信号
- **修法:** 加 coverage badge，或至少在 Development 段注明 "23 tests, all passing"

### 4. 已有配置文件未在 README 提及
- **存在但未提及的文件:**
  - `policy.example.json` — 策略配置模板（repo 白名单 + 分支保护）
  - `.env.example` — 环境变量模板
  - `.github/workflows/ci.yml` — CI 流程
- **修法:** README 的 Security Model 段引用 `policy.example.json` 路径和格式；Quick Start 段用 `cp .env.example .env` 替代手写 echo

### 5. Dockerfile 存在但与 README 描述不完全匹配
- **Dockerfile 内容:** `FROM python:3.11-slim`, COPY src/ + pyproject.toml, ENTRYPOINT python3 -m src.main
- **问题:** README 只说 `docker build -t ...` 但没说明容器内没有 .env 文件如何配置 Token；Docker run 命令用 `-e GITHUB_TOKEN=...` 是对的但没解释
- **修法:** Docker 段加一句说明 `-e GITHUB_TOKEN=...` 的作用

## MEDIUM — Polish

### 6. FAQ "不同于官方"的理由太弱
- **当前:** "local review rules, policy guards, audit trail logging"
- **问题:** 没突出差异化——官方 MCP server 也有基本的工具。应该强调：策略引擎（repo 白名单 + 分支保护 = Agent 不会误伤生产分支）、审计追踪（每次写操作可追溯）、dry-run 安全模式
- **建议:** 重写为 "Adds a policy enforcement layer that official server lacks — repo allowlists prevent agents from touching unauthorized repos, branch protection blocks accidental PRs to main, and every write action is audit-logged with timestamps"

### 7. 架构图里 review engine 缺失
- **当前 ASCII 图:** 只有 Policy Guard + Audit Log + github_client
- **缺失:** review_engine (ruff analyzer) 和 diff_parser 没出现
- **建议:** 加一行 "Review Engine (ruff + regex rules)" 在 github_client 旁边

### 8. CONTRIBUTING 缺 troubleshooting
- **缺失:** 没有 "常见问题" 段——Token 权限不够怎么办、MCP Inspector 怎么测试、stdio 模式怎么看日志

## LOW — Nice to Have

### 9. Badge 不完整
- 缺: coverage badge, PyPI version badge (placeholder), Python versions badge
- CI badge 链接可能因 repo 名变更而 404

### 10. 缺少 CHANGELOG.md
- CONTRIBUTING 提到 "changelog updated" 但没有 CHANGELOG.md 文件
- 建议创建并链接

---

## 实测数据

```
$ python3 -m pytest tests/ -v
23 passed in 0.71s

$ python3 -m src.main
FastMCP 3.4.0 — GitHub MCP Agent Server — stdio mode

$ python -m pytest tests/ -v
python: command not found  ← 文档的 bug
```

## 修复优先级

1. 统一 python → python3（README + CONTRIBUTING）
2. CONTRIBUTING 加 `pip install black ruff mypy` 步骤
3. README 引用 policy.example.json + .env.example
4. 加强 FAQ 差异化描述
5. 架构图补 review engine
6. README 加测试通过数和 badge

# GitHub MCP Server — 技术架构与实现文档

> 作者：傅茂根（Morgan Fu）
> 版本：0.1.0
> 更新时间：2026-06-07

---

## 目录

1. [项目定位](#1-项目定位)
2. [MCP 协议基础](#2-mcp-协议基础)
3. [系统架构](#3-系统架构)
4. [源码详解](#4-源码详解)
5. [策略引擎](#5-策略引擎)
6. [审计系统](#6-审计系统)
7. [代码审查引擎](#7-代码审查引擎)
8. [GitHub API 集成](#8-github-api-集成)
9. [MCP 工具清单](#9-mcp-工具清单)
10. [测试体系](#10-测试体系)
11. [部署方案](#11-部署方案)
12. [与官方 GitHub MCP Server 的对比](#12-与官方-github-mcp-server-的对比)
13. [面试话术](#13-面试话术)
14. [灰度测试与 Debug 实战](#14-灰度测试与-debug-实战)

---

## 1. 项目定位

### 一句话

**给 AI Agent 发放受控的 GitHub 访问权限，每步操作可审计。**

### 核心问题

AI Agent（Claude Code、Codex、Cursor 等）需要操作 GitHub，但直接给它们 Personal Access Token（PAT）存在严重安全隐患：

- Agent 可能推代码到不允许的仓库
- Agent 可能直接合入 main 分支跳过 review
- 没有操作记录，出问题无法追溯

### 解决方案

在 Agent 和 GitHub API 之间插入一个**安全中间件**：

```
AI Agent ──MCP──► GitHub MCP Server ──► GitHub API
                    │
                    ├── Policy Guard（策略守卫）
                    │   ├── 仓库白名单
                    │   ├── 分支保护
                    │   └── 干运行模式
                    │
                    └── Audit Logger（审计日志）
                        ├── JSONL 结构化日志
                        └── 敏感信息脱敏
```

### 差异化优势（vs 官方 github/github-mcp-server）

| 维度 | 官方（Go，30k★） | 本项目 |
|------|-----------------|--------|
| 定位 | 暴露全量 GitHub API | 安全受控的 Agent 网关 |
| 安全模型 | OAuth / PAT | repo allowlist + branch protection + dry-run |
| 审计 | 无 | JSONL 全量写操作审计 + 脱敏 |
| 代码审查 | 无 | ruff + regex 本地审查引擎 |
| 语言 | Go | Python |
| 部署 | 依赖 GitHub 远程服务 | 自托管 Docker，数据不出境 |

---

## 2. MCP 协议基础

### MCP 是什么

**Model Context Protocol（MCP）** 是 Anthropic 于 2024 年提出的开放协议，让 AI Agent 能通过标准化接口调用外部工具。

类比：MCP 之于 AI Agent = USB-C 之于硬件外设。一个统一接口，即插即用。

### 核心概念

```
┌──────────────────┐                  ┌──────────────────┐
│   MCP Client     │  JSON-RPC 2.0   │   MCP Server     │
│  (Claude Code,   │ ◄──────────────► │  (我们的项目)      │
│   Codex, Cursor) │   over stdio     │                  │
│                  │   or HTTP        │                  │
└──────────────────┘                  └──────────────────┘
```

**MCP Client**：AI 应用端（Claude Code、Codex CLI、VS Code Copilot）
**MCP Server**：工具提供端（我们的 GitHub MCP Server）
**传输层**：stdio（标准输入输出）或 HTTP（Streamable HTTP）

### JSON-RPC 2.0 消息格式

MCP 使用 JSON-RPC 2.0 作为通信协议：

```json
// 请求：Agent 调用工具
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_file_contents",
    "arguments": {
      "repo": "FMorgan-111/github-mcp-server",
      "path": "README.md"
    }
  }
}

// 响应：Server 返回结果
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "File: README.md (6396 bytes)...\n---\n# GitHub MCP Agent Server\n..."}]
  }
}
```

### 生命周期

1. **初始化**：Client 发送 `initialize` 请求，Server 返回能力列表
2. **工具发现**：Client 调用 `tools/list`，Server 返回所有可用工具及其 JSON Schema
3. **工具调用**：Client 发送 `tools/call`，指定工具名和参数
4. **关闭**：Client 发送 `shutdown` 或断开连接

### FastMCP 框架

本项目使用 **FastMCP**（Python MCP 框架），它封装了 JSON-RPC 细节，开发者只需写 Python 函数 + 装饰器：

```python
from fastmcp import FastMCP

mcp = FastMCP("GitHub MCP Agent Server")

@mcp.tool()
def search_code(query: str, repo: str | None = None) -> str:
    """Search for code in GitHub repositories."""
    # ... 实现
    return result

mcp.run(transport="stdio")  # 一行启动
```

FastMCP 自动处理：
- JSON-RPC 协议编解码
- 工具注册与发现（从函数签名生成 JSON Schema）
- 参数类型校验
- stdio / HTTP 双传输模式

---

## 3. 系统架构

### 整体分层

```
┌─────────────────────────────────────────────────────┐
│                    MCP Transport                      │
│               stdio / HTTP (FastMCP)                  │
├─────────────────────────────────────────────────────┤
│                   tools.py（工具层）                   │
│  12 个 @mcp.tool() 函数                              │
│  ├── 读工具（4个）：无需策略守卫                       │
│  └── 写工具（8个）：策略守卫 + 审计日志                 │
├──────────────┬──────────────────┬───────────────────┤
│   policy.py  │    audit.py      │  review_engine.py │
│   策略引擎    │    审计日志       │   代码审查引擎     │
├──────────────┴──────────────────┴───────────────────┤
│               github_client.py（API 层）              │
│           httpx → GitHub REST API v3                 │
├─────────────────────────────────────────────────────┤
│               config.py（配置层）                      │
│          环境变量 / .env → 配置项                     │
└─────────────────────────────────────────────────────┘
```

### 请求处理流程（写操作为例）

```
1. Agent 调用 create_issue("owner/repo", "title", "body")
        ↓
2. tools.py: create_issue() 函数
        ↓
3. 解析 dry_run 状态
        ↓
4. policy.check_repo("owner/repo")  ← 仓库白名单检查
        ↓                          ├── allow → 继续
        │                          └── deny  → 拒绝 + 审计记录
        ↓
5. （create_pr 额外）policy.check_branch_for_pr("main") ← 分支保护
        ↓
6. dry_run? → 预览模式，不实际调用 API
        ↓
7. GitHubClient.create_issue()  → httpx → GitHub API
        ↓
8. audit.log()  ← 记录完整操作（请求 + 响应 + 脱敏）
        ↓
9. 返回格式化结果给 Agent
```

### 文件清单与职责

| 文件 | 行数 | 职责 |
|------|------|------|
| `src/main.py` | 63 | 入口点，支持 stdio/HTTP 双传输模式，SIGTERM 优雅关闭 |
| `src/tools.py` | 620 | 12 个 MCP 工具函数，策略守卫集成，审计日志集成 |
| `src/github_client.py` | 328 | GitHub REST API 客户端（httpx），12 个 API 方法 |
| `src/policy.py` | 204 | 策略引擎：仓库白名单、分支保护、热重载、通配符匹配 |
| `src/audit.py` | 120 | 审计日志：JSONL 输出、敏感信息脱敏、目录校验 |
| `src/config.py` | 40 | 环境变量读取（GITHUB_TOKEN 等） |
| `src/review_engine.py` | 83 | 审查编排器：diff 解析 → ruff 分析 → regex 回退 |
| `src/review.py` | 106 | 旧版 regex 审查规则（print/TODO/secrets/bare-except/function-length） |
| `src/diff_parser.py` | 36 | unified diff 解析器，提取 ChangedFile {path, added_lines} |
| `src/analyzers/base.py` | 21 | Analyzer 协议定义 + Finding 数据类 |
| `src/analyzers/ruff.py` | 49 | Ruff 子进程分析器（--output-format json） |

---

## 4. 源码详解

### 4.1 main.py — 入口点

```python
# 双传输模式
parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
parser.add_argument("--port", type=int, default=8000)  # HTTP 模式端口

# stdio 模式（默认）
mcp.run(transport="stdio")

# HTTP 模式（--transport http）
mcp.run(transport="http", port=args.port, json_response=True)
```

**设计决策：**
- stdio 是 MCP 标准传输方式，适合 Claude Code / Codex 本地调用
- HTTP 模式支持远程部署 + 多客户端共享
- `--no-watch` 标志禁用策略文件热重载（容器环境不需要）

### 4.2 github_client.py — API 客户端

**核心设计模式：错误处理统一化**

所有 API 方法遵循相同模式：

```python
def some_method(self, ...) -> dict[str, Any]:
    try:
        # httpx 调用
        return {"result": ...}
    except Exception as e:
        return {"error": f"Some operation failed: {str(e)}"}
```

**设计决策：**
- 返回 `{"error": "..."}` 而不是抛出异常 → 上层 tools.py 统一 `"error" in result` 检查
- 每个方法独立创建 `httpx.Client()` → 避免连接复用问题
- `timeout=20` 秒 → GitHub API 通常 <1s，20s 足够覆盖重试

**关键 API 方法：**

```python
# 文件读取 — GET /repos/{owner}/{repo}/contents/{path}
get_file_contents(repo, path, ref="")
# → 自动 Base64 解码 → UTF-8 文本

# 文件写入 — PUT /repos/{owner}/{repo}/contents/{path}
create_or_update_file(repo, path, message, content, sha="", branch="")
# → 自动 UTF-8 → Base64 编码
# → sha 参数用于冲突检测（更新已有文件时必须提供）

# 批量提交 — Git Data API（6 步）
push_files(repo, branch, message, files)
# 1. GET refs/heads/{branch}    → 获取当前 commit SHA
# 2. GET git/commits/{sha}      → 获取当前 tree SHA
# 3. POST git/blobs (×N)        → 为每个文件创建 blob
# 4. POST git/trees             → 基于原 tree + 新 blobs 创建新 tree
# 5. POST git/commits           → 创建新 commit（parent=原 commit）
# 6. PATCH refs/heads/{branch} → 更新分支指针（force=false）
```

### 4.3 config.py — 配置层

所有配置通过环境变量读取，无硬编码：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `GITHUB_TOKEN` | （必填） | GitHub Personal Access Token |
| `GITHUB_API_BASE` | `https://api.github.com` | API 地址（支持 GHE） |
| `GITHUB_POLICY_PATH` | `policy.json` | 策略文件路径 |
| `GITHUB_POLICY_REQUIRED` | `false` | 策略文件缺失时是否拒绝所有操作 |
| `GITHUB_AUDIT_LOG` | `stdout` | 审计日志输出（stdout/stderr/文件路径） |
| `GITHUB_DRY_RUN` | `false` | 全局干运行模式（所有写操作只预览不执行） |
| `GITHUB_REVIEW_MAX_DIFF_BYTES` | `524288` (500KB) | 代码审查最大 diff 大小 |
| `GITHUB_AUDIT_DIR_ALLOWLIST` | 空 | 审计文件目录白名单 |

---

## 5. 策略引擎

### 5.1 设计理念

**安全默认：拒绝优先（deny-by-default）**

```
          有策略文件？
         /         \
       是           否
       │            │
   JSON 有效？    required=true?
   /      \      /      \
  是      否     是      否
  │       │     │       │
 检查   拒绝   拒绝    允许
 规则   所有   启动    所有
```

### 5.2 核心数据结构

```python
@dataclass
class PolicyDecision:
    action: str       # "allow" | "deny" | "dry_run"
    reason: str       # 人类可读的解释
    matched_rule: str # 触发的规则名（用于审计）

@dataclass
class PolicyConfig:
    repo_allowlist: list[str]  # e.g. ["FMorgan-111/*", "fastapi/fastapi"]
    deny_pr_base: list[str]    # e.g. ["main", "master", "release/*"]
    deny_force_push: bool = True
```

### 5.3 策略文件格式（policy.json）

```json
{
  "repo_allowlist": [
    "FMorgan-111/*",
    "fastapi/fastapi",
    "numpy/numpy"
  ],
  "protected_branches": {
    "deny_pr_base": ["main", "master", "release/*"],
    "deny_force_push": true
  }
}
```

### 5.4 通配符匹配算法

```python
def _wildcard_match(pattern: str, value: str) -> bool:
    """Glob 风格匹配：'FMorgan-111/*' 匹配 'FMorgan-111/任何仓库'"""
    if pattern == "*":
        return True                    # * 匹配全部
    if "*" in pattern:
        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        return bool(re.match(regex, value))
    return pattern == value            # 精确匹配
```

### 5.5 策略热重载

```
policy-watcher 守护线程（每 500ms 轮询）
    │
    ├── mtime 变化?
    │   ├── 是 → _reload_policy() → 线程安全更新
    │   └── 否 → 继续轮询
    │
    └── stop_evt.is_set()? → 退出
```

**线程安全保证：** 所有策略读取/更新操作在 `self._lock` 保护下执行。

---

## 6. 审计系统

### 6.1 审计日志格式（JSONL）

每行一个 JSON 对象：

```json
{
  "timestamp": "2026-06-07T12:00:00.123456+00:00",
  "request_id": "a1b2c3d4e5f6",
  "tool": "create_or_update_file",
  "action": "file.upsert",
  "repo": "FMorgan-111/github-mcp-server",
  "dry_run": false,
  "policy": {
    "decision": "allow",
    "matched_rule": "repo_allowlist:FMorgan-111/*"
  },
  "request": {
    "path": "src/app.py",
    "message": "Update app.py",
    "branch": "main"
  },
  "response": {
    "commit_sha": "abc1234",
    "content_sha": "def5678",
    "path": "src/app.py",
    "html_url": "https://github.com/..."
  },
  "error": null
}
```

### 6.2 敏感信息脱敏

```python
REDACT_KEYS = {
    "GITHUB_TOKEN", "token", "password", "api_key",
    "authorization", "auth", "secret"
}

def _redact(obj):
    """递归脱敏：遇到敏感 key → '***REDACTED***'"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in REDACT_KEYS:
                out[k] = "***REDACTED***"
            elif isinstance(v, (dict, list)):
                out[k] = _redact(v)
            elif isinstance(v, str) and len(v) > 200:
                out[k] = v[:200] + "..."  # 截断长字符串
            else:
                out[k] = v
```

### 6.3 目录安全

审计文件写入受目录白名单保护：

```python
# 通过 GITHUB_AUDIT_DIR_ALLOWLIST 限制写入目录
allowed = allowlist_str.split(",")
if not any(os.path.commonpath([parent, d]) == d for d in allowed):
    raise ValueError(f"Audit sink parent not in allowlist")
```

---

## 7. 代码审查引擎

### 7.1 双层审查架构

```
         review_engine.py
              │
    ┌─────────┴──────────┐
    │                    │
    ▼                    ▼
ruff (新)          regex (旧)
子进程调用          内建规则
Python 专用          通用文本
```

### 7.2 Ruff 分析器

```python
class RuffAnalyzer:
    def analyze(self, file_path: str) -> list[Finding]:
        # 调用 ruff check --output-format json
        result = subprocess.run(
            ["ruff", "check", "--output-format", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        violations = json.loads(result.stdout)
        # 转换为 Finding 对象
```

**设计决策：**
- Ruff 不可用时静默降级（不崩溃）
- 只报告**变更行**的问题（通过 diff_parser 的 changed_lines 过滤）
- 30 秒超时防止 ruff 卡死

### 7.3 Regex 回退规则

| 规则 | 严重度 | 检测内容 |
|------|--------|----------|
| `no-print` | warning | `print()` 语句（跳过 test 文件） |
| `no-todo-comments` | warning | TODO/FIXME/HACK 注释 |
| `no-hardcoded-secrets` | error | password= / api_key= / token= 赋值 |
| `no-bare-except` | error | `except:` 裸异常捕获 |
| `function-length` | warning | 函数超过 80 行 |

### 7.4 Diff 大小保护

```python
_DEFAULT_MAX_DIFF_BYTES = 500 * 1024    # 500KB 默认
_MAX_DIFF_BYTES_HARD_CAP = 1024 * 1024   # 1MB 硬上限

# 超大 diff 拒绝审查，防止 OOM
if diff_bytes > max_bytes:
    return [Finding(
        severity="error",
        rule="diff-too-large",
        message=f"Diff too large ({diff_bytes//1024} KB, limit {max_bytes//1024} KB). Review skipped."
    )]
```

---

## 8. GitHub API 集成

### 8.1 API 端点映射

| MCP 工具 | HTTP 方法 | API 路径 | 特殊 Header |
|----------|-----------|----------|-------------|
| search_code | GET | `/search/code?q=repo:{r}+{q}` | — |
| list_issues | GET | `/repos/{r}/issues` | — |
| create_issue | POST | `/repos/{r}/issues` | — |
| get_pr_diff | GET | `/repos/{r}/pulls/{n}` | `Accept: application/vnd.github.v3.diff` |
| create_pr | POST | `/repos/{r}/pulls` | — |
| comment_pr_review | POST | `/repos/{r}/pulls/{n}/reviews` | — |
| get_file_contents | GET | `/repos/{r}/contents/{p}?ref={b}` | — |
| create_or_update_file | PUT | `/repos/{r}/contents/{p}` | — |
| push_files | 6 步 | Git Data API | — |
| add_issue_comment | POST | `/repos/{r}/issues/{n}/comments` | — |
| merge_pull_request | PUT | `/repos/{r}/pulls/{n}/merge` | — |

### 8.2 认证方式

项目仅支持 **Personal Access Token（PAT）**：

```python
self.headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
```

**未来可扩展：** GitHub App 认证（JWT → Installation Token），提供按仓库粒度的权限控制。

---

## 9. MCP 工具清单

### 9.1 读工具（无需策略守卫）

| 工具 | 参数 | 说明 |
|------|------|------|
| `search_code` | `query`, `repo?` | 搜索仓库代码 |
| `list_issues` | `repo`, `state?` | 列 issues |
| `get_pr_diff` | `repo`, `pr_number` | 获取 PR diff |
| `get_file_contents` | `repo`, `path`, `ref?` | 读文件内容 |

### 9.2 写工具（策略守卫 + 审计日志）

| 工具 | 参数 | 守卫类型 |
|------|------|----------|
| `create_issue` | `repo`, `title`, `body`, `dry_run?` | repo allowlist |
| `create_pr` | `repo`, `title`, `body`, `head`, `base`, `dry_run?` | repo allowlist + branch protection |
| `create_or_update_file` | `repo`, `path`, `content`, `message?`, `branch?`, `sha?`, `dry_run?` | repo allowlist |
| `push_files` | `repo`, `branch`, `message`, `files_json`, `dry_run?` | repo allowlist |
| `add_issue_comment` | `repo`, `issue_number`, `body`, `dry_run?` | repo allowlist |
| `merge_pull_request` | `repo`, `pr_number`, `commit_title?`, `merge_method?`, `dry_run?` | repo allowlist |
| `review_pr_diff` | `repo`, `pr_number` | 读操作（无守卫） |
| `comment_pr_review` | `repo`, `pr_number` | 写操作（repo allowlist） |

### 9.3 干运行模式（Dry Run）

所有写工具支持 `dry_run=True` 参数：

```
[DRY RUN] Would create issue in owner/repo:
  Title: Bug Report
  Body:  Steps to reproduce...
  Policy: repo owner/repo matches allowlist owner/*
```

用法：
- 参数级别：`create_issue("r", "t", "b", dry_run=True)`
- 环境级别：`GITHUB_DRY_RUN=true`（全部写操作变成预览模式）

优先级：**显式参数 > 环境变量 > 默认 false**

---

## 10. 测试体系

### 10.1 测试哲学

**纯 mock 单元测试 + 高覆盖率。** 所有外部依赖（httpx、ruff、文件系统）通过 `unittest.mock.patch` 替换。

### 10.2 测试分层

```
106 tests, 1 xfail
├── test_github_client.py (13 tests) — API 客户端层
│   ├── 方法调用参数验证
│   ├── 错误处理路径
│   └── Base64 编解码正确性
│
├── test_tools.py (33 tests) — 工具层
│   ├── 读工具（search/list/get diff/file）
│   ├── 写工具成功/失败/策略拒绝/dry-run
│   └── 响应格式化
│
├── test_policy.py (14 tests) — 策略引擎
│   ├── 仓库白名单（精确 + 通配符）
│   ├── 分支保护
│   ├── 空配置/无效 JSON 行为
│   └── 热重载 + 线程安全
│
├── test_audit.py (8 tests) — 审计日志
│   ├── JSONL 格式
│   ├── 脱敏规则
│   └── 文件/stream 输出
│
├── test_review_engine.py (10 tests) — 审查引擎
│   ├── Diff 大小限制
│   ├── Ruff 结果过滤
│   └── 二进制/非 UTF-8 处理
│
├── test_diff_parser.py (5 tests) — Diff 解析器
├── test_ruff_analyzer.py (3 tests) — Ruff 分析器
├── test_config.py (3 tests) — 配置
├── test_main.py (4 tests) — 入口点
├── test_http_transport.py (3 tests) — HTTP 传输
└── test_edge_cases.py (4 tests) — 边界情况
```

### 10.3 Mock 工具客户端（FakeHttpxClient）

```python
class FakeHttpxClient:
    """模拟 httpx.Client 的上下文管理器"""
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.get_calls = []     # 记录 GET 调用
        self.post_calls = []    # 记录 POST 调用
        self.put_calls = []     # 记录 PUT 调用
        self.patch_calls = []   # 记录 PATCH 调用

    def __enter__(self):
        if self.error:
            raise self.error    # 模拟连接失败
        return self

    def get/post/put/patch(self, *args, **kwargs):
        # 记录调用参数，返回预设响应
        ...
```

### 10.4 CI 管道

```yaml
# .github/workflows/ci.yml
strategy:
  matrix:
    python: ["3.10", "3.11", "3.12"]  # 多版本覆盖

steps:
  - ruff check src/ tests/            # 代码风格
  - mypy --strict src/                # 类型检查
  - pytest tests/ -v                  # 单元测试
```

---

## 11. 部署方案

### 11.1 本地开发

```bash
git clone https://github.com/FMorgan-111/github-mcp-server.git
cd github-mcp-server
cp .env.example .env && nano .env   # 填入 GITHUB_TOKEN
pip install fastmcp httpx python-dotenv
python3 -m src.main                 # stdio 模式启动
```

### 11.2 Claude Code 注册

```bash
claude mcp add github-agent -- python3 /mnt/e/hermes-work/github-mcp-server/src/main.py
```

或在 `~/.claude/settings.json` 中：

```json
{
  "mcp_servers": {
    "github-agent": {
      "command": "python3",
      "args": ["-m", "src.main"],
      "workdir": "/mnt/e/hermes-work/github-mcp-server",
      "env": {}
    }
  }
}
```

### 11.3 Docker 部署

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY src/ src/
COPY pyproject.toml .
RUN pip install --no-cache-dir fastmcp httpx python-dotenv
CMD ["python3", "-m", "src.main"]
```

```bash
docker build -t github-mcp-server .
docker run -e GITHUB_TOKEN=ghp_xxx -i github-mcp-server
```

**注意：** `.env` 文件不会打入镜像，必须通过 `-e` 传入环境变量。

### 11.4 HTTP 模式（多客户端共享）

```bash
python3 -m src.main --transport http --port 8000
# 多个 Agent 通过 http://host:8000/mcp 连接
```

### 11.5 PyPI 安装

```bash
pip install mcp-github-agent
GITHUB_TOKEN=ghp_xxx github-mcp
```

---

## 12. 与官方 GitHub MCP Server 的对比

### 官方（github/github-mcp-server）

- **语言：** Go
- **Stars：** 30,000+
- **定位：** 暴露 GitHub 平台全能力给 AI Agent
- **工具集：** 20+ 工具集（repos、issues、pr、actions、code_security、dependabot、discussions、gists、git、projects、orgs、users…）
- **安全模型：** OAuth / PAT，信任 Agent 完整操作
- **部署：** GitHub 托管远程服务 `api.githubcopilot.com/mcp/`
- **独有：** Copilot Coding Agent 集成、GitHub Support Docs 搜索

### 本项目（FMorgan-111/github-mcp-server）

- **语言：** Python
- **定位：** 安全可控的 AI Agent 网关 — 不信任 Agent，每一步受控
- **工具：** 12 个精选工具（核心工作流覆盖）
- **安全模型：** 仓库白名单 + 分支保护 + 干运行模式
- **审计：** JSONL 全量写操作审计日志 + 敏感信息脱敏
- **代码审查：** ruff + regex 本地审查引擎（diff 大小保护 + OOM 防护）
- **部署：** 自托管（Docker / PyPI），数据不出境
- **独有：** 策略引擎、审计日志、热重载策略

### 如何回答"为什么不用官方"

> 官方 MCP Server 的信任模型是"Agent 可以随意操作 GitHub"，而我们的产品定位是企业需要在给 AI Agent 发 Token 的同时保证安全可控。策略引擎（仓库白名单 + 分支保护）和审计日志（每步操作可追溯）是官方没有也不会有的一层——因为 GitHub 自己做的产品不会在自身平台上加"不信任 AI"的中间层。这是一个天然只能由第三方做的细分方向。

---

## 14. 灰度测试与 Debug 实战

### 14.1 测试策略

项目测试分两层：

| 层级 | 工具 | 覆盖范围 | 运行方式 |
|------|------|----------|----------|
| 单元测试 | pytest（106→107 tests） | 所有模块 mock 覆盖 | CI 自动运行 |
| 灰度测试 | Claude Code Opus / Hermes | 真实 GitHub API 端到端 | 手动触发 |

单元测试验证代码逻辑正确，灰度测试验证**真实 API 交互 + 工具协作**正确。

### 14.2 灰度测试 Workflow

使用 Claude Code Opus（claude-opus-4-20250514）连接本项目的 MCP Server，执行完整的 Agent 工作流：

```
Step 1: get_file_contents     → 读 README.md
Step 2: create_or_update_file → 在新分支创建测试文件
Step 3: push_files            → 批量 push 两个文件（Git Data API 6 步）
Step 4: create_pr             → 创建 Pull Request
Step 5: review_pr_diff        → ruff + regex 双引擎审查
Step 6: add_issue_comment     → PR 下评论
Step 7: 清理                  → 关闭 PR + 删除分支
```

所有操作通过 MCP 协议，不直接操作 GitHub，真实模拟 Agent 使用场景。

### 14.3 Opus 灰度测试发现的问题

#### Bug #1：`_deny_all` 永久粘滞（严重）

**发现过程：** Codex 对 commit 6c15a24 做静态分析时发现。

**根因：**

```python
# policy.py load() 方法 — 修复前
except (json.JSONDecodeError, OSError) as e:
    self._loaded = True
    self._deny_all = True      # ← 设置为 True
    self.repo_allowlist = []
    return self

# 成功加载路径 — 修复前
self.repo_allowlist = _ensure_list(data.get("repo_allowlist"))
# ... 其他赋值
self._loaded = True
# ⚠ 没有 self._deny_all = False！
return self
```

**影响：** 一旦策略文件出现 JSON 格式错误，即使后来修复文件并通过热重载重新加载，`_deny_all` 仍然为 `True`，`check_repo()` 中：

```python
if getattr(self, "_deny_all", False):
    return PolicyDecision("deny", "policy load failed — denying all", ...)
```

会导致**所有仓库操作被永久拒绝**，只能重启服务。

**修复：** 在成功加载路径显式设置 `self._deny_all = False`（policy.py:68）。

**教训：** 状态机的异常路径和正常路径必须对称清理。任何一个 `set` 都要对应一个 `clear`。热重载放大了这个问题——单次加载时重启即可恢复，但热重载下用户会困惑"明明修好了 JSON 为什么还不工作"。

#### Bug #2：`create_or_update_file` 分支不存在时 404

**发现过程：** CC Opus 灰度测试 Step 2 直接失败。

**根因：** GitHub Contents API 的 PUT 操作在目标分支不存在时返回 404。之前的 Hermes 测试没暴露这个问题，因为 Hermes 测试脚本在 Step 0 手动创建了分支。

```
Agent: create_or_update_file(repo, "src/test.py", branch="new-branch")
MCP Server: PUT /repos/{r}/contents/src/test.py → 404 ❌
Agent: "失败，停止"  ← 用户体验差
```

**修复：** 在 `github_client.py` 添加 `_ensure_branch()` 方法，404 时自动从 main 创建分支后重试：

```python
if resp.status_code == 404 and branch:
    self._ensure_branch(client, repo, branch)  # 创建分支
    resp = client.put(...)                       # 重试
```

**教训：** 单元测试 mock 了 httpx，返回 200，走不到 404 分支。灰度测试填补了这个盲区。

#### Bug #3：线程 join 无 timeout

**发现过程：** Codex 静态分析 `test_edge_cases.py:60`。

```python
# 修复前
for t in threads:
    t.join()  # ⚠ 如果 reader deadlock，CI 永久挂死
```

**修复：**

```python
for t in threads:
    t.join(timeout=10)
    assert not t.is_alive(), "Reader thread hung — possible deadlock"
```

#### Bug #4：Watcher 清理不在 finally 里

**发现过程：** 同上，Codex 静态分析。

```python
# 修复前
cfg.start_watching(f.name)
# ... 中间有任何断言失败 ...
cfg.stop_watching()  # ← 永远不会执行，daemon 线程泄漏

# 修复后
cfg.start_watching(f.name)
try:
    # ... 测试逻辑 ...
finally:
    cfg.stop_watching()  # ← 无论如何都会执行
```

### 14.4 Debug 方法论

#### 原则 1：永远用最贵的模型做灰度测试

Claude Opus 的代码分析能力远超 Sonnet。同样的问题，Sonnet 可能"看起来能跑"（输出正确格式但不检查边界条件），Opus 会主动暴露。灰度测试的价值不在功能验证，而在**边界发现**。

#### 原则 2：Mock 测试过不了真实 API

> "单元测试全都过了，灰度测试一分钟就炸了。"

这是本项目的真实经历。`create_or_update_file` 的 404 bug 在 106 个单元测试中全部通过，因为 mock 永远返回 200。只有真实 API 调用能暴露此类问题。

**结论：** 任何涉及外部 API 的项目，必须有真实调用测试。mock 测试保下限，灰度测试探上限。

#### 原则 3：状态机对称性

每个 `set` 都要有对应的 `clear`，每个 `start` 都要有对应的 `stop`，每个 `acquire` 都要有对应的 `release`。

`_deny_all` bug 的本质是违反了对称性原则——在异常路径设置了 `_deny_all = True`，但在正常路径忘记 `_deny_all = False`。

**检查方法：** grep 所有 `self._xxx = True`，反向检查每个 `True` 赋值是否都有对应的 `False` 清除。

#### 原则 4：finally 里做清理

任何 `start/begin/open` 之后，必须用 try/finally 包裹清理逻辑。不是在"happy path"末尾清理，而是在 finally 里清理。因为：

- 测试断言失败 → finally 执行
- 中间抛异常 → finally 执行
- 正常结束 → finally 执行

`test_edge_cases.py` 里 watcher 泄漏就是违反了这个原则。

#### 原则 5：Timeout 是 CI 的生命线

所有 `thread.join()`、`subprocess.wait()`、`socket.connect()` 必须有 timeout。没有 timeout 的等待 = CI 挂了没人知道为什么。

### 14.5 灰度测试文件

- `tests/workflow_test.py` — Hermes 直连 GitHub API 的集成测试脚本
- CC Opus 命令：`ANTHROPIC_MODEL="claude-opus-4-20250514" claude -p --dangerously-skip-permissions "..."`

---

## 15. 面试话术

### 项目介绍（30 秒版）

> 我做了一个 GitHub MCP Server，用 Python 写的，已经发布到 PyPI。它在 AI Agent 和 GitHub API 之间加了一层安全中间件：策略引擎控制 Agent 能访问哪些仓库、不能往哪些分支提 PR；审计日志记录每一步写操作，支持敏感信息脱敏。12 个 MCP 工具覆盖了读文件 → 写代码 → 批量提交 → 开 PR → Code Review → 合并的完整工作流。106 个单元测试全部通过，CI 覆盖 Python 3.10-3.12。

### 技术亮点

| 亮点 | 面试官角度 | 技术细节 |
|------|-----------|---------|
| 策略引擎 | "你知道安全很重要" | deny-by-default、通配符匹配、热重载、线程安全 |
| 审计日志 | "你懂企业级需求" | JSONL 结构化、脱敏、目录白名单防护 |
| 批量提交 | "你理解 Git 内部原理" | 自己实现了 Git Data API 6 步流程 |
| 代码审查 | "你有工程品味" | ruff + regex 双层架构、diff 大小 OOM 防护 |
| 测试体系 | "你写可维护代码" | 106 tests、FakeHttpxClient、分层测试 |
| MCP 协议 | "你懂 AI 基础设施" | JSON-RPC 2.0、FastMCP 框架、双传输模式 |

### 常见追问

**Q: 为什么用 Python 而不是 Go？**

> 选型时期考虑了三点：(1) MCP 生态中 Python 的 FastMCP 框架最成熟，开发效率远高于 Go；(2) 目标用户（AI Agent 开发者）更熟悉 Python，方便他们扩展自定义工具；(3) 策略引擎和审计日志的逻辑复杂度高，Python 的动态特性更适合快速迭代。性能方面，这个场景的瓶颈在 GitHub API 调用（网络 I/O），不在语言选择。

**Q: 和官方 GitHub MCP Server 有什么区别？**

> 官方做的是"把 GitHub 全部能力暴露给 AI"，我们做的是"给 AI 受控的 GitHub 能力"。两个关键差别：(1) 策略引擎 — 仓库白名单 + 分支保护，防止 Agent 误操作；(2) 审计日志 — 每一步写操作可追溯。这两个能力官方没有，因为 GitHub 自己做的话等于承认"AI Agent 不可信"，这在产品层面是不可能的。

**Q: 如果让你重新设计，会改什么？**

> (1) 加 GitHub App 认证 — PAT 方式颗粒度太粗，GitHub App 可以做到 per-repo 授权；(2) 策略引擎用 OPA（Open Policy Agent）而不是自定义 JSON — Rego 策略语言表达能力更强，且是业界标准；(3) 用 Pydantic 做输入参数验证 — 目前依赖 FastMCP 的默认校验，不够严格。

---

## 附录：术语表

| 术语 | 全称 | 说明 |
|------|------|------|
| MCP | Model Context Protocol | AI Agent 调用外部工具的开放协议 |
| PAT | Personal Access Token | GitHub 个人访问令牌 |
| JSON-RPC | JSON Remote Procedure Call | MCP 的通信协议 |
| JSONL | JSON Lines | 每行一个 JSON 对象的日志格式 |
| OPA | Open Policy Agent | CNCF 的策略即代码引擎 |
| OOM | Out of Memory | 内存溢出 |
| GHE | GitHub Enterprise | GitHub 企业版 |
| stdio | Standard Input/Output | 标准输入输出（MCP 默认传输方式） |
| dry run | 干运行/预览模式 | 只模拟操作不实际执行 |
| ruff | — | Python 代码检查工具（Rust 实现，比 flake8 快 10-100x） |

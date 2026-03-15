# Codex CLI vs Claude Code 全面对比

| 条目 | 内容 |
|------|------|
| **主题** | OpenAI Codex CLI 与 Anthropic Claude Code 的系统性架构与功能对比 |
| **Codex 版本** | v0.94.0+（Rust 原生实现） |
| **Claude Code 版本** | v2.x+ |

---

## 1 背景

Codex CLI 和 Claude Code 是当前最具代表性的两个 AI 编程代理 CLI 工具。Codex CLI 由 OpenAI 开发，基于 GPT-5 系列模型；Claude Code 由 Anthropic 开发，基于 Claude 4 系列模型。两者都旨在让开发者通过终端与 AI 进行交互式编程协作，但在架构设计、安全模型、工具系统等方面做出了截然不同的技术选择。

本文从十个维度对两个工具进行系统性对比，每个维度不仅比较表面差异，更分析背后的设计动机和工程权衡。目标是帮助读者建立对两种架构理念的全面理解——不是评判孰优孰劣，而是理解为什么它们做出了不同的选择。

---

## 2 架构对比

两个工具在底层实现上的差异是所有其他差异的根源。

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **实现语言** | Rust（2024 edition） | TypeScript / Node.js |
| **代码规模** | 70+ Rust crate（workspace） | 单一 npm 包 |
| **异步运行时** | tokio（full features） | Node.js 事件循环 |
| **TUI 框架** | ratatui + crossterm（Rust 原生） | Ink（React for CLI） |
| **数据库** | SQLite（sqlx 编译期查询检查） | 纯文件系统 |
| **序列化** | serde + ts-rs（自动 TS 类型生成） | 原生 JSON |
| **二进制分发** | 编译后的原生二进制（LTO + strip） | Node.js + npm 包 |
| **通信模型** | SQ/EQ（Submission Queue / Event Queue） | 直接函数调用 |
| **开源许可** | Apache-2.0 | MIT |

Codex 选择 Rust 带来了显著的性能优势——原生二进制启动更快、内存占用更低、沙箱实现更彻底。但代价是开发迭代速度较慢、社区贡献门槛更高。Claude Code 选择 TypeScript 使其能快速迭代、利用 npm 生态，但在系统级功能（如沙箱）上受到语言能力的限制。

Codex 的 SQ/EQ 架构使得同一个核心引擎可以服务多种前端（TUI、MCP Server、App Server、Exec 模式），这是微服务式的设计思维。Claude Code 的直接函数调用模式更简单直接，适合单入口的 CLI 场景。

### 2.1 Agentic Loop 对比图

两个工具的 agentic loop 虽然都遵循"接收输入 -> 模型推理 -> 工具执行 -> 反馈结果"的基本模式，但在内部流转机制上存在根本差异。Codex 采用 SQ/EQ 异步队列解耦前端和核心引擎，Claude Code 采用同步函数调用链。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Codex CLI: SQ/EQ Agentic Loop                        │
│                                                                         │
│  ┌─────────┐    Submission     ┌──────────────┐    Responses API       │
│  │   TUI   │──── Queue ──────>│  Core Engine  │<──── SSE Stream ──────│
│  │ ratatui │    (Op::UserTurn) │  (codex-core) │     (ResponseItem)    │
│  └────┬────┘                   └──────┬───────┘                        │
│       ^                               │                                │
│       │         Event Queue           v                                │
│       │    ┌──────────────────────────────────┐                        │
│       │    │  EventMsg variants:               │                       │
│       │    │   TurnStarted -> ExecCommandBegin │                       │
│       └────│   -> ExecCommandEnd -> AgentMsg   │                       │
│            │   -> TurnComplete                 │                       │
│            └──────────────────────────────────┘                        │
│                                                                         │
│  ┌─ 多前端复用 ─────────────────────────────────┐                      │
│  │  TUI  |  MCP Server  |  App Server  |  Exec  │                     │
│  └───────────────────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                  Claude Code: Sync Agentic Loop                         │
│                                                                         │
│  ┌─────────┐    direct call    ┌──────────────┐    Messages API        │
│  │   Ink   │──────────────────>│  Agent Loop  │<──── SSE Stream ──────│
│  │  React  │                   │  (TypeScript) │     (content block)   │
│  └────┬────┘                   └──────┬───────┘                        │
│       ^                               │                                │
│       │       sync return             v                                │
│       │    ┌──────────────────────────────────┐                        │
│       │    │  content[] iteration:             │                       │
│       └────│   thinking -> tool_use -> execute │                       │
│            │   -> tool_result -> text          │                       │
│            └──────────────────────────────────┘                        │
│                                                                         │
│  ┌─ 单一入口 ───────────┐                                              │
│  │  CLI (Ink terminal)  │                                              │
│  └──────────────────────┘                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

> 📌 **重点**：Codex 的 SQ/EQ 架构解耦了前端和核心引擎，`Submission` 通过 `Op` 枚举提交操作，`Event` 通过 `EventMsg` 枚举分发事件。每个 `Submission` 都有唯一 `id` 用于关联对应的 `Event`。这使得同一个 `codex-core` 可以同时服务 TUI、MCP Server、App Server 和 headless Exec 四种模式。Claude Code 的同步调用链更直接，`content[]` 数组中的 `thinking` -> `tool_use` -> `tool_result` -> `text` 顺序即为执行流程。

---

## 3 会话存储格式

### 3.1 文件组织

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **存储根目录** | `~/.codex/` | `~/.claude/` |
| **目录自定义** | `CODEX_HOME` 环境变量 | 不可自定义 |
| **会话目录** | `sessions/YYYY/MM/DD/` | `projects/{encoded-path}/` |
| **文件命名** | `rollout-{timestamp}-{session-id}.jsonl` | `{session-id}.jsonl` |
| **子代理** | 独立 rollout 文件（`SubAgent(ThreadSpawn)` 来源） | `{session-id}/subagents/agent-*.jsonl` |
| **归档** | `archived_sessions/` 独立目录 | 无归档机制 |

Codex 按日期组织会话，便于按时间范围查找和清理；Claude Code 按项目路径组织，便于查找特定项目的所有会话。两种方式都有其合理性，取决于主要的查询模式。

#### 目录结构并排对比

```
~/.codex/                                  ~/.claude/
├── config.toml                            ├── settings.json
├── history.jsonl                          ├── history.jsonl
├── memories/                              ├── CLAUDE.md
│   ├── raw_memories.md                    │
│   ├── MEMORY.md                          ├── projects/
│   ├── memory_summary.md                  │   ├── -Users-me-myapp/
│   └── rollout_summaries/                 │   │   ├── 85f42726-...-f4c9.jsonl
│       └── {thread-id}.md                 │   │   ├── 2b6ed192-...-a066.jsonl
│                                          │   │   └── memory/
├── sessions/                              │   │       └── MEMORY.md
│   └── 2026/03/15/                        │   └── -Users-me-other/
│       ├── rollout-2026-03-15T10-        │       └── ...
│       │   30-00-{uuid}.jsonl             │
│       └── rollout-2026-03-15T14-        ├── todos/
│           20-00-{uuid}.jsonl             │   └── {session-id}-agent-*.json
│                                          │
├── archived_sessions/                     ├── file-history/
│   └── 2026/03/14/                        │   └── {session-id}/
│       └── rollout-....jsonl              │       └── {file-path}.history
│                                          │
├── skills/                                ├── plugins/
│   ├── .system/                           │   ├── installed_plugins.json
│   │   ├── openai-docs/SKILL.md           │   └── cache/
│   │   └── skill-creator/SKILL.md         │
│   └── my-custom-skill/SKILL.md           └── statsig/
│                                              └── {feature-flags}
└── state.db  (SQLite)
```

> 💡 **最佳实践**：Codex 的按日期组织对于日志轮转和批量清理很友好（`find ~/.codex/sessions -mtime +30 -delete`），而 Claude Code 的按项目组织对于"查看某项目历史"更直观。两者都使用 `history.jsonl` 作为全局索引，避免了遍历所有 JSONL 文件的开销。

### 3.2 消息结构

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **顶层包装** | `{timestamp, type, payload}` | `{type, uuid, sessionId, message}` |
| **事件类型** | `RolloutItem` 枚举（5 变体） | 无统一枚举 |
| **角色系统** | `developer` / `user` / `assistant` | `user` / `assistant` |
| **消息链接** | `turn_id` 关联同一轮次 | `parentUuid` 链接父子消息 |
| **UUID 格式** | UUID v7（含时间戳） | UUID v4（随机） |
| **时间戳格式** | ISO 8601 字符串 | 毫秒级 Unix epoch |

#### 完整 Session JSONL 首行对比

Codex 的 rollout 文件首行总是 `session_meta` 类型，记录会话级元数据；Claude Code 的 JSONL 文件首行通常是第一条 `user` 消息。

**Codex rollout 首行（`session_meta`）：**

```json
{
  "timestamp": "2026-03-15T10:30:00.123456Z",
  "type": "session_meta",
  "payload": {
    "id": "01965a3b-7c8e-7f00-a1b2-c3d4e5f60718",
    "forked_from_id": null,
    "timestamp": "2026-03-15T10:30:00.123456Z",
    "cwd": "/Users/dev/my-project",
    "originator": "codex-rs/0.94.0",
    "cli_version": "0.94.0",
    "source": "Cli",
    "agent_nickname": null,
    "agent_role": null,
    "model_provider": "openai",
    "base_instructions": "developer",
    "memory_mode": "full",
    "git": {
      "branch": "main",
      "commit": "a1b2c3d",
      "remote_url": "https://github.com/user/repo.git"
    }
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | String | ISO 8601 格式，外层为 rollout line 时间戳 |
| `type` | String | `RolloutItem` 枚举 tag：`session_meta` / `response_item` / `compacted` / `turn_context` / `event_msg` |
| `payload.id` | String | UUID v7 格式的 thread ID（含时间戳信息） |
| `payload.source` | String | 会话来源：`Cli` / `VSCode` / `SubAgent(ThreadSpawn)` |
| `payload.base_instructions` | String | 基础指令集类型：`developer` / `custom` |
| `payload.git` | Object | Git 仓库信息快照，可为 `null` |

**Claude Code JSONL 首行（`user` 消息）：**

```json
{
  "type": "user",
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "sessionId": "2b6ed192-046f-495a-b8ed-5d500c01a066",
  "parentUuid": null,
  "timestamp": 1742025600000,
  "isSidechain": false,
  "cwd": "/Users/dev/my-project",
  "gitBranch": "main",
  "message": {
    "role": "user",
    "content": "Help me refactor the auth module"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | String | 消息类型：`user` / `assistant` / `progress` / `file-history-snapshot` |
| `uuid` | String | UUID v4 格式，每条消息唯一 |
| `sessionId` | String | 所属会话 ID，与文件名对应 |
| `parentUuid` | String | 父消息 UUID，构成链式对话图（首条为 `null`） |
| `timestamp` | Number | 毫秒级 Unix epoch |
| `isSidechain` | Boolean | 是否为侧链分支消息 |

> ⚠️ **注意**：Codex 使用 UUID v7（时间序列），天然有序，可直接排序；Claude Code 使用 UUID v4（随机），必须依赖 `timestamp` 字段或 `parentUuid` 链来恢复消息顺序。解析工具需要据此选择不同的排序策略。

### 3.3 关键数据类型对比

**工具调用**：

```json
// Codex: OpenAI function_call format
{
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "exec_command",
    "arguments": "{\"cmd\":\"pwd\"}",
    "call_id": "call_C9l32..."
  }
}

// Claude Code: Anthropic tool_use format (embedded in message.content)
{
  "type": "assistant",
  "message": {
    "content": [{
      "type": "tool_use",
      "id": "toolu_01...",
      "name": "Bash",
      "input": {"command": "pwd"}
    }]
  }
}
```

**推理/思考**：

```json
// Codex: Encrypted reasoning
{
  "type": "response_item",
  "payload": {
    "type": "reasoning",
    "summary": [],
    "encrypted_content": "gAAAAABp..."
  }
}

// Claude Code: Plaintext thinking
{
  "type": "assistant",
  "message": {
    "content": [{
      "type": "thinking",
      "thinking": "Let me analyze this code..."
    }]
  }
}
```

> 📌 **重点**：Codex 的推理内容是加密的（`encrypted_content`），用户和第三方工具无法读取模型的思维过程。Claude Code 的 `thinking` 块以明文存储，对分析和调试更友好，但隐私保护程度较低。

#### 工具调用结果对比

工具执行完成后，结果的回传格式也存在显著差异。Codex 将结果作为独立的 `response_item` 记录，Claude Code 将结果嵌入 `user` 类型消息的 `tool_result` content block 中。

```json
// Codex: function_call_output（独立 response_item）
{
  "timestamp": "2026-03-15T10:30:05.456Z",
  "type": "response_item",
  "payload": {
    "type": "function_call_output",
    "call_id": "call_C9l32xK7pQn4aRtM",
    "output": "/Users/dev/my-project"
  }
}

// Claude Code: tool_result（嵌入 user 消息 content 数组）
{
  "type": "user",
  "uuid": "660e8400-e29b-41d4-a716-446655440001",
  "sessionId": "2b6ed192-046f-495a-b8ed-5d500c01a066",
  "parentUuid": "91ff20aa-3255-4fb4-b383-605ddd2a37e1",
  "timestamp": 1742025605000,
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_01DAWALsTf6siYK1fiZfh8AK",
        "content": [
          {
            "type": "text",
            "text": "/Users/dev/my-project"
          }
        ],
        "is_error": false
      }
    ]
  }
}
```

| 对比维度 | Codex | Claude Code |
|---------|-------|-------------|
| **结果位置** | 顶层 `response_item` | 嵌套在 `user.message.content[]` |
| **关联方式** | `call_id` 匹配 `function_call.call_id` | `tool_use_id` 匹配 `tool_use.id` |
| **结果格式** | 纯字符串 `output` | `content[]` 数组，支持多模态 |
| **错误标记** | 无显式字段（依赖 output 内容） | `is_error: true/false` |

#### Codex `RolloutItem` 枚举完整变体

Codex 的 rollout 文件中每一行都是一个 `RolloutLine`，内部的 `RolloutItem` 枚举有 5 个变体，覆盖了会话的完整生命周期：

```
RolloutItem 枚举
├── SessionMeta      ─── 会话元数据（首行，包含 git/cwd/model 等）
├── ResponseItem     ─── OpenAI Responses API 返回项
│   ├── Message      ─── 文本消息（role: assistant/developer/user）
│   ├── FunctionCall ─── 工具调用请求
│   └── Reasoning    ─── 推理内容（加密）
├── Compacted        ─── 上下文压缩后的摘要替换
├── TurnContext      ─── 每轮附加上下文（cwd、sandbox policy、model 等）
└── EventMsg         ─── 引擎事件（TurnStarted、TokenCount、ExecCommandBegin 等）
```

---

## 4 工具系统对比

### 4.1 工具调用格式

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **API 格式** | OpenAI Responses API `function_call` | Anthropic Messages API `tool_use` |
| **参数格式** | JSON 字符串（需二次解析） | 原生 JSON 对象 |
| **调用 ID 前缀** | `call_` | `toolu_` |
| **结果格式** | `function_call_output` | `tool_result` |

#### 工具调用格式并排代码对比

以"搜索文件"这一常见操作为例，展示两种工具从调用到结果的完整数据流：

**场景：搜索代码中的 `TODO` 注释**

```json
// ═══════════════════════════════════════════════════════
// Codex CLI: grep_files 工具调用
// ═══════════════════════════════════════════════════════

// 1. 模型发起调用（response_item / function_call）
{
  "timestamp": "2026-03-15T10:31:00Z",
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "grep_files",
    "call_id": "call_xK7pQn4aRtM9bC2d",
    "arguments": "{\"pattern\":\"TODO\",\"include\":\"*.py\",\"max_results\":10}"
  }
}
// 注意：arguments 是 JSON 字符串，需要二次 JSON.parse()

// 2. 执行结果（response_item / function_call_output）
{
  "timestamp": "2026-03-15T10:31:02Z",
  "type": "response_item",
  "payload": {
    "type": "function_call_output",
    "call_id": "call_xK7pQn4aRtM9bC2d",
    "output": "src/auth.py:42: # TODO: implement token refresh\nsrc/db.py:108: # TODO: add connection pooling"
  }
}
```

```json
// ═══════════════════════════════════════════════════════
// Claude Code: Grep 工具调用
// ═══════════════════════════════════════════════════════

// 1. 模型发起调用（assistant 消息 / tool_use content block）
{
  "type": "assistant",
  "uuid": "a1b2c3d4-...",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "id": "toolu_01XyZ9AbCdEfGhIjKl",
        "name": "Grep",
        "input": {
          "pattern": "TODO",
          "glob": "*.py",
          "head_limit": 10
        }
      }
    ]
  }
}
// 注意：input 是原生 JSON 对象，无需二次解析

// 2. 执行结果（user 消息 / tool_result content block）
{
  "type": "user",
  "uuid": "e5f6a7b8-...",
  "parentUuid": "a1b2c3d4-...",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_01XyZ9AbCdEfGhIjKl",
        "content": [{"type": "text", "text": "src/auth.py:42: # TODO: implement token refresh\nsrc/db.py:108: # TODO: add connection pooling"}],
        "is_error": false
      }
    ]
  }
}
```

> 💡 **最佳实践**：解析 Codex rollout 时，需要对 `arguments` 字段执行 `JSON.parse(payload.arguments)` 二次解析。Claude Code 的 `input` 已经是结构化 JSON 对象，可直接访问字段。编写跨工具分析器时，应在适配层统一处理这一差异。

### 4.2 工具能力对比

| 功能 | Codex CLI 工具 | Claude Code 工具 |
|------|---------------|------------------|
| **命令执行** | `shell` / `exec_command` | `Bash` |
| **文件读取** | `read_file`（offset/limit/mode） | `Read`（offset/limit） |
| **文件编辑** | `apply_patch`（Tree-sitter patch） | `Edit`（精确字符串替换） |
| **文件创建** | 通过 `apply_patch` | `Write` |
| **文件搜索** | `grep_files` | `Grep` |
| **目录列表** | `list_dir` | `Glob` |
| **代码搜索** | `file-search`（nucleo BM25） | 无独立引擎 |
| **图片查看** | `view_image` | `Read`（多模态） |
| **JS REPL** | `js_repl`（持久 Node.js 内核） | 无 |
| **计划管理** | `plan` / `update_plan` | `EnterPlanMode` / `ExitPlanMode` |
| **多代理** | `spawn_agent` / `wait_agent` / `close_agent` / `send_input` / `resume_agent` | `Agent` |
| **任务管理** | 无 | `TaskCreate` / `TaskUpdate` / `TaskList` |
| **用户交互** | `request_user_input` | `AskUserQuestion` |
| **权限请求** | `request_permissions` | 无 |
| **工具发现** | `_tool_search` / `_tool_suggest` | 无 |
| **MCP** | `McpHandler`（客户端）+ `mcp-server`（服务端） | 内置 MCP 支持 |
| **动态工具** | `DynamicToolSpec`（数据库持久化） | 无 |
| **批量任务** | `spawn_agents_on_csv` | 无 |
| **Notebook** | 无 | `NotebookEdit` |
| **Web 搜索** | 内置 Web 搜索工具 | `WebSearch` / `WebFetch` |

**设计理念差异**：Codex 的工具命名更偏向底层操作语义（`exec_command`、`apply_patch`、`grep_files`），Claude Code 的工具命名更偏向用户操作语义（`Bash`、`Edit`、`Read`、`Glob`）。Codex 提供了 `_tool_search` 等元工具让模型自主发现可用工具，Claude Code 使用固定的工具集。

#### 文件编辑方式深度对比

文件编辑是两个工具差异最大的功能点之一。Codex 使用 `apply_patch` 基于 unified diff 语义（配合 Tree-sitter 解析），Claude Code 使用 `Edit` 基于精确字符串匹配替换。

```json
// ═══════════════════════════════════════════════════════
// Codex: apply_patch（unified diff 语义）
// ═══════════════════════════════════════════════════════
{
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "apply_patch",
    "call_id": "call_patch_001",
    "arguments": "{\"patch\":\"--- a/src/auth.py\\n+++ b/src/auth.py\\n@@ -42,3 +42,8 @@\\n     def validate_token(self, token: str) -> bool:\\n-        # TODO: implement token refresh\\n-        return True\\n+        if self.is_expired(token):\\n+            token = self.refresh_token(token)\\n+        return self.verify_signature(token)\"}"
  }
}
```

```json
// ═══════════════════════════════════════════════════════
// Claude Code: Edit（精确字符串替换）
// ═══════════════════════════════════════════════════════
{
  "type": "assistant",
  "message": {
    "content": [{
      "type": "tool_use",
      "id": "toolu_edit_001",
      "name": "Edit",
      "input": {
        "file_path": "/Users/dev/my-project/src/auth.py",
        "old_string": "    def validate_token(self, token: str) -> bool:\n        # TODO: implement token refresh\n        return True",
        "new_string": "    def validate_token(self, token: str) -> bool:\n        if self.is_expired(token):\n            token = self.refresh_token(token)\n        return self.verify_signature(token)"
      }
    }]
  }
}
```

| 对比维度 | Codex `apply_patch` | Claude Code `Edit` |
|---------|--------------------|--------------------|
| **定位方式** | 行号范围（`@@ -42,3 +42,8 @@`） | 精确字符串匹配（`old_string`） |
| **失败模式** | 行号偏移时 fuzzy match | `old_string` 不唯一时报错 |
| **批量修改** | 单个 patch 可包含多个 hunk | 每次只能替换一处（除非 `replace_all`） |
| **新文件** | diff 中 `/dev/null` -> 新路径 | 使用独立的 `Write` 工具 |

---

## 5 沙箱与安全对比

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **沙箱层级** | 操作系统原生 | 应用层 |
| **macOS** | Seatbelt（`.sbpl` sandbox profiles） | 无原生沙箱 |
| **Linux** | Bubblewrap + Landlock LSM + seccomp | 无原生沙箱 |
| **Windows** | Restricted Token + ACL + Firewall | 无原生沙箱 |
| **沙箱策略** | `SandboxPolicy` 枚举（3 模式 + 扩展） | 无显式沙箱策略 |
| **网络控制** | `network-proxy` crate（rama 框架） | 无独立网络控制 |
| **命令审批** | `AskForApproval`（5 种模式） | 权限模式（allow/deny per tool） |
| **细粒度审批** | `GranularApprovalConfig`（5 个维度） | 无 |
| **规则引擎** | Starlark ExecPolicy | 无 |
| **AI 审批** | Guardian 子代理（AI 风险评估） | 无 |
| **权限提升** | `SandboxPermissions`（3 级） | 无 |
| **企业管理** | MDM 托管策略 | 无 |
| **特性标志** | `Feature` 枚举 + `Stage` 生命周期 | 无 |

> ⚠️ **注意**：这是两个工具之间最显著的架构差异。Codex 在操作系统层面实施隔离（内核级 LSM、系统调用过滤），而 Claude Code 主要依赖应用层面的权限检查和用户确认。Codex 的方式更安全但更复杂，Claude Code 的方式更简单但防护深度不足。在企业部署场景中，Codex 的 MDM 策略和 Guardian AI 审批具有明显优势。

#### 沙箱策略枚举对比

Codex 的 `SandboxPolicy` 是一个结构化枚举，支持细粒度的读写和网络控制；Claude Code 没有对应的沙箱枚举，依赖用户在 `settings.json` 中配置 `allowedTools` / `blockedTools`。

```
Codex SandboxPolicy 枚举
├── DangerFullAccess      ─── 无任何限制（危险模式）
├── ReadOnly              ─── 只读访问
│   ├── access            ─── ReadOnlyAccess（全盘读 / 受限路径读）
│   └── network           ─── bool（是否允许出站网络）
└── WorkspaceWrite        ─── 工作区写入
    ├── writable_roots    ─── Vec<PathBuf>（可写路径白名单）
    └── network           ─── bool（是否允许出站网络）

Codex AskForApproval 枚举
├── UnlessTrusted         ─── 仅安全只读命令自动批准
├── OnFailure             ─── 沙箱内自动执行，失败时升级（已弃用）
├── OnRequest             ─── 沙箱内自动执行，升级请求时询问
├── Never                 ─── 全自动（headless 模式）
└── Always                ─── 每个命令都询问

Claude Code 权限模型
├── settings.json         ─── allowedTools / blockedTools 列表
├── 运行时提示            ─── 首次使用工具时询问用户
└── 会话级缓存            ─── 本次会话已批准的操作
```

---

## 6 配置系统对比

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **格式** | TOML | JSON |
| **主配置文件** | `~/.codex/config.toml` | `~/.claude/settings.json` |
| **层级数** | 7 层 | 3 层 |
| **合并算法** | 递归深度合并 | 简单覆盖 |
| **约束系统** | `Constrained<T>` | 无 |
| **项目信任** | 显式 `trust_level` | 无 |
| **Profile** | `[profiles.<name>]` | 无 |
| **企业策略** | MDM 托管配置 | 无 |
| **人格** | `Personality` 枚举 | 无 |
| **协作模式** | `CollaborationMode` | Plan Mode |
| **环境变量控制** | `[shell_environment_policy]` | 无 |
| **遥测** | `[otel]` OpenTelemetry | 内置遥测 |

Codex 的配置系统更适合企业环境——7 层配置栈覆盖了从系统管理员到临时覆盖的所有场景，`Constrained<T>` 确保关键策略不被绕过。Claude Code 的配置更简洁，适合个人开发者。

#### 配置文件实例并排对比

以"配置模型、MCP 服务器和审批策略"这一典型场景为例：

**Codex `~/.codex/config.toml`：**

```toml
# ─── 模型配置
model = "gpt-5.1"
model_provider = "openai"
model_reasoning_effort = "medium"
model_context_window = 200000

# ─── 审批与沙箱
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
writable_roots = ["/Users/dev/my-project"]

# ─── Shell 环境策略
[shell_environment_policy]
inherit = ["PATH", "HOME", "LANG"]
set = { EDITOR = "vim", NODE_ENV = "development" }
block = ["AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"]

# ─── MCP 服务器
[mcp_servers.github]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
env = { GITHUB_PERSONAL_ACCESS_TOKEN = "ghp_xxx" }

[mcp_servers.postgres]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"]

# ─── Profile 切换
[profiles.safe]
model = "gpt-5.1-codex-mini"
approval_policy = "unless-trusted"

[profiles.fast]
model = "gpt-5.1-codex-mini"
approval_policy = "never"
service_tier = "fast"

# ─── 人格
personality = "concise"

# ─── OpenTelemetry
[otel]
endpoint = "http://localhost:4317"
service_name = "codex-dev"
```

**Claude Code `~/.claude/settings.json`：**

```json
{
  "permissions": {
    "allowedTools": [
      "Bash(npm run *)",
      "Bash(git *)",
      "Read",
      "Glob",
      "Grep"
    ],
    "blockedTools": [
      "Bash(rm -rf *)"
    ]
  },
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"
      }
    },
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres",
               "postgresql://localhost/mydb"]
    }
  }
}
```

| 对比维度 | Codex config.toml | Claude Code settings.json |
|---------|-------------------|---------------------------|
| **模型选择** | `model = "gpt-5.1"` | 环境变量 `ANTHROPIC_MODEL` |
| **审批粒度** | 5 种 `approval_policy` + `sandbox_mode` | `allowedTools` / `blockedTools` 正则 |
| **Profile** | `[profiles.safe]` 命名配置集 | 无（需手动编辑） |
| **环境变量** | `[shell_environment_policy]` 白名单/黑名单/固定值 | 无独立控制 |
| **MCP 配置** | TOML `[mcp_servers.name]` | JSON `mcpServers.name` |
| **可读性** | TOML 注释友好，表格嵌套清晰 | JSON 不支持注释 |

#### Codex 7 层配置栈

Codex 的配置加载器按照以下优先级从低到高合并 7 层配置，每一层都可以覆盖前一层的值，但 `Constrained<T>` 约束限制了某些关键字段不能被低权限层修改：

```
优先级（低 → 高）
┌───────────────────────────────────────────────────────┐
│  Layer 7: CLI 参数 / 环境变量覆盖                       │  最高优先
│  Layer 6: 项目级 .codex/config.toml                    │
│  Layer 5: 工作区级 config.toml                         │
│  Layer 4: 用户级 ~/.codex/config.toml                  │
│  Layer 3: MDM 托管配置（macOS Managed Preferences）     │
│  Layer 2: 系统级 requirements.toml（管理员策略）         │
│  Layer 1: 编译时内置默认值                              │  最低优先
└───────────────────────────────────────────────────────┘

Claude Code 3 层配置栈
┌───────────────────────────────────────────────────────┐
│  Layer 3: 项目级 .claude/settings.json                 │  最高优先
│  Layer 2: 用户级 ~/.claude/settings.json               │
│  Layer 1: 内置默认值                                   │  最低优先
└───────────────────────────────────────────────────────┘
```

> 📌 **重点**：Codex 的 `Constrained<T>` 类型系统是企业安全的关键——管理员可以在 Layer 2（requirements.toml）中设置 `allowed_approval_policies = ["unless-trusted"]`，这样即使用户在 Layer 4 设置 `approval_policy = "never"`，约束系统也会将其限制在允许的范围内。Claude Code 没有类似的约束机制，每一层的配置直接覆盖前一层。

---

## 7 多代理对比

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **子代理创建** | `spawn_agent`（参数：message、agent_type、model、fork_context） | `Agent`（参数：prompt、subagent_type） |
| **子代理通信** | `send_input`（同步消息 + interrupt 中断） | 无运行时通信 |
| **等待机制** | `wait_agent`（timeout: 10s-1h） | 同步返回结果 |
| **关闭/恢复** | `close_agent` + `resume_agent` | 无（自动结束） |
| **子代理存储** | 独立 rollout 文件（`SubAgent` 来源） | `subagents/agent-*.jsonl` |
| **层级关系** | `parent_thread_id` + `depth` 追踪 | 文件系统嵌套 |
| **批量任务** | `spawn_agents_on_csv`（CSV 驱动） | 无 |
| **上下文分叉** | `fork_context` 参数 | 独立上下文 |
| **模型覆盖** | 每个子代理可独立设置模型 | 可设置模型 |
| **角色系统** | `agent_type` / `agent_role` | `subagent_type` |
| **worktree 隔离** | 无 | `isolation: "worktree"` |

Codex 的多代理系统更像一个完整的分布式任务系统——支持异步通信、中断恢复、超时控制和批量任务。Claude Code 的 `Agent` 工具更简单，采用同步的"启动-等待-返回"模式。Codex 的设计适合长时间运行的复杂任务编排，Claude Code 的设计适合简单的并行子任务。

#### 多代理执行流程对比

```
Codex CLI 多代理流程（异步 + 消息传递）
══════════════════════════════════════════════════════

Main Thread                    Sub-Agent A              Sub-Agent B
    │                              │                        │
    ├─ spawn_agent(msg, ──────────>│                        │
    │    agent_role="reviewer")    │                        │
    │                              │                        │
    ├─ spawn_agent(msg, ──────────────────────────────────>│
    │    agent_role="coder")       │                        │
    │                              │                        │
    │   ... 继续处理其他任务 ...     ├─ 独立运行              ├─ 独立运行
    │                              │  （独立 rollout 文件）   │  （独立 rollout 文件）
    │                              │                        │
    ├─ send_input(A, "更新进度") ──>│                        │
    │                              │                        │
    ├─ wait_agent(B, timeout=300) ─────────────────────────>│
    │   ... 阻塞等待 ...            │                       ├─ 返回结果
    │<──────────────────────────────────────────────────────┤
    │                              │                        │
    ├─ close_agent(A) ────────────>│ 终止                   │
    │                              X                        │
    │                                                       │
    ├─ resume_agent(B, "继续优化") ────────────────────────>│
    │                                                      ├─ 恢复执行
    └                                                       │


Claude Code 多代理流程（同步 fire-and-wait）
══════════════════════════════════════════════════════

Main Thread                    Sub-Agent
    │                              │
    ├─ Agent(prompt="review ───── >│
    │    this code",               │
    │    subagent_type="research") │
    │                              │
    │   ... 同步阻塞 ...            ├─ 执行完成
    │                              │  （subagents/agent-*.jsonl）
    │<──── 返回完整结果 ────────────┤
    │                              X  自动结束
    │
    ├─ Agent(prompt="fix ─────── >│  （新的子代理）
    │    the bug found")           │
    │                              │
    │   ... 同步阻塞 ...            ├─ 执行完成
    │<──── 返回完整结果 ────────────┤
    │                              X  自动结束
    └
```

> ⚠️ **注意**：Codex 的 `spawn_agent` 支持 `fork_context` 参数，子代理可以继承父代理的对话历史。每个子代理都会生成独立的 rollout 文件，`SessionMeta` 中的 `source` 字段标记为 `SubAgent(ThreadSpawn)`，`agent_role` 记录角色信息。Claude Code 的子代理上下文完全独立，通过 `subagents/` 目录组织文件。

---

## 8 记忆与指令对比

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **记忆机制** | 两阶段 ML 流水线（全自动） | MEMORY.md 文件（手动 + 半自动） |
| **记忆模型** | Phase 1: `gpt-5.1-codex-mini`，Phase 2: `gpt-5.3-codex` | 无独立记忆模型 |
| **记忆触发** | 启动时自动异步执行 | 用户请求或 `/memory` 命令 |
| **记忆存储** | `~/.codex/memories/` + SQLite | `~/.claude/projects/*/memory/` |
| **记忆成本** | 每次启动消耗额外 API 调用 | 无额外成本 |
| **指令文件** | `AGENTS.md` / `AGENTS.override.md` | `CLAUDE.md` |
| **指令发现** | git root -> cwd 层级 | 类似层级发现 |
| **Override 机制** | `.override.md` 在每级优先 | 无 |
| **大小限制** | 32 KiB（可配） | 无固定限制 |
| **备用文件名** | `project_doc_fallback_filenames` | 无 |

#### Codex 两阶段记忆流水线

Codex 的记忆系统在每次启动时自动运行，是一个完全自动化的 ML 流水线：

```
Codex 记忆流水线
══════════════════════════════════════════════════════════════════

Phase 1: Extraction（并发，每个 rollout 独立处理）
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌─────────┐    扫描最近会话     ┌──────────────────────┐     │
│  │ SQLite  │───────────────────>│ 筛选未处理的 rollout  │     │
│  │ 状态 DB │   (最多 5000 个)    │  文件                 │     │
│  └─────────┘                    └──────┬───────────────┘     │
│                                        │                     │
│                          ┌─────────────┼─────────────┐       │
│                          v             v             v       │
│                    ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│                    │ rollout  │  │ rollout  │  │ rollout  │  │
│                    │    #1    │  │    #2    │  │    #3    │  │
│                    └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│                         v             v             v        │
│                  gpt-5.1-codex-mini（低 reasoning effort）    │
│                    提取 raw memories（每个 rollout 独立）      │
│                         │             │             │        │
│                         v             v             v        │
│                    ┌──────────────────────────────────┐      │
│                    │  rollout_summaries/{thread-id}.md │      │
│                    │  raw_memories.md                  │      │
│                    └──────────────────────────────────┘      │
│  并发上限：8 个任务 | Job Lease：3600s | 重试延迟：3600s        │
└──────────────────────────────────────────────────────────────┘
                              │
                              v
Phase 2: Consolidation（全局单例，加锁执行）
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  ┌───────────────────────┐         ┌──────────────────────┐  │
│  │ raw_memories.md       │────────>│   gpt-5.3-codex      │  │
│  │ (合并所有 stage-1 输出)│         │  (中等 reasoning)     │  │
│  └───────────────────────┘         └──────────┬───────────┘  │
│                                               │              │
│                                               v              │
│                                    ┌────────────────────┐    │
│                                    │   MEMORY.md        │    │
│                                    │   memory_summary.md│    │
│                                    └────────────────────┘    │
│  心跳间隔：90s | Job Lease：3600s                              │
└──────────────────────────────────────────────────────────────┘
```

#### 指令文件实例对比

**Codex `AGENTS.md`（项目根目录）：**

```markdown
# Rust/codex-rs

In the codex-rs folder where the rust code lives:

- Crate names are prefixed with `codex-`. For example, the `core`
  folder's crate is named `codex-core`
- When using format! and you can inline variables into {}, always do that.
- Always collapse if statements per clippy::collapsible_if
- Always inline format! args when possible per clippy::uninlined_format_args
- Use method references over closures when possible
- Avoid bool or ambiguous `Option` parameters that force callers
  to write hard-to-read code such as `foo(false)` or `bar(None)`.
- When possible, make `match` statements exhaustive and avoid wildcard arms.
- When writing tests, prefer comparing the equality of entire objects
  over fields one by one.

Run `just fmt` automatically after you have finished making Rust code changes.
```

**Claude Code `CLAUDE.md`（项目根目录）：**

```markdown
# CLAUDE.md

Write code that is correct, readable, and maintainable.
Prefer clarity over cleverness.

## General Rules

- One function does one thing.
- Functions should be short enough to fit on one screen (~30 lines).
- No magic numbers or strings. Use named constants with ALL_CAPS.
- No dead code. Delete unused imports, variables, functions.
- Fail fast, fail loud. Validate inputs at the boundary.
- Return early. Use guard clauses to eliminate nesting.
- Limit function arguments to 3.
- Add typing annotation to function input parameters.

## Python Conventions

- **Linter:** Ruff. All code must pass before commit.
- **Types:** Annotate all function signatures. Use `Optional[X]`.
- **Docstrings:** Google style on all public functions/classes/modules.
```

| 对比维度 | Codex `AGENTS.md` | Claude Code `CLAUDE.md` |
|---------|-------------------|-------------------------|
| **文件名** | `AGENTS.md`（可配备用名） | `CLAUDE.md`（固定） |
| **Override** | 同目录 `AGENTS.override.md` 优先 | 无 override 机制 |
| **发现路径** | git root -> 每级子目录 -> cwd | 类似层级发现 |
| **大小限制** | `project_doc_max_bytes`（默认 32 KiB） | 无固定限制 |
| **语义** | 面向"代理"的指令（AGENTS = 代理们） | 面向"Claude"的指令 |
| **注入位置** | `<user_instructions>` XML tag 包裹注入 | system prompt 注入 |

#### Codex 技能文件（SKILL.md）示例

Codex 的 `SKILL.md` 采用 YAML frontmatter + Markdown body 的结构，是可安装、可版本化的知识单元：

```markdown
---
name: "openai-docs"
description: "Use when the user asks how to build with OpenAI
  products or APIs and needs up-to-date official documentation
  with citations, help choosing the latest model for a use case,
  or explicit GPT-5.4 upgrade and prompt-upgrade guidance."
---

# OpenAI Docs

Provide authoritative, current guidance from OpenAI developer
docs using the developers.openai.com MCP server.

## Quick start

- Use `mcp__openaiDeveloperDocs__search_openai_docs` to find
  the most relevant doc pages.
- Use `mcp__openaiDeveloperDocs__fetch_openai_doc` to pull
  exact sections and quote/paraphrase accurately.

## Workflow

1. Clarify the product scope
2. Search docs via MCP
3. Cite sources accurately
```

Claude Code 没有对应的 `SKILL.md` 机制，但可以通过 `CLAUDE.md` 中嵌入特定领域指令或配置 MCP 插件来实现类似效果。

---

## 9 技能系统与 API 格式对比

### 9.1 技能系统

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **技能格式** | `SKILL.md`（YAML frontmatter + Markdown） | 无对应机制 |
| **系统技能** | 编译时嵌入，指纹缓存 | 无 |
| **技能安装** | 从 GitHub 安装（`skill-installer`） | 无 |
| **技能目录** | `~/.codex/skills/` | 无 |
| **技能注入** | `SkillsManager`（显式/隐式匹配） | 无 |

Claude Code 没有对应的技能系统，但通过 `CLAUDE.md` 层级指令和 MCP 插件实现了部分类似功能。Codex 的技能系统更结构化、更可组合——每个技能是一个独立的、版本化的、可安装的知识单元。

### 9.2 API 格式

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **API** | OpenAI Responses API | Anthropic Messages API |
| **模型** | GPT-5 系列 | Claude 4 系列 |
| **推理可见性** | 加密（`encrypted_content`） | 明文（`thinking`） |
| **工具调用** | `function_call` | `tool_use` |
| **流式传输** | Server-Sent Events + WebSocket | Server-Sent Events |
| **Token 统计** | `event_msg/token_count` 事件 | 内嵌于 `usage` 字段 |

---

## 10 综合特性矩阵

| 特性 | Codex CLI | Claude Code |
|------|:---------:|:-----------:|
| 命令执行 | ✓ | ✓ |
| 文件读写 | ✓ | ✓ |
| 代码编辑 | ✓（patch 语义） | ✓（替换语义） |
| 文件搜索 | ✓（BM25 引擎） | ✓（Glob + Grep） |
| 多代理协作 | ✓（5 工具 + 异步） | ✓（Agent 工具） |
| MCP 支持 | ✓（客户端 + 服务端） | ✓ |
| Web 搜索 | ✓ | ✓ |
| 图片处理 | ✓ | ✓ |
| JS REPL | ✓ | — |
| Notebook 编辑 | — | ✓ |
| 任务管理 | — | ✓（Todo） |
| Worktree 隔离 | — | ✓ |
| OS 沙箱 | ✓（3 平台） | — |
| AI 审批（Guardian） | ✓ | — |
| 规则引擎 | ✓（Starlark） | — |
| 企业 MDM | ✓ | — |
| 自动记忆 | ✓（ML 流水线） | 半自动 |
| 技能系统 | ✓（SKILL.md） | — |
| SQLite 状态 | ✓ | — |
| TOML 配置 | ✓ | JSON |
| Profile 切换 | ✓ | — |
| 人格系统 | ✓ | — |
| 语音输入 | ✓（实验性） | — |
| PDF 读取 | — | ✓ |

> 💡 **最佳实践**：选择哪个工具取决于使用场景。Codex CLI 更适合需要严格安全控制、企业策略管理和复杂多代理编排的场景。Claude Code 更适合需要快速上手、简洁配置和丰富生态（Notebook、PDF、任务管理）的个人开发场景。两者并非互斥——了解两种架构理念有助于在设计自己的 AI 代理时做出更好的技术决策。

---

## 11 CLI 终端输出对比

两个工具在终端中的实际输出风格也反映了不同的设计哲学。以下是典型交互过程中的终端输出示例。

#### 启动过程

```
═══════════════════════════════════════════════
Codex CLI 启动输出
═══════════════════════════════════════════════

$ codex
Starting Codex v0.94.0...
  model: gpt-5.1
  sandbox: workspace-write
  approval: on-request
  cwd: /Users/dev/my-project
  memories: loading (2 rollouts pending)

╭─ Codex (gpt-5.1) ────────────────────────╮
│                                           │
│  How can I help you today?                │
│                                           │
╰── sandbox: workspace-write ── on-request ─╯
>
```

```
═══════════════════════════════════════════════
Claude Code 启动输出
═══════════════════════════════════════════════

$ claude
╭────────────────────────────────────────────╮
│ ✻ Welcome to Claude Code!                  │
│                                            │
│   /help for help                           │
│                                            │
│   cwd: /Users/dev/my-project               │
╰────────────────────────────────────────────╯

Tips for getting started:
- Ask me to help with code, debug issues, or explore your codebase
- Use /compact to free up context when conversations get long

>
```

#### 工具执行过程

```
═══════════════════════════════════════════════
Codex CLI 工具执行
═══════════════════════════════════════════════

> Find all Python files with syntax errors

⟡ Searching for Python files...

  ┌─ shell ──────────────────────────────────┐
  │ $ find . -name "*.py" -exec python       │
  │     -m py_compile {} \; 2>&1             │
  │                                          │
  │ ./src/utils.py: SyntaxError: invalid     │
  │   syntax (line 42)                       │
  │ ./tests/test_auth.py: SyntaxError:       │
  │   unexpected EOF (line 108)              │
  └──────────────────── exit code: 1 ────────┘

Found 2 files with syntax errors:
1. `src/utils.py` line 42
2. `tests/test_auth.py` line 108
```

```
═══════════════════════════════════════════════
Claude Code 工具执行
═══════════════════════════════════════════════

> Find all Python files with syntax errors

● I'll search for Python files with syntax errors.

  ⎿  Bash(find . -name "*.py" -exec python -m py_compile {} \; 2>&1)

     ./src/utils.py: SyntaxError: invalid syntax (line 42)
     ./tests/test_auth.py: SyntaxError: unexpected EOF (line 108)

  Found 2 files with syntax errors:
  1. `src/utils.py` line 42
  2. `tests/test_auth.py` line 108

  Would you like me to fix them?
```

| 对比维度 | Codex CLI | Claude Code |
|---------|-----------|-------------|
| **TUI 框架** | ratatui 全屏 TUI（支持滚动、面板切换） | Ink inline 渲染 |
| **命令预览** | 框内显示完整命令 + exit code | 单行工具名 + 参数 |
| **状态栏** | 底部持久显示 sandbox/approval/model/token | 无持久状态栏 |
| **交互模式** | Alt-screen 全屏（可配置 `alt_screen_mode`） | Inline 流式输出 |
| **审批提示** | TUI 内 modal dialog | inline `Allow?` 提示 |

---

## 12 场景选择指南

根据不同的开发场景和组织需求，以下是选择 Codex CLI 和 Claude Code 的建议矩阵：

### 选择 Codex CLI 的场景

| 场景 | 原因 |
|------|------|
| **企业级安全合规** | OS 级沙箱 + MDM 策略 + Guardian AI 审批 + Starlark 规则引擎，提供多层防护 |
| **复杂多代理编排** | 5 个多代理工具 + 异步通信 + 中断恢复 + CSV 批量任务，适合长时间运行的编排场景 |
| **多前端集成** | SQ/EQ 架构天然支持 TUI / MCP Server / App Server / Exec 四种模式 |
| **低资源环境** | Rust 原生二进制启动更快、内存占用更低，适合 CI/CD 和资源受限的服务器 |
| **自动记忆需求** | 两阶段 ML 流水线全自动提取和整合历史经验，无需手动维护 |
| **配置精细管理** | 7 层配置栈 + Profile 切换 + `Constrained<T>` 约束系统 |
| **OpenAI 生态** | 原生集成 GPT-5 系列模型 + Responses API + 技能系统 |

### 选择 Claude Code 的场景

| 场景 | 原因 |
|------|------|
| **快速上手个人开发** | `npm install -g @anthropic-ai/claude-code` 即装即用，3 层配置极简 |
| **Jupyter Notebook 工作流** | 原生 `NotebookEdit` 工具支持，适合数据科学和研究场景 |
| **PDF 文档分析** | 内置 PDF 读取支持，适合需要分析文档的工作流 |
| **Git Worktree 隔离** | 原生 `isolation: "worktree"` 支持，每个子代理可在独立的 worktree 中工作 |
| **透明推理调试** | `thinking` 块以明文存储，便于分析模型的推理过程和调试 |
| **丰富任务管理** | `TaskCreate` / `TaskUpdate` / `TaskList` 工具支持结构化任务追踪 |
| **Anthropic 生态** | 原生集成 Claude 4 系列模型 + Messages API + MCP 标准 |

### 混合使用建议

```
项目生命周期中的工具选择
══════════════════════════════════════════════════

  探索阶段              开发阶段              部署阶段
  ┌──────────┐         ┌──────────┐         ┌──────────┐
  │Claude Code│         │ 两者皆可 │         │Codex CLI │
  │          │         │          │         │          │
  │ 快速原型  │  ────>  │ 功能开发  │  ────>  │ CI/CD    │
  │ 代码探索  │         │ 多文件编辑│         │ 安全审计  │
  │ 文档分析  │         │ 测试编写  │         │ 企业合规  │
  │ Notebook │         │ 重构     │         │ 批量任务  │
  └──────────┘         └──────────┘         └──────────┘

  推荐理由：              推荐理由：            推荐理由：
  - 零配置启动            - 取决于团队偏好       - OS 沙箱保障
  - 明文 thinking         - 取决于模型偏好       - MDM 策略管控
    便于学习              - 取决于生态需求       - headless 自动化
  - Notebook 友好                              - Guardian 审批
```

> 💡 **最佳实践**：两个工具并非互斥。在团队中可以根据角色分工选择不同的工具——安全敏感的 CI/CD 流程使用 Codex CLI 的沙箱和 Guardian 审批，个人开发和探索阶段使用 Claude Code 的简洁体验。`AGENTS.md` 和 `CLAUDE.md` 的指令内容可以相互参考和复用，确保无论使用哪个工具都能获得一致的代码规范指导。

---

## Reference

- [Codex CLI 官方文档](https://developers.openai.com/codex/cli/)
- [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code)
- [Codex GitHub 仓库](https://github.com/openai/codex)
- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Anthropic Messages API](https://docs.anthropic.com/en/api/messages)
- [Codex CLI 功能特性](https://developers.openai.com/codex/cli/features/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

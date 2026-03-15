# Codex CLI 本地数据管理系统

| 条目 | 内容 |
|------|------|
| **主题** | OpenAI Codex CLI 工具的本地数据存储和管理机制 |
| **存储位置** | `~/.codex` 目录（可通过 `CODEX_HOME` 环境变量自定义） |
| **适用版本** | Codex CLI v0.94.0+（Rust 原生实现） |
| **平台** | macOS、Linux（Windows WSL2 实验性支持） |

---

## 1 背景与设计思想

Codex CLI 是 OpenAI 推出的本地编程代理工具，基于 GPT-5 模型，使用 Rust 编写以获得更好的性能。与 Claude Code 类似，Codex 需要在本地保存会话数据、配置信息和各种状态文件。Codex 的本地存储以 `~/.codex` 为根目录（可通过 `CODEX_HOME` 环境变量重定向），采用 TOML 配置、JSONL 会话日志和 SQLite 状态数据库的混合存储策略。

与 Claude Code 的关键差异：
- **配置格式**：Codex 使用 TOML（`config.toml`），Claude Code 使用 JSON（`settings.json`）。
- **会话目录结构**：Codex 使用日期层级 `sessions/YYYY/MM/DD/rollout-*.jsonl`，Claude Code 使用项目路径编码 `projects/{encoded-path}/{session-id}.jsonl`。
- **自定义指令文件**：Codex 使用 `AGENTS.md`，Claude Code 使用 `CLAUDE.md`。
- **状态管理**：Codex 使用 SQLite 数据库（`state_5.sqlite`）集中管理线程元数据，Claude Code 依赖文件系统。
- **技能系统**：Codex 内置 `skills/` 目录和 `SKILL.md` 规范，Claude Code 无对应机制。

---

## 2 目录结构总览

```
~/.codex/
├── config.toml                   # 用户配置（TOML 格式）
├── auth.json                     # 认证凭证
├── history.jsonl                 # 全局会话索引（简要记录）
├── version.json                  # CLI 版本信息和更新检查
├── .personality_migration        # 人格迁移标记文件
│
├── sessions/                     # 核心：会话 rollout 日志
│   └── YYYY/MM/DD/
│       └── rollout-{timestamp}-{session-id}.jsonl
│
├── state_5.sqlite                # 线程/会话元数据数据库
├── state_5.sqlite-wal            # SQLite WAL 日志
├── state_5.sqlite-shm            # SQLite 共享内存
│
├── logs_1.sqlite                 # 应用日志数据库
│
├── log/                          # TUI 日志
│   └── codex-tui.log
│
├── skills/                       # 技能系统
│   └── .system/                  # 内置系统技能
│       ├── skill-creator/        # 技能创建引导
│       │   ├── SKILL.md
│       │   ├── agents/openai.yaml
│       │   ├── scripts/
│       │   ├── references/
│       │   └── assets/
│       └── skill-installer/      # 技能安装器
│           ├── SKILL.md
│           ├── agents/openai.yaml
│           ├── scripts/
│           └── assets/
│
├── memories/                     # 持久化记忆（agent 可写）
│
├── shell_snapshots/              # Shell 环境快照
│   └── {session-id}.sh
│
└── tmp/                          # 临时文件
    └── arg0/
        └── codex-arg0{random}/
            └── .lock
```

---

## 3 配置系统

### 3.1 config.toml

Codex 的配置使用 TOML 格式，支持多级配置源和优先级覆盖。

**配置优先级（从高到低）：**

1. CLI 命令行参数和 `--config` 覆盖
2. Profile 配置（通过 `--profile <name>` 选择）
3. 项目级配置（`.codex/config.toml`，仅受信项目生效）
4. 用户级配置（`~/.codex/config.toml`）
5. 系统级配置（`/etc/codex/config.toml`）
6. 内置默认值

**实际文件示例：**

```toml
model = "gpt-5.4"

[projects."/Users/username/my-project"]
trust_level = "trusted"

[notice.model_migrations]
"gpt-5.3-codex" = "gpt-5.4"

[tui]
status_line = ["model-with-reasoning", "context-remaining", "current-dir"]
```

**常用配置键：**

| 配置键 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| `model` | String | 默认模型 | `"gpt-5.4"` |
| `approval_policy` | String | 命令审批策略 | `"untrusted"` / `"on-request"` / `"never"` |
| `sandbox_mode` | String | 沙箱模式 | `"read-only"` / `"workspace-write"` / `"danger-full-access"` |
| `web_search` | String | 网络搜索行为 | `"cached"` / `"live"` / `"disabled"` |
| `model_reasoning_effort` | String | 推理强度 | `"high"` |
| `personality` | String | 沟通风格 | `"friendly"` / `"pragmatic"` / `"none"` |
| `log_dir` | String | 日志目录 | 自定义路径 |

**配置段（Sections）：**

| 段名 | 说明 |
|------|------|
| `[profiles.<name>]` | 命名配置方案，通过 `--profile` 切换 |
| `[model_providers.*]` | 自定义 LLM 端点（如 Ollama 本地模型） |
| `[shell_environment_policy]` | 子进程环境变量控制（`include_only`、`exclude` 等） |
| `[otel]` | OpenTelemetry 遥测配置 |
| `[tui]` | 终端 UI 选项（主题、状态栏等） |
| `[history]` | 历史持久化控制（`max_bytes` 等） |
| `[features]` | 功能开关（`shell_snapshot`、`multi_agent` 等） |
| `[projects."<path>"]` | 按项目路径设置信任级别和覆盖配置 |

### 3.2 项目级配置

Codex 从项目根目录到当前工作目录逐级查找 `.codex/config.toml`，依次加载合并。未受信（untrusted）项目的 `.codex/` 配置层会被跳过，仅使用用户级和系统级默认值。

### 3.3 AGENTS.md 自定义指令

Codex 的自定义指令文件等同于 Claude Code 的 `CLAUDE.md`。发现顺序：

1. **全局级**：`~/.codex/AGENTS.override.md` → `~/.codex/AGENTS.md`（第一个非空文件生效）
2. **项目级**：从 Git 根目录到当前目录，每一级检查 `AGENTS.override.md` → `AGENTS.md` → fallback 文件名
3. **合并规则**：从根向下串联，`.override.md` 变体在每一级优先

合并后的指令总大小默认上限为 **32 KiB**（可通过 `project_doc_max_bytes` 调整）。可在 `config.toml` 中通过 `project_doc_fallback_filenames` 自定义备用文件名（如 `TEAM_GUIDE.md`）。

---

## 4 会话数据存储机制

### 4.1 两层存储设计

Codex 同样采用"索引 + 详细日志"的两层设计：

1. **全局索引层（history.jsonl）**：每次会话追加一条简要记录，包含会话 ID、时间戳和用户首条消息。
2. **会话日志层（sessions/）**：完整的会话交互记录，按日期组织目录，以 rollout 文件形式存储。

**两层索引流程图：**

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        用户启动 Codex 会话                               │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Layer 1: history.jsonl（全局索引）                                       │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ {"session_id":"019ced27-...","ts":1773505492,"text":"My first..."}│  │
│  │ {"session_id":"019cf3ab-...","ts":1773591234,"text":"Fix bug..."}│  │
│  │ ...（每行一条，append-only）                                        │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│  作用: 快速遍历所有会话摘要，O(1) append，无需加载完整日志                   │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │ session_id → 定位 rollout 文件
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Layer 2: sessions/YYYY/MM/DD/rollout-*.jsonl（按日期分层的详细日志）       │
│                                                                          │
│  sessions/                                                               │
│  └── 2026/                                                               │
│      └── 03/                                                             │
│          ├── 14/                                                         │
│          │   ├── rollout-2026-03-14T12-21-29-019ced27-...jsonl ◄─────┐  │
│          │   └── rollout-2026-03-14T15-30-00-019ced8f-...jsonl       │  │
│          └── 15/                                                     │  │
│              └── rollout-2026-03-15T09-00-12-019cf3ab-...jsonl       │  │
│                                                                      │  │
│  每个文件包含一个会话的完整交互记录（session_meta → events → ...）      │  │
└──────────────────────────────────────────────────────────────────────┘│  │
                                                                       │  │
┌──────────────────────────────────────────────────────────────────────┐│  │
│  Layer 2.5: state_5.sqlite（结构化元数据索引）                        ││  │
│  ┌──────────────────────────────────────────────────────────────────┐││  │
│  │ threads 表: id, rollout_path, cwd, title, tokens_used, ...     │├┘  │
│  │ → 提供按项目、按来源、按时间的高效查询                             │├───┘
│  └──────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘
```

> 📌 **重点**：Codex 实际上是"两层半"设计。`history.jsonl` 是轻量级 append-only 索引，`state_5.sqlite` 的 `threads` 表提供按 `cwd`、`source`、`model_provider` 等维度的结构化查询能力，rollout 文件则存储完整的事件流。SQLite 不可用时，系统会 fallback 到纯文件系统扫描。

### 4.2 history.jsonl 文件格式

每行是一条独立的 JSON 对象，记录会话的入口信息。

**数据结构示例：**

```json
{
  "session_id": "019ced27-1efa-78f0-936a-69a9afac75fa",
  "ts": 1773505492,
  "text": "This is my first use of Codex but I have used other coding agents."
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | String | 会话唯一标识符（UUID v7 格式，含时间戳信息） |
| `ts` | Number | 时间戳（**秒级** Unix epoch，注意 Claude Code 使用毫秒） |
| `text` | String | 用户首条消息文本 |

> 与 Claude Code 的 `history.jsonl` 对比：Codex 的索引更简洁，不包含 `project`（项目路径）和 `pastedContents`（粘贴内容）字段。项目关联信息存储在 SQLite 数据库的 `threads` 表中。

### 4.3 Rollout JSONL 文件格式（核心数据）

**文件命名规则**：`rollout-{ISO-timestamp}-{session-id}.jsonl`

- 时间戳格式：`YYYY-MM-DDTHH-MM-SS`（使用 `-` 代替 `:`）
- 示例：`rollout-2026-03-14T12-21-29-019ced27-1efa-78f0-936a-69a9afac75fa.jsonl`

**文件存储路径**：`~/.codex/sessions/YYYY/MM/DD/`

每个 rollout 文件包含完整的会话交互记录。文件中的每一行是一个 JSON 对象，包含 `timestamp`、`type` 和 `payload` 三个顶层字段。

#### 4.3.1 顶层事件类型（RolloutItem 枚举）

Rollout 文件中的每一行对应 `RolloutItem` 枚举的一个变体（定义于 `codex-rs/protocol/src/protocol.rs`）：

| 事件类型 | 对应变体 | 说明 |
|----------|----------|------|
| `session_meta` | `SessionMeta` | 会话元数据（仅出现一次，在文件开头） |
| `response_item` | `ResponseItem` | API 请求/响应中的单个项目（消息、工具调用、推理等） |
| `compacted` | `Compacted` | 上下文压缩后的加密摘要（长会话中出现） |
| `turn_context` | `TurnContext` | 每轮对话的上下文信息 |
| `event_msg` | `EventMsg` | 客户端事件（任务开始/完成、用户消息、token 统计等） |

**Rollout 事件处理 Pipeline：**

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Rollout JSONL 文件逐行读取与分类                             │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ 每行 → serde_json::from_str::<RolloutLine>
                                  ▼
              ┌───────────────────────────────────────┐
              │     RolloutItem 枚举分发               │
              └───┬─────┬─────┬─────┬─────┬───────────┘
                  │     │     │     │     │
     ┌────────────┘     │     │     │     └──────────────┐
     ▼                  ▼     │     ▼                    ▼
┌──────────┐  ┌──────────┐   │  ┌──────────┐   ┌──────────────┐
│ session  │  │ response │   │  │  event   │   │  compacted   │
│  _meta   │  │  _item   │   │  │  _msg    │   │  (上下文压缩) │
└────┬─────┘  └────┬─────┘   │  └────┬─────┘   └──────────────┘
     │              │         │       │
     ▼              │         │       ▼
┌──────────┐        │         │  ┌──────────────────────────────┐
│ 提取:     │        │         │  │ 分类:                        │
│ • id      │        │         │  │ • task_started → 轮次开始    │
│ • cwd     │        │         │  │ • user_message → 用户输入    │
│ • source  │        │         │  │ • token_count → 用量统计     │
│ • model   │        │         │  │ • task_complete → 轮次结束   │
│ • version │        │         │  │ • exec_command_* → 命令执行  │
└──────────┘        │         │  │ • collab_* → 多代理协作       │
                    ▼         │  └──────────────────────────────┘
     ┌──────────────────────┐ │
     │ payload.type 分发:    │ │
     ├──────────────────────┤ │   ┌──────────────┐
     │ message (user)       │─┼──▶│ 用户消息      │
     │ message (assistant)  │─┼──▶│ 助手回复      │
     │ message (developer)  │─┼──▶│ 系统指令      │
     │ function_call        │─┼──▶│ 工具调用      │──┐
     │ function_call_output │─┼──▶│ 工具结果      │──┤ call_id 关联
     │ reasoning            │─┼──▶│ 推理过程      │  │
     └──────────────────────┘ │   └──────────────┘  │
                              │                     │
                              ▼                     ▼
                     ┌──────────────┐    ┌───────────────────┐
                     │ turn_context │    │ 工具调用配对:       │
                     │ 每轮上下文:   │    │ function_call.     │
                     │ • model      │    │   call_id          │
                     │ • sandbox    │    │     ═══            │
                     │ • approval   │    │ function_call_     │
                     │ • timezone   │    │   output.call_id   │
                     └──────────────┘    └───────────────────┘
```

> 💡 **最佳实践**：解析 rollout 文件时建议采用两遍扫描策略。第一遍收集所有 `function_call_output` 建立 `call_id → output` 映射表，第二遍处理消息流，在遇到 `function_call` 时直接从映射表中 O(1) 查找对应结果。这样可以避免前向扫描或乱序匹配的复杂性。

#### 4.3.2 session_meta 事件

文件的第一行，记录会话级别的元数据。

```json
{
  "timestamp": "2026-03-14T16:24:52.480Z",
  "type": "session_meta",
  "payload": {
    "id": "019ced27-1efa-78f0-936a-69a9afac75fa",
    "timestamp": "2026-03-14T16:21:29.981Z",
    "cwd": "/Users/username/my-project",
    "originator": "codex_cli_rs",
    "cli_version": "0.114.0",
    "source": "cli",
    "model_provider": "openai",
    "base_instructions": {
      "text": "You are Codex, a coding agent based on GPT-5..."
    }
  }
}
```

**payload 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String | 会话 ID（与文件名中的 session-id 一致） |
| `timestamp` | String | 会话创建时间（ISO 8601） |
| `cwd` | String | 会话的工作目录 |
| `originator` | String | 发起者标识（`codex_cli_rs` = CLI，`vscode` = VS Code 扩展） |
| `cli_version` | String | Codex CLI 版本号 |
| `source` | String | 来源类型，对应 `SessionSource` 枚举：`"cli"` / `"vscode"` / `"exec"` / `"mcp"` / `"sub_agent"` / `"unknown"` |
| `model_provider` | String | 模型提供者（`"openai"` 等） |
| `base_instructions` | Object | 基础系统指令（含完整人格设定和工具使用规则） |
| `agent_nickname` | String? | 子代理昵称（仅 `SubAgent` 来源时存在） |
| `agent_role` | String? | 子代理角色（仅 `SubAgent` 来源时存在） |
| `dynamic_tools` | Array? | 动态工具定义列表 |
| `memory_mode` | String? | 记忆模式（默认 `"enabled"`） |
| `forked_from_id` | String? | 分叉来源的线程 ID |

#### 4.3.3 turn_context 事件

每轮对话开始时记录当前环境上下文。

```json
{
  "timestamp": "2026-03-14T16:24:52.481Z",
  "type": "turn_context",
  "payload": {
    "turn_id": "019ced2a-35e9-7ac0-938d-33d2fd05ef40",
    "cwd": "/Users/username/my-project",
    "current_date": "2026-03-14",
    "timezone": "America/New_York",
    "approval_policy": "on-request",
    "sandbox_policy": {
      "type": "workspace-write",
      "writable_roots": ["/Users/username/.codex/memories"],
      "network_access": false
    },
    "model": "gpt-5.4",
    "personality": "pragmatic",
    "collaboration_mode": {
      "mode": "default",
      "settings": { "model": "gpt-5.4", "reasoning_effort": null }
    }
  }
}
```

**payload 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `turn_id` | String | 当前轮次的唯一标识符 |
| `cwd` | String | 当前工作目录 |
| `current_date` | String | 当前日期 |
| `timezone` | String | 时区（IANA 格式） |
| `approval_policy` | String | 当前审批策略 |
| `sandbox_policy` | Object | 沙箱策略详情（类型、可写目录、网络访问） |
| `model` | String | 当前使用的模型 |
| `personality` | String | 人格风格 |
| `collaboration_mode` | Object | 协作模式（`default` 或 `plan`） |

#### 4.3.4 response_item 事件

API 交互中的各类项目。`payload.type` 决定具体子类型。

**用户消息（developer/user role）：**

```json
{
  "timestamp": "2026-03-14T16:24:52.481Z",
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "user",
    "content": [
      {
        "type": "input_text",
        "text": "What's your advantages compared to others?"
      }
    ]
  }
}
```

**系统指令（developer role）：**

```json
{
  "timestamp": "2026-03-14T16:24:52.481Z",
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "developer",
    "content": [
      {
        "type": "input_text",
        "text": "<permissions instructions>..."
      }
    ]
  }
}
```

**助手回复：**

```json
{
  "timestamp": "2026-03-14T16:25:05.041Z",
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "assistant",
    "content": [
      {
        "type": "output_text",
        "text": "The practical advantages here are..."
      }
    ]
  }
}
```

**工具调用（function_call）：**

```json
{
  "timestamp": "2026-03-14T16:26:06.638Z",
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "exec_command",
    "arguments": "{\"cmd\":\"pwd\",\"workdir\":\"/Users/username/project\",\"max_output_tokens\":120}",
    "call_id": "call_C9l32tO7DEqE1g5xdG0BEpTR"
  }
}
```

**工具结果（function_call_output）：**

```json
{
  "timestamp": "2026-03-14T16:26:06.708Z",
  "type": "response_item",
  "payload": {
    "type": "function_call_output",
    "call_id": "call_C9l32tO7DEqE1g5xdG0BEpTR",
    "output": "Chunk ID: 538a4d\nWall time: 0.0000 seconds\nProcess exited with code 0\nOriginal token count: 14\nOutput:\n/Users/username/project\n"
  }
}
```

**推理（reasoning）：**

```json
{
  "timestamp": "2026-03-14T16:24:57.543Z",
  "type": "response_item",
  "payload": {
    "type": "reasoning",
    "summary": [],
    "content": null,
    "encrypted_content": "gAAAAABptYvZ..."
  }
}
```

> 与 Claude Code 的关键差异：Codex 的推理内容（`encrypted_content`）是加密的，不像 Claude Code 的 `thinking` 块以明文存储。`summary` 数组通常为空，推理过程对用户不可见。

**response_item payload 子类型汇总：**

| payload.type | role | content 类型 | 说明 |
|--------------|------|-------------|------|
| `message` | `developer` | `input_text` | 系统指令（沙箱规则、AGENTS.md 内容等） |
| `message` | `user` | `input_text` | 用户输入消息 |
| `message` | `assistant` | `output_text` | 助手文本回复 |
| `function_call` | — | — | 工具调用（`name` + `arguments` JSON 字符串） |
| `function_call_output` | — | — | 工具执行结果（`call_id` + `output` 文本） |
| `reasoning` | — | — | 模型推理过程（加密存储） |

#### 4.3.5 event_msg 事件

客户端生成的事件，用于标记任务生命周期和用户交互。`EventMsg` 枚举定义于 `codex-rs/protocol/src/protocol.rs`，包含 60+ 个变体。以下列出核心事件和按类别分组的完整列表。

**核心生命周期事件：**

| payload.type | 说明 | 关键字段 |
|--------------|------|----------|
| `task_started` | 轮次开始（内部名 `TurnStarted`，v1 兼容序列化为 `task_started`） | `turn_id`, `model_context_window`, `collaboration_mode_kind` |
| `task_complete` | 轮次完成（内部名 `TurnComplete`） | `turn_id`, `last_agent_message` |
| `turn_aborted` | 轮次中止 | — |
| `user_message` | 用户发送的原始消息 | `message`, `images`, `local_images`, `text_elements` |
| `agent_message` | 助手的完整回复文本 | `message`（纯文本） |
| `token_count` | Token 使用统计 | `info`, `rate_limits` |
| `session_configured` | 会话初始配置完成 | — |
| `shutdown_complete` | 会话关闭完成 | — |

**工具执行事件：**

| payload.type | 说明 |
|--------------|------|
| `exec_command_begin` | Shell 命令开始执行 |
| `exec_command_output_delta` | 命令输出增量 |
| `exec_command_end` | Shell 命令执行结束 |
| `patch_apply_begin` | 代码补丁开始应用 |
| `patch_apply_end` | 代码补丁应用结束 |
| `view_image_tool_call` | 图片查看工具调用 |
| `mcp_tool_call_begin` / `mcp_tool_call_end` | MCP 工具调用开始/结束 |
| `mcp_startup_update` / `mcp_startup_complete` | MCP 服务启动进度/完成 |

**多代理协作事件（Collab）：**

| payload.type | 说明 |
|--------------|------|
| `collab_agent_spawn_begin` / `collab_agent_spawn_end` | 子代理创建开始/结束 |
| `collab_agent_interaction_begin` / `collab_agent_interaction_end` | 子代理交互开始/结束 |
| `collab_waiting_begin` / `collab_waiting_end` | 等待子代理开始/结束 |
| `collab_close_begin` / `collab_close_end` | 关闭子代理开始/结束 |
| `collab_resume_begin` / `collab_resume_end` | 恢复子代理开始/结束 |

**流式增量事件：**

| payload.type | 说明 |
|--------------|------|
| `agent_message_delta` | 助手消息增量 |
| `agent_message_content_delta` | 助手消息内容增量 |
| `agent_reasoning` / `agent_reasoning_delta` | 推理内容/增量 |
| `reasoning_content_delta` / `reasoning_raw_content_delta` | 推理内容增量 |
| `plan_delta` | 计划内容增量 |
| `item_started` / `item_completed` | 响应项开始/完成 |

**其他事件：**

| payload.type | 说明 |
|--------------|------|
| `web_search_begin` / `web_search_end` | 网络搜索开始/结束 |
| `image_generation_begin` / `image_generation_end` | 图片生成开始/结束 |
| `exec_approval_request` | 命令执行审批请求 |
| `apply_patch_approval_request` | 补丁应用审批请求 |
| `request_permissions` | 权限提升请求 |
| `request_user_input` | 请求用户输入 |
| `guardian_assessment` | Guardian 风险评估结果 |
| `context_compacted` | 上下文压缩完成 |
| `thread_rolled_back` | 线程回滚 |
| `thread_name_updated` | 线程名称更新 |
| `hook_started` / `hook_completed` | 钩子执行开始/完成 |
| `undo_started` / `undo_completed` | 撤销操作开始/完成 |
| `turn_diff` | 轮次差异 |
| `error` / `warning` / `stream_error` | 错误/警告/流错误 |
| `background_event` | 后台事件 |
| `deprecation_notice` | 弃用通知 |
| `model_reroute` | 模型重路由 |

**user_message 示例：**

```json
{
  "timestamp": "2026-03-14T16:24:52.481Z",
  "type": "event_msg",
  "payload": {
    "type": "user_message",
    "message": "This is my first use of Codex.",
    "images": [],
    "local_images": [],
    "text_elements": []
  }
}
```

**task_started 示例：**

```json
{
  "timestamp": "2026-03-14T16:24:52.481Z",
  "type": "event_msg",
  "payload": {
    "type": "task_started",
    "turn_id": "019ced2a-35e9-7ac0-938d-33d2fd05ef40",
    "model_context_window": 258400,
    "collaboration_mode_kind": "default"
  }
}
```

### 4.4 会话生命周期状态机

一个 Codex 会话从创建到完成，经历以下状态转换。这些状态由 rollout 文件中的 `event_msg` 事件驱动：

```
                    ┌──────────────────────────────────────────────┐
                    │              会话生命周期状态机                │
                    └──────────────────────────────────────────────┘

  codex 启动
      │
      ▼
┌───────────┐  session_meta 写入    ┌───────────┐  session_configured
│  Created  │─────────────────────▶│ Configured│──────────────────┐
└───────────┘                      └───────────┘                  │
                                                                  ▼
                                                          ┌───────────┐
  ┌──────────────────────────────────────────────────────▶│   Idle    │
  │                                                       └─────┬─────┘
  │                                            user_message │   │
  │                                                         ▼   │
  │  task_complete                                ┌───────────┐ │
  ├───────────────────────────────────────────────│  Active   │ │
  │                                               │ (Turn)    │ │
  │                                               └──┬──┬──┬──┘ │
  │                                                  │  │  │    │
  │        ┌─────────────────────────────────────────┘  │  │    │
  │        │                                            │  │    │
  │        ▼                                            │  │    │
  │  ┌───────────┐    审批通过      ┌───────────┐       │  │    │
  │  │ Awaiting  │───────────────▶│ Executing │───────┘  │    │
  │  │ Approval  │    审批拒绝      │ Tool      │          │    │
  │  │           │─────┐          └───────────┘          │    │
  │  └───────────┘     │                                  │    │
  │                    │                                  │    │
  │                    ▼                                  │    │
  │             ┌───────────┐    context_compacted        │    │
  │             │ Aborted   │◄───────────────────────────┘    │
  │             │ (turn_    │                                  │
  │             │  aborted) │                                  │
  │             └─────┬─────┘                                  │
  │                   │                                        │
  │                   └────────────────────────────────────────┘
  │
  │  shutdown_complete
  ▼
┌───────────┐
│ Shutdown  │  → rollout 文件关闭，SQLite 行 updated_at 更新
└───────────┘
```

**状态转换触发事件一览：**

| 当前状态 | 触发事件 | 目标状态 | 说明 |
|----------|----------|----------|------|
| Created | `session_meta` 写入 | Configured | rollout 文件创建，元数据记录 |
| Configured | `session_configured` | Idle | MCP 服务启动、配置合并完成 |
| Idle | `user_message` | Active | 用户发送新消息，开启一轮对话 |
| Active | `task_started` | Active | 轮次正式开始（模型推理启动） |
| Active | `exec_approval_request` | Awaiting Approval | 命令执行等待用户审批 |
| Awaiting Approval | 用户批准 | Executing Tool | 开始执行工具 |
| Awaiting Approval | 用户拒绝 | Active | 返回模型重新规划 |
| Active | `task_complete` | Idle | 轮次完成，等待下一条用户消息 |
| Active | `turn_aborted` | Idle | 用户中断当前轮次（Ctrl+C） |
| Active | `context_compacted` | Active | 上下文压缩（长会话自动触发） |
| Idle | `shutdown_complete` | Shutdown | 会话正常退出 |

> ⚠️ **注意**：在多代理协作模式下，主代理可能在 Active 状态期间通过 `collab_agent_spawn_begin` 创建子代理，子代理拥有独立的 rollout 文件和独立的生命周期。主代理通过 `wait_agent` / `close_agent` 管理子代理状态。

### 4.5 与 Claude Code 会话格式的对比

| 特性 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **文件命名** | `rollout-{timestamp}-{session-id}.jsonl` | `{session-id}.jsonl` |
| **目录组织** | 按日期 `YYYY/MM/DD/` | 按项目路径编码 `projects/{encoded-path}/` |
| **消息结构** | 顶层 `{timestamp, type, payload}` 包装 | 直接的 `{type, uuid, sessionId, message}` |
| **角色系统** | `developer` / `user` / `assistant` | `user` / `assistant` |
| **工具调用** | `function_call` + `function_call_output` | `tool_use` + `tool_result`（嵌入 message.content） |
| **推理记录** | 加密（`encrypted_content`） | 明文（`thinking` 块） |
| **消息链接** | 通过 `turn_id` 关联同一轮次 | 通过 `parentUuid` 链接父子消息 |
| **子代理** | 多代理协作工具（`spawn_agent` / `wait_agent` 等），子代理有独立 rollout 文件，通过 `SubAgent(ThreadSpawn)` 来源标识 | `{session-id}/subagents/agent-*.jsonl` |
| **UUID 格式** | UUID v7（含时间戳） | UUID v4（随机） |
| **Token 使用** | 通过 `event_msg/token_count` 事件 | 内嵌于助手消息的 `usage` 字段 |

---

## 5 SQLite 数据库

### 5.1 state_5.sqlite（状态数据库）

Codex 使用 SQLite 数据库集中管理线程元数据和后台任务状态，这是与 Claude Code 最大的架构差异之一。

**主要表结构：**

#### threads 表（会话/线程元数据）

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | 线程 ID（UUID） |
| `rollout_path` | TEXT | 对应 rollout JSONL 文件路径 |
| `created_at` | INTEGER | 创建时间（Unix 时间戳） |
| `updated_at` | INTEGER | 更新时间 |
| `source` | TEXT | 来源（`"cli"` / `"vscode"`） |
| `model_provider` | TEXT | 模型提供者 |
| `cwd` | TEXT | 工作目录 |
| `title` | TEXT | 会话标题（通常为首条用户消息） |
| `sandbox_policy` | TEXT | 沙箱策略（JSON 字符串） |
| `approval_mode` | TEXT | 审批模式 |
| `tokens_used` | INTEGER | 已使用的 token 数 |
| `has_user_event` | INTEGER | 是否有用户事件 |
| `archived` | INTEGER | 是否已归档 |
| `git_sha` | TEXT | Git commit SHA |
| `git_branch` | TEXT | Git 分支名 |
| `git_origin_url` | TEXT | Git 远程 URL |
| `cli_version` | TEXT | CLI 版本 |
| `first_user_message` | TEXT | 首条用户消息 |
| `agent_nickname` | TEXT | Agent 昵称 |
| `agent_role` | TEXT | Agent 角色 |
| `memory_mode` | TEXT | 记忆模式（默认 `"enabled"`） |

#### stage1_outputs 表（记忆/摘要处理）

| 列名 | 类型 | 说明 |
|------|------|------|
| `thread_id` | TEXT PK | 关联的线程 ID |
| `raw_memory` | TEXT | 原始记忆文本 |
| `rollout_summary` | TEXT | 会话摘要 |
| `rollout_slug` | TEXT | 会话简称 |
| `usage_count` | INTEGER | 使用次数 |
| `selected_for_phase2` | INTEGER | 是否被选入第二阶段处理 |

#### agent_jobs 表（批量 Agent 任务）

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | 任务 ID |
| `name` | TEXT | 任务名称 |
| `status` | TEXT | 任务状态 |
| `instruction` | TEXT | 任务指令 |
| `input_csv_path` | TEXT | 输入 CSV 路径 |
| `output_csv_path` | TEXT | 输出 CSV 路径 |
| `max_runtime_seconds` | INTEGER | 最大运行时间 |

#### agent_job_items 表（批量任务项）

| 列名 | 类型 | 说明 |
|------|------|------|
| `job_id` | TEXT | 关联的任务 ID |
| `item_id` | TEXT | 项目 ID |
| `row_index` | INTEGER | 行号 |
| `status` | TEXT | 项目状态 |
| `assigned_thread_id` | TEXT | 分配的线程 ID |
| `result_json` | TEXT | 结果 JSON |

#### thread_dynamic_tools 表（动态工具注册）

| 列名 | 类型 | 说明 |
|------|------|------|
| `thread_id` | TEXT | 关联的线程 ID（FK → threads） |
| `position` | INTEGER | 工具排序位置 |
| `name` | TEXT | 工具名称 |
| `description` | TEXT | 工具描述 |
| `input_schema` | TEXT | 输入参数 JSON Schema |
| `defer_loading` | INTEGER | 是否延迟加载（默认 0） |

#### jobs 表（后台任务队列）

| 列名 | 类型 | 说明 |
|------|------|------|
| `kind` | TEXT | 任务类型 |
| `job_key` | TEXT | 任务键（唯一标识） |
| `status` | TEXT | 任务状态 |
| `worker_id` | TEXT | 工作节点 ID |
| `ownership_token` | TEXT | 所有权令牌 |
| `started_at` | INTEGER | 开始时间 |
| `finished_at` | INTEGER | 完成时间 |
| `lease_until` | INTEGER | 租约过期时间 |
| `retry_at` | INTEGER | 重试时间 |
| `retry_remaining` | INTEGER | 剩余重试次数 |
| `last_error` | TEXT | 最后错误信息 |
| `input_watermark` | TEXT | 输入水位 |
| `last_success_watermark` | TEXT | 最后成功水位 |

#### backfill_state 表（数据回填状态）

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 固定为 1（单例表） |
| `status` | TEXT | 回填状态 |
| `last_watermark` | TEXT | 最后处理水位 |
| `last_success_at` | INTEGER | 最后成功时间 |

> 📌 **重点**：`state_5.sqlite` 的 schema 由 19 个增量迁移文件（`0001_threads.sql` 至 `0019_thread_dynamic_tools_defer_loading.sql`）构建而成，使用 `sqlx` 库的编译期查询检查确保类型安全。

### 5.2 logs_1.sqlite（日志数据库）

独立的应用日志数据库，记录 Codex CLI 运行时的结构化日志。

**logs 表结构：**

| 列名 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增日志 ID |
| `ts` | INTEGER | 时间戳（秒） |
| `ts_nanos` | INTEGER | 纳秒精度时间戳 |
| `level` | TEXT | 日志级别（INFO、WARN、ERROR 等） |
| `target` | TEXT | 日志目标（Rust 模块路径） |
| `message` | TEXT | 日志消息 |
| `module_path` | TEXT | 源代码模块路径 |
| `file` | TEXT | 源文件名 |
| `line` | INTEGER | 源代码行号 |
| `thread_id` | TEXT | 关联的线程 ID |
| `process_uuid` | TEXT | 进程 UUID |

---

## 6 认证与安全

### 6.1 auth.json

存储认证凭证，支持两种认证方式：

- **文件存储**：凭证保存在 `auth.json` 中
- **系统密钥链**：macOS Keychain 或 Linux keyring

认证通过 `codex login` 命令完成，支持 OAuth、设备授权和 API 密钥三种方式。

### 6.2 沙箱策略

Codex 提供三种沙箱模式：

| 模式 | 说明 |
|------|------|
| `read-only` | 只读访问，不能修改任何文件 |
| `workspace-write` | 可读取所有文件，仅能编辑 cwd 和 writable_roots 下的文件 |
| `danger-full-access` | 完全访问（危险模式） |

沙箱策略在 `turn_context` 事件和 `threads` 表的 `sandbox_policy` 列中均有记录。

---

## 7 技能系统（Skills）

### 7.1 技能目录结构

技能存储在 `~/.codex/skills/` 下，每个技能是一个独立目录，必须包含 `SKILL.md` 文件。

```
skills/
├── .system/                          # 内置系统技能
│   ├── .codex-system-skills.marker   # 系统技能标记
│   ├── skill-creator/                # 创建新技能的引导
│   │   ├── SKILL.md                  # 技能说明（YAML frontmatter + Markdown）
│   │   ├── agents/openai.yaml        # Agent 配置
│   │   ├── scripts/                  # 辅助脚本
│   │   │   ├── init_skill.py
│   │   │   ├── quick_validate.py
│   │   │   └── generate_openai_yaml.py
│   │   ├── references/               # 参考文档
│   │   │   └── openai_yaml.md
│   │   └── assets/                   # 图标等静态资源
│   └── skill-installer/              # 从 GitHub 安装技能
│       ├── SKILL.md
│       ├── agents/openai.yaml
│       └── scripts/
│           ├── list-skills.py
│           ├── install-skill-from-github.py
│           └── github_utils.py
└── [user-installed-skills]/          # 用户安装的技能
```

### 7.2 SKILL.md 格式

每个技能的入口文件，使用 YAML frontmatter + Markdown 格式：

```markdown
---
name: skill-creator
description: Guide for creating effective skills.
metadata:
  short-description: Create or update a skill
---

# Skill Creator

[技能的详细说明和使用指南...]
```

技能可通过以下方式安装：
- `codex` 中使用 skill-installer 技能
- 从 [openai/skills](https://github.com/openai/skills) 仓库安装精选或实验性技能
- 从任意 GitHub 仓库安装

---

## 8 其他文件

### 8.1 version.json

记录 CLI 版本和更新检查状态。

```json
{
  "latest_version": "0.114.0",
  "last_checked_at": "2026-03-14T15:32:53.540089Z",
  "dismissed_version": null
}
```

### 8.2 shell_snapshots/

每个会话可能生成一个 shell 环境快照文件（`.sh` 格式），记录会话开始时的完整 shell 状态，包括：

- 所有函数定义（`unalias -a` + 函数声明）
- 环境变量
- Shell 选项和设置

文件名为 `{session-id}.sh`，用于在沙箱环境中重建一致的 shell 状态。

### 8.3 memories/（持久化记忆系统）

Codex 采用两阶段（Two-Phase）ML 流水线自动提取和整合记忆，存储在 `~/.codex/memories/` 目录。

```
memories/
├── raw_memories.md              # 阶段一输出合并的原始记忆
├── memory_summary.md            # 阶段二整合后的记忆摘要
├── MEMORY.md                    # 整合输出
└── rollout_summaries/           # 每个 rollout 的独立摘要
    ├── rollout-2026-03-14-xxx.md
    └── ...
```

**阶段一（Phase 1）：原始记忆提取**
- 使用 `gpt-5.1-codex-mini` 模型，`ReasoningEffort::Low`
- 并发上限 8 个任务，每个 rollout 最多处理 150,000 tokens
- 上下文窗口使用率 70%
- 任务租约 1 小时，失败后 1 小时重试
- 输出存入 `stage1_outputs` 表（`raw_memory`、`rollout_summary`、`rollout_slug`）

**阶段二（Phase 2）：记忆整合**
- 使用 `gpt-5.3-codex` 模型，`ReasoningEffort::Medium`
- 全局锁（同时只有一个整合任务），心跳间隔 90 秒
- 从 `stage1_outputs` 表读取已选记忆，同步 rollout summaries 到文件系统
- 重建 `raw_memories.md`，派发整合子代理

在沙箱模式 `workspace-write` 下，`~/.codex/memories/` 通常被加入 `writable_roots`，允许 Agent 在此目录中读写持久化的记忆文件。

### 8.4 log/codex-tui.log

Codex TUI（终端用户界面）的运行时日志，使用 Rust 的 tracing 框架输出结构化日志。记录模型选择、缓存状态、shell 快照创建等 TUI 层面的事件。

### 8.5 tmp/arg0/

临时目录，存储 Codex 进程的锁文件。每个子目录名格式为 `codex-arg0{random}`，内含 `.lock` 文件防止多实例冲突。

### 8.6 .personality_migration

简单标记文件，记录人格系统的迁移版本号（如 `v1`），用于 Codex 在版本升级时执行一次性的配置迁移。

---

## 9 Codex 工具系统

早期版本的 Codex 主要通过单一的 `exec_command` 工具执行所有操作，但源码显示当前版本已发展为拥有 30+ 工具的完整工具系统。工具通过 `ToolRegistryBuilder` 注册，由 `ToolRegistry` 派发调用，每个工具实现 `ToolHandler` trait。

### 9.1 标准工具

| 工具名称 | Handler | 说明 |
|----------|---------|------|
| `shell` | `ShellHandler` | Shell 命令执行（PTY 模式） |
| `container.exec` | `ShellHandler` | 容器内命令执行（共享 handler） |
| `local_shell` | `ShellHandler` | 本地 shell（共享 handler） |
| `exec_command` | `UnifiedExecHandler` | 统一命令执行（含沙箱、权限控制） |
| `write_stdin` | `UnifiedExecHandler` | 向运行中进程的 stdin 写入数据 |
| `apply_patch` | `ApplyPatchHandler` | 结构化代码编辑（Tree-sitter / Lark 语法） |
| `read_file` | `ReadFileHandler` | 文件读取（支持 offset/limit/mode） |
| `grep_files` | `GrepFilesHandler` | 文件内容搜索 |
| `list_dir` | `ListDirHandler` | 目录列表 |
| `view_image` | `ViewImageHandler` | 图片查看 |
| `js_repl` | `JsReplHandler` | JavaScript REPL（Node.js 内核，持久绑定） |
| `js_repl_reset` | `JsReplResetHandler` | 重置 JS REPL 状态 |
| `plan` / `update_plan` | `PlanHandler` | 协作模式计划工具 |
| `artifacts` | `ArtifactsHandler` | 制品管理 |

### 9.2 用户交互与发现工具

| 工具名称 | Handler | 说明 |
|----------|---------|------|
| `request_user_input` | `RequestUserInputHandler` | 请求用户输入 |
| `request_permissions` | `RequestPermissionsHandler` | 请求沙箱权限提升 |
| `_tool_search` | `ToolSearchHandler` | 工具发现搜索 |
| `_tool_suggest` | `ToolSuggestHandler` | 工具建议 |

### 9.3 多代理协作工具

当 `config.collab_tools` 启用时注册：

| 工具名称 | Handler | 说明 |
|----------|---------|------|
| `spawn_agent` | `SpawnAgentHandler` | 创建子代理（参数：`message`/`items`、`agent_type`、`model`、`fork_context`） |
| `send_input` | `SendInputHandler` | 向子代理发送消息（支持 `interrupt` 中断当前任务） |
| `wait_agent` | `WaitAgentHandler` | 等待子代理完成（超时：min 10s / default 30s / max 1h） |
| `close_agent` | `CloseAgentHandler` | 关闭不再需要的子代理 |
| `resume_agent` | `ResumeAgentHandler` | 恢复已关闭的子代理 |

### 9.4 批量任务与 MCP 工具

| 工具名称 | Handler | 说明 |
|----------|---------|------|
| `spawn_agents_on_csv` | `BatchJobHandler` | 基于 CSV 批量创建 Agent 任务 |
| `report_agent_job_result` | `BatchJobHandler` | 报告批量任务结果（条件注册） |
| `list_mcp_resources` | `McpResourceHandler` | 列出 MCP 资源 |
| `read_mcp_resource` | `McpResourceHandler` | 读取 MCP 资源 |
| 动态 MCP 工具 | `McpHandler` | 通过 MCP 协议注册的动态工具 |
| 自定义动态工具 | `DynamicToolHandler` | `DynamicToolSpec` 注册的自定义工具 |

### 9.5 工具调用格式

工具调用以 OpenAI 的 function calling 格式记录：`arguments` 为 JSON 字符串，`call_id` 以 `call_` 前缀开头。工具结果在 `function_call_output` 事件中返回，包含执行元数据（wall time、exit code、chunk ID、原始 token 数）。

> 📌 **重点**：与 Claude Code 的工具调用格式（Anthropic `tool_use` / `tool_result`）不同，Codex 使用 OpenAI Responses API 的 `function_call` / `function_call_output` 格式。Claude Code 的工具名更贴近用户操作（`Read`、`Write`、`Edit`、`Bash`），而 Codex 的工具名更偏向底层操作（`shell`、`exec_command`、`apply_patch`）。

---

## 10 数据解析要点

为 VibeLens 添加 Codex 会话解析支持时，需注意以下关键点：

1. **文件发现**：遍历 `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`，而非按项目目录。
2. **会话 ID 提取**：从文件名解析，格式为 `rollout-{timestamp}-{session-id}.jsonl`，session-id 是最后一个 UUID 段。也可从 `session_meta` 事件的 `payload.id` 获取。
3. **项目关联**：rollout 文件不直接包含项目路径编码。项目路径来自 `session_meta.payload.cwd` 或 `state_5.sqlite` 的 `threads.cwd`。
4. **消息提取**：过滤 `type == "response_item"` 的行，根据 `payload.type` 和 `payload.role` 区分用户、助手和系统消息。
5. **工具调用重组**：`function_call` 和 `function_call_output` 通过 `call_id` 关联。
6. **时间戳**：所有时间戳为 ISO 8601 字符串（与 Claude Code 的毫秒级 Unix epoch 不同）。
7. **子代理 rollout**：Codex 的多代理功能（`spawn_agent`）会为子代理创建独立的 rollout 文件，其 `session_meta.source` 为 `"sub_agent"`，包含 `parent_thread_id`、`depth`、`agent_nickname` 和 `agent_role` 信息。
8. **源类型识别**：通过 `session_meta.payload.source` 区分 `"cli"` 和 `"vscode"` 来源。

---

## 11 编程解析示例

### 11.1 Python：解析 Rollout JSONL 文件

以下示例展示如何用纯 Python 解析 Codex rollout 文件，提取会话元数据、消息和工具调用。这是 VibeLens `CodexParser` 的简化版本，体现了核心解析逻辑。

```python
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ToolCall:
    """解析后的工具调用记录。"""
    call_id: str
    name: str
    arguments: dict | str
    output: str = ""
    is_error: bool = False


@dataclass
class Message:
    """解析后的会话消息。"""
    role: str
    content: str
    timestamp: datetime | None = None
    model: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str = ""


@dataclass
class SessionInfo:
    """从 session_meta 提取的会话元数据。"""
    session_id: str = ""
    cwd: str = ""
    source: str = ""
    model_provider: str = ""
    cli_version: str = ""
    timestamp: str = ""


# Codex 工具输出的结构化前缀（包含 exit code 和 wall time）
OUTPUT_PREFIX_RE = re.compile(
    r"^(?:Chunk ID:.*\n)?Wall time:.*\n"
    r"Process exited with code (\d+)\n"
    r"Original token count:.*\nOutput:\n",
    re.DOTALL,
)


def parse_rollout_file(file_path: Path) -> tuple[SessionInfo, list[Message]]:
    """解析单个 Codex rollout JSONL 文件。

    Args:
        file_path: rollout-*.jsonl 文件路径。

    Returns:
        (SessionInfo, messages) 元组。
    """
    entries = _load_entries(file_path)
    session_info = _extract_session_info(entries)
    messages = _build_messages(entries)
    return session_info, messages


def _load_entries(file_path: Path) -> list[dict]:
    """逐行解析 JSONL 文件，跳过格式错误的行。"""
    entries = []
    for line in file_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 跳过损坏的行
    return entries


def _extract_session_info(entries: list[dict]) -> SessionInfo:
    """从 session_meta 事件提取会话元数据。"""
    for entry in entries:
        if entry.get("type") == "session_meta":
            payload = entry.get("payload", {})
            return SessionInfo(
                session_id=payload.get("id", ""),
                cwd=payload.get("cwd", ""),
                source=payload.get("source", ""),
                model_provider=payload.get("model_provider", ""),
                cli_version=payload.get("cli_version", ""),
                timestamp=payload.get("timestamp", ""),
            )
    return SessionInfo()


def _collect_tool_outputs(entries: list[dict]) -> dict[str, dict]:
    """第一遍扫描：构建 call_id → 工具结果映射表。

    预先收集所有 function_call_output，使后续主循环可以
    在遇到 function_call 时 O(1) 查找对应结果。
    """
    outputs: dict[str, dict] = {}
    for entry in entries:
        if entry.get("type") != "response_item":
            continue
        payload = entry.get("payload", {})
        if payload.get("type") != "function_call_output":
            continue
        call_id = payload.get("call_id", "")
        if not call_id:
            continue
        raw_output = payload.get("output", "")
        cleaned, is_error = _parse_tool_output(raw_output)
        outputs[call_id] = {"output": cleaned, "is_error": is_error}
    return outputs


def _build_messages(entries: list[dict]) -> list[Message]:
    """第二遍扫描：构建有序消息列表，关联工具调用。"""
    tool_outputs = _collect_tool_outputs(entries)
    messages: list[Message] = []
    pending_tools: list[ToolCall] = []
    current_model = ""

    for entry in entries:
        entry_type = entry.get("type", "")
        timestamp = _parse_timestamp(entry.get("timestamp"))
        payload = entry.get("payload", {})

        # turn_context 更新当前模型名
        if entry_type == "turn_context":
            current_model = payload.get("model", current_model)
            continue

        if entry_type == "response_item":
            payload_type = payload.get("type", "")

            if payload_type == "message":
                role = payload.get("role", "")
                if role not in ("user", "assistant"):
                    continue  # 跳过 developer 角色（系统指令）
                # 消息边界：将缓存的工具调用附加到上一条 assistant 消息
                _flush_pending_tools(messages, pending_tools)
                content = _extract_text(payload)
                messages.append(Message(
                    role=role,
                    content=content,
                    timestamp=timestamp,
                    model=current_model if role == "assistant" else "",
                ))

            elif payload_type == "function_call":
                call_id = payload.get("call_id", "")
                result = tool_outputs.get(call_id, {})
                arguments = payload.get("arguments", "")
                try:
                    parsed_args = json.loads(arguments)
                except (json.JSONDecodeError, TypeError):
                    parsed_args = arguments
                pending_tools.append(ToolCall(
                    call_id=call_id,
                    name=payload.get("name", "unknown"),
                    arguments=parsed_args,
                    output=result.get("output", ""),
                    is_error=result.get("is_error", False),
                ))

    # 清空最后一批工具调用
    _flush_pending_tools(messages, pending_tools)
    return messages


def _flush_pending_tools(
    messages: list[Message],
    pending_tools: list[ToolCall],
) -> None:
    """将缓存的工具调用附加到最近的 assistant 消息。"""
    if not pending_tools:
        return
    for msg in reversed(messages):
        if msg.role == "assistant":
            msg.tool_calls.extend(pending_tools)
            break
    pending_tools.clear()


def _extract_text(payload: dict) -> str:
    """从 message payload 提取纯文本内容。

    Codex 使用 input_text（用户）和 output_text（助手），
    与 Claude Code 统一的 text 类型不同。
    """
    content = payload.get("content", [])
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") in ("input_text", "output_text"):
            text = block.get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts)


def _parse_tool_output(raw: str) -> tuple[str, bool]:
    """解析结构化工具输出，剥离 Codex 元数据前缀。"""
    if not raw:
        return "", False
    match = OUTPUT_PREFIX_RE.match(raw)
    if not match:
        return raw, False
    exit_code = int(match.group(1))
    return raw[match.end():], exit_code != 0


def _parse_timestamp(ts_str: str | None) -> datetime | None:
    """解析 ISO 8601 时间戳字符串。"""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return None


# ─── 使用示例 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path

    rollout_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not rollout_path or not rollout_path.exists():
        print("Usage: python parse_codex.py <rollout-file.jsonl>")
        sys.exit(1)

    info, msgs = parse_rollout_file(rollout_path)
    print(f"Session:  {info.session_id}")
    print(f"Project:  {info.cwd}")
    print(f"Source:   {info.source}")
    print(f"CLI:      {info.cli_version}")
    print(f"Messages: {len(msgs)}")
    print()

    for msg in msgs:
        preview = msg.content[:80].replace("\n", " ")
        tool_info = f" [{len(msg.tool_calls)} tools]" if msg.tool_calls else ""
        model_info = f" ({msg.model})" if msg.model else ""
        print(f"  [{msg.role}]{model_info}{tool_info}: {preview}...")
```

**运行输出示例：**

```
Session:  019ced27-1efa-78f0-936a-69a9afac75fa
Project:  /Users/username/my-project
Source:   cli
CLI:      0.114.0
Messages: 8

  [user]: What's your advantages compared to others?...
  [assistant] (gpt-5.4): The practical advantages here are...
  [user]: Can you show me the project structure?...
  [assistant] (gpt-5.4) [2 tools]: Let me check the project structure for you...
  [user]: Fix the bug in main.py...
  [assistant] (gpt-5.4) [1 tools]: I'll fix the issue. Let me first read the fi...
  [user]: Thanks, looks good...
  [assistant] (gpt-5.4): You're welcome! The fix addresses the root cause...
```

### 11.2 Python：发现和遍历所有会话文件

```python
import os
import re
from pathlib import Path

# Codex 默认根目录（可通过 CODEX_HOME 环境变量覆盖）
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
SESSIONS_DIR = CODEX_HOME / "sessions"
ROLLOUT_PATTERN = re.compile(
    r"^rollout-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})-"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)


def discover_rollout_files(sessions_dir: Path | None = None) -> list[Path]:
    """遍历 sessions/YYYY/MM/DD/ 目录结构，发现所有 rollout 文件。

    按创建时间降序排列（最新的在前）。
    """
    root = sessions_dir or SESSIONS_DIR
    if not root.exists():
        return []

    rollout_files = []
    for year_dir in sorted(root.iterdir(), reverse=True):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.iterdir(), reverse=True):
            if not month_dir.is_dir():
                continue
            for day_dir in sorted(month_dir.iterdir(), reverse=True):
                if not day_dir.is_dir():
                    continue
                for f in sorted(day_dir.iterdir(), reverse=True):
                    if ROLLOUT_PATTERN.match(f.name):
                        rollout_files.append(f)
    return rollout_files


def extract_session_id_from_filename(filename: str) -> str | None:
    """从 rollout 文件名提取 session ID (UUID)。"""
    match = ROLLOUT_PATTERN.match(filename)
    return match.group(2) if match else None
```

### 11.3 Python：查询 SQLite 元数据

```python
import sqlite3
from pathlib import Path


def query_threads(db_path: Path, limit: int = 20) -> list[dict]:
    """查询 state_5.sqlite 获取线程元数据。

    Args:
        db_path: state_5.sqlite 文件路径。
        limit: 返回的最大记录数。

    Returns:
        按 updated_at 降序排列的线程元数据列表。
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        """
        SELECT id, rollout_path, cwd, title, source,
               model_provider, tokens_used, cli_version,
               created_at, updated_at, git_branch
        FROM threads
        WHERE archived = 0 AND has_user_event = 1
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# 使用示例
if __name__ == "__main__":
    db = Path.home() / ".codex" / "state_5.sqlite"
    if db.exists():
        for thread in query_threads(db, limit=5):
            print(f"{thread['id'][:8]}... | {thread['cwd']} | {thread['title'][:50]}")
```

---

## 12 典型数据规模参考

了解 Codex 本地数据的典型规模有助于设计高效的解析和分析工具。

### 12.1 文件大小参考

| 文件/资源 | 典型大小 | 说明 |
|-----------|----------|------|
| `history.jsonl` | 5 KB ~ 500 KB | 每行约 150 ~ 300 bytes，活跃用户 1000+ 条 |
| 单个 rollout 文件（短会话） | 10 KB ~ 50 KB | 3~5 轮对话，无复杂工具调用 |
| 单个 rollout 文件（中等会话） | 100 KB ~ 500 KB | 10~20 轮对话，包含文件编辑和命令执行 |
| 单个 rollout 文件（长会话） | 1 MB ~ 10 MB | 50+ 轮对话，大量代码修改，含上下文压缩 |
| 子代理 rollout | 20 KB ~ 200 KB | 通常比主代理小，单一任务聚焦 |
| `state_5.sqlite` | 100 KB ~ 5 MB | 取决于会话总数和元数据丰富程度 |
| `logs_1.sqlite` | 1 MB ~ 50 MB | 积累的运行时日志，可定期清理 |
| `config.toml` | 0.5 KB ~ 3 KB | 用户配置，通常很小 |
| Shell snapshot `.sh` | 5 KB ~ 50 KB | 完整的 shell 环境快照 |
| `memories/` 目录 | 10 KB ~ 500 KB | 取决于会话历史积累 |

### 12.2 事件分布参考

以一个典型的 15 轮对话会话（含文件编辑和命令执行）为例：

| 事件类型 | 典型数量 | 占比 |
|----------|----------|------|
| `session_meta` | 1 | < 1% |
| `turn_context` | 15 | ~8% |
| `response_item` (message) | 30~45 | ~25% |
| `response_item` (function_call) | 20~40 | ~20% |
| `response_item` (function_call_output) | 20~40 | ~20% |
| `response_item` (reasoning) | 10~15 | ~8% |
| `event_msg` (task_started/complete) | 30 | ~15% |
| `event_msg` (其他) | 5~10 | ~5% |
| **总计** | **130~200 行** | 100% |

> 💡 **最佳实践**：解析大型 rollout 文件时，可以先读取前 10 行获取 `session_meta` 和首条 `user_message` 进行快速预览（源码中 `HEAD_RECORD_LIMIT = 10`），避免加载整个文件。对于列表展示场景，优先查询 `state_5.sqlite` 的 `threads` 表，仅在需要完整对话内容时才加载 rollout 文件。

---

## 13 Codex vs Claude Code 格式对比详表

以下表格从数据解析的角度对两种格式进行系统对比，帮助构建跨平台的统一解析器。

### 13.1 存储架构对比

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **根目录** | `~/.codex`（可通过 `CODEX_HOME` 覆盖） | `~/.claude`（固定） |
| **配置格式** | TOML (`config.toml`) | JSON (`settings.json`) |
| **会话文件组织** | 按日期 `sessions/YYYY/MM/DD/` | 按项目 `projects/{encoded-path}/` |
| **文件命名** | `rollout-{timestamp}-{uuid}.jsonl` | `{uuid}.jsonl` |
| **全局索引** | `history.jsonl`（简洁三字段） | `history.jsonl`（含 project、pastedContents） |
| **结构化索引** | `state_5.sqlite`（SQLite） | 无（纯文件系统） |
| **自定义指令** | `AGENTS.md` | `CLAUDE.md` |
| **UUID 版本** | v7（时间戳有序） | v4（随机） |

### 13.2 JSONL 行格式对比

```
Codex 每行结构:
┌──────────────────────────────────────────────────────────┐
│ { "timestamp": "ISO-8601",                               │
│   "type": "response_item|event_msg|session_meta|...",    │
│   "payload": { ... } }                                   │
└──────────────────────────────────────────────────────────┘

Claude Code 每行结构:
┌──────────────────────────────────────────────────────────┐
│ { "type": "user|assistant|progress|...",                  │
│   "uuid": "UUID-v4",                                     │
│   "sessionId": "UUID-v4",                                │
│   "parentUuid": "UUID-v4",                               │
│   "timestamp": 1767734674932,                            │
│   "message": { "role": "...", "content": [...] } }       │
└──────────────────────────────────────────────────────────┘
```

### 13.3 消息与工具调用格式对比

| 特性 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **时间戳格式** | ISO 8601 字符串 `"2026-03-14T16:24:52.480Z"` | 毫秒级 Unix epoch `1767734674932` |
| **角色系统** | `developer` / `user` / `assistant` | `user` / `assistant` |
| **系统指令** | `developer` 角色的 `message` | 隐含在助手消息的 `system` 上下文中 |
| **消息内容类型** | `input_text`（用户）/ `output_text`（助手） | 统一 `text` 类型 |
| **消息链接** | `turn_id` 关联同一轮次 | `parentUuid` 链接父子消息 |
| **工具调用** | 独立的 `function_call` 行 | 嵌入 assistant message 的 `content` 数组 |
| **工具结果** | 独立的 `function_call_output` 行 | 嵌入 user message 的 `content` 数组 |
| **工具配对键** | `call_id`（格式 `call_xxx`） | `tool_use_id`（格式 `toolu_xxx`） |
| **推理记录** | 加密 `encrypted_content` | 明文 `thinking` 块 |
| **Token 统计** | `event_msg/token_count` 事件（每轮累计） | 内嵌于 assistant message 的 `usage` 字段 |

### 13.4 跨平台解析策略

```
┌─────────────────────────────────────────────────────────────────┐
│                    统一解析器设计                                  │
└─────────────────────────────────────────────────────────────────┘

       ┌──────────┐          ┌───────────┐          ┌───────────┐
       │  Codex   │          │ Claude    │          │ Dataclaw  │
       │ Rollout  │          │ Code JSONL│          │ Export    │
       └────┬─────┘          └────┬──────┘          └────┬──────┘
            │                     │                      │
            ▼                     ▼                      ▼
   ┌────────────────┐   ┌────────────────┐   ┌────────────────────┐
   │ CodexParser    │   │ ClaudeCode     │   │ DataclawParser     │
   │                │   │ Parser         │   │                    │
   │ • 两遍扫描     │   │ • parentUuid   │   │ • 单行完整会话     │
   │ • call_id 配对 │   │   消息树重建   │   │ • 预计算 stats     │
   │ • turn_context │   │ • tool_use/    │   │ • 无工具输出       │
   │   模型追踪     │   │   tool_result  │   │   (隐私清洗)       │
   │ • ISO-8601 ts  │   │   配对         │   │ • ISO-8601 ts      │
   │                │   │ • ms-epoch ts  │   │                    │
   └───────┬────────┘   └───────┬────────┘   └──────────┬─────────┘
           │                    │                       │
           └────────────────────┼───────────────────────┘
                                │
                                ▼
                  ┌──────────────────────────┐
                  │  Unified Data Models     │
                  │  ┌────────────────────┐  │
                  │  │ SessionSummary     │  │
                  │  │ • session_id       │  │
                  │  │ • project_id       │  │
                  │  │ • message_count    │  │
                  │  │ • tool_call_count  │  │
                  │  │ • models           │  │
                  │  └────────────────────┘  │
                  │  ┌────────────────────┐  │
                  │  │ Message            │  │
                  │  │ • role             │  │
                  │  │ • content          │  │
                  │  │ • tool_calls[]     │  │
                  │  │ • usage            │  │
                  │  └────────────────────┘  │
                  └──────────────────────────┘
```

> 📌 **重点**：构建跨平台解析器的关键挑战在于工具调用的结构差异。Codex 的 `function_call` 和 `function_call_output` 是独立的 rollout 行，需要通过 `call_id` 在后处理阶段配对；而 Claude Code 的 `tool_use` 和 `tool_result` 分别嵌入在 assistant 和 user message 的 `content` 数组中，通过相邻消息的 `parentUuid` 自然关联。统一模型层应抽象这些差异，将两种格式归一化为 `ToolCall(name, input, output, is_error)` 结构。

---

## 参考资料

- [Codex CLI 官方文档](https://developers.openai.com/codex/cli/)
- [Codex CLI 命令行参考](https://developers.openai.com/codex/cli/reference)
- [Codex 配置基础](https://developers.openai.com/codex/config-basic/)
- [Codex 高级配置](https://developers.openai.com/codex/config-advanced/)
- [Codex AGENTS.md 指南](https://developers.openai.com/codex/guides/agents-md/)
- [Codex CLI 功能特性](https://developers.openai.com/codex/cli/features/)
- [Codex GitHub 仓库](https://github.com/openai/codex)

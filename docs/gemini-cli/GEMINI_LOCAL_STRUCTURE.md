# Gemini CLI 本地数据管理系统

| 条目 | 内容 |
|------|------|
| **主题** | Gemini CLI 工具的本地数据存储和管理机制 |
| **存储位置** | `~/.gemini` 目录（用户主目录下的 .gemini 隐藏文件夹） |
| **适用版本** | Gemini CLI（Google 官方开源版本） |
| **平台** | macOS、Linux、Windows |

---

## 1 背景与设计思想

Gemini CLI 是 Google 推出的开源终端 AI 代理工具，将 Gemini 模型的能力直接带入终端环境。与 Claude Code 类似，Gemini CLI 需要在本地存储会话数据、认证凭证、配置信息和临时文件。其本地数据采用**项目隔离**策略：每个项目通过唯一的 project hash 或短名映射到独立的存储空间，会话数据以 JSON 格式保存，支持自动保存和恢复。

与 Claude Code 的关键区别：

| 维度 | Claude Code (`~/.claude`) | Gemini CLI (`~/.gemini`) |
|------|--------------------------|--------------------------|
| **会话格式** | JSONL（每行一条事件） | JSON（完整会话对象） |
| **会话索引** | `history.jsonl` 全局索引 | `logs.json` 按项目记录用户输入 |
| **项目标识** | 路径编码（`/` → `-`） | SHA-256 hash + 短名映射 |
| **认证方式** | API Key / OAuth | Google OAuth（个人/企业） |
| **思考过程** | `thinking` content block | `thoughts` 数组（带 subject/description） |
| **工具调用** | `tool_use` content block | `toolCalls` 数组（内嵌结果） |
| **子代理** | Agent tool（spawns subagent） | `cli_help` 等内置子代理，独立 session 文件 |

> 📌 **重点**：Gemini CLI 的会话数据结构比 Claude Code 更扁平——工具调用和结果内嵌在同一条消息中，而非分散在相邻的 user/assistant 消息对中。

---

## 2 目录结构总览

Gemini CLI 的本地存储结构如下：

```
~/.gemini/
├── installation_id                # 安装唯一标识（UUID）
├── google_accounts.json           # Google 账号配置
├── oauth_creds.json               # OAuth 认证凭证（敏感）
├── settings.json                  # 用户全局配置
├── state.json                     # 应用状态（如提示显示计数）
├── projects.json                  # 项目路径 → 短名映射
├── trustedFolders.json            # 受信任文件夹列表
├── GEMINI.md                      # 全局自定义指令（可选）
│
├── commands/                      # 全局自定义命令（可选）
│   └── [command-name].toml        # TOML 格式的命令定义
│
├── history/                       # 会话历史索引
│   └── {project-short-name}/
│       └── .project_root          # 记录项目绝对路径
│
└── tmp/                           # 临时文件和运行时数据
    ├── bin/
    │   └── rg                     # 内置 ripgrep 二进制
    └── {project-short-name}/
        ├── .project_root          # 记录项目绝对路径
        ├── logs.json              # 用户输入日志
        ├── shell_history          # Shell 命令执行历史
        └── chats/                 # 会话数据文件
            ├── session-{timestamp}-{session-id-prefix}.json  # 主会话
            └── session-{timestamp}-{session-id-prefix}.json  # 子代理会话
```

**项目命名约定**：

项目目录名使用 `projects.json` 中定义的短名（如 `agent-guideline`），而非路径编码。`projects.json` 维护完整路径到短名的映射。`history/` 和 `tmp/` 下的子目录使用相同的短名。

---

## 3 认证与账号管理

### 3.1 installation_id

位置：`~/.gemini/installation_id`

纯文本文件，存储一个 UUID v4，用于标识当前安装实例。

```
61de2480-e02d-4f7d-9565-8780c973631f
```

### 3.2 google_accounts.json

位置：`~/.gemini/google_accounts.json`

管理当前活跃的 Google 账号和历史账号。

```json
{
  "active": "user@gmail.com",
  "old": []
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `active` | String | 当前活跃的 Google 账号邮箱 |
| `old` | Array | 曾经使用过的历史账号列表 |

### 3.3 oauth_creds.json

位置：`~/.gemini/oauth_creds.json`（权限 `600`，仅用户可读写）

存储 Google OAuth 2.0 凭证，用于 API 认证。

**字段结构（不展示实际值）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `access_token` | String | OAuth 访问令牌（短期有效） |
| `refresh_token` | String | 刷新令牌（用于获取新的 access_token） |
| `scope` | String | 授权范围（包含 Gemini API 相关权限） |
| `token_type` | String | 令牌类型（通常为 `Bearer`） |
| `id_token` | String | JWT 格式的身份令牌 |
| `expiry_date` | Number | 令牌过期时间（毫秒级 Unix 时间戳） |

> ⚠️ **安全提醒**：此文件包含敏感凭证，不应被提交到版本控制。Gemini CLI 默认将其权限设为 `600`。

---

## 4 配置系统

### 4.1 settings.json —— 用户配置

位置：`~/.gemini/settings.json`（全局）或 `<project>/.gemini/settings.json`（项目级）

控制 Gemini CLI 的行为、外观和安全设置。

**实际文件示例：**

```json
{
  "security": {
    "auth": {
      "selectedType": "oauth-personal"
    }
  },
  "ui": {
    "theme": "Default Light"
  }
}
```

**完整配置分类：**

| 分类 | 配置项 | 说明 |
|------|--------|------|
| **安全** | `security.auth.selectedType` | 认证方式：`oauth-personal`（个人 OAuth）、`oauth-adc`（应用默认凭证）、`api-key`（API 密钥） |
| **安全** | `security.sandbox` | 沙箱设置，控制工具执行的隔离级别 |
| **UI** | `ui.theme` | 颜色主题（`Default Light`、`Default Dark` 等自定义主题） |
| **UI** | `ui.outputFormat` | 输出格式：`text`（默认）或 `json` |
| **UI** | `ui.showThinking` | 思考过程显示模式：`off` 或 `full` |
| **通用** | `general.editor` | 首选编辑器（用于打开文件） |
| **通用** | `general.vimKeybindings` | 是否启用 Vim 键绑定 |
| **工具** | `tools.excludeTools` | 排除的工具列表 |
| **MCP** | `mcpServers` | MCP 服务器配置（同 Claude Code 的 MCP 概念） |
| **遥测** | `telemetry` | 日志和指标收集设置 |

**配置优先级（从低到高）：**

1. 应用内置默认值
2. 系统默认文件（`/Library/Application Support/GeminiCli/system-defaults.json`）
3. 用户全局配置（`~/.gemini/settings.json`）
4. 项目配置（`<project>/.gemini/settings.json`）
5. 系统配置文件（覆盖所有）
6. 环境变量（`.env` 文件）
7. 命令行参数（最高优先级）

> 💡 **JSON Schema**：可引用官方 schema 进行编辑器自动补全验证：`https://raw.githubusercontent.com/google-gemini/gemini-cli/main/schemas/settings.schema.json`

### 4.2 state.json —— 应用状态

位置：`~/.gemini/state.json`

记录 CLI 的运行状态（非用户配置）。

```json
{
  "tipsShown": 4
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `tipsShown` | Number | 已显示的使用提示数量（用于控制新手引导频率） |

### 4.3 projects.json —— 项目映射

位置：`~/.gemini/projects.json`

维护项目绝对路径到短名的映射关系。

```json
{
  "projects": {
    "/Users/JinghengYe/Documents/Projects/Agent-Guideline": "agent-guideline"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `projects` | Object | 键为项目绝对路径，值为项目短名（用作 `history/` 和 `tmp/` 下的目录名） |

短名通常取项目目录的最后一级名称（如 `Agent-Guideline` → `agent-guideline`）。短名用于构建会话存储路径，替代 Claude Code 中对完整路径的 `-` 编码方案。

### 4.4 trustedFolders.json —— 受信任文件夹

位置：`~/.gemini/trustedFolders.json`

控制哪些项目目录被信任，决定 CLI 是否加载项目级配置。

```json
{
  "/Users/JinghengYe/Documents/Projects/Agent-Guideline": "TRUST_FOLDER"
}
```

| 值 | 说明 |
|------|------|
| `"TRUST_FOLDER"` | 完全信任，加载项目配置和 `.env` |
| `"UNTRUST_FOLDER"` | 不信任，以安全模式运行（忽略项目 `.gemini/settings.json` 和 `.env`） |

**安全模式限制：** 当文件夹不受信任时，CLI 会禁用项目级配置加载、环境变量加载和自定义工具，仅使用全局配置运行。

---

## 5 会话数据存储机制

### 5.1 会话存储架构

Gemini CLI 的会话存储与 Claude Code 的"两层索引"不同，采用**项目隔离 + 双文件**策略：

1. **用户输入日志（logs.json）**：记录用户在各会话中发送的消息，类似简化版索引。
2. **完整会话文件（chats/session-*.json）**：每个会话保存为独立的 JSON 文件（非 JSONL），包含完整的对话内容、工具调用和 token 统计。

关键差异：

| 维度 | Claude Code | Gemini CLI |
|------|------------|------------|
| 索引 | 全局 `history.jsonl` | 按项目 `logs.json` |
| 会话文件 | JSONL（逐行追加） | JSON（完整对象） |
| 文件命名 | `{uuid}.jsonl` | `session-{timestamp}-{session-id-prefix}.json` |
| 工具结果 | 分散在相邻消息中 | 内嵌在 `toolCalls[].result` 中 |

### 5.2 logs.json —— 用户输入日志

位置：`~/.gemini/tmp/{project-short-name}/logs.json`

记录用户在该项目中的所有输入消息，跨会话累积。

```json
[
  {
    "sessionId": "97253fa9-55cd-4a38-b241-17369143df91",
    "messageId": 0,
    "type": "user",
    "message": "This is my first use of Codex but I have used other coding agents.",
    "timestamp": "2026-03-14T16:40:26.486Z"
  },
  {
    "sessionId": "97253fa9-55cd-4a38-b241-17369143df91",
    "messageId": 1,
    "type": "user",
    "message": "Create a README file for this project.",
    "timestamp": "2026-03-14T16:47:33.371Z"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `sessionId` | String | 会话 UUID |
| `messageId` | Number | 消息序号（从 0 开始，按发送顺序递增） |
| `type` | String | 消息类型（始终为 `"user"`） |
| `message` | String | 用户输入的原始文本 |
| `timestamp` | String | ISO-8601 格式时间戳 |

> 💡 `logs.json` 仅记录用户输入，不包含模型回复。它的作用类似于 Claude Code 的 `history.jsonl`，但仅存储文本而不是会话元信息。

### 5.3 .project_root —— 项目根路径标记

位置：`~/.gemini/history/{project}/` 和 `~/.gemini/tmp/{project}/`

纯文本文件，存储该项目的绝对路径：

```
/Users/JinghengYe/Documents/Projects/Agent-Guideline
```

用于将短名目录反向映射回实际的项目路径。

### 5.4 会话 JSON 文件格式（核心数据）

位置：`~/.gemini/tmp/{project}/chats/session-{timestamp}-{session-id-prefix}.json`

**文件命名规则：**
- `{timestamp}`：会话创建时间，格式为 `YYYY-MM-DDTHH-MM`（注意使用 `-` 而非 `:`）
- `{session-id-prefix}`：sessionId 的前 8 位（UUID 前缀）
- 示例：`session-2026-03-14T16-40-97253fa9.json`

**顶层结构：**

```json
{
  "sessionId": "97253fa9-55cd-4a38-b241-17369143df91",
  "projectHash": "28d80dc91fa5879b6716792896dea2dc41cebbc37ef4003e20a54f390d6cfd48",
  "startTime": "2026-03-14T16:40:26.798Z",
  "lastUpdated": "2026-03-14T16:47:58.600Z",
  "kind": "main",
  "messages": [...]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `sessionId` | String | 会话唯一标识（UUID v4） |
| `projectHash` | String | 项目路径的 SHA-256 哈希值 |
| `startTime` | String | 会话开始时间（ISO-8601） |
| `lastUpdated` | String | 最后更新时间（ISO-8601） |
| `kind` | String | 会话类型：`"main"`（主会话）或 `"subagent"`（子代理会话） |
| `messages` | Array | 消息数组（见下文） |

> 📌 **注意**：同一个 `sessionId` 可能对应多个 JSON 文件——主会话（`kind: "main"`）和子代理会话（`kind: "subagent"`）共享同一 `sessionId`，但保存在不同文件中。

---

## 6 消息格式详解

### 6.1 用户消息（User Message）

```json
{
  "id": "2cfde2f1-13e0-4d5c-8b8d-6ea64c935cfd",
  "timestamp": "2026-03-14T16:40:26.798Z",
  "type": "user",
  "content": [
    {
      "text": "This is my first use of Codex but I have used other coding agents."
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String | 消息唯一标识（UUID v4） |
| `timestamp` | String | ISO-8601 时间戳 |
| `type` | String | 固定为 `"user"` |
| `content` | Array | 内容块数组，每个元素包含 `text` 字段 |

**与 Claude Code 的区别：** Gemini CLI 的用户消息不包含 `cwd`、`gitBranch`、`parentUuid`、`isSidechain` 等上下文字段。消息关联通过在 `messages` 数组中的位置顺序隐式表达，而非 UUID 链接。

### 6.2 助手消息（Gemini Message）

#### 纯文本回复

```json
{
  "id": "ddc1c20a-06b4-4d9c-91fb-ff187714cc8b",
  "timestamp": "2026-03-14T16:42:06.613Z",
  "type": "gemini",
  "content": "Welcome to Gemini CLI! Compared to other coding agents...",
  "thoughts": [
    {
      "subject": "Commencing Next Task",
      "description": "I'm now focused on the next step...",
      "timestamp": "2026-03-14T16:41:29.894Z"
    }
  ],
  "tokens": {
    "input": 8385,
    "output": 349,
    "cached": 5749,
    "thoughts": 159,
    "tool": 0,
    "total": 8893
  },
  "model": "gemini-3-flash-preview"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String | 消息唯一标识 |
| `timestamp` | String | ISO-8601 时间戳 |
| `type` | String | 固定为 `"gemini"` |
| `content` | String | 模型回复的文本内容（可为空字符串，当仅有工具调用时） |
| `thoughts` | Array | 思考过程数组（见 6.3 节） |
| `tokens` | Object | Token 使用统计（见 6.4 节） |
| `model` | String | 使用的模型标识（如 `"gemini-3-flash-preview"`） |
| `toolCalls` | Array | 工具调用数组（可选，见 6.5 节） |

**与 Claude Code 的关键区别：**

| 维度 | Claude Code | Gemini CLI |
|------|------------|------------|
| 消息类型标识 | `type: "assistant"` | `type: "gemini"` |
| 内容格式 | `content` 为 Array（content blocks） | `content` 为 String |
| 思考过程 | `thinking` content block 内嵌在 content 数组中 | 独立的 `thoughts` 数组 |
| 工具调用 | `tool_use` content block 内嵌在 content 数组中 | 独立的 `toolCalls` 数组 |
| 停止原因 | `stop_reason` 字段 | 无对应字段 |
| API 请求 ID | `requestId` 字段 | 无对应字段 |

#### 包含工具调用的回复

```json
{
  "id": "6951e895-f598-4ca8-9f79-d0589e9d0a97",
  "timestamp": "2026-03-14T16:47:38.315Z",
  "type": "gemini",
  "content": "I will read the CLAUDE.md file to understand the project's purpose.",
  "thoughts": [...],
  "tokens": {...},
  "model": "gemini-3-flash-preview",
  "toolCalls": [
    {
      "id": "read_file_1773506858312_0",
      "name": "read_file",
      "args": {
        "file_path": "CLAUDE.md"
      },
      "result": [...],
      "status": "success",
      "timestamp": "2026-03-14T16:47:49.012Z",
      "resultDisplay": {...},
      "displayName": "ReadFile",
      "description": "Reads and returns the content of a specified file...",
      "renderOutputAsMarkdown": true
    }
  ]
}
```

### 6.3 思考过程（Thoughts）

Gemini CLI 的思考过程使用独立的 `thoughts` 数组，每个元素包含主题和描述：

```json
{
  "subject": "Exploring Feature Advantages",
  "description": "I've been considering the potential of 'Auto routing' and 'Pro routing' features...",
  "timestamp": "2026-03-14T16:41:47.191Z"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `subject` | String | 思考主题的简短标题 |
| `description` | String | 思考过程的详细描述 |
| `timestamp` | String | 该思考步骤的时间戳 |

**与 Claude Code 的区别：** Claude Code 的思考是纯文本块（`type: "thinking"`），嵌入在 `content` 数组中；Gemini CLI 的思考是结构化对象，带有 `subject` 标题，方便分段展示和检索。

一条 gemini 消息可包含多个 thoughts 条目，代表多轮递进式推理。

### 6.4 Token 使用统计

```json
{
  "input": 8385,
  "output": 349,
  "cached": 5749,
  "thoughts": 159,
  "tool": 0,
  "total": 8893
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `input` | Number | 输入 token 数 |
| `output` | Number | 输出 token 数 |
| `cached` | Number | 缓存命中的 token 数（类似 Claude Code 的 `cache_read_input_tokens`） |
| `thoughts` | Number | 思考过程消耗的 token 数 |
| `tool` | Number | 工具调用消耗的 token 数 |
| `total` | Number | 总 token 数 |

**与 Claude Code 的区别：** Gemini CLI 的 token 统计更扁平（6 个字段），而 Claude Code 使用嵌套结构（`usage.cache_creation.ephemeral_5m_input_tokens` 等），并区分缓存创建和缓存读取。

### 6.5 工具调用（Tool Calls）

工具调用是 Gemini CLI 会话数据中最丰富的部分。每个工具调用包含完整的输入、结果和元信息。

**完整的工具调用结构：**

```json
{
  "id": "write_file_1773506869302_0",
  "name": "write_file",
  "args": {
    "file_path": "README.md",
    "content": "# Agent-Guideline: A collection of tools..."
  },
  "result": [
    {
      "functionResponse": {
        "id": "write_file_1773506869302_0",
        "name": "write_file",
        "response": {
          "output": "Successfully created and wrote to new file: ..."
        }
      }
    }
  ],
  "status": "success",
  "timestamp": "2026-03-14T16:47:57.344Z",
  "resultDisplay": {
    "fileDiff": "Index: README.md\n===...",
    "fileName": "README.md",
    "filePath": "/Users/.../README.md",
    "originalContent": "",
    "newContent": "# Agent-Guideline: ...",
    "diffStat": {
      "model_added_lines": 1,
      "model_removed_lines": 0,
      "model_added_chars": 118,
      "model_removed_chars": 0,
      "user_added_lines": 0,
      "user_removed_lines": 0,
      "user_added_chars": 0,
      "user_removed_chars": 0
    },
    "isNewFile": true
  },
  "displayName": "WriteFile",
  "description": "Writes content to a specified file in the local filesystem.",
  "renderOutputAsMarkdown": true
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String | 工具调用 ID，格式为 `{tool_name}_{timestamp}_{index}` |
| `name` | String | 工具内部名称（如 `read_file`、`write_file`、`cli_help`） |
| `args` | Object | 工具参数（键值对） |
| `result` | Array | 工具执行结果，包含 `functionResponse` 对象 |
| `status` | String | 执行状态：`"success"` 或 `"error"` |
| `timestamp` | String | 工具执行完成时间 |
| `resultDisplay` | Object \| String | UI 展示用的结果数据（文件 diff、搜索结果等） |
| `displayName` | String | 工具在 UI 中的显示名称 |
| `description` | String | 工具的功能描述 |
| `renderOutputAsMarkdown` | Boolean | 结果是否应按 Markdown 渲染 |

**工具调用 ID 命名规则：** `{工具名}_{毫秒时间戳}_{序号}`，例如 `read_file_1773506858312_0`，其中序号用于区分同一轮次中的多个同名工具调用。

**与 Claude Code 的关键区别：**

| 维度 | Claude Code | Gemini CLI |
|------|------------|------------|
| 调用位置 | `tool_use` block 在 assistant 的 `content` 中 | `toolCalls` 数组在 gemini 消息顶层 |
| 结果位置 | 下一条 user 消息的 `tool_result` block | 同一 toolCall 的 `result` 字段（**内嵌**） |
| 结果格式 | `{ type: "tool_result", tool_use_id, content }` | `{ functionResponse: { id, name, response } }` |
| 展示信息 | 无（UI 自行渲染） | `resultDisplay` 包含 diff、统计等富数据 |
| 调用 ID | `toolu_` 前缀（Anthropic 分配） | `{tool}_{timestamp}_{index}`（本地生成） |

> 📌 **数据分析启示**：Gemini CLI 的工具调用数据自包含（调用和结果在同一对象中），解析时无需像 Claude Code 那样在相邻消息间匹配 `tool_use_id`。

**resultDisplay 的变体：**

- **文件操作**（`write_file`）：包含 `fileDiff`、`originalContent`、`newContent`、`diffStat`、`isNewFile`
- **文件读取**（`read_file`）：`resultDisplay` 为 String 类型（文件内容的文本表示）
- **子代理**（`cli_help`）：`resultDisplay` 为 String 类型（子代理回答的文本）

**diffStat 字段详解：**

```json
{
  "model_added_lines": 1,       // 模型添加的行数
  "model_removed_lines": 0,     // 模型删除的行数
  "model_added_chars": 118,     // 模型添加的字符数
  "model_removed_chars": 0,     // 模型删除的字符数
  "user_added_lines": 0,        // 用户修改后添加的行数
  "user_removed_lines": 0,      // 用户修改后删除的行数
  "user_added_chars": 0,        // 用户修改后添加的字符数
  "user_removed_chars": 0       // 用户修改后删除的字符数
}
```

此结构区分了模型提议的修改和用户实际接受/修改后的结果，有助于分析用户对模型建议的接受率。

---

## 7 子代理会话（Subagent Sessions）

### 7.1 子代理机制

Gemini CLI 支持将特定任务委托给子代理（如 `cli_help`），子代理在独立的会话文件中运行。

**子代理会话特征：**

- `kind` 字段为 `"subagent"`（主会话为 `"main"`）
- 与主会话共享同一个 `sessionId`
- 保存在独立的 JSON 文件中（文件名时间戳通常晚于主会话）
- 消息内容通常以系统指令开头（如 `"Your task is to answer the following question..."`)

**子代理会话示例：**

```json
{
  "sessionId": "97253fa9-55cd-4a38-b241-17369143df91",
  "projectHash": "28d80dc91fa5879b6716792896dea2dc41cebbc37ef4003e20a54f390d6cfd48",
  "startTime": "2026-03-14T16:41:31.246Z",
  "lastUpdated": "2026-03-14T16:41:59.718Z",
  "kind": "subagent",
  "messages": [
    {
      "id": "1b90460e-c155-45af-bd64-78fc0b12b899",
      "timestamp": "2026-03-14T16:41:31.246Z",
      "type": "user",
      "content": [
        {
          "text": "Your task is to answer the following question about Gemini CLI:\n<question>\nWhat are Gemini CLI's advantages?\n</question>"
        }
      ]
    },
    {
      "id": "03883956-39cb-4040-83f4-4137d358dc4b",
      "timestamp": "2026-03-14T16:41:34.290Z",
      "type": "gemini",
      "content": "",
      "thoughts": [
        {
          "subject": "Discovering Competitive Edges",
          "description": "I'm now digging into the documentation..."
        }
      ],
      "tokens": {
        "input": 2507,
        "output": 10,
        "cached": 0,
        "thoughts": 56,
        "tool": 0,
        "total": 2573
      },
      "model": "gemini-3-flash-preview"
    }
  ]
}
```

### 7.2 子代理执行上限

子代理有最大轮次限制。当超出限制时，系统会注入一条特殊的用户消息：

```json
{
  "type": "user",
  "content": [
    {
      "text": "You have exceeded the maximum number of turns. You have one final chance to complete the task..."
    }
  ]
}
```

### 7.3 与 Claude Code 子代理的区别

| 维度 | Claude Code | Gemini CLI |
|------|------------|------------|
| 触发方式 | `Agent` tool 显式启动 | 模型自动调用（如 `cli_help`） |
| 存储方式 | 同一 JSONL 文件中的嵌套事件 | 独立 JSON 文件（`kind: "subagent"`） |
| 会话关联 | 通过 `isSidechain` / `parentUuid` | 共享 `sessionId` + 不同 `kind` |
| 多模型支持 | 子代理可指定不同模型 | 子代理使用相同模型 |

---

## 8 GEMINI.md 指令系统

### 8.1 层级结构

Gemini CLI 使用与 Claude Code 的 `CLAUDE.md` 类似的指令文件系统，通过 `GEMINI.md` 文件向模型提供持久化的上下文和指令。

**加载顺序（从上到下，后者可覆盖前者）：**

1. `~/.gemini/GEMINI.md` —— 全局指令（适用于所有项目）
2. `<project-root>/GEMINI.md` —— 项目根目录指令
3. `<subdirectory>/GEMINI.md` —— 子目录指令（当工具访问该目录时自动加载）

所有找到的 GEMINI.md 文件会被拼接后发送给模型。

**管理命令：**

| 命令 | 说明 |
|------|------|
| `/memory show` | 显示当前加载的所有 GEMINI.md 内容 |
| `/memory reload` | 重新扫描和加载所有 GEMINI.md 文件 |

### 8.2 与 Claude Code 的区别

| 维度 | Claude Code (`CLAUDE.md`) | Gemini CLI (`GEMINI.md`) |
|------|--------------------------|--------------------------|
| 全局文件位置 | `~/.claude/CLAUDE.md` | `~/.gemini/GEMINI.md` |
| 项目文件位置 | `<project>/CLAUDE.md` | `<project>/GEMINI.md` |
| 子目录扫描 | 支持 | 支持（当工具访问时触发） |
| 管理命令 | 无专用命令 | `/memory show`、`/memory reload` |
| 加载时机 | 会话启动时 | 每次 prompt 发送时 |

---

## 9 自定义命令系统

### 9.1 命令定义

Gemini CLI 支持通过 TOML 文件定义自定义命令（类似 Claude Code 的 Skill 系统）。

**存储位置：**

| 类型 | 路径 | 作用域 |
|------|------|--------|
| 全局命令 | `~/.gemini/commands/` | 所有项目可用 |
| 项目命令 | `<project>/.gemini/commands/` | 仅当前项目可用 |

**命名规则：** 文件名决定命令名。子目录创建命名空间，路径分隔符转为 `:`。例如 `commands/git/commit.toml` → `/git:commit`。

**冲突解决：** 项目级命令优先于全局命令（同名时覆盖）。

### 9.2 与 Claude Code 的区别

| 维度 | Claude Code | Gemini CLI |
|------|------------|------------|
| 命令格式 | 内置 Skill 系统 | TOML 文件 |
| 调用方式 | `/<skill-name>` | `/<command-name>` |
| 命名空间 | 扁平 | 支持 `:` 分隔的层级命名 |
| 版本控制 | 不支持 | 项目命令可提交到 Git |

---

## 10 其他运行时数据

### 10.1 tmp/bin/ —— 内置工具

位置：`~/.gemini/tmp/bin/`

Gemini CLI 在此目录存放所需的外部二进制工具：

| 文件 | 说明 |
|------|------|
| `rg` | ripgrep（用于代码搜索） |

### 10.2 shell_history —— Shell 命令历史

位置：`~/.gemini/tmp/{project}/shell_history`

记录 Gemini CLI 在该项目中执行的所有 shell 命令。

### 10.3 .geminiignore —— 文件排除

位置：`<project>/.geminiignore`（项目根目录）

类似 `.gitignore` 的语法，用于排除特定文件或目录不被 Gemini CLI 的工具读取。与 `.gitignore` 的区别是：被 `.geminiignore` 排除的文件仍会被 Git 追踪。

适用场景：排除 `.env`、大型资源文件、数据集等不需要 AI 分析的内容。

---

## 11 会话生命周期与管理

### 11.1 自动保存

Gemini CLI 的会话在每次交互后自动保存，无需手动操作。保存内容包括：

- 所有用户 prompt 和模型响应
- 工具调用的输入和输出
- Token 使用统计
- 思考过程摘要

### 11.2 会话恢复

| 命令 | 说明 |
|------|------|
| `gemini --resume` / `gemini -r` | 恢复最近的会话 |
| `/chat save <tag>` | 将当前会话保存为命名标签 |
| `/chat resume <tag>` | 恢复命名标签的会话 |
| `/chat delete <tag>` | 删除命名标签的会话 |

已保存的命名会话存储为 `~/.gemini/tmp/{project}/chats/{tag}.json`。

### 11.3 检查点（Checkpointing）

检查点功能在 AI 工具修改文件系统前自动创建项目快照：

- 默认**禁用**，需在 `settings.json` 中启用
- 包含 Git 快照、完整会话状态、触发工具调用信息
- 使用 `/restore` 命令回滚到检查点

### 11.4 自动清理

Gemini CLI 自动清理过期的会话数据：

- 默认保留期限：**30 天**
- 可通过 `/settings` 命令或 `settings.json` 自定义保留策略

---

## 12 数据分析对比总结

从数据分析和 VibeLens 集成的角度，以下是 Claude Code 与 Gemini CLI 数据格式的对照表：

| 分析维度 | Claude Code 数据来源 | Gemini CLI 数据来源 |
|---------|---------------------|-------------------|
| **会话列表** | `~/.claude/history.jsonl` | `~/.gemini/tmp/{project}/logs.json` |
| **会话内容** | `~/.claude/projects/{path}/{uuid}.jsonl` | `~/.gemini/tmp/{project}/chats/session-*.json` |
| **模型信息** | `message.model` 字段 | `model` 字段（顶层） |
| **Token 统计** | `message.usage`（嵌套结构） | `tokens`（扁平结构） |
| **思考过程** | `content[type="thinking"].thinking` | `thoughts[].description` |
| **工具调用** | `content[type="tool_use"]` → 下一条 `tool_result` | `toolCalls[]`（调用+结果内嵌） |
| **文件修改** | 需从工具结果中提取 | `toolCalls[].resultDisplay.diffStat` |
| **子代理** | 同文件 `isSidechain` 标记 | 独立文件 `kind: "subagent"` |
| **用户接受率** | 需推断 | `diffStat` 区分 model vs user 修改 |
| **项目标识** | 路径编码（`/` → `-`） | `projects.json` 短名映射 |

> 💡 **VibeLens 集成建议**：Gemini CLI 的 `diffStat` 提供了模型修改 vs 用户修改的直接数据，可用于计算"建议接受率"——这是 Claude Code 数据中需要复杂推断才能获得的指标。

---

## 13 程序化解析 Gemini CLI 会话数据

### 13.1 会话文件发现流程

以下 ASCII 图展示了从磁盘定位并解析 Gemini CLI 会话文件的完整流程：

```
                         ┌──────────────────────┐
                         │  ~/.gemini/           │
                         │  projects.json        │
                         │  ┌──────────────────┐ │
                         │  │ "projects": {    │ │
                         │  │   "/path/to/proj" │ │
                         │  │   : "my-project"  │ │
                         │  │ }                 │ │
                         │  └────────┬─────────┘ │
                         └───────────┼───────────┘
                                     │ 查找 short name
                                     ▼
                         ┌──────────────────────┐
                         │  ~/.gemini/tmp/       │
                         │  {short-name}/        │
                         │  ├── logs.json        │◄── 用户输入索引
                         │  ├── .project_root    │◄── 反向路径映射
                         │  └── chats/           │
                         │      ├── session-A.json
                         │      ├── session-B.json
                         │      └── session-C.json
                         └───────────┼───────────┘
                                     │ 遍历 session-*.json
                                     ▼
                    ┌────────────────────────────────┐
                    │  读取每个 session JSON          │
                    │  ┌───────────────────────────┐  │
                    │  │ {                         │  │
                    │  │   "sessionId": "...",      │  │
                    │  │   "kind": "main",          │  │
                    │  │   "messages": [...]        │  │
                    │  │ }                          │  │
                    │  └───────────────────────────┘  │
                    └────────────────┼───────────────┘
                                     │ 过滤 kind != "subagent"
                                     ▼
                    ┌────────────────────────────────┐
                    │  提取会话元数据                   │
                    │  - sessionId / startTime        │
                    │  - 消息数 / token 统计           │
                    │  - 首条用户消息（displayName）    │
                    │  - 工具调用汇总                   │
                    └────────────────────────────────┘
```

> 📌 **关键要点**：与 Claude Code 通过全局 `history.jsonl` 索引查找会话不同，Gemini CLI 需要先解析 `projects.json` 获得项目短名，再扫描对应的 `chats/` 目录。源码中 `Storage.listProjectChatFiles()` 方法即执行此逻辑。

### 13.2 Python 解析代码示例

以下代码演示如何用 Python 程序化地发现和解析 Gemini CLI 的所有会话文件：

```python
import json
from pathlib import Path
from dataclasses import dataclass, field


GEMINI_DIR = Path.home() / ".gemini"
SESSION_FILE_PREFIX = "session-"


@dataclass
class GeminiMessage:
    """单条 Gemini CLI 消息的解析结构。"""
    id: str
    timestamp: str
    msg_type: str
    content: str
    thoughts: list = field(default_factory=list)
    tokens: dict = field(default_factory=dict)
    tool_calls: list = field(default_factory=list)
    model: str = ""


@dataclass
class GeminiSession:
    """完整的 Gemini CLI 会话。"""
    session_id: str
    project_hash: str
    start_time: str
    last_updated: str
    kind: str
    messages: list
    file_path: Path


def discover_projects(gemini_dir: Path) -> dict:
    """读取 projects.json，返回 {项目路径: 短名} 映射。"""
    projects_file = gemini_dir / "projects.json"
    if not projects_file.exists():
        return {}
    data = json.loads(projects_file.read_text())
    return data.get("projects", {})


def list_session_files(gemini_dir: Path, short_name: str) -> list:
    """列出指定项目下的所有会话 JSON 文件。"""
    chats_dir = gemini_dir / "tmp" / short_name / "chats"
    if not chats_dir.exists():
        return []
    return sorted(
        f for f in chats_dir.glob(f"{SESSION_FILE_PREFIX}*.json")
    )


def parse_message(raw: dict) -> GeminiMessage:
    """将原始 JSON dict 转换为 GeminiMessage 对象。"""
    content_raw = raw.get("content", "")
    # content 可能是 str（gemini 消息）或 list（user 消息）
    if isinstance(content_raw, list):
        content_text = " ".join(
            part.get("text", "") for part in content_raw
        )
    else:
        content_text = content_raw

    return GeminiMessage(
        id=raw.get("id", ""),
        timestamp=raw.get("timestamp", ""),
        msg_type=raw.get("type", ""),
        content=content_text,
        thoughts=raw.get("thoughts", []),
        tokens=raw.get("tokens", {}),
        tool_calls=raw.get("toolCalls", []),
        model=raw.get("model", ""),
    )


def parse_session_file(file_path: Path) -> GeminiSession:
    """解析单个会话 JSON 文件，返回 GeminiSession。"""
    data = json.loads(file_path.read_text())
    messages = [parse_message(m) for m in data.get("messages", [])]
    return GeminiSession(
        session_id=data.get("sessionId", ""),
        project_hash=data.get("projectHash", ""),
        start_time=data.get("startTime", ""),
        last_updated=data.get("lastUpdated", ""),
        kind=data.get("kind", "main"),
        messages=messages,
        file_path=file_path,
    )


def load_all_sessions(gemini_dir: Path) -> list:
    """发现并加载所有项目的所有会话。"""
    projects = discover_projects(gemini_dir)
    all_sessions = []
    for project_path, short_name in projects.items():
        session_files = list_session_files(gemini_dir, short_name)
        for sf in session_files:
            session = parse_session_file(sf)
            all_sessions.append(session)
    return all_sessions


# ─── 使用示例
if __name__ == "__main__":
    sessions = load_all_sessions(GEMINI_DIR)
    for session in sessions:
        user_count = sum(
            1 for m in session.messages if m.msg_type == "user"
        )
        gemini_count = sum(
            1 for m in session.messages if m.msg_type == "gemini"
        )
        print(
            f"[{session.kind}] {session.session_id[:8]}  "
            f"messages={len(session.messages)} "
            f"(user={user_count}, gemini={gemini_count})  "
            f"file={session.file_path.name}"
        )
```

> 💡 **content 类型差异**：Gemini CLI 的用户消息 `content` 是 `Array<{text: string}>`，而助手消息 `content` 是纯 `String`。解析时需要处理这两种情况，上面的 `parse_message` 函数通过 `isinstance` 检查实现了统一处理。

### 13.3 Token 使用量提取与汇总

每条 `type: "gemini"` 的消息都包含 `tokens` 对象，可以按会话或按项目汇总 token 消耗：

```python
from dataclasses import dataclass


@dataclass
class TokenSummary:
    """会话级别的 token 汇总。"""
    total_input: int = 0
    total_output: int = 0
    total_cached: int = 0
    total_thoughts: int = 0
    total_tool: int = 0
    grand_total: int = 0
    message_count: int = 0


def compute_session_tokens(session: GeminiSession) -> TokenSummary:
    """从会话中的所有 gemini 消息提取并汇总 token 用量。"""
    summary = TokenSummary()
    for msg in session.messages:
        if msg.msg_type != "gemini" or not msg.tokens:
            continue
        summary.total_input += msg.tokens.get("input", 0)
        summary.total_output += msg.tokens.get("output", 0)
        summary.total_cached += msg.tokens.get("cached", 0)
        summary.total_thoughts += msg.tokens.get("thoughts", 0)
        summary.total_tool += msg.tokens.get("tool", 0)
        summary.grand_total += msg.tokens.get("total", 0)
        summary.message_count += 1
    return summary


# ─── 使用示例
if __name__ == "__main__":
    sessions = load_all_sessions(GEMINI_DIR)
    for session in sessions:
        if session.kind == "subagent":
            continue
        token_summary = compute_session_tokens(session)
        cache_ratio = (
            token_summary.total_cached / token_summary.total_input * 100
            if token_summary.total_input > 0
            else 0.0
        )
        print(
            f"Session {session.session_id[:8]}: "
            f"input={token_summary.total_input:,}  "
            f"output={token_summary.total_output:,}  "
            f"cached={token_summary.total_cached:,} "
            f"({cache_ratio:.1f}%)  "
            f"total={token_summary.grand_total:,}"
        )
```

**Token 字段与 API 响应的映射关系：**

源码中 `ChatRecordingService.recordMessageTokens()` 方法揭示了 token 字段的来源：

| 会话文件字段 | API `UsageMetadata` 字段 | 说明 |
|-------------|-------------------------|------|
| `tokens.input` | `promptTokenCount` | 输入 prompt 的 token 数 |
| `tokens.output` | `candidatesTokenCount` | 模型生成的 token 数 |
| `tokens.cached` | `cachedContentTokenCount` | 缓存命中的 token 数 |
| `tokens.thoughts` | `thoughtsTokenCount` | 思考过程 token 数 |
| `tokens.tool` | `toolUsePromptTokenCount` | 工具调用描述 token 数 |
| `tokens.total` | `totalTokenCount` | 所有类别之和 |

> ⚠️ **注意**：`tokens.total` 不一定等于 `input + output + cached + thoughts + tool` 的算术和。这是因为 `cached` 是 `input` 的子集（缓存命中的输入 token），API 返回的 `totalTokenCount` 由服务端计算。

---

## 14 数据规模参考

### 14.1 典型会话文件大小

以下数据基于真实 Gemini CLI 会话的统计，帮助评估存储需求和解析性能：

| 会话类型 | 消息数（轮次） | 工具调用数 | 文件大小 | 说明 |
|---------|-------------|----------|---------|------|
| 简短问答 | 2-4 | 0 | 2-5 KB | 纯文本交互，无工具调用 |
| 代码阅读 | 6-12 | 3-8 | 15-50 KB | 读取文件 + 讨论 |
| 功能开发 | 15-30 | 10-25 | 50-200 KB | 读写文件 + 多轮修改 |
| 复杂重构 | 30-60 | 30-80 | 200-800 KB | 大量文件操作 + 子代理 |
| 长时间会话 | 60+ | 50+ | 500 KB-2 MB | 持续数小时的开发 |

**影响文件大小的主要因素：**

1. **`toolCalls[].result`**：工具执行结果（尤其是 `read_file` 读取大文件时）是最大的数据块
2. **`resultDisplay.fileDiff`**：文件写入操作的 diff 内容
3. **`resultDisplay.originalContent` / `newContent`**：完整文件内容（写入操作时保存）
4. **`thoughts[].description`**：思考过程的详细描述文本

> 💡 **与 Claude Code 对比**：Claude Code 使用 JSONL 格式（逐行追加），单个会话文件可增长到 10-50 MB（因为包含完整工具输出）。Gemini CLI 的 JSON 格式通常更紧凑，但由于整体写入（非追加），在极长会话中写入性能会下降。

### 14.2 项目级数据规模估算

```python
import os
from pathlib import Path


def estimate_project_storage(gemini_dir: Path, short_name: str) -> dict:
    """估算单个项目的存储占用。"""
    project_tmp = gemini_dir / "tmp" / short_name
    if not project_tmp.exists():
        return {"error": "project not found"}

    chats_dir = project_tmp / "chats"
    session_files = list(chats_dir.glob("session-*.json")) if chats_dir.exists() else []
    total_bytes = sum(f.stat().st_size for f in session_files)
    main_count = 0
    subagent_count = 0
    total_messages = 0

    for sf in session_files:
        data = json.loads(sf.read_text())
        kind = data.get("kind", "main")
        msg_count = len(data.get("messages", []))
        total_messages += msg_count
        if kind == "subagent":
            subagent_count += 1
        else:
            main_count += 1

    return {
        "session_count": len(session_files),
        "main_sessions": main_count,
        "subagent_sessions": subagent_count,
        "total_messages": total_messages,
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "avg_session_kb": round(
            total_bytes / len(session_files) / 1024, 1
        ) if session_files else 0,
    }
```

---

## 15 格式对比：Gemini CLI JSON vs Claude Code JSONL

### 15.1 结构差异对照

以下表格对同一概念在两种格式中的具体字段名和结构进行精确映射：

| 概念 | Gemini CLI (JSON) | Claude Code (JSONL) | 结构差异 |
|------|-------------------|---------------------|---------|
| **会话容器** | 单个 `.json` 文件，顶层对象 | 单个 `.jsonl` 文件，每行一条事件 | 整体 vs 逐行 |
| **会话 ID** | `sessionId` (顶层) | `sessionId` (每条 history 记录) | 相同概念 |
| **消息类型** | `type: "user" \| "gemini"` | `type: "user" \| "assistant"` | 值不同 |
| **用户消息内容** | `content: [{text: "..."}]` | `message.content: [{type:"text", text:"..."}]` | Gemini 无 `type` 字段 |
| **助手消息内容** | `content: "plain string"` | `message.content: [{type:"text", text:"..."}]` | String vs Array |
| **思考过程** | `thoughts: [{subject, description}]` | `content: [{type:"thinking", thinking:"..."}]` | 独立数组 vs 内嵌 block |
| **工具调用** | `toolCalls: [{id, name, args, result}]` | `content: [{type:"tool_use", id, name, input}]` | 自包含 vs 分散 |
| **工具结果** | `toolCalls[].result` (同一对象) | 下一条 `user` 消息的 `tool_result` block | 内嵌 vs 跨消息 |
| **Token 统计** | `tokens: {input, output, cached, ...}` | `usage: {input_tokens, output_tokens, ...}` | 扁平 vs 嵌套 |
| **模型名称** | `model` (消息级) | `model` (消息级) | 位置相同 |
| **子代理标记** | `kind: "subagent"` (文件级) | `isSidechain: true` (消息级) | 文件级 vs 消息级 |
| **工作目录** | 不记录 | `cwd` (每条用户消息) | Gemini 无此上下文 |
| **Git 分支** | 不记录 | `gitBranch` (每条用户消息) | Gemini 无此上下文 |

### 15.2 同一对话的格式对比示例

**Gemini CLI 格式（JSON）：**

```json
{
  "sessionId": "97253fa9-55cd-4a38-b241-17369143df91",
  "projectHash": "28d80dc91fa5...",
  "startTime": "2026-03-14T16:40:26.798Z",
  "lastUpdated": "2026-03-14T16:47:58.600Z",
  "kind": "main",
  "messages": [
    {
      "id": "2cfde2f1-...",
      "timestamp": "2026-03-14T16:40:26.798Z",
      "type": "user",
      "content": [{"text": "Read the README file"}]
    },
    {
      "id": "6951e895-...",
      "timestamp": "2026-03-14T16:40:30.123Z",
      "type": "gemini",
      "content": "I'll read the README file for you.",
      "thoughts": [{"subject": "Planning", "description": "Reading README..."}],
      "tokens": {"input": 1200, "output": 45, "cached": 800, "total": 1245},
      "model": "gemini-3-flash-preview",
      "toolCalls": [{
        "id": "read_file_1773506858312_0",
        "name": "read_file",
        "args": {"file_path": "README.md"},
        "result": [{"functionResponse": {"id": "...", "name": "read_file", "response": {"output": "# My Project\n..."}}}],
        "status": "success"
      }]
    }
  ]
}
```

**Claude Code 格式（JSONL，等效对话）：**

```jsonl
{"parentUuid":"root","uuid":"msg-001","type":"user","message":{"role":"user","content":[{"type":"text","text":"Read the README file"}]},"cwd":"/Users/user/project","gitBranch":"main","timestamp":"2026-03-14T16:40:26.798Z"}
{"parentUuid":"msg-001","uuid":"msg-002","type":"assistant","message":{"role":"assistant","content":[{"type":"thinking","thinking":"I need to read the README..."},{"type":"text","text":"I'll read the README file for you."},{"type":"tool_use","id":"toolu_abc123","name":"Read","input":{"file_path":"README.md"}}],"model":"claude-sonnet-4-20250514","usage":{"input_tokens":1200,"output_tokens":45,"cache_read_input_tokens":800}},"sessionId":"2b6ed192-..."}
{"parentUuid":"msg-002","uuid":"msg-003","type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_abc123","content":"# My Project\n..."}]}}
```

> 📌 **关键区别**：Gemini CLI 的工具调用和结果在**同一个 gemini 消息**中自包含（`toolCalls[].result`），而 Claude Code 需要在**相邻的三条消息**中关联——assistant 消息的 `tool_use` block → user 消息的 `tool_result` block（通过 `tool_use_id` 匹配）。这使得 Gemini CLI 的数据解析更加直接。

### 15.3 解析复杂度对比

```
Gemini CLI 解析流程（简单）:
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ json.load()  │────▶│ 遍历 messages │────▶│ 直接读取      │
│ 整个文件      │     │ 数组          │     │ toolCalls[]  │
└──────────────┘     └──────────────┘     └──────────────┘

Claude Code 解析流程（需要跨行关联）:
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ 逐行读取      │────▶│ json.loads() │────▶│ 按 uuid 链   │────▶│ 匹配 tool_use│
│ .jsonl 文件   │     │ 每行独立      │     │ 构建消息树    │     │ 与 tool_result│
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

---

## 16 会话重建：从原始文件到对话时间线

### 16.1 会话重建场景

在数据分析、会话回放或迁移场景中，需要从磁盘上的原始文件重建完整的对话时间线。以下代码展示了如何将 Gemini CLI 的会话数据重建为结构化的对话事件流：

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TimelineEvent:
    """时间线上的单个事件。"""
    timestamp: str
    event_type: str
    role: str
    content: str
    metadata: dict


def reconstruct_timeline(session: GeminiSession) -> list:
    """从会话数据重建完整的对话时间线。

    将消息、思考过程、工具调用展开为扁平的时间线事件列表，
    按时间戳排序。
    """
    events = []

    for msg in session.messages:
        # 用户消息事件
        if msg.msg_type == "user":
            events.append(TimelineEvent(
                timestamp=msg.timestamp,
                event_type="message",
                role="user",
                content=msg.content,
                metadata={"message_id": msg.id},
            ))
            continue

        # Gemini 消息：先处理思考过程
        for thought in msg.thoughts:
            events.append(TimelineEvent(
                timestamp=thought.get("timestamp", msg.timestamp),
                event_type="thought",
                role="gemini",
                content=thought.get("description", ""),
                metadata={
                    "subject": thought.get("subject", ""),
                    "message_id": msg.id,
                },
            ))

        # Gemini 消息：文本回复
        if msg.content:
            events.append(TimelineEvent(
                timestamp=msg.timestamp,
                event_type="message",
                role="gemini",
                content=msg.content,
                metadata={
                    "message_id": msg.id,
                    "model": msg.model,
                    "tokens": msg.tokens,
                },
            ))

        # Gemini 消息：工具调用事件
        for tool_call in msg.tool_calls:
            events.append(TimelineEvent(
                timestamp=tool_call.get("timestamp", msg.timestamp),
                event_type="tool_call",
                role="gemini",
                content=f"{tool_call.get('name', 'unknown')}({json.dumps(tool_call.get('args', {}), ensure_ascii=False)[:200]})",
                metadata={
                    "tool_id": tool_call.get("id", ""),
                    "tool_name": tool_call.get("name", ""),
                    "status": tool_call.get("status", ""),
                    "display_name": tool_call.get("displayName", ""),
                    "has_diff": "fileDiff" in (tool_call.get("resultDisplay") or {}),
                },
            ))

    # 按时间戳排序
    events.sort(key=lambda e: e.timestamp)
    return events


def print_timeline(session: GeminiSession) -> None:
    """以可读格式打印会话时间线。"""
    events = reconstruct_timeline(session)
    print(f"=== Session {session.session_id[:8]} ({session.kind}) ===")
    print(f"    Start: {session.start_time}")
    print(f"    End:   {session.last_updated}")
    print(f"    Events: {len(events)}")
    print()

    for event in events:
        time_short = event.timestamp[11:19]  # HH:MM:SS
        icon = {
            "message": "MSG",
            "thought": "THK",
            "tool_call": "TUL",
        }.get(event.event_type, "???")
        role_tag = event.role.upper()[:4]
        content_preview = event.content[:80].replace("\n", " ")
        print(f"  {time_short} [{icon}] {role_tag}: {content_preview}")
```

**输出示例：**

```
=== Session 97253fa9 (main) ===
    Start: 2026-03-14T16:40:26.798Z
    End:   2026-03-14T16:47:58.600Z
    Events: 8

  16:40:26 [MSG] USER: This is my first use of Codex but I have used other coding agents.
  16:41:29 [THK] GEMI: I'm now focused on the next step...
  16:41:47 [THK] GEMI: I've been considering the potential of 'Auto routing' and 'Pro routing'
  16:42:06 [MSG] GEMI: Welcome to Gemini CLI! Compared to other coding agents...
  16:47:33 [MSG] USER: Create a README file for this project.
  16:47:38 [THK] GEMI: I need to read the existing project structure...
  16:47:49 [TUL] GEMI: read_file({"file_path": "CLAUDE.md"})
  16:47:57 [TUL] GEMI: write_file({"file_path": "README.md", "content": "# Agent-Guideline:..."})
```

### 16.2 关联主会话与子代理会话

同一个 `sessionId` 可能对应多个文件（主会话 + 子代理会话）。以下代码展示如何将它们关联成完整的会话视图：

```python
from collections import defaultdict


def group_sessions_by_id(gemini_dir: Path, short_name: str) -> dict:
    """将同一 sessionId 的主会话和子代理会话分组。"""
    session_files = list_session_files(gemini_dir, short_name)
    grouped = defaultdict(lambda: {"main": None, "subagents": []})

    for sf in session_files:
        session = parse_session_file(sf)
        if session.kind == "main":
            grouped[session.session_id]["main"] = session
        else:
            grouped[session.session_id]["subagents"].append(session)

    return dict(grouped)


def compute_session_stats(session_group: dict) -> dict:
    """计算包含子代理的完整会话统计。"""
    main_session = session_group["main"]
    subagents = session_group["subagents"]

    main_tokens = compute_session_tokens(main_session) if main_session else TokenSummary()
    subagent_token_list = [
        compute_session_tokens(sa) for sa in subagents
    ]

    total_input = main_tokens.total_input + sum(
        st.total_input for st in subagent_token_list
    )
    total_output = main_tokens.total_output + sum(
        st.total_output for st in subagent_token_list
    )

    tool_calls_count = 0
    file_changes_count = 0
    if main_session:
        for msg in main_session.messages:
            for tc in msg.tool_calls:
                tool_calls_count += 1
                result_display = tc.get("resultDisplay")
                if isinstance(result_display, dict) and "fileDiff" in result_display:
                    file_changes_count += 1

    return {
        "session_id": main_session.session_id if main_session else "unknown",
        "start_time": main_session.start_time if main_session else "",
        "main_messages": len(main_session.messages) if main_session else 0,
        "subagent_count": len(subagents),
        "subagent_messages": sum(len(sa.messages) for sa in subagents),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "tool_calls": tool_calls_count,
        "file_changes": file_changes_count,
    }
```

> 💡 **实用技巧**：源码中 `SessionSelector` 类在列举可恢复会话时会自动跳过 `kind: "subagent"` 的文件。在数据分析时也建议先过滤子代理文件，按需关联。子代理会话的文件名时间戳通常晚于主会话，因为它们在主会话运行中途被创建。

---

## 17 迁移模式：在 Gemini CLI 与 Claude Code 之间转换数据

### 17.1 Gemini CLI → Claude Code JSONL

以下代码将 Gemini CLI 的 JSON 会话转换为 Claude Code 兼容的 JSONL 格式，适用于统一分析或数据迁移场景：

```python
import json
import uuid
from pathlib import Path


def gemini_to_claude_jsonl(session: GeminiSession) -> list:
    """将 Gemini CLI 会话转换为 Claude Code JSONL 行列表。

    映射规则：
    - gemini type:"user"   → claude type:"user", role:"user"
    - gemini type:"gemini"  → claude type:"assistant", role:"assistant"
    - gemini toolCalls      → claude tool_use + tool_result（拆分为两条消息）
    - gemini thoughts       → claude thinking content block
    """
    lines = []
    parent_uuid = "root"

    for msg in session.messages:
        current_uuid = f"msg-{uuid.uuid4().hex[:12]}"

        if msg.msg_type == "user":
            content_blocks = [{"type": "text", "text": msg.content}]
            record = {
                "parentUuid": parent_uuid,
                "uuid": current_uuid,
                "type": "user",
                "message": {
                    "role": "user",
                    "content": content_blocks,
                },
                "timestamp": msg.timestamp,
            }
            lines.append(json.dumps(record, ensure_ascii=False))
            parent_uuid = current_uuid

        elif msg.msg_type == "gemini":
            content_blocks = []

            # 思考过程 → thinking blocks
            for thought in msg.thoughts:
                content_blocks.append({
                    "type": "thinking",
                    "thinking": f"[{thought.get('subject', '')}] {thought.get('description', '')}",
                })

            # 文本内容
            if msg.content:
                content_blocks.append({
                    "type": "text",
                    "text": msg.content,
                })

            # 工具调用 → tool_use blocks
            tool_result_pairs = []
            for tc in msg.tool_calls:
                tool_use_id = f"toolu_{uuid.uuid4().hex[:20]}"
                content_blocks.append({
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": tc.get("name", ""),
                    "input": tc.get("args", {}),
                })
                # 收集工具结果用于下一条 user 消息
                result_text = ""
                for result_item in (tc.get("result") or []):
                    func_resp = result_item.get("functionResponse", {})
                    resp = func_resp.get("response", {})
                    result_text += resp.get("output", "")
                tool_result_pairs.append((tool_use_id, result_text))

            usage = {}
            if msg.tokens:
                usage = {
                    "input_tokens": msg.tokens.get("input", 0),
                    "output_tokens": msg.tokens.get("output", 0),
                    "cache_read_input_tokens": msg.tokens.get("cached", 0),
                }

            record = {
                "parentUuid": parent_uuid,
                "uuid": current_uuid,
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": content_blocks,
                    "model": msg.model or "gemini-3-flash-preview",
                    "usage": usage,
                },
                "timestamp": msg.timestamp,
                "sessionId": session.session_id,
            }
            lines.append(json.dumps(record, ensure_ascii=False))
            parent_uuid = current_uuid

            # 工具结果 → 独立的 user/tool_result 消息
            if tool_result_pairs:
                result_uuid = f"msg-{uuid.uuid4().hex[:12]}"
                result_blocks = []
                for tool_use_id, result_text in tool_result_pairs:
                    result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_text,
                    })
                result_record = {
                    "parentUuid": parent_uuid,
                    "uuid": result_uuid,
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": result_blocks,
                    },
                    "timestamp": msg.timestamp,
                }
                lines.append(json.dumps(result_record, ensure_ascii=False))
                parent_uuid = result_uuid

    return lines


def convert_and_save(session: GeminiSession, output_path: Path) -> None:
    """将 Gemini 会话转换并保存为 JSONL 文件。"""
    lines = gemini_to_claude_jsonl(session)
    output_path.write_text("\n".join(lines) + "\n")
    print(
        f"Converted {len(session.messages)} messages "
        f"→ {len(lines)} JSONL lines → {output_path}"
    )
```

### 17.2 Claude Code JSONL → Gemini CLI JSON

反向转换——将 Claude Code 会话数据转换为 Gemini CLI 格式：

```python
def claude_jsonl_to_gemini(jsonl_path: Path) -> dict:
    """将 Claude Code JSONL 会话转换为 Gemini CLI JSON 格式。

    关键挑战：Claude Code 的工具调用分散在 assistant 消息（tool_use）
    和后续 user 消息（tool_result）中，需要关联合并。
    """
    raw_messages = []
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                raw_messages.append(json.loads(line))

    # 构建 tool_use_id → result 的映射
    tool_results_map = {}
    for raw in raw_messages:
        msg = raw.get("message", {})
        for block in (msg.get("content") or []):
            if block.get("type") == "tool_result":
                tool_results_map[block["tool_use_id"]] = block.get("content", "")

    gemini_messages = []
    for raw in raw_messages:
        msg = raw.get("message", {})
        msg_type = raw.get("type", "")
        content_blocks = msg.get("content", [])

        # 跳过纯 tool_result 的 user 消息（已合并到 assistant）
        is_pure_tool_result = all(
            b.get("type") == "tool_result" for b in content_blocks
        )
        if msg_type == "user" and is_pure_tool_result:
            continue

        if msg_type == "user":
            text_parts = [
                b.get("text", "")
                for b in content_blocks
                if b.get("type") == "text"
            ]
            gemini_messages.append({
                "id": raw.get("uuid", str(uuid.uuid4())),
                "timestamp": raw.get("timestamp", ""),
                "type": "user",
                "content": [{"text": t} for t in text_parts],
            })

        elif msg_type == "assistant":
            thoughts = []
            text_content = ""
            tool_calls = []

            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "thinking":
                    thoughts.append({
                        "subject": "Thinking",
                        "description": block.get("thinking", ""),
                        "timestamp": raw.get("timestamp", ""),
                    })
                elif block_type == "text":
                    text_content += block.get("text", "")
                elif block_type == "tool_use":
                    tool_id = block.get("id", "")
                    result_content = tool_results_map.get(tool_id, "")
                    tool_calls.append({
                        "id": tool_id,
                        "name": block.get("name", ""),
                        "args": block.get("input", {}),
                        "result": [{
                            "functionResponse": {
                                "id": tool_id,
                                "name": block.get("name", ""),
                                "response": {"output": result_content},
                            }
                        }],
                        "status": "success",
                        "timestamp": raw.get("timestamp", ""),
                    })

            usage = msg.get("usage", {})
            tokens = {
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "cached": usage.get("cache_read_input_tokens", 0),
                "thoughts": 0,
                "tool": 0,
                "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }

            gemini_msg = {
                "id": raw.get("uuid", str(uuid.uuid4())),
                "timestamp": raw.get("timestamp", ""),
                "type": "gemini",
                "content": text_content,
                "thoughts": thoughts,
                "tokens": tokens,
                "model": msg.get("model", ""),
            }
            if tool_calls:
                gemini_msg["toolCalls"] = tool_calls

            gemini_messages.append(gemini_msg)

    first_ts = raw_messages[0].get("timestamp", "") if raw_messages else ""
    last_ts = raw_messages[-1].get("timestamp", "") if raw_messages else ""
    session_id = str(uuid.uuid4())

    return {
        "sessionId": session_id,
        "projectHash": "",
        "startTime": first_ts,
        "lastUpdated": last_ts,
        "kind": "main",
        "messages": gemini_messages,
    }
```

> ⚠️ **迁移注意事项**：
> - Claude Code 的 `content` 为 Array of blocks，Gemini CLI 的助手 `content` 为 String——转换时会丢失 block 级别的结构信息
> - Claude Code 的 `cwd`、`gitBranch`、`parentUuid`、`isSidechain` 等上下文字段在 Gemini CLI 中无对应项
> - 两种格式的 `tool_use_id` 命名规则完全不同（`toolu_` 前缀 vs `{name}_{timestamp}_{index}`）
> - Token 统计的字段名和粒度不同，转换时部分精度会丢失（如 Claude Code 区分 `cache_creation` 和 `cache_read`，Gemini CLI 仅有 `cached`）

---

## 参考资料

- [Gemini CLI 官方文档](https://geminicli.com/docs/)
- [Gemini CLI GitHub 仓库](https://github.com/google-gemini/gemini-cli)
- [Gemini CLI 配置参考](https://geminicli.com/docs/reference/configuration/)
- [GEMINI.md 上下文文件](https://geminicli.com/docs/cli/gemini-md/)
- [受信任文件夹](https://geminicli.com/docs/cli/trusted-folders/)
- [自定义命令](https://geminicli.com/docs/cli/custom-commands/)
- [会话管理](https://geminicli.com/docs/cli/session-management/)
- [检查点功能](https://geminicli.com/docs/cli/checkpointing/)
- [Token 缓存优化](https://geminicli.com/docs/cli/token-caching/)
- [MCP 服务器配置](https://geminicli.com/docs/tools/mcp-server/)
- [扩展系统](https://geminicli.com/docs/extensions/)
- [settings.json Schema](https://raw.githubusercontent.com/google-gemini/gemini-cli/main/schemas/settings.schema.json)

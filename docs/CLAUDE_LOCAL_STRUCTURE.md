# Claude Code 本地数据管理系统

| 条目 | 内容 |
|------|------|
| **主题** | Claude Code CLI 工具的本地数据存储和管理机制 |
| **存储位置** | `~/.claude` 目录（用户主目录下的 .claude 隐藏文件夹） |
| **适用版本** | Claude Code v0.1.0+ |
| **平台** | macOS、Linux（Windows WSL2 可用） |

---

## 1 背景与设计思想

Claude Code 是 Anthropic 推出的官方 CLI 工具，用于在终端中与 Claude AI 进行交互式对话。与网页版本不同，CLI 工具需要在本地保存会话数据、配置信息和各种中间文件。为了实现离线可用、快速查询和灵活扩展，Claude Code 采取了分布式存储策略：所有数据都存储在用户主目录下的 `~/.claude` 隐藏目录中，采用 JSON Lines（JSONL）格式记录对话，使用 UUID 标识会话，支持多个项目的并行管理。

> 📌 **重点**：理解 `~/.claude` 目录的结构和各类文件的作用，是进行会话数据分析、调试和集成的基础。

---

## 2 目录结构总览

Claude Code 的本地存储采用分层设计，不同类型的数据存储在独立的目录中，便于管理和扩展。以下是完整的目录树结构：

```
~/.claude/
├── history.jsonl                  # 全局会话索引
├── settings.json                  # 用户配置
├── policy-limits.json             # 政策限制配置
├── stats-cache.json               # 统计缓存
├── mcp-needs-auth-cache.json      # MCP 认证缓存
├── CLAUDE.md                      # 用户自定义文档
│
├── projects/                      # 核心：项目会话数据
│   ├── -Users-JinghengYe-Documents-Projects-Agent-Guideline/
│   │   ├── 2b6ed192-046f-495a-b8ed-5d500c01a066.jsonl
│   │   ├── 15380153-3fff-4ff6-8723-39f2a7f3c050.jsonl
│   │   └── [更多会话文件...]
│   └── [其他项目目录...]
│
├── todos/                         # 任务列表（按会话保存）
│   ├── 005ca605-db47-41ee-af69-f7c80c5673f8-agent-[ID].json
│   └── [其他任务文件...]
│
├── plans/                         # 已保存的规划
│   ├── [plan-id]-title.md
│   └── [其他计划文件...]
│
├── tasks/                         # 任务队列
│   ├── [task-id]/
│   │   ├── 1.json
│   │   ├── 2.json
│   │   └── [任务步骤...]
│   └── [其他任务...]
│
├── plugins/                       # 插件系统
│   ├── installed_plugins.json     # 已安装插件注册表
│   ├── blocklist.json             # 插件黑名单
│   ├── known_marketplaces.json    # 已知插件市场
│   ├── cache/
│   │   └── local-plugins/
│   │       └── [plugin-name]/[version]/
│   └── marketplaces/              # 插件市场缓存
│
├── file-history/                  # 文件编辑历史
│   ├── [session-id]/
│   │   └── [file-path].history    # 该文件的编辑历史
│   └── [其他文件历史...]
│
├── shell-snapshots/               # Shell 快照
│   └── [snapshot-id].json         # 命令执行快照
│
├── session-env/                   # 会话环境变量
│   └── [session-id].json          # 该会话的环境变量备份
│
├── debug/                         # 调试信息
│   └── [session-id].txt           # 会话的调试日志
│
├── backups/                       # 备份文件
│   └── [备份的历史或配置文件]
│
├── cache/                         # 通用缓存
│   └── [缓存的数据]
│
├── telemetry/                     # 遥测数据（使用统计）
│   └── [遥测事件记录]
│
├── paste-cache/                   # 粘贴内容缓存
│   └── [剪贴板内容]
│
├── ide/                           # IDE 集成数据
│   └── [IDE 配置]
│
└── statsig/                       # Statsig 功能开关
    └── [功能标志配置]
```

---

## 3 会话数据存储机制

### 3.1 会话如何被保存

Claude Code 采用"两层索引"的设计来管理会话：

1. **全局索引层（history.jsonl）**：每当开始或切换会话时，Claude Code 会向 `~/.claude/history.jsonl` 追加一条索引记录，记录该会话的基本信息（会话 ID、所属项目、首条消息、时间戳等）。这个文件是 JSONL 格式（JSON Lines），每行代表一条历史条目，便于追加和流式读取。

2. **会话数据层（projects/{project}/sessionId.jsonl）**：每个项目对应一个目录，项目目录名遵循特殊编码规则（将项目的绝对路径中的 `/` 替换为 `-`）。每个会话保存为一个独立的 `.jsonl` 文件，文件名为该会话的 UUID。文件中的每一行代表一条消息或系统事件，包含完整的对话内容、工具调用、模型输出等。

这种"两层"设计的优势是：

- **快速索引**：可以快速从 `history.jsonl` 遍历所有会话，提取会话摘要，无需加载完整的会话数据文件。
- **懒加载**：只在用户主动查看会话时才加载对应的 `.jsonl` 文件，节省内存。
- **灵活扩展**：支持多个项目的并行管理，每个项目的会话独立存储，互不影响。

### 3.2 history.jsonl 文件格式

`history.jsonl` 是全局会话索引，每行都是一条独立的 JSON 对象，记录一个会话的基本元信息。

**数据结构示例：**

```json
{
  "display": "Who are you?",
  "pastedContents": {},
  "timestamp": 1767734674932,
  "project": "/Users/JinghengYe/Documents/Projects/Flask-WebShop-Init",
  "sessionId": "85f42726-fcea-47bb-b93e-f6b58da3f4c9"
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `display` | String | 该会话的首条用户消息，用于在会话列表中显示摘要（通常截断为200字) |
| `pastedContents` | Object | 该会话中粘贴的外部内容（文件片段、代码等），键为文件路径，值为内容 |
| `timestamp` | Number | 会话创建的时间戳（毫秒级别的 Unix epoch） |
| `project` | String | 该会话关联的项目的绝对路径 |
| `sessionId` | String | 会话的唯一标识符（UUID v4 格式） |

> 💡 **最佳实践**：分析会话历史时，应该通过 `history.jsonl` 快速获取会话列表，而不是直接扫描 `projects/` 目录下的所有 `.jsonl` 文件。

### 3.3 会话 JSONL 文件格式（核心数据）

每个会话对应的 `.jsonl` 文件包含了完整的对话内容。文件中的每一行代表一条"事件"或"消息"，可能是：

- 用户消息（`type: "user"`）
- 助手回复（`type: "assistant"`）
- 系统事件（`type: "progress"`、`type: "file-history-snapshot"` 等）
- 工具调用和结果

#### 3.3.1 用户消息（User Message）

**基础用户消息示例：**

```json
{
  "type": "user",
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "sessionId": "2b6ed192-046f-495a-b8ed-5d500c01a066",
  "parentUuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "timestamp": 1767734674932,
  "isSidechain": false,
  "cwd": "/Users/JinghengYe/Documents/Projects/Agent-Guideline",
  "gitBranch": "main",
  "message": {
    "role": "user",
    "content": "Search for pytest best practices in the codebase"
  }
}
```

**包含工具结果的用户消息（工具结果消息）：**

```json
{
  "type": "user",
  "uuid": "660e8400-e29b-41d4-a716-446655440001",
  "sessionId": "2b6ed192-046f-495a-b8ed-5d500c01a066",
  "parentUuid": "91ff20aa-3255-4fb4-b383-605ddd2a37e1",
  "timestamp": 1767734685000,
  "isSidechain": false,
  "cwd": "/Users/JinghengYe/Documents/Projects/Agent-Guideline",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_01DAWALsTf6siYK1fiZfh8AK",
        "content": [
          {
            "type": "text",
            "text": "Found 5 test files matching the pattern 'test_*.py' in src/tests/:\n- test_utils.py (23 lines)\n- test_models.py (156 lines)\n- test_api.py (89 lines)\n- test_fixtures.py (42 lines)\n- test_integration.py (203 lines)"
          }
        ],
        "is_error": false
      }
    ]
  }
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `parentUuid` | String | 指向前一条消息（通常是 assistant 消息），用于建立会话链 |
| `isSidechain` | Boolean | 是否为"副链"消息（例如背景任务或并行对话分支） |
| `cwd` | String | 该消息执行时的工作目录（当前目录） |
| `gitBranch` | String | 当前的 Git 分支名称（如果项目是 Git 仓库） |

#### 3.3.2 助手消息（Assistant Message）

**纯文本回复示例：**

```json
{
  "type": "assistant",
  "uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "sessionId": "2b6ed192-046f-495a-b8ed-5d500c01a066",
  "timestamp": 1767734680000,
  "requestId": "req_011CYx3MkR26doX55wDG5bv5",
  "message": {
    "role": "assistant",
    "model": "claude-opus-4-6",
    "id": "msg_011faSK3m9AZcCHdrYh6QGzC",
    "type": "message",
    "stop_reason": "end_turn",
    "content": [
      {
        "type": "text",
        "text": "Here are some pytest best practices..."
      }
    ],
    "usage": {
      "input_tokens": 512,
      "output_tokens": 1024,
      "cache_creation_input_tokens": 128,
      "cache_read_input_tokens": 256
    }
  }
}
```

**包含工具调用的助手消息（关键示例）：**

```json
{
  "type": "assistant",
  "uuid": "91ff20aa-3255-4fb4-b383-605ddd2a37e1",
  "sessionId": "2b6ed192-046f-495a-b8ed-5d500c01a066",
  "timestamp": 1767734680123,
  "requestId": "req_011CYx3MkR26doX55wDG5bv5",
  "message": {
    "role": "assistant",
    "model": "claude-opus-4-6",
    "id": "msg_011faSK3m9AZcCHdrYh6QGzC",
    "type": "message",
    "stop_reason": "tool_use",
    "content": [
      {
        "type": "text",
        "text": "Let me search for pytest best practices in your codebase..."
      },
      {
        "type": "tool_use",
        "id": "toolu_01DAWALsTf6siYK1fiZfh8AK",
        "name": "Grep",
        "input": {
          "pattern": "def test_",
          "path": "src/tests",
          "type": "py"
        },
        "caller": {
          "type": "direct"
        }
      },
      {
        "type": "tool_use",
        "id": "toolu_02EBXBMtUg7jdZL2giBeI9BL",
        "name": "Read",
        "input": {
          "file_path": "/Users/JinghengYe/Documents/Projects/Agent-Guideline/src/tests/conftest.py"
        },
        "caller": {
          "type": "direct"
        }
      }
    ],
    "usage": {
      "input_tokens": 3,
      "output_tokens": 9,
      "cache_creation_input_tokens": 4022,
      "cache_read_input_tokens": 19532,
      "cache_creation": {
        "ephemeral_5m_input_tokens": 0,
        "ephemeral_1h_input_tokens": 4022
      },
      "service_tier": "standard",
      "inference_geo": "not_available"
    }
  }
}
```

**助手消息字段详解：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `message.id` | String | 该消息的 Anthropic API ID（以 `msg_` 开头） |
| `message.type` | String | 固定为 `"message"`，表示这是一个完整的模型消息 |
| `stop_reason` | String | 消息停止的原因：`end_turn`（正常结束）、`tool_use`（需要调用工具）、`max_tokens`（达到 token 限制） |
| `message.content` | Array | 内容块数组，可包含多种类型的块 |
| `requestId` | String | 该请求的 API 请求 ID（以 `req_` 开头），用于日志追踪 |

**Token 使用详解：**

```json
"usage": {
  "input_tokens": 3,               // 本消息的输入 token 数
  "output_tokens": 9,              // 本消息的输出 token 数
  "cache_creation_input_tokens": 4022,  // 创建缓存的 input token（降价 10%）
  "cache_read_input_tokens": 19532,     // 读取缓存的 input token（降价 90%）
  "cache_creation": {
    "ephemeral_5m_input_tokens": 0,     // 5分钟 TTL 缓存的 token
    "ephemeral_1h_input_tokens": 4022   // 1小时 TTL 缓存的 token
  },
  "service_tier": "standard",      // 服务层级（standard/pro）
  "inference_geo": "not_available" // 推理地区（出于隐私可能不可用）
}
```

**Token 缓存节省计算：**

```
总 input token 成本 = (3 * 1) + (4022 * 0.1) + (19532 * 0.1)
                   = 3 + 402.2 + 1953.2
                   = 2358.4 token
相比无缓存的 (3 + 4022 + 19532 = 23557 token)：
节省比例 = (23557 - 2358.4) / 23557 = 90%
```

**包含 Extended Thinking 的助手消息：**

```json
{
  "type": "assistant",
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "sessionId": "2b6ed192-046f-495a-b8ed-5d500c01a066",
  "timestamp": 1767734690000,
  "message": {
    "role": "assistant",
    "model": "claude-opus-4-6",
    "content": [
      {
        "type": "thinking",
        "thinking": "The user is asking about test organization best practices. This is a complex topic that involves:\n1. Test structure and organization (unit, integration, e2e)\n2. Test naming conventions\n3. Fixture management\n4. Test data strategies\n5. Mocking and patching\n\nI should provide a comprehensive guide with examples..."
      },
      {
        "type": "text",
        "text": "Here's a comprehensive guide to pytest best practices..."
      }
    ]
  }
}
```

> 📌 **重点**：`thinking` 块表示 Claude 的内部思考过程，仅在启用 Extended Thinking 功能时出现。思考内容对用户透明且可读，有助于理解 Claude 的推理过程。

**主要字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | String | 事件类型：`user`（用户消息）、`assistant`（助手回复）、`progress`（进度更新）、`file-history-snapshot`（文件快照）等 |
| `uuid` | String | 该条消息的唯一标识符 |
| `sessionId` | String | 所属会话的 ID |
| `timestamp` | Number | 消息的时间戳（毫秒） |
| `parentUuid` | String | 父消息的 UUID（用于链接工具调用和结果） |
| `message.role` | String | 消息的发送者：`user` 或 `assistant` |
| `message.model` | String | 生成该消息的模型（如 `claude-opus-4-6`）仅助手消息有此字段 |
| `message.content` | String \| Array | 消息内容，可能是纯文本字符串或内容块数组 |

**内容块（Content Blocks）的类型：**

当 `message.content` 是数组时，数组中的每个元素代表不同类型的内容块：

| 类型 | 字段 | 说明 |
|------|------|------|
| `text` | `text` | 纯文本内容 |
| `thinking` | `thinking` | Claude 的内部思考过程（使用 extended thinking 时） |
| `tool_use` | `id`, `name`, `input` | 工具调用块，指定了要调用的工具、参数等 |
| `tool_result` | `tool_use_id`, `content`, `is_error` | 工具执行结果，由下一条用户消息中包含 |

**Token 使用情况（usage 字段）：**

```json
"usage": {
  "input_tokens": 512,
  "output_tokens": 1024,
  "cache_creation_input_tokens": 128,
  "cache_read_input_tokens": 64,
  "service_tier": "free"
}
```

这些字段记录了模型推理的成本：

- `input_tokens`：输入 token 数量
- `output_tokens`：输出 token 数量
- `cache_creation_input_tokens`：创建缓存的 input token（计费时降价）
- `cache_read_input_tokens`：读取缓存的 input token（计费时大幅降价）

> ⚠️ **注意**：并非所有字段都一定存在。例如，系统事件（`type: "progress"`）可能没有 `message` 字段，工具结果作为用户消息的内容块出现，而不是独立的行。

### 3.4 工具调用与结果的配对

工具调用（tool_use）和工具结果（tool_result）的对应关系需要通过 UUID 进行匹配：

1. 在某一条**助手消息**中，`content` 数组中包含 `type: "tool_use"` 的块，其中 `id` 字段是该工具调用的唯一标识。
2. 下一条**用户消息**的 `content` 数组中，会包含对应的 `type: "tool_result"` 块，其 `tool_use_id` 字段指向前面的工具调用 ID。
3. 通过这个 ID 对应关系，可以重构完整的工具调用-结果流程。

**流程示例：**

```
消息 N（助手）：
  content: [
    { type: "text", text: "Let me search..." },
    { type: "tool_use", id: "call_123", name: "Grep", input: {...} }
  ]

消息 N+1（用户）：
  content: [
    { type: "tool_result", tool_use_id: "call_123", content: "Search results..." }
  ]
```

---

## 4 配置系统

Claude Code 使用一系列 JSON 配置文件管理用户偏好、插件启用状态和安全策略。

### 4.1 settings.json —— 用户配置

位置：`~/.claude/settings.json`

这是 Claude Code 的**全局配置文件**，控制默认行为、模型选择、插件启用状态和高级特性。该文件在 CLI 启动时被读取，所有修改在下次会话启动时生效。

**完整的文件示例（带注释）：**

```json
{
  "model": "haiku",
  "enabledPlugins": {
    "claude-telemetry@local-plugins": true,
    "code-review@claude-plugins-official": false,
    "custom-hook@local-plugins": true
  },
  "alwaysThinkingEnabled": false,
  "maxTokensPerMessage": 8000,
  "autoSaveSession": true,
  "verboseLogging": false,
  "customModelEndpoint": "",
  "modelAliases": {
    "current": "opus",
    "fast": "haiku",
    "balanced": "sonnet"
  }
}
```

**配置项详细说明：**

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model` | String | `haiku` | 默认使用的模型。可选值：`haiku`（快速、便宜）、`sonnet`（平衡）、`opus`（最强）。可用 `claude --model opus` 临时覆盖 |
| `enabledPlugins` | Object | `{}` | 插件启用状态字典，键为插件标识（`name@marketplace`），值为布尔值。`true` 表示启用，`false` 表示禁用（但仍保留安装）。添加新键时自动启用新安装的插件 |
| `alwaysThinkingEnabled` | Boolean | `false` | 是否为所有消息启用扩展思考（Extended Thinking）。当启用时，Claude 会显示内部思考过程，但会增加 token 消耗和延迟 |
| `maxTokensPerMessage` | Integer | 8000 | 单条消息的最大输出 token 限制。超过此限制的响应会被截断（若未配置则无限制） |
| `autoSaveSession` | Boolean | `true` | 是否自动保存会话。禁用后需手动 `/save` 保存 |
| `verboseLogging` | Boolean | `false` | 是否启用详细日志。启用后会在 `~/.claude/debug/` 中输出更多诊断信息 |
| `customModelEndpoint` | String | "" | 自定义模型 API 端点（用于连接私有部署的模型）。留空时使用官方 Anthropic API |
| `modelAliases` | Object | （见右表） | 创建模型的别名，便于快速切换。例如 `claude --model balanced` 等价于 `claude --model sonnet` |

**配置示例场景：**

**场景 1：轻量化使用（仅用于快速脚本）**

```json
{
  "model": "haiku",
  "enabledPlugins": {},
  "alwaysThinkingEnabled": false,
  "maxTokensPerMessage": 2000
}
```

**场景 2：开发工作流（需要完整功能）**

```json
{
  "model": "sonnet",
  "enabledPlugins": {
    "claude-telemetry@local-plugins": true,
    "code-review@claude-plugins-official": true,
    "git-integration@local-plugins": true
  },
  "alwaysThinkingEnabled": false,
  "verboseLogging": true,
  "modelAliases": {
    "debug": "opus",
    "quick": "haiku"
  }
}
```

**场景 3：研究和分析（需要强大的推理）**

```json
{
  "model": "opus",
  "enabledPlugins": {
    "claude-telemetry@local-plugins": true
  },
  "alwaysThinkingEnabled": true,
  "maxTokensPerMessage": 16000
}
```

**修改 settings.json 的影响：**

| 修改项 | 何时生效 | 影响范围 |
|--------|---------|---------|
| `model` | 下一个 `claude` 命令 | 只影响新会话，已开始的会话保持原模型 |
| `enabledPlugins` | 立即生效（如果插件有热加载机制） | 影响所有后续的钩子调用 |
| `alwaysThinkingEnabled` | 下一个 Claude 回复 | 影响响应格式和 token 消耗 |
| `customModelEndpoint` | 下一个 API 请求 | 全局影响所有模型调用 |
| `verboseLogging` | 下一个日志写入 | 仅影响日志级别，不影响功能 |

> 💡 **最佳实践**：
> 1. 通过 CLI 命令 `claude config set` 修改配置，避免手动编辑引入的 JSON 格式错误
> 2. 对于临时的模型切换，使用 `--model` 标志而不是修改默认值
> 3. 定期备份 `settings.json`，以便快速恢复配置
> 4. 在团队环境中，可以在项目根目录的 `CLAUDE.md` 中指定推荐的配置，供其他开发者参考

### 4.2 policy-limits.json —— 安全策略

位置：`~/.claude/policy-limits.json`

**文件示例：**

```json
{
  "restrictions": {
    "allow_remote_control": {
      "allowed": false
    }
  }
}
```

该文件用于控制 Claude Code 的安全策略。例如，`allow_remote_control` 限制 Claude 是否可以远程控制用户的设备。

> ⚠️ **注意**：此文件通常由安全管理员或组织策略工具修改，普通用户一般不需要手动编辑。

### 4.3 其他配置文件

- **mcp-needs-auth-cache.json**：缓存需要认证的 MCP（Model Context Protocol）服务器列表
- **stats-cache.json**：缓存的统计信息（命令频率、工具使用等）
- **CLAUDE.md**：用户自定义的项目级别文档或指导说明（可选）

---

## 5 插件系统

Claude Code 支持通过插件扩展功能。插件可以来自多个来源（本地、官方市场、第三方市场），通过一个分布式注册系统进行管理。

### 5.1 插件的生命周期

```
发现（Discover）
    ↓
安装（Install）→ 注册（Register）
    ↓
启用/禁用（Enable/Disable）
    ↓
更新（Update）
    ↓
卸载（Uninstall）
```

### 5.2 installed_plugins.json —— 插件注册表

位置：`~/.claude/plugins/installed_plugins.json`

这是 Claude Code 的**插件系统的核心注册文件**，记录了所有已安装插件的元数据、安装位置和版本信息。每当安装或更新插件时，此文件都会被更新。

**完整的文件结构示例：**

```json
{
  "version": 2,
  "plugins": {
    "claude-telemetry@local-plugins": [
      {
        "scope": "user",
        "installPath": "/Users/JinghengYe/.claude/plugins/cache/local-plugins/claude-telemetry/2.0.0",
        "version": "2.0.0",
        "installedAt": "2026-03-12T03:23:49.858Z",
        "lastUpdated": "2026-03-12T03:23:49.858Z"
      }
    ],
    "code-review@claude-plugins-official": [
      {
        "scope": "user",
        "installPath": "/Users/JinghengYe/.claude/plugins/cache/claude-plugins-official/code-review/1.2.3",
        "version": "1.2.3",
        "installedAt": "2026-02-15T10:23:00.000Z",
        "lastUpdated": "2026-03-11T15:45:30.123Z"
      },
      {
        "scope": "system",
        "installPath": "/opt/claude/plugins/code-review/1.2.2",
        "version": "1.2.2",
        "installedAt": "2026-01-10T08:00:00.000Z",
        "lastUpdated": "2026-01-10T08:00:00.000Z"
      }
    ]
  }
}
```

**字段详细说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | Integer | 注册表版本号（当前为 2）。当注册表结构变化时递增，用于向后兼容 |
| `plugins` | Object | 插件字典，采用 `{name}@{marketplace}` 的标准格式作为键。同一插件可能有多个版本或作用域的安装（因此值是数组） |
| `scope` | String | 插件的安装范围：`user`（用户级别，存储在 `~/.claude`）或 `system`（系统级别，存储在系统路径） |
| `installPath` | String | 插件在磁盘上的安装路径。指向插件代码、依赖和配置的根目录 |
| `version` | String | 该插件的版本号，采用 semver 格式（例如 `2.0.0`、`1.2.3`） |
| `installedAt` | String | 首次安装该版本的时间戳（ISO 8601 格式，UTC）。对于系统级插件可能是预装时间 |
| `lastUpdated` | String | 上次更新该版本的时间戳。如果从未更新过，则与 `installedAt` 相同 |

**关键特性分析：**

1. **多版本管理**：同一插件可以有多个版本同时安装（如上例中的 code-review@1.2.3 和 1.2.2）。这允许用户进行版本回退或进行兼容性测试。

2. **插件命名空间**：使用 `name@marketplace` 格式隔离来自不同市场的同名插件。例如：
   - `code-review@claude-plugins-official` - 官方市场的代码审查插件
   - `code-review@my-company-marketplace` - 企业市场的同名插件

3. **作用域隔离**：`scope` 字段区分用户安装和系统范围的安装，便于权限管理和隔离。

**版本启用与禁用的流程：**

虽然 `installed_plugins.json` 记录了所有**已安装**的版本，但**启用状态**记录在 `~/.claude/settings.json` 中：

```json
// settings.json
{
  "enabledPlugins": {
    "claude-telemetry@local-plugins": true,
    "code-review@claude-plugins-official": false,
    "code-review@my-company-marketplace": true
  }
}
```

这样的分离设计有几个优势：

- **灵活的启用/禁用**：可以启用多个版本的同一插件（例如用于 A/B 测试）
- **快速切换**：在版本间切换只需修改 settings.json，无需重新安装
- **备份恢复**：若配置损坏，可以独立恢复安装注册和启用状态

### 5.3 插件的安装流程

当用户执行 `claude plugin install <plugin-id>` 时，Claude Code 会：

1. **查找插件**：从已知市场（`known_marketplaces.json`）中查找插件的元数据
2. **下载**：将插件的代码和依赖下载到 `~/.claude/plugins/cache/{marketplace}/{plugin-name}/{version}/`
3. **注册**：在 `installed_plugins.json` 中添加该插件的记录
4. **初始化**：执行插件的初始化脚本（如安装依赖：`pip install -r requirements.txt`）

### 5.4 插件的卸载流程

卸载插件时，Claude Code 会：

1. 从 `installed_plugins.json` 中移除该插件的记录
2. 从磁盘上删除插件的缓存目录
3. 从 `settings.json` 中移除该插件的启用状态条目

> 📌 **重点**：卸载插件只会移除 `installed_plugins.json` 中的注册记录和缓存目录，但不会修改 `settings.json`。如果稍后重新安装同一插件，它会恢复之前的启用/禁用状态。

### 5.5 known_marketplaces.json —— 已知插件市场

位置：`~/.claude/plugins/known_marketplaces.json`

这个文件定义了 Claude Code 可以访问的插件市场来源。每个市场可以是 GitHub 仓库、本地目录或远程 HTTP 服务器。

**完整示例：**

```json
{
  "claude-plugins-official": {
    "source": {
      "source": "github",
      "repo": "anthropics/claude-plugins-official"
    },
    "installLocation": "/Users/JinghengYe/.claude/plugins/marketplaces/claude-plugins-official",
    "lastUpdated": "2026-03-12T02:34:45.784Z"
  },
  "anthropic-agent-skills": {
    "source": {
      "source": "github",
      "repo": "anthropics/skills"
    },
    "installLocation": "/Users/JinghengYe/.claude/plugins/marketplaces/anthropic-agent-skills",
    "lastUpdated": "2026-02-08T02:08:35.711Z"
  },
  "local-desktop-app-uploads": {
    "source": {
      "source": "directory",
      "path": "/Users/JinghengYe/.claude/plugins/marketplaces/local-desktop-app-uploads"
    },
    "installLocation": "/Users/JinghengYe/.claude/plugins/marketplaces/local-desktop-app-uploads",
    "lastUpdated": "2026-03-09T23:09:50.585Z"
  },
  "local-plugins": {
    "source": {
      "source": "directory",
      "path": "/Users/JinghengYe/.claude/plugins/marketplaces/local-plugins"
    },
    "installLocation": "/Users/JinghengYe/.claude/plugins/marketplaces/local-plugins",
    "lastUpdated": "2026-03-11T00:00:00.000Z"
  },
  "my-company-private-plugins": {
    "source": {
      "source": "http",
      "url": "https://plugins.mycompany.com/v1/",
      "auth": "bearer_token"
    },
    "installLocation": "/Users/JinghengYe/.claude/plugins/marketplaces/my-company-private-plugins",
    "lastUpdated": "2026-03-10T15:30:00.000Z"
  }
}
```

**市场来源类型详解：**

| 来源类型 | 配置参数 | 说明 | 示例 |
|----------|---------|------|------|
| `github` | `repo` | GitHub 仓库中的插件清单 | `anthropics/claude-plugins-official` |
| `directory` | `path` | 本地文件系统目录，包含插件子目录 | `/path/to/local/plugins` |
| `http` | `url`, `auth` | 远程 HTTP API 服务器，可选认证 | `https://api.plugins.com/v1` |
| `s3` | `bucket`, `region`, `prefix` | AWS S3 存储桶（企业版） | （暂未支持） |

**市场目录结构示例：**

对于 `directory` 类型的市场，目录结构应该是：

```
/Users/JinghengYe/.claude/plugins/marketplaces/local-plugins/
├── claude-telemetry/
│   ├── 2.0.0/
│   │   ├── pyproject.toml
│   │   ├── hooks-handlers/
│   │   └── ...
│   └── 1.9.0/
├── custom-tool/
│   ├── 1.0.0/
│   └── 1.0.1/
└── manifest.json  # 可选，描述此市场中所有插件
```

**manifest.json 示例（可选）：**

```json
{
  "version": "1.0",
  "plugins": [
    {
      "id": "claude-telemetry",
      "name": "Claude Telemetry",
      "description": "Logs telemetry events from Claude Code sessions",
      "versions": ["1.9.0", "2.0.0"],
      "author": "Anthropic",
      "license": "MIT"
    },
    {
      "id": "custom-tool",
      "name": "Custom Tool",
      "description": "User-defined tool for project analysis",
      "versions": ["1.0.0", "1.0.1"],
      "author": "local-user"
    }
  ]
}
```

**市场缓存更新机制：**

Claude Code 定期从配置的市场源获取最新的插件列表：

```
应用启动
  ↓
检查每个市场的 lastUpdated 时间戳
  ↓
对于超过 24 小时未更新的市场：
  - 从源获取最新的插件列表（GitHub API / HTTP 请求）
  - 更新 installLocation 中的本地缓存
  - 更新 lastUpdated 时间戳
  ↓
展示可用插件列表
```

### 5.6 blocklist.json —— 插件黑名单

位置：`~/.claude/plugins/blocklist.json`

黑名单用于阻止已知有问题的插件被安装或使用。这可以是由组织管理员或 Anthropic 官方维护的。

**完整示例：**

```json
{
  "fetchedAt": "2026-03-12T04:27:12.150Z",
  "source": "https://api.anthropic.com/blocklist",
  "plugins": [
    {
      "plugin": "code-review@claude-plugins-official",
      "added_at": "2026-02-11T03:16:31.424Z",
      "reason": "security",
      "text": "Contains malicious code execution vulnerability CVE-2026-1234",
      "severity": "critical",
      "expiresAt": "2026-06-12T00:00:00.000Z"
    },
    {
      "plugin": "fizz@testmkt-marketplace",
      "added_at": "2026-02-12T00:00:00.000Z",
      "reason": "compatibility",
      "text": "Incompatible with Claude Code 0.2.x, breaks sessions",
      "severity": "high"
    },
    {
      "plugin": "deprecated-tool@old-marketplace",
      "added_at": "2026-01-01T00:00:00.000Z",
      "reason": "deprecated",
      "text": "Plugin discontinued, use 'modern-tool@new-marketplace' instead",
      "severity": "low",
      "replacement": "modern-tool@new-marketplace"
    }
  ]
}
```

**黑名单字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `fetchedAt` | String | 黑名单从源服务器获取的时间 |
| `source` | String | 黑名单的来源 URL（可选） |
| `plugin` | String | 被黑名单的插件 ID（`name@marketplace` 格式） |
| `added_at` | String | 添加到黑名单的时间 |
| `reason` | String | 黑名单原因：`security`（安全）、`compatibility`（兼容性）、`deprecated`（已弃用） |
| `text` | String | 详细的黑名单说明，包括 CVE 号或链接 |
| `severity` | String | 严重程度：`critical`（关键）、`high`（高）、`medium`（中）、`low`（低） |
| `expiresAt` | String | 黑名单过期时间（可选）。过期后插件可以使用 |
| `replacement` | String | 推荐的替代插件（可选，用于弃用原因） |

**黑名单的执行：**

```python
# Claude Code 在多个地方检查黑名单

# 1. 安装时
def install_plugin(plugin_id, version):
    if is_in_blocklist(plugin_id):
        reason = get_blocklist_reason(plugin_id)
        if reason['severity'] == 'critical':
            raise PluginBlockedError(f"插件已被黑名单: {reason['text']}")
        else:
            warn(f"警告: 该插件存在问题: {reason['text']}")

# 2. 启用时
def enable_plugin(plugin_id):
    if is_in_blocklist(plugin_id) and not is_expired(plugin_id):
        if get_severity(plugin_id) == 'critical':
            raise PluginBlockedError(f"无法启用黑名单插件")

# 3. 钩子加载时
def load_plugin_hooks(plugin_id):
    if is_in_blocklist_with_high_severity(plugin_id):
        log_security_incident(plugin_id)
        return False  # 跳过加载
```

> 📌 **重点**：黑名单通常由 Anthropic 官方维护，但组织也可以创建自己的黑名单进行分发。定期同步黑名单是重要的安全实践。

---

## 6 任务和计划系统

Claude Code 支持将复杂的工作分解为任务（Tasks）和计划（Plans），便于长期跟踪和执行。

### 6.1 todos 目录 —— 任务列表

位置：`~/.claude/todos/{session-uuid}-agent-{agent-id}.json`

**文件格式：**

```json
[
  {
    "content": "Update requirements.txt with Flask dependencies",
    "status": "completed",
    "activeForm": "Updating requirements.txt with Flask dependencies"
  },
  {
    "content": "Implement configuration classes in config.py",
    "status": "completed",
    "activeForm": "Implementing configuration classes in config.py"
  },
  {
    "content": "Define database models (User, Product, Order)",
    "status": "in_progress",
    "activeForm": "Defining database models (User, Product, Order)"
  },
  {
    "content": "Set up Flask app factory with extensions and blueprints",
    "status": "pending",
    "activeForm": "Setting up Flask app factory with extensions and blueprints"
  }
]
```

**状态值：**

- `pending`：待执行
- `in_progress`：执行中
- `completed`：已完成
- `deleted`：已删除

**字段说明：**

| 字段 | 说明 |
|------|------|
| `content` | 任务的文本描述 |
| `status` | 任务的当前状态 |
| `activeForm` | 任务在进行中时的进行时形式描述（用于 UI 展示） |

### 6.2 plans 目录 —— 计划文档

位置：`~/.claude/plans/{plan-id}-{title}.md`

每个保存的计划都是一个 Markdown 文件，包含详细的实现步骤、架构决策和验证清单。这些计划通常是在 `/plan` 命令下生成，用于指导多步骤的工程任务。

### 6.3 tasks 目录 —— 任务队列

位置：`~/.claude/tasks/{task-id}/`

复杂任务可能包含多个步骤，每一步保存为一个 JSON 文件：

```
tasks/
└── 944ea16d-0c36-4ae9-abb4-df484cc7d3c3/
    ├── 1.json    # 步骤 1
    ├── 2.json    # 步骤 2
    ├── 3.json    # 步骤 3
    └── ...
```

每个步骤文件包含该步骤的详细信息（描述、输入、输出等）。

---

## 7 文件编辑历史系统

### 7.1 file-history 目录

位置：`~/.claude/file-history/{session-id}/`

当 Claude Code 使用工具（如 Edit、Write）修改文件时，会在此目录中记录编辑历史：

```
file-history/
└── 2b6ed192-046f-495a-b8ed-5d500c01a066/
    ├── src_main.py.history
    ├── src_config.py.history
    └── ...
```

每个 `.history` 文件记录了该文件在该会话中的所有编辑版本，便于回溯和恢复。

### 7.2 shell-snapshots 目录

位置：`~/.claude/shell-snapshots/`

当 Claude Code 执行 Bash 命令时，会保存命令的执行快照，包括：

- 执行的命令
- 输出结果
- 执行状态码
- 时间戳

这些快照可用于调试和审计。

---

## 8 会话环境与上下文管理

### 8.1 session-env 目录

位置：`~/.claude/session-env/{session-id}.json`

每个会话会保存其执行环境的快照，包括：

```json
{
  "PATH": "/usr/local/bin:/usr/bin:...",
  "PYTHONPATH": "/Users/JinghengYe/.venv/lib/python3.9/site-packages",
  "USER": "JinghengYe",
  "HOME": "/Users/JinghengYe",
  "PWD": "/Users/JinghengYe/Documents/Projects/Agent-Guideline"
}
```

这样可以确保重新加载会话时环境变量与原始执行环境保持一致。

### 8.2 debug 目录

位置：`~/.claude/debug/{session-id}.txt`

每个会话的调试日志，记录 Claude Code 的内部操作、错误堆栈跟踪等，用于故障排查。

---

## 9 缓存系统

Claude Code 使用多个缓存目录优化性能和用户体验：

| 目录 | 用途 | 重要性 |
|------|------|--------|
| `cache/` | 通用缓存（如已下载的模型信息、市场元数据） | 中 |
| `paste-cache/` | 用户粘贴的内容缓存（用于快速访问历史粘贴） | 低 |
| `plugins/cache/` | 已安装插件的源代码和依赖 | **高** |
| `stats-cache.json` | 聚合的统计信息（每日活动、工具使用统计） | 中 |
| `mcp-needs-auth-cache.json` | MCP（Model Context Protocol）认证状态缓存 | 低 |

### 9.1 stats-cache.json —— 统计缓存的详细结构

位置：`~/.claude/stats-cache.json`

这个文件存储的是聚合统计数据，用于快速显示使用统计而无需遍历所有会话。系统定期（例如每天）重新计算统计数据。

**完整的数据结构示例：**

```json
{
  "version": 2,
  "lastComputedDate": "2026-03-11",
  "dailyActivity": [
    {
      "date": "2026-02-05",
      "messageCount": 2362,
      "sessionCount": 20,
      "toolCallCount": 651
    },
    {
      "date": "2026-02-06",
      "messageCount": 4006,
      "sessionCount": 29,
      "toolCallCount": 675
    },
    {
      "date": "2026-02-09",
      "messageCount": 6571,
      "sessionCount": 9,
      "toolCallCount": 463
    }
  ],
  "toolUsageStats": {
    "Bash": {
      "count": 2341,
      "avgTokens": 128.5,
      "errorRate": 0.08
    },
    "Edit": {
      "count": 1832,
      "avgTokens": 256.3,
      "errorRate": 0.02
    },
    "Read": {
      "count": 5023,
      "avgTokens": 512.1,
      "errorRate": 0.0
    },
    "Grep": {
      "count": 1247,
      "avgTokens": 64.2,
      "errorRate": 0.01
    }
  },
  "modelUsageStats": {
    "haiku": {
      "count": 8234,
      "totalTokens": 1234567,
      "avgTokensPerMessage": 150
    },
    "sonnet": {
      "count": 3421,
      "totalTokens": 5678901,
      "avgTokensPerMessage": 1660
    },
    "opus": {
      "count": 888,
      "totalTokens": 2345678,
      "avgTokensPerMessage": 2641
    }
  },
  "projectBreakdown": {
    "Agent-Guideline": {
      "sessions": 72,
      "messages": 12543,
      "toolCalls": 3821
    },
    "Avalon-Agent": {
      "sessions": 18,
      "messages": 2341,
      "toolCalls": 612
    }
  },
  "weeklyTrend": [
    {
      "week": "2026-W05",
      "messageCount": 8934,
      "sessionCount": 35,
      "toolCallCount": 2341
    },
    {
      "week": "2026-W06",
      "messageCount": 12556,
      "sessionCount": 48,
      "toolCallCount": 3456
    }
  ]
}
```

**统计数据字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | Integer | 缓存版本号，当数据结构变化时递增 |
| `lastComputedDate` | String | 上次计算统计数据的日期（YYYY-MM-DD 格式） |
| `dailyActivity` | Array | 每日活动记录数组，包含消息数、会话数、工具调用数 |
| `toolUsageStats` | Object | 各工具的使用统计（调用次数、平均 token、错误率） |
| `modelUsageStats` | Object | 各模型的使用统计（使用次数、总 token、平均 token） |
| `projectBreakdown` | Object | 按项目统计会话、消息、工具调用数 |
| `weeklyTrend` | Array | 按周统计的趋势数据 |

**使用场景：**

- **仪表板显示**：无需遍历所有会话即可快速显示统计数据
- **趋势分析**：识别使用模式变化
- **工具效率**：找出哪些工具最常用和最有问题（错误率）
- **成本估算**：基于模型使用统计估算 API 成本

### 9.2 插件缓存结构详解

位置：`~/.claude/plugins/cache/`

插件缓存存储了已安装插件的完整源代码和依赖。结构如下：

```
plugins/cache/
├── local-plugins/
│   └── claude-telemetry/
│       ├── 2.0.0/              # 版本目录
│       │   ├── pyproject.toml
│       │   ├── requirements.txt
│       │   ├── .deps_installed  # 标记文件，表示依赖已安装
│       │   ├── hooks-handlers/
│       │   │   ├── session_start.py
│       │   │   ├── conversation_logger.py
│       │   │   └── event_logger.py
│       │   ├── utils/
│       │   │   ├── __init__.py
│       │   │   ├── config.py
│       │   │   ├── logging.py
│       │   │   ├── time.py
│       │   │   ├── env.py
│       │   │   ├── io.py
│       │   │   └── mongodb.py
│       │   ├── LICENSE
│       │   └── CHANGELOG.md
│       └── 1.9.0/              # 旧版本（可共存）
│           └── ...
├── claude-plugins-official/
│   ├── code-review/
│   │   ├── 1.2.3/
│   │   │   ├── main.py
│   │   │   ├── config.json
│   │   │   └── ...
│   │   └── 1.2.2/
│   └── another-plugin/
└── my-company-marketplace/
    └── custom-tool/
        ├── 2.0.0/
        └── ...
```

**插件发现机制：**

Claude Code 根据 `installed_plugins.json` 中的 `installPath` 直接定位插件。如果路径不存在，该插件在启用时会触发错误。

**插件钩子加载顺序：**

```
应用启动
  ↓
读取 installed_plugins.json
  ↓
遍历 enabledPlugins（来自 settings.json）
  ↓
对每个已启用的插件：
  1. 解析 installPath
  2. 执行 hooks-handlers/session_start.py
  3. 注册其他钩子（tool_called, message_sent, 等）
  ↓
会话开始，可以使用插件功能
```

定期清理这些缓存可以节省磁盘空间，但需要注意：

```bash
# 查看插件缓存大小
du -sh ~/.claude/plugins/cache/

# 清理旧版本插件（保留最新版本）
# 注意：只有在 installed_plugins.json 中不再引用该版本时才能删除
find ~/.claude/plugins/cache -type d -name "*.*.0" -o -name "*.*.1" | \
  while read dir; do
    version=$(basename "$dir")
    echo "考虑删除: $dir (检查是否在 installed_plugins.json 中使用)"
  done

# 清理粘贴缓存（保留最近 30 天）
find ~/.claude/paste-cache -type f -mtime +30 -delete
```

> ⚠️ **警告**：不要随意删除 `plugins/cache/` 中的内容。始终先检查 `installed_plugins.json` 确认该版本不再使用，否则会导致插件加载失败。

---

## 10 遥测与统计

Claude Code 会收集使用统计信息以改进产品：

### 10.1 stats-cache.json

```json
{
  "total_sessions": 356,
  "total_messages": 12543,
  "tool_usage": {
    "Bash": 2341,
    "Edit": 1832,
    "Read": 5023,
    "Grep": 1247,
    "Write": 892
  },
  "models_used": {
    "haiku": 8234,
    "sonnet": 3421,
    "opus": 888
  }
}
```

### 10.2 telemetry 目录

`~/.claude/telemetry/` 存储详细的遥测事件（如果启用）。这些事件可帮助 Anthropic 了解工具的使用模式。

> ⚠️ **隐私提示**：遥测数据是匿名的，不包含用户的实际代码或敏感信息。用户可以通过配置禁用遥测收集。

---

## 11 项目编码规则

### 11.1 项目目录名编码

项目目录是通过对项目的绝对路径进行编码生成的。编码规则很简单：**将路径中的所有 `/` 替换为 `-`，并移除开头的 `-`**。

**编码示例：**

| 项目路径 | 编码后的目录名 |
|----------|---|
| `/Users/JinghengYe/Documents/Projects/Agent-Guideline` | `Users-JinghengYe-Documents-Projects-Agent-Guideline` |
| `/Users/JinghengYe/Documents/Projects/Flask-WebShop-Init` | `Users-JinghengYe-Documents-Projects-Flask-WebShop-Init` |
| `/home/ubuntu/workspace/myapp` | `home-ubuntu-workspace-myapp` |

这种编码方式的优点是：

- **可逆**：可以通过替换 `-` 为 `/` 恢复原始路径
- **文件系统兼容**：避免在项目路径中包含 `/` 这样的非法字符
- **唯一性**：确保不同路径的项目不会产生冲突

### 11.2 会话 UUID 命名

每个会话的 JSONL 文件名就是该会话的 UUID（RFC 4122 v4 格式）：

```
2b6ed192-046f-495a-b8ed-5d500c01a066.jsonl
15380153-3fff-4ff6-8723-39f2a7f3c050.jsonl
```

---

## 12 数据一致性与恢复

### 12.1 幽灵记录（Ghost Records）问题详解

**问题现象：**

在 VibeLens 等分析工具中，可能会遇到这样的情况：`history.jsonl` 中记录了某个会话，但实际上无法加载该会话，提示 "404 Not Found"。这些在 `history.jsonl` 中存在但没有对应 `.jsonl` 文件的记录称为**幽灵记录**。

**原因分析：**

幽灵记录通常由以下几个原因造成：

1. **项目目录删除**：
   ```
   场景：用户在 /Users/Foo/Documents/Projects/OldProject 中进行了会话，
         后来删除了整个 /Users/Foo/Documents/Projects/OldProject 目录

   结果：会话记录仍在 history.jsonl 中，
         但对应的 ~/.claude/projects/-Users-Foo-Documents-Projects-OldProject/ 目录不存在
   ```

2. **会话文件被误删**：
   ```
   场景：用户手动删除了 ~/.claude/projects/xxx/ 目录下的某些 .jsonl 文件

   结果：history.jsonl 中仍有该会话的索引，但文件已不存在
   ```

3. **数据迁移或恢复失败**：
   ```
   场景：从备份恢复时，history.jsonl 被恢复了，但 projects/ 目录的部分数据丢失

   结果：不完整的恢复导致记录和文件不同步
   ```

4. **并发操作冲突**：
   ```
   场景：多个 Claude Code 实例同时运行，删除操作和索引更新发生竞争

   结果：索引删除后但文件删除前发生了崩溃，造成不一致
   ```

**统计数据示例（来自本地数据）：**

```
总会话记录: 357
实际存在文件的会话: 72
幽灵记录: 285 (79.8%)

幽灵记录分布（按项目）:
- Flask-WebShop-Init: 45 条（项目整个被删除）
- Flask-WebShop-Main: 38 条（项目整个被删除）
- OpenHands: 52 条（项目整个被删除）
- StudyNote: 23 条（部分文件丢失）
- ... 其他项目
```

**检测幽灵记录的方法：**

```python
import json
from pathlib import Path
from collections import defaultdict

def find_ghost_records(claude_dir):
    """检测幽灵记录"""
    history_file = claude_dir / 'history.jsonl'
    projects_dir = claude_dir / 'projects'

    # 构建文件索引
    existing_files = {}
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            for jsonl_file in project_dir.glob('*.jsonl'):
                session_id = jsonl_file.stem
                existing_files[session_id] = jsonl_file

    # 检查历史记录
    ghost_records = []
    projects_with_ghosts = defaultdict(int)

    with open(history_file) as f:
        for line in f:
            entry = json.loads(line)
            session_id = entry['sessionId']
            project = entry.get('project', 'unknown')

            if session_id not in existing_files:
                ghost_records.append({
                    'session_id': session_id,
                    'project': project,
                    'display': entry.get('display', ''),
                    'timestamp': entry.get('timestamp', 0)
                })
                projects_with_ghosts[project] += 1

    print(f"幽灵记录统计:")
    print(f"  总数: {len(ghost_records)}")
    print(f"  涉及项目数: {len(projects_with_ghosts)}")
    print(f"\n按项目分布:")
    for project, count in sorted(projects_with_ghosts.items(),
                                  key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {Path(project).name}: {count} 条记录")

    return ghost_records

# 使用示例
claude_dir = Path.home() / '.claude'
ghosts = find_ghost_records(claude_dir)
```

**处理幽灵记录的策略：**

| 策略 | 优点 | 缺点 | 场景 |
|------|------|------|------|
| **忽略** | 不影响现有数据，安全 | 列表里仍有垃圾数据 | 记录不多，不影响使用 |
| **清理索引** | 从 history.jsonl 中删除幽灵记录 | 永久丢失索引信息 | 确认文件无法恢复 |
| **尝试恢复** | 可能恢复有价值的数据 | 需要备份或文件恢复工具 | 误删的重要会话 |
| **自动过滤** | 在应用层隐藏幽灵记录 | 需要修改应用代码 | VibeLens 等分析工具 |

**推荐方案：应用层过滤（VibeLens 的方案）**

```python
# VibeLens 的 LocalSource 实现
class LocalSource:
    def __init__(self, claude_dir):
        self._claude_dir = claude_dir
        self._file_index = {}
        self._build_file_index()

    def _build_file_index(self):
        """扫描磁盘，构建实际存在的会话文件索引"""
        projects_dir = self._claude_dir / 'projects'
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                for jsonl_file in project_dir.glob('*.jsonl'):
                    session_id = jsonl_file.stem
                    self._file_index[session_id] = jsonl_file

    def list_sessions(self, limit=100, offset=0):
        """仅返回有文件的会话，自动过滤幽灵记录"""
        # 读取 history.jsonl
        all_sessions = parse_history_index(self._claude_dir)

        # 只返回在 _file_index 中存在的会话
        valid_sessions = [
            s for s in all_sessions
            if s.session_id in self._file_index
        ]

        return valid_sessions[offset:offset+limit]
```

这样做的好处是：
- 用户界面中只看到可加载的会话
- 不修改原始的 `history.jsonl`（保留所有历史记录）
- 可以轻松统计和识别幽灵记录比例
- 下次找到数据文件（例如恢复备份）时，自动重新可用

### 12.2 备份策略

`~/.claude/backups/` 目录存储历史文件的备份，防止意外删除或损坏。Claude Code 会定期创建快照。

**备份内容：**

- `history.jsonl` 的历史版本（按日期命名）
- 重要配置文件的备份（settings.json、installed_plugins.json）
- 可选：session 文件的快照

**手动备份脚本：**

```bash
#!/bin/bash
# 完整备份 ~/.claude 目录（排除大型缓存）

BACKUP_DIR="${HOME}/.claude-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "备份 ~/.claude ..."
rsync -av \
  --exclude='paste-cache' \
  --exclude='plugins/cache' \
  --exclude='telemetry' \
  ${HOME}/.claude/ \
  "$BACKUP_DIR/"

echo "备份完成: $BACKUP_DIR"
echo "大小: $(du -sh $BACKUP_DIR | cut -f1)"
```

### 12.3 数据损坏恢复

如果 JSONL 文件损坏（例如行格式错误），可以：

1. **检查文件完整性**：

```bash
# 验证每一行是否都是有效的 JSON
python3 << 'EOF'
import json
import sys

def validate_jsonl(filepath):
    errors = []
    with open(filepath) as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                errors.append({
                    'line': i,
                    'error': str(e),
                    'content': line[:100]
                })

    if errors:
        print(f"发现 {len(errors)} 个格式错误:")
        for err in errors[:5]:  # 只显示前 5 个
            print(f"  行 {err['line']}: {err['error']}")
            print(f"    内容: {err['content']}")
        return False
    else:
        print(f"✓ 文件有效")
        return True

validate_jsonl('/Users/JinghengYe/.claude/projects/.../sessionId.jsonl')
EOF
```

2. **恢复备份**：从 `~/.claude/backups/` 或 `~/.claude-backups/` 目录恢复最近的备份版本

3. **手动修复**：对于部分损坏的文件，可以删除损坏的行，其余行仍可正常解析

```bash
# 移除格式错误的行（危险操作，先备份！）
python3 << 'EOF'
import json

def repair_jsonl(filepath):
    """移除无法解析的行"""
    valid_lines = []
    removed = 0

    with open(filepath) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                json.loads(line)
                valid_lines.append(line)
            except json.JSONDecodeError:
                removed += 1

    if removed > 0:
        with open(filepath, 'w') as f:
            f.writelines(valid_lines)
        print(f"修复完成: 移除 {removed} 个无效行")
    else:
        print(f"文件无错误")

repair_jsonl('/Users/JinghengYe/.claude/projects/.../sessionId.jsonl')
EOF
```

> ⚠️ **注意**：JSONL 格式的关键优势是其容错性——一行的损坏不会影响其他行的解析。但**在修复之前务必备份**，且要了解丢失数据的后果。

---

## 13 性能和存储优化

### 13.1 存储空间分析

```bash
# 统计各目录的磁盘占用
du -sh ~/.claude/*/

# 找出最大的单个文件
find ~/.claude -type f -exec ls -lh {} \; | sort -k5 -hr | head -20
```

通常，`projects/` 目录占用最多空间（会话数据），其次是 `telemetry/`（遥测数据）和 `paste-cache/`（粘贴缓存）。

### 13.2 清理不必要的文件

```bash
# 删除过期的粘贴缓存（90 天以前）
find ~/.claude/paste-cache -type f -mtime +90 -delete

# 删除空目录
find ~/.claude -type d -empty -delete

# 压缩旧的遥测数据
gzip ~/.claude/telemetry/*.json
```

### 13.3 JSONL 文件优化

当会话文件过大时，可以考虑：

1. **归档旧会话**：将完成的会话数据移到离线存储
2. **压缩**：使用 `gzip` 压缩历史会话文件
3. **增量备份**：只备份新增的消息行

---

## 14 常见问题解答

### Q1: 我误删了某个会话文件，如何恢复？

**A:** 首先检查 `~/.claude/backups/` 目录是否有自动备份。如果没有，可以通过以下方式尝试恢复：

```bash
# 检查文件系统的垃圾桶或回收站
ls ~/.Trash/

# 或使用系统恢复工具（时间机器等）
```

如果确实无法恢复，会话数据将永久丢失。这是为什么定期手动备份 `~/.claude/projects/` 很重要。

### Q2: 为什么某个会话在列表中看不到？

**A:** 可能的原因：

1. **无对应的 `.jsonl` 文件**：会话出现在 `history.jsonl` 中，但实际的会话数据文件丢失（例如项目目录被删除）
2. **编码错误**：项目路径编码不正确，导致会话文件位置错误
3. **缓存未刷新**：应用缓存了旧的会话列表，需要重启 Claude Code

### Q3: 如何导出特定会话的对话内容？

**A:** 可以编写脚本从 JSONL 文件中提取并转换为其他格式：

```python
import json
from pathlib import Path

def export_session_to_markdown(jsonl_path, output_path):
    """将会话导出为 Markdown 格式"""
    with open(jsonl_path) as f, open(output_path, 'w') as out:
        for line in f:
            obj = json.loads(line)
            if obj.get('type') not in ('user', 'assistant'):
                continue
            msg = obj.get('message', {})
            role = msg.get('role', '')
            content = msg.get('content', '')

            if isinstance(content, str):
                out.write(f"\n**{role.upper()}**\n\n{content}\n")
            # 其他内容块类型的处理...

export_session_to_markdown(
    '~/.claude/projects/.../sessionId.jsonl',
    './session_export.md'
)
```

### Q4: 如何禁用遥测数据收集？

**A:** 编辑 `~/.claude/settings.json`，添加：

```json
{
  "telemetryEnabled": false
}
```

或通过 CLI 命令：

```bash
claude config set telemetryEnabled false
```

### Q5: 插件系统如何与 Claude 的工具调用整合？

**A:** 插件通过"钩子"（Hooks）系统与 Claude Code 的各个生命周期阶段集成：

- **session_start**：会话启动时执行的初始化逻辑
- **tool_called**：工具被调用时拦截和修改参数
- **tool_result**：工具执行完成后处理结果
- **message_sent**：消息发送前过滤或修改

例如，`claude-telemetry` 插件通过这些钩子记录所有工具的使用情况。

---

## 15 安全建议

### 15.1 文件权限

`~/.claude/` 目录中的某些文件包含敏感信息（如认证令牌、会话内容等），应确保正确的文件权限：

```bash
# 确保目录权限为 700（仅所有者可访问）
chmod 700 ~/.claude

# 检查权限
ls -ld ~/.claude
```

### 15.2 备份时的敏感信息

备份会话数据时，要注意：

- 不要备份到云存储中（除非已加密）
- 不要将备份文件上传到公开的代码仓库
- 定期检查备份的访问权限

### 15.3 插件安全

仅从信任的市场安装插件。黑名单中的插件应避免安装：

```bash
# 查看已安装的所有插件
cat ~/.claude/plugins/installed_plugins.json | python3 -m json.tool

# 检查黑名单
cat ~/.claude/plugins/blocklist.json
```

---

## 16 集成与扩展

### 16.1 使用 VibeLens 分析会话数据

本项目的 VibeLens 工具就是一个例子，展示了如何整合 `~/.claude` 中的数据：

```python
from pathlib import Path
from vibelens.ingest.claude_code import parse_history_index, parse_session_jsonl

# 快速列出所有会话
sessions = parse_history_index(Path.home() / '.claude')
for session in sessions[:10]:
    print(f"{session.session_id}: {session.first_message}")

# 加载完整会话数据
messages = parse_session_jsonl(
    Path.home() / '.claude' / 'projects' / '...' / 'sessionId.jsonl'
)
for msg in messages:
    if msg.role == 'user':
        print(f"User: {msg.content}")
```

### 16.2 自定义分析脚本

可以编写脚本分析工具使用情况、会话统计等：

```python
import json
from collections import Counter
from pathlib import Path

def analyze_tool_usage(history_jsonl_path):
    """统计所有工具的使用频率"""
    tool_counts = Counter()

    with open(history_jsonl_path) as f:
        for line in f:
            obj = json.loads(line)
            if obj.get('type') != 'assistant':
                continue
            msg = obj.get('message', {})
            content = msg.get('content', [])

            if isinstance(content, list):
                for block in content:
                    if block.get('type') == 'tool_use':
                        tool_counts[block.get('name')] += 1

    return tool_counts

# 使用
usage = analyze_tool_usage(Path.home() / '.claude' / 'history.jsonl')
for tool, count in usage.most_common(10):
    print(f"{tool}: {count} times")
```

---

## 17 版本兼容性

Claude Code 的数据格式会随着版本演进。重要的版本变更包括：

| 版本 | 主要变更 |
|------|---------|
| 0.1.0 | 初始版本，JSONL 格式稳定 |
| 0.1.x | 添加 extended thinking 支持，引入 `thinking` 内容块 |
| 0.2.0+ | 可能引入新的序列化格式或数据结构 |

> 💡 **最佳实践**：在依赖 Claude Code 内部数据格式的工具中，应该进行版本检查和格式验证，以应对未来的升级。

---

## 18 实战工具：会话数据分析脚本

### 18.1 完整的会话统计分析脚本

以下脚本可以快速分析 `~/.claude` 中的所有数据：

```python
#!/usr/bin/env python3
"""Complete Claude Code session analysis toolkit"""

import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

class ClaudeAnalyzer:
    def __init__(self, claude_dir=None):
        self.claude_dir = Path(claude_dir or Path.home() / '.claude')
        self.history_file = self.claude_dir / 'history.jsonl'
        self.projects_dir = self.claude_dir / 'projects'
        self.sessions = []
        self.existing_files = set()
        self._load_data()

    def _load_data(self):
        """加载所有会话数据"""
        # 构建文件索引
        if self.projects_dir.exists():
            for project_dir in self.projects_dir.iterdir():
                if project_dir.is_dir():
                    for jsonl_file in project_dir.glob('*.jsonl'):
                        self.existing_files.add(jsonl_file.stem)

        # 加载 history.jsonl
        if self.history_file.exists():
            with open(self.history_file) as f:
                for line in f:
                    self.sessions.append(json.loads(line))

    def stats_summary(self):
        """打印总体统计"""
        total = len(self.sessions)
        existing = sum(1 for s in self.sessions if s['sessionId'] in self.existing_files)
        ghost = total - existing

        print(f"📊 会话统计")
        print(f"  总记录: {total}")
        print(f"  有效会话: {existing} ({existing/total*100:.1f}%)")
        print(f"  幽灵记录: {ghost} ({ghost/total*100:.1f}%)")
        print()

    def project_breakdown(self):
        """按项目统计"""
        projects = defaultdict(lambda: {'count': 0, 'existing': 0, 'ghost': 0})

        for session in self.sessions:
            project = Path(session['project']).name if 'project' in session else 'unknown'
            projects[project]['count'] += 1
            if session['sessionId'] in self.existing_files:
                projects[project]['existing'] += 1
            else:
                projects[project]['ghost'] += 1

        print(f"📁 项目分布（Top 10）")
        for project, stats in sorted(projects.items(),
                                      key=lambda x: x[1]['count'], reverse=True)[:10]:
            pct = stats['existing'] / stats['count'] * 100 if stats['count'] > 0 else 0
            print(f"  {project:40} {stats['count']:3} ({stats['existing']:3} 有效, {pct:5.1f}%)")
        print()

# 使用示例
if __name__ == '__main__':
    analyzer = ClaudeAnalyzer()
    analyzer.stats_summary()
    analyzer.project_breakdown()
```

### 18.2 快速数据检查命令

```bash
# 检查 history.jsonl 大小和行数
ls -lh ~/.claude/history.jsonl
wc -l ~/.claude/history.jsonl

# 查看最新的会话
tail -1 ~/.claude/history.jsonl | python3 -m json.tool

# 统计会话数据大小
du -sh ~/.claude/projects/

# 找出最大的会话文件
find ~/.claude/projects -name '*.jsonl' -exec ls -lh {} \; | sort -k5 -hr | head -5

# 检查项目目录一致性
python3 << 'EOF'
import json
from pathlib import Path
from collections import defaultdict

projects = defaultdict(list)
for proj_dir in (Path.home() / '.claude' / 'projects').iterdir():
    if proj_dir.is_dir():
        for f in proj_dir.glob('*.jsonl'):
            projects[proj_dir.name].append(f.stem)

print(f"项目目录: {len(projects)}")
for name in sorted(projects.keys())[:10]:
    print(f"  {name}: {len(projects[name])} 个会话")
EOF
```

---

## 20 参考资料

- [Claude Code Official Documentation](https://claude.com/claude-code)
- [JSON Lines Format](https://jsonlines.org/) —— JSONL 格式规范
- [UUID RFC 4122](https://tools.ietf.org/html/rfc4122) —— UUID 标准
- [Claude Code Plugins Architecture](https://docs.anthropic.com/en/docs/about-claude/plugin-system) —— 插件系统文档

---

## 21 总结

`~/.claude` 目录是 Claude Code 的数据心脏，采用分层设计和分布式存储策略：

- **核心数据**：会话数据存储在 `projects/` 下的 JSONL 文件中，通过 `history.jsonl` 进行快速索引
- **配置管理**：用户偏好和安全策略通过 JSON 配置文件管理
- **扩展机制**：插件系统提供了灵活的功能扩展方式
- **性能优化**：多层缓存、JSONL 格式和懒加载策略确保性能
- **数据安全**：备份系统、文件权限和恢复机制保障数据完整性

理解这一结构是进行会话分析、插件开发、数据集成和系统调试的基础。通过 VibeLens 这样的工具，我们可以充分利用 Claude Code 积累的数据，进行可视化分析和智能查询。

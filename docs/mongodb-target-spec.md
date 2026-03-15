# MongoDB Target & Source 设计规范

## 1. 概述

VibeLens 使用 MongoDB 作为远程数据存储，支持将本地解析的 agent session 数据推送（push）到 MongoDB，以及从 MongoDB 查询（pull）session 数据。设计兼容所有三种 agent 接口：Claude Code、Codex CLI、Gemini CLI。

核心设计原则：
- **数据完整性**：零数据丢失，所有字段忠实保存
- **多 agent 兼容**：统一 Pydantic model 层已完成格式归一化
- **16 MB BSON 限制**：两集合设计规避大文档问题
- **幂等性**：重复推送自动跳过已存在的 session

## 2. 两集合 Schema 设计

### 为什么不使用嵌入式文档？

一个 200+ 消息的 session（含 tool output）很容易超过 MongoDB 的 16 MB BSON 文档限制。两集合设计与现有 SQLite schema（`sessions` + `messages` 表）保持一致，同时支持高效的消息分页。

```
┌─────────────────────────────────────────────┐
│                  MongoDB                     │
│  ┌──────────────┐  ┌─────────────────────┐  │
│  │  sessions     │  │  messages            │  │
│  │  (summary +   │  │  (flat, one doc per  │  │
│  │   sub-session │  │   message, agent_id  │  │
│  │   metadata)   │  │   discriminator)     │  │
│  └──────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────┘
```

### sessions 集合

| 字段 | 类型 | 说明 |
|------|------|------|
| `_id` | string | session_id（自然主键） |
| `project_id` | string | 编码后的项目路径标识符 |
| `project_name` | string | 人类可读的项目名 |
| `timestamp` | string (ISO-8601) | 会话开始时间 |
| `duration` | int | 总时长（秒） |
| `message_count` | int | 用户和助手消息数 |
| `tool_call_count` | int | 工具调用总数 |
| `models` | list[string] | 使用的 LLM 模型 |
| `first_message` | string | 首条用户消息预览 |
| `source_type` | string | 数据来源类型 |
| `source_name` | string | 数据源名称 |
| `source_host` | string | 远程主机/URL |
| `total_input_tokens` | int | 输入 token 总量 |
| `total_output_tokens` | int | 输出 token 总量 |
| `total_cache_read` | int | 缓存读取 token 数 |
| `total_cache_write` | int | 缓存写入 token 数 |
| `diagnostics` | object \| null | 解析诊断信息 |
| `sub_sessions` | list[object] | 子 agent 元数据（不含消息） |

### messages 集合

| 字段 | 类型 | 说明 |
|------|------|------|
| `_id` | string | 消息 UUID |
| `session_id` | string | 所属 session ID |
| `agent_id` | string | "" = 主会话, "agent-xxx" = 子 agent |
| `parent_uuid` | string | 父消息 UUID |
| `role` | string | "user" 或 "assistant" |
| `type` | string | 消息类型 |
| `content` | string \| list[object] | 文本或 ContentBlock 列表 |
| `thinking` | string \| null | Extended thinking 内容 |
| `model` | string | 生成该消息的模型 |
| `timestamp` | string (ISO-8601) | 消息创建时间 |
| `is_sidechain` | bool | 是否为 sidechain 消息 |
| `usage` | object \| null | TokenUsage 统计 |
| `tool_calls` | list[object] | ToolCall 列表 |

## 3. Push 工作流

```
SQLite (local)  →  MongoDBTarget.push_sessions()  →  MongoDB (remote)
     │                      │
     │   query_session_detail()   _serialize_session()
     │   for each session_id  →   check existence → insert session doc
     │                            _flatten_messages() → batch insert messages
     └──────────────────────────────────────────────────────────┘
```

序列：
1. API 接收 `PushRequest`（session_ids + target=mongodb）
2. 从 SQLite 加载每个 session 的 `SessionDetail`
3. 对每个 session：
   - 检查 `_id` 是否已存在（幂等跳过）
   - 序列化 `SessionSummary` → session 文档
   - 递归展平所有消息（主会话 + 子 agent），标记 `agent_id`
   - 以 `BATCH_SIZE=500` 批量插入消息
4. 返回 `PushResult`（uploaded / skipped / errors）

## 4. Query/Pull 工作流

```
MongoDBSource.list_sessions()  →  sessions 集合 find() + filter/sort/paginate
MongoDBSource.get_session()    →  sessions + messages 集合 → 重建 SubAgentSession 层级
MongoDBSource.list_projects()  →  sessions.distinct("project_name")
```

## 5. Sub-agent 重建算法

Push 时将 sub-session 元数据（不含消息）嵌入 session 文档，消息则以 `agent_id` 标识扁平存储。

Pull 时重建步骤：
1. 按 `session_id` 查询所有消息
2. 按 `agent_id` 分组：`""` = 主会话，其余为子 agent
3. 递归遍历 session 文档中的 `sub_sessions` 元数据
4. 将对应 `agent_id` 的消息附加到各 `SubAgentSession`
5. 支持多层嵌套（agent 可 spawn 子 agent）

## 6. 索引设计

### sessions 集合
- `_id`：自然主键（session_id），自动索引
- `source_type`：按数据源类型过滤
- `project_name`：按项目名过滤
- `(timestamp, -1)`：按时间倒序排列

### messages 集合
- `_id`：自然主键（message UUID），自动索引
- `(session_id, timestamp)`：加载 session 所有消息并按时间排序
- `(session_id, agent_id)`：按 agent 过滤消息

## 7. 错误处理

| 场景 | 处理方式 |
|------|----------|
| MongoDB 连接失败 | `ValueError` at config validation |
| session 已存在 | 幂等跳过，计入 `skipped` |
| 单个 session 插入失败 | 记录 error，继续处理其余 session |
| 消息批量插入部分失败 | `ordered=False` 确保其余消息继续插入 |
| session 不存在于 SQLite | 跳过并 log warning |
| MongoDB 查询失败 | 异常向上传播到 API 层 |

## 8. 配置参考

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `VIBELENS_MONGODB_URI` | `""` | MongoDB 连接 URI |
| `VIBELENS_MONGODB_DB` | `"vibelens"` | 数据库名 |

配置为空时，MongoDB 相关功能不激活。`/api/sources` 和 `/api/targets` 只在配置非空时列出 MongoDB。

## 9. API 调用示例

### Push sessions

```http
POST /api/push/mongodb
Content-Type: application/json

{
    "session_ids": ["uuid-1", "uuid-2"],
    "target": "mongodb"
}
```

Response:
```json
{
    "total": 2,
    "uploaded": 2,
    "skipped": 0,
    "errors": []
}
```

### 查询 targets/sources

```http
GET /api/targets
→ [{"type": "mongodb", "name": "MongoDB"}]

GET /api/sources
→ [{"type": "local", "name": "Local Claude Code"}, {"type": "mongodb", "name": "MongoDB"}]
```

## 10. 兼容性矩阵

| Agent | Parser | SessionSummary | SessionDetail | Sub-agents | Push | Pull |
|-------|--------|---------------|---------------|------------|------|------|
| Claude Code | `ClaudeCodeParser` | ✅ | ✅ | ✅ (recursive) | ✅ | ✅ |
| Codex CLI | `CodexParser` | ✅ | ✅ | ❌ (no sub-agents) | ✅ | ✅ |
| Gemini CLI | `GeminiParser` | ✅ | ✅ | ❌ (no sub-agents) | ✅ | ✅ |
| Dataclaw | `DataclawParser` | ✅ | ✅ | ❌ | ✅ | ✅ |

所有 parser 输出统一的 `SessionDetail` / `Message` 模型，MongoDB 层对 agent 类型透明。

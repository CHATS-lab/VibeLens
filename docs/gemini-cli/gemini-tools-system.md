# Gemini CLI Tools System 深度解析

| 条目 | 内容 |
|------|------|
| **主题** | Gemini CLI 工具系统架构与实现 |
| **源码版本** | gemini-cli (Google, Apache-2.0) |
| **核心路径** | `packages/core/src/tools/` |
| **涉及模块** | Tool 类型层次、ToolRegistry、MCP 集成、Scheduler、ToolExecutor |
| **关联对比** | Claude Code Tool System |
| **撰写日期** | 2026-03-14 |

---

## 1 概述

Gemini CLI 的工具系统采用 **Builder / Invocation 双阶段模式**：首先由 `DeclarativeTool`（Builder）校验参数并生成 `ToolInvocation` 对象，然后由 `Scheduler` 编排执行。这种设计将"参数验证 + Schema 声明"与"执行逻辑"完全解耦，使得同一个 tool 定义可以被不同的 scheduler、sub-agent 复用。

整体数据流可概括为：

```
Model FunctionCall → ToolRegistry.getTool(name)
  → DeclarativeTool.build(params)  // 验证 + 创建 Invocation
    → Scheduler.schedule(request)
      → Policy check → Confirmation flow
        → ToolExecutor.execute(invocation)
          → ToolResult { llmContent, returnDisplay, error? }
```

### 1.1 Tool 生命周期全景图

下面的 ASCII 图展示了一个 tool call 从 Gemini API 返回到最终渲染的完整生命周期，涵盖正常路径和异常分支：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Gemini API Response (model turn)                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  candidates[0].content.parts[]:                                   │ │
│  │    { functionCall: { name: "read_file", args: {...}, id: "uuid" } │ │
│  │    { functionCall: { name: "replace",   args: {...}, id: "uuid" } │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────┐
│  Scheduler.schedule(ToolCallRequestInfo[])           │
│  ┌───────────────────────────────────────────────┐  │
│  │ for each request:                             │  │
│  │   1. ToolRegistry.getTool(name)               │  │
│  │      └─ alias fallback (legacy names)         │  │
│  │   2. tool.build(params)                       │  │
│  │      ├─ SchemaValidator.validate() ──► Error? │  │──► Validating
│  │      └─ createInvocation(params)              │  │
│  │   3. checkPolicy(invocation)                  │  │
│  │      ├─ ALLOW  ──────────────────────────►    │  │──► Scheduled
│  │      ├─ DENY   ──────────────────────────►    │  │──► Error (policy_violation)
│  │      └─ ASK_USER ────────────────────────►    │  │──► AwaitingApproval
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────┬────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
     │ ALLOW        │ │ ASK_USER    │ │ DENY         │
     │ (auto-pass)  │ │ (show UI)   │ │ (rejected)   │
     └──────┬───────┘ └──────┬──────┘ └──────┬───────┘
            │                │               │
            │         ┌──────┴──────┐        │
            │         │ User picks: │        │
            │         │ ProceedOnce │        │
            │         │ ProceedAlways        │
            │         │ ModifyWithEditor     │
            │         │ Cancel ──────────────┤
            │         └──────┬──────┘        │
            │                │               │
            ▼                ▼               ▼
┌──────────────────────────────────┐  ┌──────────────┐
│  ToolExecutor.execute(invocation)│  │  ErrorResult  │
│  ┌────────────────────────────┐  │  │  (Cancelled   │
│  │ executeToolWithHooks()     │  │  │   or Denied)  │
│  │  ├─ pre-hook              │  │  └──────────────┘
│  │  ├─ invocation.execute()  │  │
│  │  └─ post-hook             │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │ Output handling:           │  │
│  │  ├─ streaming (shell)     │  │
│  │  ├─ truncation check      │  │
│  │  └─ save to temp file     │  │
│  └────────────────────────────┘  │
└──────────────────┬───────────────┘
                   │
         ┌─────────┼─────────┐
         ▼         ▼         ▼
   ┌──────────┐ ┌──────┐ ┌──────────┐
   │ Success  │ │Error │ │Cancelled │
   │ToolResult│ │Result│ │Result    │
   └────┬─────┘ └──┬───┘ └────┬─────┘
        │          │          │
        ▼          ▼          ▼
┌──────────────────────────────────────────────┐
│  convertToFunctionResponse()                  │
│  → Part[] { functionResponse: { response } }  │
│  → 返回给 Gemini API 作为下一轮 user content   │
└──────────────────────────────────────────────┘
```

> 📌 **关键要点**：一个 tool call 最多经历 7 个状态（`Validating` → `Scheduled` → `AwaitingApproval` → `Executing` → `Success`/`Error`/`Cancelled`）。状态转换由 `SchedulerStateManager` 统一管理并通过 `MessageBus` 广播给 UI 层。

---

## 2 Tool 类型层次

### 2.1 核心接口与抽象类

源文件：`packages/core/src/tools/tools.ts`

```
ToolInvocation<TParams, TResult>          (interface — 已验证的可执行工具调用)
  └── BaseToolInvocation<TParams, TResult> (abstract class — 封装 confirmation 逻辑)

ToolBuilder<TParams, TResult>              (interface — 工具定义 + 构建器)
  └── DeclarativeTool<TParams, TResult>    (abstract class — Schema、validate、build)
        └── BaseDeclarativeTool<TParams, TResult> (abstract class — 增加 SchemaValidator + createInvocation)
```

> 📌 **ToolInvocation** 是最终被执行的单元，包含四个关键方法：`getDescription()`、`toolLocations()`、`shouldConfirmExecute()`、`execute()`。

> 💡 **BaseDeclarativeTool** 是推荐的工具基类。它把 `build()` 拆成两步：先用 `SchemaValidator.validate()` 做 JSON Schema 校验，再调用子类实现的 `createInvocation()` 产出具体的 Invocation 实例。

### 2.2 类型别名

```typescript
type AnyToolInvocation = ToolInvocation<object, ToolResult>;
type AnyDeclarativeTool = DeclarativeTool<object, ToolResult>;
```

### 2.3 Kind 枚举——工具分类与权限

```typescript
enum Kind {
  Read, Edit, Delete, Move, Search, Execute,
  Think, Agent, Fetch, Communicate, Plan, SwitchMode, Other
}
```

- **MUTATOR_KINDS**：`[Edit, Delete, Move, Execute]` — 有副作用的操作
- **READ_ONLY_KINDS**：`[Read, Search, Fetch]` — 只读操作，`isReadOnly` 由 Kind 自动推导

### 2.4 FunctionDeclaration 实际 JSON 示例

每个工具通过 `getSchema()` 生成发送给 Gemini API 的 `FunctionDeclaration`。以下是几个核心工具的真实 Schema（源自 `definitions/model-family-sets/default-legacy.ts`），展示 `parametersJsonSchema` 与自动注入的 `wait_for_previous` 字段：

**`read_file` FunctionDeclaration**

```json
{
  "name": "read_file",
  "description": "Reads and returns the content of a specified file. If the file is large, the content will be truncated...",
  "parametersJsonSchema": {
    "type": "object",
    "properties": {
      "file_path": {
        "description": "The path to the file to read.",
        "type": "string"
      },
      "start_line": {
        "description": "Optional: The 1-based line number to start reading from.",
        "type": "number"
      },
      "end_line": {
        "description": "Optional: The 1-based line number to end reading at (inclusive).",
        "type": "number"
      },
      "wait_for_previous": {
        "type": "boolean",
        "description": "Set to true to wait for all previously requested tools in this turn to complete before starting..."
      }
    },
    "required": ["file_path"]
  }
}
```

**`run_shell_command` FunctionDeclaration**

```json
{
  "name": "run_shell_command",
  "description": "Runs a shell command on the user's system...",
  "parametersJsonSchema": {
    "type": "object",
    "properties": {
      "command": {
        "description": "The shell command to execute.",
        "type": "string"
      },
      "description": {
        "description": "Describe what this command does...",
        "type": "string"
      },
      "dir_path": {
        "description": "Optional working directory for the command.",
        "type": "string"
      },
      "is_background": {
        "description": "Set to true to run in the background.",
        "type": "boolean"
      },
      "wait_for_previous": {
        "type": "boolean",
        "description": "Set to true to wait for all previously requested tools..."
      }
    },
    "required": ["command"]
  }
}
```

**`replace` (Edit) FunctionDeclaration**

```json
{
  "name": "replace",
  "description": "Replaces text within a file. By default, expects exactly ONE occurrence of old_string...",
  "parametersJsonSchema": {
    "type": "object",
    "properties": {
      "file_path": {
        "description": "The path to the file to modify.",
        "type": "string"
      },
      "instruction": {
        "description": "A clear, semantic instruction for the code change...",
        "type": "string"
      },
      "old_string": {
        "description": "The exact literal text to replace...",
        "type": "string"
      },
      "new_string": {
        "description": "The exact literal text to replace old_string with...",
        "type": "string"
      },
      "allow_multiple": {
        "type": "boolean",
        "description": "If true, replace ALL occurrences of old_string."
      },
      "wait_for_previous": {
        "type": "boolean",
        "description": "..."
      }
    },
    "required": ["file_path", "instruction", "old_string", "new_string"]
  }
}
```

> 💡 **`wait_for_previous`** 由 `DeclarativeTool.addWaitForPreviousParameter()` 自动注入到每个工具的 Schema 中，模型无需在每个工具的参数定义中手动声明。

---

## 3 全量内置工具清单

源文件：`packages/core/src/tools/tool-names.ts` 中导出的 `ALL_BUILTIN_TOOL_NAMES` 以及各实现文件。

| # | Tool Name (API 名称) | 显示名 | Kind | 源文件 | 功能概述 |
|---|---------------------|--------|------|--------|---------|
| 1 | `read_file` | ReadFile | Read | `read-file.ts` | 读取单个文件，支持 `start_line` / `end_line` 行范围 |
| 2 | `write_file` | WriteFile | Edit | `write-file.ts` | 创建或覆写文件，含 LLM content correction 与 diff 确认 |
| 3 | `replace` | Edit | Edit | `edit.ts` | 精确字符串替换编辑，支持 fuzzy match recovery |
| 4 | `run_shell_command` | — | Execute | `shell.ts` | 执行 shell 命令，支持前台/后台、streaming output |
| 5 | `glob` | FindFiles | Search | `glob.ts` | Glob 模式文件搜索 |
| 6 | `grep_search` | — | Search | `grep.ts` / `ripGrep.ts` | 内容搜索 (内置 grep 或 ripgrep) |
| 7 | `list_directory` | — | Read | `ls.ts` | 列出目录内容 |
| 8 | `read_many_files` | — | Read | `read-many-files.ts` | 批量读取多个文件 |
| 9 | `google_web_search` | — | Fetch | `web-search.ts` | Google 网络搜索，使用 Grounding API |
| 10 | `web_fetch` | — | Fetch | `web-fetch.ts` | 获取 URL 内容，HTML→text 转换 |
| 11 | `write_todos` | — | Other | `write-todos.ts` | 管理 todo 列表 (pending/in_progress/completed/cancelled) |
| 12 | `save_memory` | — | Edit | `memoryTool.ts` | 持久化记忆事实到 GEMINI.md |
| 13 | `get_internal_docs` | — | Read | `get-internal-docs.ts` | 读取内置文档 |
| 14 | `activate_skill` | — | Other | `activate-skill.ts` | 激活预定义 skill |
| 15 | `ask_user` | Ask User | Communicate | `ask-user.ts` | 向用户提问（支持选项/多选/文本输入） |
| 16 | `enter_plan_mode` | — | SwitchMode | `enter-plan-mode.ts` | 进入 Plan Mode |
| 17 | `exit_plan_mode` | — | Plan | `exit-plan-mode.ts` | 退出 Plan Mode 并提交计划 |
| 18 | `tracker_create_task` | — | Other | `trackerTools.ts` | 创建任务跟踪条目 |
| 19 | `tracker_update_task` | — | Other | `trackerTools.ts` | 更新任务状态 |
| 20 | `tracker_get_task` | — | Read | `trackerTools.ts` | 查询单个任务 |
| 21 | `tracker_list_tasks` | — | Read | `trackerTools.ts` | 列出所有任务 |
| 22 | `tracker_add_dependency` | — | Other | `trackerTools.ts` | 添加任务依赖关系 |
| 23 | `tracker_visualize` | — | Read | `trackerTools.ts` | 可视化任务依赖图 |

> 📌 **Plan Mode 工具子集**：在 Plan Mode 下，只有 `glob`、`grep_search`、`read_file`、`list_directory`、`google_web_search`、`ask_user`、`activate_skill` 可用（定义在 `PLAN_MODE_TOOLS`）。`write_file` 和 `replace` 仍可用但只能操作 plans 目录下的 `.md` 文件。

> 💡 除内置工具外，还有两种可发现工具：**DiscoveredTool**（通过 `toolDiscoveryCommand` 发现的外部命令行工具）和 **DiscoveredMCPTool**（通过 MCP 协议发现的工具）。

### 3.1 Tool 调用与输出示例

以下示例展示模型发出的 FunctionCall JSON 和工具返回的 `ToolResult` 结构。所有数据基于源码中的实际处理逻辑还原。

#### 3.1.1 `read_file` — 正常读取

**模型发出的 FunctionCall：**

```json
{
  "functionCall": {
    "name": "read_file",
    "id": "fc_a1b2c3d4",
    "args": {
      "file_path": "src/utils/parser.ts",
      "start_line": 1,
      "end_line": 50
    }
  }
}
```

**工具返回的 ToolResult：**

```json
{
  "llmContent": "1: import path from 'node:path';\n2: import fs from 'node:fs';\n3: \n4: export function parseConfig(filePath: string) {\n5:   const raw = fs.readFileSync(filePath, 'utf8');\n...(lines 6-50)...",
  "returnDisplay": "src/utils/parser.ts (lines 1-50)"
}
```

> 📌 当文件被截断时，`llmContent` 会在前面插入 `IMPORTANT: The file content has been truncated.` 警告，并提示使用 `start_line` 参数继续读取。

#### 3.1.2 `read_file` — 文件不存在

```json
{
  "llmContent": "Error: File not found: /workspace/src/nonexistent.ts",
  "returnDisplay": "Error reading file",
  "error": {
    "message": "Error: File not found: /workspace/src/nonexistent.ts",
    "type": "file_not_found"
  }
}
```

#### 3.1.3 `run_shell_command` — 成功执行

**模型发出的 FunctionCall：**

```json
{
  "functionCall": {
    "name": "run_shell_command",
    "id": "fc_e5f6g7h8",
    "args": {
      "command": "git log --oneline -5",
      "description": "Show recent 5 commits"
    }
  }
}
```

**工具返回的 ToolResult：**

```json
{
  "llmContent": "Output: f8df77e Refactor ingest module with BaseParser ABC\n764ad0a Initialize VibeLens project skeleton\nabc1234 Add README\ndef5678 Initial commit\n789abcd Setup CI pipeline\nProcess Group PGID: 42356",
  "returnDisplay": "f8df77e Refactor ingest module with BaseParser ABC\n764ad0a Initialize VibeLens project skeleton\nabc1234 Add README\ndef5678 Initial commit\n789abcd Setup CI pipeline"
}
```

> 💡 `llmContent` 总是包含 `Output:` 前缀以及可选的 `Error:`、`Exit Code:`、`Signal:`、`Background PIDs:`、`Process Group PGID:` 字段。`returnDisplay` 则只包含用户可见的干净输出。

#### 3.1.4 `run_shell_command` — 命令超时

当 shell 命令超过 `shellToolInactivityTimeout` 指定的时间无输出时，自动取消：

```json
{
  "llmContent": "Command was automatically cancelled because it exceeded the timeout of 2.0 minutes without output. Below is the output before it was cancelled:\nCompiling module 1/25...\nCompiling module 2/25...",
  "returnDisplay": "Command was automatically cancelled because it exceeded the timeout of 2.0 minutes without output.\n\nOutput before cancellation:\nCompiling module 1/25...\nCompiling module 2/25..."
}
```

#### 3.1.5 `run_shell_command` — 非零退出码

```json
{
  "llmContent": "Output: src/main.ts(12,5): error TS2304: Cannot find name 'foo'.\nExit Code: 2",
  "returnDisplay": "src/main.ts(12,5): error TS2304: Cannot find name 'foo'.",
  "error": {
    "message": "src/main.ts(12,5): error TS2304: Cannot find name 'foo'.",
    "type": "shell_execute_error"
  }
}
```

#### 3.1.6 `run_shell_command` — 后台执行

```json
{
  "functionCall": {
    "name": "run_shell_command",
    "args": {
      "command": "npm run dev",
      "is_background": true
    }
  }
}
```

**工具返回：**

```json
{
  "llmContent": "Command moved to background (PID: 18234). Output hidden. Press Ctrl+B to view.",
  "returnDisplay": "Command moved to background (PID: 18234). Output hidden. Press Ctrl+B to view.",
  "data": {
    "pid": 18234,
    "command": "npm run dev",
    "initialOutput": "Server started on port 3000\n"
  }
}
```

#### 3.1.7 `replace` (Edit) — 成功编辑

**模型发出的 FunctionCall：**

```json
{
  "functionCall": {
    "name": "replace",
    "id": "fc_i9j0k1l2",
    "args": {
      "file_path": "src/config.ts",
      "instruction": "Update the default port from 3000 to 8080 to avoid conflicts with the dev proxy.",
      "old_string": "const DEFAULT_PORT = 3000;",
      "new_string": "const DEFAULT_PORT = 8080;"
    }
  }
}
```

**工具返回的 ToolResult（成功时 `returnDisplay` 为 `FileDiff` 对象）：**

```json
{
  "llmContent": "Successfully modified file: /workspace/src/config.ts (1 replacements). Here is the updated code:\n@@ -10,7 +10,7 @@\n import path from 'node:path';\n \n-const DEFAULT_PORT = 3000;\n+const DEFAULT_PORT = 8080;\n \n export function getPort() {",
  "returnDisplay": {
    "fileDiff": "--- a/config.ts\n+++ b/config.ts\n@@ -10,7 +10,7 @@\n-const DEFAULT_PORT = 3000;\n+const DEFAULT_PORT = 8080;",
    "fileName": "config.ts",
    "filePath": "/workspace/src/config.ts",
    "originalContent": "...full original content...",
    "newContent": "...full new content...",
    "diffStat": {
      "model_added_lines": 1,
      "model_removed_lines": 1,
      "model_added_chars": 27,
      "model_removed_chars": 27,
      "user_added_lines": 0,
      "user_removed_lines": 0,
      "user_added_chars": 0,
      "user_removed_chars": 0
    },
    "isNewFile": false
  }
}
```

#### 3.1.8 `replace` (Edit) — old_string 未找到

当 exact match、flexible match、regex match 和 fuzzy match 全部失败时：

```json
{
  "llmContent": "Failed to edit, 0 occurrences found for old_string in src/config.ts. Ensure you're not escaping content incorrectly and check whitespace, indentation, and context. Use read_file tool to verify.",
  "returnDisplay": "Error: Failed to edit, could not find the string to replace.",
  "error": {
    "message": "Failed to edit, 0 occurrences found for old_string in src/config.ts...",
    "type": "edit_no_occurrence_found"
  }
}
```

> ⚠️ Edit 工具使用四级匹配策略：`exact` → `flexible`（忽略行首缩进）→ `regex`（token 化正则匹配）→ `fuzzy`（Levenshtein 距离 ≤ 10%）。如果四级全部失败且未禁用 LLM correction，还会调用 `FixLLMEditWithInstruction()` 尝试自修复。

#### 3.1.9 `write_file` — 权限被拒

```json
{
  "llmContent": "Permission denied writing to file: /etc/hosts (EACCES)",
  "returnDisplay": "Permission denied writing to file: /etc/hosts (EACCES)",
  "error": {
    "message": "Permission denied writing to file: /etc/hosts (EACCES)",
    "type": "permission_denied"
  }
}
```

#### 3.1.10 `write_file` — 路径在 workspace 之外

```json
{
  "llmContent": "Path '/tmp/outside/file.txt' is outside the allowed workspace directory.",
  "returnDisplay": "Error: Path not in workspace.",
  "error": {
    "message": "Path '/tmp/outside/file.txt' is outside the allowed workspace directory.",
    "type": "path_not_in_workspace"
  }
}
```

### 3.2 ToolErrorType 完整枚举

源文件：`packages/core/src/tools/tool-error.ts`

所有工具错误按可恢复性分为两类。**Fatal error** 会导致 CLI 退出，**Recoverable error** 允许 LLM 自我修正后重试。

| 错误类型 | 值 | 触发场景 | Fatal? |
|---------|-----|---------|--------|
| `INVALID_TOOL_PARAMS` | `invalid_tool_params` | Schema 校验失败 | No |
| `EXECUTION_FAILED` | `execution_failed` | `execute()` 抛出异常 | No |
| `FILE_NOT_FOUND` | `file_not_found` | 读/编辑不存在的文件 | No |
| `FILE_WRITE_FAILURE` | `file_write_failure` | 写文件失败（通用） | No |
| `PERMISSION_DENIED` | `permission_denied` | EACCES 错误 | No |
| `NO_SPACE_LEFT` | `no_space_left` | ENOSPC 磁盘满 | **Yes** |
| `TARGET_IS_DIRECTORY` | `target_is_directory` | 写入目标是目录 | No |
| `PATH_NOT_IN_WORKSPACE` | `path_not_in_workspace` | 路径超出 workspace 范围 | No |
| `EDIT_NO_OCCURRENCE_FOUND` | `edit_no_occurrence_found` | old_string 在文件中找不到 | No |
| `EDIT_EXPECTED_OCCURRENCE_MISMATCH` | `edit_expected_occurrence_mismatch` | 找到多个 old_string 但 `allow_multiple` 未设置 | No |
| `EDIT_NO_CHANGE` | `edit_no_change` | old_string 和 new_string 完全相同 | No |
| `SHELL_EXECUTE_ERROR` | `shell_execute_error` | Shell 命令执行出错 | No |
| `MCP_TOOL_ERROR` | `mcp_tool_error` | MCP 工具返回 `isError: true` | No |
| `TOOL_NOT_REGISTERED` | `tool_not_registered` | 找不到对应工具名 | No |
| `POLICY_VIOLATION` | `policy_violation` | Policy Engine 拒绝执行 | No |

> 📌 目前只有 `NO_SPACE_LEFT` 被视为 fatal error（`isFatalToolError()` 函数检查）。其余所有错误都允许 LLM 在下一个 turn 中修正参数后重试。

---

## 4 ToolRegistry：注册、别名与排序

源文件：`packages/core/src/tools/tool-registry.ts`

### 4.1 注册与查找

`ToolRegistry` 使用 `Map<string, AnyDeclarativeTool>` 存储所有已知工具。核心方法：

| 方法 | 功能 |
|------|------|
| `registerTool(tool)` | 注册工具，同名则覆盖并打印 warn |
| `unregisterTool(name)` | 按名称注销 |
| `getTool(name)` | 查找工具，支持 legacy alias 回退 |
| `getAllTools()` | 返回所有活跃工具，按 displayName 排序，去重 |
| `getAllToolNames()` | 返回所有活跃工具名称集合 |
| `getFunctionDeclarations(modelId?)` | 生成 Gemini API 的 FunctionDeclaration 数组 |
| `sortTools()` | 按优先级排序：Built-in → DiscoveredTool → DiscoveredMCPTool（按 serverName） |

### 4.2 Legacy Alias 机制

```typescript
const TOOL_LEGACY_ALIASES: Record<string, string> = {
  search_file_content: 'grep_search',  // 旧名 → 新名
};
```

`getTool()` 首先查 `allKnownTools`，未命中时通过 `TOOL_LEGACY_ALIASES` 映射到当前名称。`getToolAliases()` 会返回一个名称关联的所有别名，用于 policy exclusion 展开。

### 4.3 Exclude 与 Active 过滤

工具排除由 `Config.getExcludeTools()` 提供排除名称集合。`isActiveTool()` 检查工具名称、类名、MCP fully-qualified name 是否在排除列表中。

```typescript
// 可能的排除匹配名称：
const possibleNames = [tool.name, normalizedClassName];
// MCP 工具额外检查 unqualified/qualified name
```

### 4.4 Model-Specific Schema

工具支持按模型族返回不同的 FunctionDeclaration。`ToolDefinition` 接口定义了 `base` + `overrides(modelId)` 模式：

```typescript
interface ToolDefinition {
  base: FunctionDeclaration;
  overrides?: (modelId: string) => Partial<FunctionDeclaration> | undefined;
}
```

目前支持两个模型族：`default-legacy` 和 `gemini-3`，通过 `getToolFamily(modelId)` 分发。

---

## 5 Tool ID 生成与 `wait_for_previous` 参数

### 5.1 Tool Call ID

Tool call 的 ID 由 Gemini API 返回的 `FunctionCall.id` 决定，格式通常为 API 层面的 UUID。在 scheduler 内部通过 `ToolCallRequestInfo.callId` 引用。

### 5.2 `wait_for_previous` 自动注入

`DeclarativeTool` 的 `addWaitForPreviousParameter()` 方法会在**每个工具**的 JSON Schema 中自动追加一个布尔参数：

```json
{
  "wait_for_previous": {
    "type": "boolean",
    "description": "Set to true to wait for all previously requested tools in this turn to complete before starting. Set to false (or omit) to run in parallel."
  }
}
```

这允许模型在同一 turn 中声明工具之间的依赖关系。Scheduler 在编排时读取此参数来决定并行还是串行执行。

### 5.3 并行与串行执行示例

模型可以在同一个 turn 中发出多个 FunctionCall。Scheduler 根据 `wait_for_previous` 参数决定执行策略：

**并行执行（默认）**：两个 `read_file` 同时发出，无依赖关系

```json
[
  {
    "functionCall": {
      "name": "read_file",
      "id": "fc_001",
      "args": { "file_path": "src/a.ts" }
    }
  },
  {
    "functionCall": {
      "name": "read_file",
      "id": "fc_002",
      "args": { "file_path": "src/b.ts" }
    }
  }
]
```

```
Timeline:
  fc_001 ──────────► (读取 a.ts)
  fc_002 ──────────► (读取 b.ts)    ← 并行执行
```

**串行执行**：第二个 `replace` 依赖第一个 `read_file` 的结果

```json
[
  {
    "functionCall": {
      "name": "read_file",
      "id": "fc_001",
      "args": { "file_path": "src/config.ts" }
    }
  },
  {
    "functionCall": {
      "name": "replace",
      "id": "fc_002",
      "args": {
        "file_path": "src/config.ts",
        "old_string": "const PORT = 3000;",
        "new_string": "const PORT = 8080;",
        "instruction": "Change default port",
        "wait_for_previous": true
      }
    }
  }
]
```

```
Timeline:
  fc_001 ──────────► (读取 config.ts)
                     │
                     ▼ wait_for_previous = true
  fc_002             ──────────► (编辑 config.ts)
```

---

## 6 MCP 集成

### 6.1 架构总览

```
McpClientManager (管理多个 MCP server 生命周期)
  └── McpClient (单个 MCP server 的连接/发现/状态)
        ├── Client (@modelcontextprotocol/sdk)
        ├── Transport (Stdio / SSE / StreamableHTTP)
        └── DiscoveredMCPTool (注册到 ToolRegistry 的工具包装)
              └── DiscoveredMCPToolInvocation (执行时创建)
```

### 6.2 Transport 类型

源文件：`packages/core/src/tools/mcp-client.ts` 中的 `createTransport()` 和 `createUrlTransport()` 函数。

| Transport | 类名 | 触发条件 |
|-----------|------|----------|
| **Stdio** | `StdioClientTransport` | 配置了 `command` 字段 |
| **Streamable HTTP** | `StreamableHTTPClientTransport` | 配置了 `httpUrl`，或 `url` + `type: "http"`，或仅 `url`（默认） |
| **SSE** | `SSEClientTransport` | 配置了 `url` + `type: "sse"`，或 HTTP 失败后自动 fallback |
| **Xcode Bridge** | `XcodeMcpBridgeFixTransport` | Xcode mcpbridge 的兼容 wrapper（修复 `structuredContent` 缺失） |

> ⚠️ Gemini CLI 不支持 WebSocket transport。对于 `url` 配置且未指定 `type` 的场景，**优先尝试 Streamable HTTP**，404 时自动 fallback 到 SSE。

Transport 选择优先级：
1. `httpUrl`（deprecated）→ StreamableHTTP
2. `url` + `type: "http"` → StreamableHTTP
3. `url` + `type: "sse"` → SSE
4. `url` 无 `type` → StreamableHTTP（失败后尝试 SSE）
5. `command` → Stdio

### 6.3 MCP 工具命名

MCP 工具使用 fully-qualified name 格式：`mcp_{serverName}_{toolName}`。

```typescript
const MCP_TOOL_PREFIX = 'mcp_';
const MCP_QUALIFIED_NAME_SEPARATOR = '_';

// 示例：mcp_github_create_issue
```

`generateValidName()` 确保名称符合 Gemini API 限制（`^[a-zA-Z_][a-zA-Z0-9_\-.:]{0,63}$`）。超过 63 字符时截断为 `前30字符...后30字符`。

### 6.4 MCP Server 状态管理

```typescript
enum MCPServerStatus {
  DISCONNECTED, DISCONNECTING, CONNECTING, CONNECTED, BLOCKED, DISABLED
}

enum MCPDiscoveryState {
  NOT_STARTED, IN_PROGRESS, COMPLETED
}
```

`McpClientManager` 负责：
- 启动所有配置的 MCP servers（`startConfiguredMcpServers()`）
- Extension 的动态加载/卸载（`startExtension()` / `stopExtension()`）
- Server allow/block list 过滤（`isBlockedBySettings()`）
- MCP context 刷新防抖（Coalescing Pattern，300ms 延迟）

### 6.5 OAuth 支持

MCP 连接支持多种认证方式：
- **Google Credentials** (`GoogleCredentialProvider`)
- **Service Account Impersonation** (`ServiceAccountImpersonationProvider`)
- **OAuth 2.0** (`MCPOAuthProvider` + `MCPOAuthTokenStorage`)
- **Bearer Token**（从已存储的 OAuth token 或显式配置中获取）

当 HTTP/SSE 连接返回 401 时，自动触发 OAuth 流程或提示用户运行 `/mcp auth` 命令。

### 6.6 MCP 工具发现与调用示例

#### 发现流程

MCP server 连接成功后，`McpClient.discover()` 调用 `tools/list` 端点获取工具列表。每个 MCP tool 被包装为 `DiscoveredMCPTool` 实例注册到 `ToolRegistry`。

假设配置了名为 `github` 的 MCP server，发现了 `create_issue` 工具，注册后的 fully-qualified name 为 `mcp_github_create_issue`。对应的 FunctionDeclaration 发送给 Gemini API：

```json
{
  "name": "mcp_github_create_issue",
  "description": "Create a new issue in a GitHub repository.",
  "parametersJsonSchema": {
    "type": "object",
    "properties": {
      "repo": { "type": "string", "description": "owner/repo format" },
      "title": { "type": "string", "description": "Issue title" },
      "body": { "type": "string", "description": "Issue body in markdown" },
      "wait_for_previous": { "type": "boolean", "description": "..." }
    },
    "required": ["repo", "title"]
  }
}
```

#### 模型调用 MCP 工具

```json
{
  "functionCall": {
    "name": "mcp_github_create_issue",
    "id": "fc_mcp_001",
    "args": {
      "repo": "user/my-project",
      "title": "Fix login timeout bug",
      "body": "The login page times out after 30 seconds..."
    }
  }
}
```

#### MCP 工具执行内部流程

`DiscoveredMCPToolInvocation.execute()` 构造 `FunctionCall[]` 数组并调用 `mcpTool.callTool()`：

```typescript
// 构造发送给 MCP server 的请求
const functionCalls: FunctionCall[] = [
  {
    name: "create_issue",   // 使用原始 tool name，非 qualified name
    args: { repo: "user/my-project", title: "Fix login timeout bug", ... }
  }
];
const rawResponseParts = await this.mcpTool.callTool(functionCalls);
```

#### MCP 工具成功返回

MCP server 返回的 raw response 经 `transformMcpContentToParts()` 转换为标准 GenAI `Part[]`：

```json
{
  "llmContent": [
    { "text": "Issue #42 created successfully at https://github.com/user/my-project/issues/42" }
  ],
  "returnDisplay": "Issue #42 created successfully at https://github.com/user/my-project/issues/42"
}
```

#### MCP 工具报错

当 MCP server 返回 `isError: true` 时：

```json
{
  "llmContent": "MCP tool 'create_issue' reported tool error for function call: {\"name\":\"create_issue\",\"args\":{...}} with response: [{...}]",
  "returnDisplay": "Error: MCP tool 'create_issue' reported an error.",
  "error": {
    "message": "MCP tool 'create_issue' reported tool error...",
    "type": "mcp_tool_error"
  }
}
```

> ⚠️ MCP 工具的确认 UI 使用 `ToolMcpConfirmationDetails` 类型，显示 `serverName`、`toolName`、`toolArgs` 和 `toolDescription`。用户可以选择 `ProceedAlwaysServer`（允许该 server 所有工具）或 `ProceedAlwaysTool`（仅允许该工具）。

---

## 7 Tool Confirmation 流与 Approval Bus

### 7.1 Confirmation 决策链

```
BaseToolInvocation.shouldConfirmExecute(abortSignal)
  → getMessageBusDecision(abortSignal)     // 通过 MessageBus 查询 Policy
    → Policy Engine 返回 ALLOW / DENY / ASK_USER
      → ALLOW: return false (跳过确认)
      → DENY:  throw Error (拒绝执行)
      → ASK_USER: return getConfirmationDetails() (需要用户确认)
```

### 7.2 MessageBus 机制

`MessageBus` 是工具与 Policy Engine 之间的通信桥梁，使用 pub/sub 模式：

```typescript
// 工具发送确认请求
messageBus.publish({
  type: MessageBusType.TOOL_CONFIRMATION_REQUEST,
  correlationId,
  toolCall: { name, args },
  serverName,
  toolAnnotations,
});

// 等待响应 (30 秒超时，默认 ASK_USER)
messageBus.subscribe(
  MessageBusType.TOOL_CONFIRMATION_RESPONSE,
  responseHandler,
);
```

### 7.3 ToolConfirmationOutcome

```typescript
enum ToolConfirmationOutcome {
  ProceedOnce,          // 仅本次允许
  ProceedAlways,        // 本 session 内始终允许
  ProceedAlwaysAndSave, // 持久化到策略文件
  ProceedAlwaysServer,  // 允许整个 MCP server
  ProceedAlwaysTool,    // 允许某个 MCP tool
  ModifyWithEditor,     // 用编辑器修改后继续
  Cancel,               // 取消
}
```

### 7.4 Confirmation 详情类型

不同工具产生不同的确认 UI 类型：

| 类型 | 使用场景 | 关键字段 |
|------|----------|----------|
| `edit` | write_file / replace | `fileDiff`, `originalContent`, `newContent`, `ideConfirmation` |
| `exec` | run_shell_command | `command`, `rootCommand`, `rootCommands` |
| `mcp` | MCP 工具 | `serverName`, `toolName`, `toolArgs`, `toolDescription` |
| `info` | 通用确认 | `prompt`, `urls` |
| `ask_user` | ask_user 工具 | `questions` |
| `exit_plan_mode` | 退出 Plan Mode | `planPath` |

---

## 8 Tool 执行管线

### 8.1 Scheduler

源文件：`packages/core/src/scheduler/scheduler.ts`

`Scheduler` 是工具执行的事件驱动编排器，其核心职责：

1. **批量调度**：`schedule()` 接收一批 `ToolCallRequestInfo[]`，支持入队排队
2. **工具解析**：从 `ToolRegistry` 查找工具实例并调用 `tool.build(params)` 创建 Invocation
3. **Policy 检查**：调用 `checkPolicy()` 确定是否需要用户确认
4. **Confirmation 编排**：通过 `resolveConfirmation()` 处理用户审批
5. **并行/串行执行**：根据 `wait_for_previous` 参数和工具 Kind 决定执行模式
6. **Tail Call**：支持 `tailToolCallRequest`，一个工具可以请求立即执行另一个工具
7. **Policy 更新**：用户选择 ProceedAlways/ProceedAlwaysAndSave 后自动更新 policy

### 8.2 ToolExecutor

源文件：`packages/core/src/scheduler/tool-executor.ts`

`ToolExecutor` 负责实际执行：

```typescript
class ToolExecutor {
  async execute(context: ToolExecutionContext): Promise<CompletedToolCall> {
    // 1. 调用 executeToolWithHooks() — 触发 pre/post hooks
    // 2. 处理 live output streaming
    // 3. 处理 abort signal
    // 4. 构造 CompletedToolCall (Success / Error / Cancelled)
    // 5. 超长输出截断 + 保存到临时文件
  }
}
```

Hook 触发通过 `executeToolWithHooks()` 实现，支持在工具执行前后运行自定义逻辑。

### 8.3 Tool Call 状态机

源文件：`packages/core/src/scheduler/types.ts`

```
Validating → Scheduled → Executing → Success
                                   → Error
                                   → Cancelled
                       → AwaitingApproval → (用户响应) → Executing / Cancelled
```

```typescript
enum CoreToolCallStatus {
  Validating,      // 正在验证参数
  Scheduled,       // 已排队等待执行
  Executing,       // 正在执行
  AwaitingApproval, // 等待用户确认
  Success,         // 执行成功
  Error,           // 执行失败
  Cancelled,       // 被取消
}
```

### 8.4 输出截断

Shell 工具和 MCP 工具的输出超过 `truncateToolOutputThreshold` 时会被截断，完整输出保存到项目临时目录中的文件，并在返回给 LLM 的内容中附上文件路径引用。

### 8.5 参数验证失败的处理路径

当模型发出的参数不合法时，`DeclarativeTool.validateBuildAndExecute()` 提供安全的错误处理路径（不抛异常），直接返回 `ToolResult`：

```
Model sends: replace({ file_path: "", old_string: "...", new_string: "..." })
                │
                ▼
  BaseDeclarativeTool.build(params)
    → SchemaValidator.validate(schema, params)
      → "The 'file_path' parameter must be non-empty."
                │
                ▼
  validateBuildAndExecute() catches Error
    → returns ToolResult {
        llmContent: "Error: Invalid parameters provided. Reason: The 'file_path' parameter must be non-empty.",
        returnDisplay: "The 'file_path' parameter must be non-empty.",
        error: { message: "...", type: "invalid_tool_params" }
      }
```

各工具的自定义验证逻辑（通过 `validateToolParamValues()` 重写）包括：

| 工具 | 验证规则 |
|------|---------|
| `read_file` | `file_path` 非空；`start_line` >= 1；`start_line` <= `end_line`；路径不在 ignore patterns 中 |
| `replace` | `file_path` 非空；路径在 workspace 内；`new_string` 不含 omission placeholders |
| `write_file` | `file_path` 非空；路径不是目录；`content` 不含 omission placeholders |
| `run_shell_command` | `command` 非空；`dir_path` 在 workspace 内 |

> 📌 Omission placeholder 检测（`detectOmissionPlaceholders()`）会拦截模型输出的 `"// rest of methods ..."` 或 `"..."` 等省略占位符，强制模型提供完整内容。

### 8.6 Tail Call 机制

某些工具在执行完毕后可以通过 `tailToolCallRequest` 请求立即执行另一个工具，无需等待模型的下一个 turn。这通过 `ToolResult.tailToolCallRequest` 字段实现：

```typescript
// 工具执行结果中包含 tail call 请求
{
  llmContent: "...",
  returnDisplay: "...",
  tailToolCallRequest: {
    name: "read_file",
    args: { file_path: "src/generated.ts" }
  }
}
```

Scheduler 检测到 `tailToolCallRequest` 后，使用 `originalRequestName` 保留原始工具名称，新建一个 `ToolCallRequestInfo` 并立即排入执行队列。最终返回给模型的 FunctionResponse 使用原始请求的名称，确保对话上下文的连贯性。

---

## 9 resultDisplay 富化：FileDiff 与 DiffStat

### 9.1 ToolResultDisplay 联合类型

```typescript
type ToolResultDisplay =
  | string          // 纯文本
  | FileDiff        // 文件差异视图
  | AnsiOutput      // 终端 ANSI 输出
  | TodoList        // Todo 列表
  | SubagentProgress; // 子代理进度
```

### 9.2 FileDiff 结构

```typescript
interface FileDiff {
  fileDiff: string;            // unified diff 文本
  fileName: string;            // 文件名
  filePath: string;            // 绝对路径
  originalContent: string | null; // 原始内容
  newContent: string;          // 新内容
  diffStat?: DiffStat;        // 统计信息
  isNewFile?: boolean;         // 是否新文件
}
```

### 9.3 DiffStat

`getDiffStat()` 函数（源文件：`packages/core/src/tools/diffOptions.ts`）计算 **model 贡献**和 **user 修改**的双维度统计：

```typescript
interface DiffStat {
  model_added_lines: number;
  model_removed_lines: number;
  model_added_chars: number;
  model_removed_chars: number;
  user_added_lines: number;    // 用户通过 ModifyWithEditor 修改的行
  user_removed_lines: number;
  user_added_chars: number;
  user_removed_chars: number;
}
```

计算过程：先用 `structuredPatch(original, aiProposed)` 得到 model 统计，再用 `structuredPatch(aiProposed, userFinal)` 得到 user 统计。

### 9.4 resultDisplay 实际输出示例

以下展示 `write_file` 工具成功执行后返回的完整 `FileDiff` 结构。此结构被 CLI UI 渲染为 diff 视图，同时用于 IDE 集成（`IdeClient.openDiff()`）。

**场景：模型创建新文件**

```json
{
  "fileDiff": "--- a/hello.ts\n+++ b/hello.ts\n@@ -0,0 +1,5 @@\n+export function greet(name: string): string {\n+  return `Hello, ${name}!`;\n+}\n+\n+console.log(greet('World'));\n",
  "fileName": "hello.ts",
  "filePath": "/workspace/src/hello.ts",
  "originalContent": "",
  "newContent": "export function greet(name: string): string {\n  return `Hello, ${name}!`;\n}\n\nconsole.log(greet('World'));\n",
  "diffStat": {
    "model_added_lines": 5,
    "model_removed_lines": 0,
    "model_added_chars": 98,
    "model_removed_chars": 0,
    "user_added_lines": 0,
    "user_removed_lines": 0,
    "user_added_chars": 0,
    "user_removed_chars": 0
  },
  "isNewFile": true
}
```

**场景：用户通过 ModifyWithEditor 修改了模型提议**

当用户在确认阶段选择 `ModifyWithEditor` 并修改了 `new_string` 内容时，`DiffStat` 会同时记录 model 和 user 的贡献：

```json
{
  "diffStat": {
    "model_added_lines": 8,
    "model_removed_lines": 3,
    "model_added_chars": 245,
    "model_removed_chars": 92,
    "user_added_lines": 2,
    "user_removed_lines": 1,
    "user_added_chars": 48,
    "user_removed_chars": 15
  }
}
```

> 💡 `user_*` 字段非零表示用户在 diff 审查阶段手动修改了 AI 提议的内容。这些统计信息用于 telemetry 和用户体验反馈。

### 9.5 Scheduler 返回给 Gemini API 的 FunctionResponse 格式

`ToolExecutor` 完成执行后，通过 `convertToFunctionResponse()` 将 `ToolResult` 转换为 Gemini API 所需的 `Part[]` 格式。这些 parts 作为 `user` role 的 content 发送回模型：

**成功场景（`read_file`）：**

```json
[
  {
    "functionResponse": {
      "id": "fc_a1b2c3d4",
      "name": "read_file",
      "response": {
        "output": "1: import path from 'node:path';\n2: ..."
      }
    }
  }
]
```

**错误场景（工具执行失败）：**

```json
[
  {
    "functionResponse": {
      "id": "fc_a1b2c3d4",
      "name": "replace",
      "response": {
        "error": "Failed to edit, 0 occurrences found for old_string in src/config.ts..."
      }
    }
  }
]
```

**取消场景（用户中断）：**

```json
[
  {
    "functionResponse": {
      "id": "fc_a1b2c3d4",
      "name": "run_shell_command",
      "response": {
        "output": "Partial output before cancellation...",
        "error": "[Operation Cancelled] User cancelled tool execution."
      }
    }
  }
]
```

---

## 10 与 Claude Code 工具系统的比较

### 10.1 架构对比

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **类型层次** | `DeclarativeTool.build()` → `ToolInvocation.execute()` 双阶段 | Tool 直接定义 `execute()` 方法 |
| **Schema 定义** | `FunctionDeclaration` (Google GenAI SDK) | Tool 内联定义 `inputSchema` (JSON Schema) |
| **Model-Specific Schema** | 支持，通过 `ToolDefinition.overrides(modelId)` | 不支持，Schema 对所有模型一致 |
| **并行执行** | 模型驱动的 `wait_for_previous` 参数控制 | 工具层面的 `isReadOnly` 判断 |
| **Registry** | `ToolRegistry` + legacy alias | 内置工具数组 + permission-based 筛选 |

### 10.2 内置工具对比

| 功能类别 | Gemini CLI | Claude Code |
|---------|-----------|-------------|
| 文件读取 | `read_file`, `read_many_files` | `Read` |
| 文件写入 | `write_file` | `Write` |
| 精确编辑 | `replace` (old_string/new_string) | `Edit` (old_string/new_string) |
| 命令执行 | `run_shell_command` (前台+后台) | `Bash` |
| 搜索 | `glob` + `grep_search` (ripgrep) | `Glob` + `Grep` (ripgrep) |
| 目录浏览 | `list_directory` | 通过 `Bash ls` 实现 |
| 网络搜索 | `google_web_search` | `WebSearch` |
| 网页获取 | `web_fetch` | `WebFetch` |
| 编辑器确认 | `ModifyWithEditor` outcome | 无 |
| 记忆持久化 | `save_memory` (→ GEMINI.md) | 无内置工具（通过 CLAUDE.md 手动管理） |
| 任务跟踪 | `tracker_*` (6 个工具) | `TodoWrite` |
| 用户交互 | `ask_user` (多类型问题) | 用户输入通过 conversation turn |
| Plan Mode | `enter_plan_mode` / `exit_plan_mode` | 无显式 Plan Mode |
| Skill 系统 | `activate_skill` | `Skill` |
| MCP 集成 | `DiscoveredMCPTool` (Stdio/SSE/HTTP) | MCP 支持 (Stdio/SSE) |

### 10.3 确认流程对比

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **策略引擎** | TOML-based Policy Engine + MessageBus | Permission-based (allowedTools) |
| **确认粒度** | ProceedOnce / ProceedAlways / ProceedAlwaysAndSave / Server / Tool | Allow once / Allow always |
| **MCP 确认** | 独立的 `ToolMcpConfirmationDetails` | 统一确认流程 |
| **编辑器修改** | `ModifyWithEditor` outcome → 重新计算 diff | 无 |
| **IDE 集成** | `IdeClient.openDiff()` 支持 IDE 内 diff 审查 | 无 |

### 10.4 MCP 集成对比

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **Transport** | Stdio, Streamable HTTP, SSE | Stdio, SSE |
| **命名** | `mcp_{server}_{tool}` (64 字符限制) | `mcp__` 前缀 |
| **OAuth** | 内置 OAuth 2.0 provider + token storage | 无内置 OAuth |
| **Trust 模型** | per-server trust + folder trust | 全局配置 |
| **Tool 注解** | `toolAnnotations` (readOnlyHint 等) 传递给 Policy | 有限的注解支持 |
| **进度通知** | `ProgressNotification` → McpProgress 事件 | 无 |

---

## 11 工具发现机制

### 11.1 命令行工具发现

通过 `toolDiscoveryCommand` 配置项执行外部命令，解析其 JSON 输出获取 FunctionDeclaration 数组。发现的工具以 `discovered_tool_` 前缀注册：

```typescript
const DISCOVERED_TOOL_PREFIX = 'discovered_tool_';
```

执行时通过 `toolCallCommand` 调用：`toolCallCommand ${originalToolName}`，参数通过 stdin 传入 JSON。

### 11.2 MCP 工具发现

`McpClient.discover()` 连接 MCP server 后调用 `tools/list` 端点获取工具列表，每个工具包装为 `DiscoveredMCPTool` 实例注册到 `ToolRegistry`。

发现完成后还会验证 policy rules 中引用的 MCP tool 名称是否与实际发现的工具匹配。

---

## 12 关键设计模式

### 12.1 Builder Pattern（DeclarativeTool → ToolInvocation）

分离"工具定义"与"工具执行"。`DeclarativeTool` 是工厂（Builder），`ToolInvocation` 是产品。好处：
- 参数验证失败不会创建 Invocation
- Schema 定义集中在 Builder，执行逻辑封装在 Invocation
- 同一 Builder 可多次 build 产出独立的 Invocation

### 12.2 Modifiable Tool Pattern

`WriteFileTool` 和 `EditTool` 实现了 `ModifiableDeclarativeTool` 接口，支持 `ModifyWithEditor` 流程：

```typescript
interface ModifyContext<ToolParams> {
  getFilePath(params): string;
  getCurrentContent(params): Promise<string>;
  getProposedContent(params): Promise<string>;
  createUpdatedParams(oldContent, modifiedContent, originalParams): ToolParams;
}
```

用户可以在确认阶段通过外部编辑器修改提议内容，系统自动重新计算 diff 并更新参数。

### 12.3 Coalescing Pattern（MCP Context Refresh）

`McpClientManager.scheduleMcpContextRefresh()` 使用防抖 + 合并模式：

```
Request 1 → 开始刷新
  Request 2 (during refresh) → 标记 pending
  Request 3 (during refresh) → 合并到 pending
  → 刷新完成 → 检测 pending → 300ms 等待 → 再次刷新
```

---

## 13 References

| 文件路径 | 说明 |
|---------|------|
| `packages/core/src/tools/tools.ts` | ToolInvocation, DeclarativeTool, BaseDeclarativeTool 等核心类型 |
| `packages/core/src/tools/tool-registry.ts` | ToolRegistry, DiscoveredTool |
| `packages/core/src/tools/tool-names.ts` | 工具名称常量、legacy alias、ALL_BUILTIN_TOOL_NAMES |
| `packages/core/src/tools/definitions/coreTools.ts` | ToolDefinition 注册与 model-family 分发 |
| `packages/core/src/tools/definitions/base-declarations.ts` | 参数名常量注册表 |
| `packages/core/src/tools/definitions/types.ts` | ToolDefinition, CoreToolSet, ToolFamily 类型 |
| `packages/core/src/tools/mcp-tool.ts` | DiscoveredMCPTool, DiscoveredMCPToolInvocation |
| `packages/core/src/tools/mcp-client.ts` | McpClient, createTransport, connectToMcpServer |
| `packages/core/src/tools/mcp-client-manager.ts` | McpClientManager |
| `packages/core/src/tools/read-file.ts` | ReadFileTool |
| `packages/core/src/tools/write-file.ts` | WriteFileTool |
| `packages/core/src/tools/edit.ts` | EditTool (replace) |
| `packages/core/src/tools/shell.ts` | ShellTool (run_shell_command) |
| `packages/core/src/tools/glob.ts` | GlobTool |
| `packages/core/src/tools/grep.ts` / `ripGrep.ts` | GrepTool |
| `packages/core/src/tools/ls.ts` | LsTool (list_directory) |
| `packages/core/src/tools/web-search.ts` | WebSearchTool |
| `packages/core/src/tools/web-fetch.ts` | WebFetchTool |
| `packages/core/src/tools/write-todos.ts` | WriteTodosTool |
| `packages/core/src/tools/memoryTool.ts` | MemoryTool (save_memory) |
| `packages/core/src/tools/get-internal-docs.ts` | GetInternalDocsTool |
| `packages/core/src/tools/activate-skill.ts` | ActivateSkillTool |
| `packages/core/src/tools/ask-user.ts` | AskUserTool |
| `packages/core/src/tools/enter-plan-mode.ts` | EnterPlanModeTool |
| `packages/core/src/tools/exit-plan-mode.ts` | ExitPlanModeTool |
| `packages/core/src/tools/trackerTools.ts` | 6 个 Tracker 工具 |
| `packages/core/src/tools/tool-error.ts` | ToolErrorType 枚举 |
| `packages/core/src/tools/diffOptions.ts` | getDiffStat, DEFAULT_DIFF_OPTIONS |
| `packages/core/src/tools/modifiable-tool.ts` | ModifiableDeclarativeTool 接口 |
| `packages/core/src/scheduler/scheduler.ts` | Scheduler 核心编排器 |
| `packages/core/src/scheduler/tool-executor.ts` | ToolExecutor |
| `packages/core/src/scheduler/types.ts` | CoreToolCallStatus, ToolCall 联合类型 |
| `packages/core/src/scheduler/confirmation.ts` | Confirmation 流程处理 |
| `packages/core/src/confirmation-bus/types.ts` | MessageBusType, 确认请求/响应类型 |

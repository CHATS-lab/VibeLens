# Codex CLI 工具系统深度解析

| 条目 | 内容 |
|------|------|
| **主题** | OpenAI Codex CLI 的工具注册、派发与执行机制 |
| **核心源码** | `codex-rs/core/src/tools/` 目录 |
| **工具数量** | 30+ 内置工具，支持 MCP 动态工具扩展 |
| **API 格式** | OpenAI Responses API function calling |

---

## 1 背景与设计理念

在 AI 编程代理中，"工具"是模型与外部世界交互的桥梁。模型通过发出工具调用（Tool Call），由运行时执行具体操作（读文件、执行命令、搜索代码等），再将结果反馈给模型。工具系统的设计直接决定了代理的能力边界和安全性。

Codex CLI 的工具系统经历了从"单一 `exec_command` 通吃"到"30+ 细分工具"的演进。早期版本将几乎所有操作都统一为 shell 命令执行，这虽然简单但缺乏精细控制。当前版本引入了独立的 `read_file`、`grep_files`、`apply_patch` 等专用工具，在保持灵活性的同时实现了更好的权限控制和用户体验。

本文将从 `ToolHandler` trait、`ToolRegistry` 注册机制入手，逐一解析所有内置工具的参数和行为，最后与 Claude Code 的工具体系进行对比。

---

## 2 核心架构

### 2.1 ToolHandler Trait

每个工具必须实现 `ToolHandler` trait（定义于 `core/src/tools/registry.rs`）：

```rust
#[async_trait]
pub trait ToolHandler: Send + Sync {
    type Output: ToolOutput + 'static;

    /// Returns the kind of tool (Function or Mcp).
    fn kind(&self) -> ToolKind;

    /// Validates that the payload kind matches this handler.
    fn matches_kind(&self, payload: &ToolPayload) -> bool {
        matches!(
            (self.kind(), payload),
            (ToolKind::Function, ToolPayload::Function { .. })
                | (ToolKind::Function, ToolPayload::ToolSearch { .. })
                | (ToolKind::Mcp, ToolPayload::Mcp { .. })
        )
    }

    /// Returns true if the invocation might mutate user's environment.
    /// Must be defensive — returns true when in doubt.
    async fn is_mutating(&self, _invocation: &ToolInvocation) -> bool {
        false
    }

    /// Perform the actual invocation and return output.
    async fn handle(&self, invocation: ToolInvocation)
        -> Result<Self::Output, FunctionCallError>;
}
```

`ToolKind` 区分两类工具来源：

```rust
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ToolKind {
    Function,  // 内置函数工具
    Mcp,       // MCP 协议动态工具
}
```

`ToolPayload` 定义了五种 payload 变体，对应不同的工具调用来源：

```rust
#[derive(Clone, Debug)]
pub enum ToolPayload {
    Function { arguments: String },           // 标准函数调用（JSON 字符串参数）
    ToolSearch { arguments: SearchToolCallParams }, // 工具搜索专用
    Custom { input: String },                 // 自定义工具（如 freeform apply_patch）
    LocalShell { params: ShellToolCallParams },    // 本地 shell 调用
    Mcp { server: String, tool: String, raw_arguments: String }, // MCP 协议调用
}
```

| 变体 | 用途 | 典型场景 |
|------|------|----------|
| `Function` | 标准 OpenAI function calling | `exec_command`、`read_file`、`grep_files` 等 |
| `ToolSearch` | 工具发现搜索 | `_tool_search` 客户端执行 |
| `Custom` | 自由格式输入 | `apply_patch` 的 Lark 语法 |
| `LocalShell` | 结构化 shell 命令 | `local_shell` 的 exec action |
| `Mcp` | MCP 协议远程调用 | 第三方 MCP server 提供的工具 |

> 📌 **重点**：`is_mutating()` 方法是安全机制的核心。对于可能修改用户环境的工具调用（文件写入、命令执行等），运行时会在执行前通过 `tool_call_gate` 进行权限检查和审批流程。`matches_kind()` 方法确保 handler 只处理兼容的 payload 类型，不匹配时 `dispatch_any()` 会返回 `Fatal` 错误。

### 2.2 ToolInvocation 上下文

每次工具调用都封装为一个 `ToolInvocation` 结构体，携带完整的运行时上下文：

```rust
#[derive(Clone)]
pub struct ToolInvocation {
    pub session: Arc<Session>,            // 会话状态（配置、权限、服务）
    pub turn: Arc<TurnContext>,           // 当前 turn 上下文（cwd、沙箱策略等）
    pub tracker: SharedTurnDiffTracker,   // diff 追踪器（记录文件变更）
    pub call_id: String,                  // 本次调用的唯一 ID
    pub tool_name: String,               // 工具名称
    pub tool_namespace: Option<String>,   // 命名空间（MCP 工具使用）
    pub payload: ToolPayload,            // 调用参数
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `session` | `Arc<Session>` | 持有 `SessionServices`（进程管理器、MCP 连接管理器、Agent 控制器等） |
| `turn` | `Arc<TurnContext>` | 包含当前工作目录 `cwd`、沙箱策略 `sandbox_policy`、审批策略 `approval_policy` 等 |
| `tracker` | `SharedTurnDiffTracker` | `Arc<Mutex<TurnDiffTracker>>` 类型，记录本轮产生的文件变更 |
| `call_id` | `String` | 由模型生成的调用 ID，用于将输出与请求配对 |
| `tool_name` | `String` | 工具名称（如 `"exec_command"`、`"read_file"`） |
| `tool_namespace` | `Option<String>` | MCP 工具的命名空间前缀 |
| `payload` | `ToolPayload` | 具体的调用参数（见上方枚举） |

### 2.3 ToolRegistry 与 ToolRegistryBuilder

工具注册采用 Builder 模式。启动时，`ToolRegistryBuilder` 收集所有工具规格（`ToolSpec`）和处理器（`ToolHandler`），然后一次性构建出不可变的 `ToolRegistry`：

```rust
pub struct ToolRegistryBuilder {
    handlers: HashMap<String, Arc<dyn AnyToolHandler>>,
    specs: Vec<ConfiguredToolSpec>,
}

impl ToolRegistryBuilder {
    pub fn register_handler<H>(&mut self, name: impl Into<String>, handler: Arc<H>)
    where H: ToolHandler + 'static;

    pub fn push_spec(&mut self, spec: ToolSpec);
    pub fn push_spec_with_parallel_support(&mut self, spec: ToolSpec, supports_parallel: bool);
    pub fn build(self) -> (Vec<ConfiguredToolSpec>, ToolRegistry);
}
```

`ConfiguredToolSpec` 在 `ToolSpec` 基础上增加了并行执行支持的标记：

```rust
#[derive(Debug, Clone)]
pub struct ConfiguredToolSpec {
    pub spec: ToolSpec,
    pub supports_parallel_tool_calls: bool,
}
```

工具可以共享 handler 实例。例如 `shell`、`container.exec` 和 `local_shell` 三个工具名都映射到同一个 `ShellHandler` 实例。

> 💡 **最佳实践**：handler 共享机制允许不同工具名映射到同一实现，减少代码重复。`ShellHandler` 通过检查 `payload` 变体来区分不同的调用来源（`Function` vs `LocalShell`），实现统一的 shell 执行逻辑。

### 2.4 ToolRouter — 路由层

`ToolRouter` 是 `ToolRegistry` 之上的路由层，负责将模型输出的 `ResponseItem` 转换为 `ToolCall`，再派发给 `ToolRegistry` 执行：

```rust
pub struct ToolRouter {
    registry: ToolRegistry,
    specs: Vec<ConfiguredToolSpec>,
    model_visible_specs: Vec<ToolSpec>,  // code_mode 下过滤嵌套工具
}

impl ToolRouter {
    pub fn from_config(config: &ToolsConfig, params: ToolRouterParams<'_>) -> Self;
    pub async fn build_tool_call(session: &Session, item: ResponseItem)
        -> Result<Option<ToolCall>, FunctionCallError>;
    pub async fn dispatch_tool_call(...) -> Result<ResponseInputItem, FunctionCallError>;
}
```

`build_tool_call` 的路由逻辑按 `ResponseItem` 类型分发：

```
ResponseItem::FunctionCall        → 检查是否为 MCP 工具 → ToolPayload::Function / ToolPayload::Mcp
ResponseItem::ToolSearchCall      → ToolPayload::ToolSearch（仅 execution == "client"）
ResponseItem::CustomToolCall      → ToolPayload::Custom
ResponseItem::LocalShellCall      → ToolPayload::LocalShell
```

### 2.5 工具派发全流程

`ToolRegistry` 通过 `dispatch_any()` 方法处理工具调用。以下是完整的派发流程图：

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           Tool Dispatch Flow                                    │
│                                                                                  │
│  Model Output                                                                    │
│  (ResponseItem)                                                                  │
│       │                                                                          │
│       ▼                                                                          │
│  ┌─────────────────┐                                                             │
│  │  ToolRouter::    │  解析 ResponseItem 为 ToolCall                              │
│  │  build_tool_call │  判断 Function / MCP / Custom / LocalShell                  │
│  └────────┬────────┘                                                             │
│           │                                                                      │
│           ▼                                                                      │
│  ┌─────────────────────────┐                                                     │
│  │  ToolRouter::            │                                                    │
│  │  dispatch_tool_call      │  构建 ToolInvocation 上下文                         │
│  └────────┬────────────────┘                                                     │
│           │                                                                      │
│           ▼                                                                      │
│  ┌─────────────────────────┐     ┌──────────────────────┐                        │
│  │  ToolRegistry::         │────▶│  handler(name,       │  按 name + namespace   │
│  │  dispatch_any()         │     │    namespace)        │  查找 handler           │
│  └────────┬────────────────┘     └──────────────────────┘                        │
│           │                                                                      │
│           ▼                                                                      │
│  ┌─────────────────────────┐                                                     │
│  │  handler.matches_kind() │  验证 payload 类型兼容性                              │
│  └────────┬────────────────┘                                                     │
│           │                                                                      │
│           ▼                                                                      │
│  ┌─────────────────────────┐     ┌──────────────────────┐                        │
│  │  handler.is_mutating()  │────▶│  is_mutating == true? │                       │
│  └────────┬────────────────┘     │  等待 tool_call_gate  │                       │
│           │                      │  (审批/权限检查)       │                       │
│           ▼                      └──────────────────────┘                        │
│  ┌─────────────────────────┐                                                     │
│  │  handler.handle(        │  执行实际工具逻辑                                     │
│  │    invocation)          │  (ShellHandler / ReadFileHandler / ...)              │
│  └────────┬────────────────┘                                                     │
│           │                                                                      │
│           ▼                                                                      │
│  ┌─────────────────────────┐     ┌──────────────────────┐                        │
│  │  dispatch_after_tool_   │────▶│  执行 after_tool_use  │                       │
│  │  use_hook()             │     │  hooks（可中止操作）   │                       │
│  └────────┬────────────────┘     └──────────────────────┘                        │
│           │                                                                      │
│           ▼                                                                      │
│  ┌─────────────────────────┐                                                     │
│  │  AnyToolResult {        │  返回给模型：                                         │
│  │    call_id,             │  ResponseInputItem::FunctionCallOutput               │
│  │    payload,             │  ResponseInputItem::McpToolCallOutput                │
│  │    result: Box<dyn      │  ResponseInputItem::CustomToolCallOutput             │
│  │      ToolOutput>        │                                                     │
│  │  }                      │                                                     │
│  └─────────────────────────┘                                                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

`dispatch_any()` 的核心实现逻辑：

```rust
impl ToolRegistry {
    pub(crate) async fn dispatch_any(
        &self,
        invocation: ToolInvocation,
    ) -> Result<AnyToolResult, FunctionCallError> {
        // 1. 查找 handler
        let handler = match self.handler(tool_name, tool_namespace) {
            Some(handler) => handler,
            None => return Err(FunctionCallError::RespondToModel(
                unsupported_tool_call_message(...)
            )),
        };

        // 2. 验证 payload 兼容性
        if !handler.matches_kind(&invocation.payload) {
            return Err(FunctionCallError::Fatal(
                format!("tool {tool_name} invoked with incompatible payload")
            ));
        }

        // 3. 检查是否为变更操作 → 等待审批 gate
        let is_mutating = handler.is_mutating(&invocation).await;
        if is_mutating {
            invocation.turn.tool_call_gate.wait_ready().await;
        }

        // 4. 执行 handler
        let result = handler.handle_any(invocation).await?;

        // 5. 触发 after_tool_use hook
        dispatch_after_tool_use_hook(...).await;

        // 6. 返回结果
        Ok(result)
    }
}
```

### 2.6 FunctionCallError 错误类型

所有工具 handler 统一使用 `FunctionCallError` 报告错误：

```rust
pub enum FunctionCallError {
    /// 将错误信息作为工具输出返回给模型（非致命，模型可据此重试）
    RespondToModel(String),
    /// LocalShellCall 缺少 call_id
    MissingLocalShellCallId,
    /// 致命错误，终止当前 turn
    Fatal(String),
}
```

| 变体 | 行为 | 典型场景 |
|------|------|----------|
| `RespondToModel` | 错误信息作为工具输出返回给模型 | 参数解析失败、文件不存在、命令超时 |
| `MissingLocalShellCallId` | 协议级错误 | `LocalShellCall` 没有 `call_id` 或 `id` |
| `Fatal` | 终止整个 turn | payload 类型不匹配、hook 中止操作 |

> ⚠️ **注意**：`RespondToModel` 是最常见的错误处理方式。模型收到错误信息后可以自行决定是否修正参数重试。`Fatal` 错误则会直接中断执行流程，不给模型重试机会。

### 2.7 ToolOrchestrator — 沙箱编排

对于需要沙箱执行的工具（`shell`、`apply_patch`），`ToolOrchestrator` 负责编排审批和沙箱策略：

```
┌───────────────────────────────────────────────────────────────┐
│                    ToolOrchestrator::run()                     │
│                                                               │
│  1. Approval                                                  │
│     ┌─────────────────────────────────────────────────────┐   │
│     │  ExecApprovalRequirement::Skip     → 跳过审批       │   │
│     │  ExecApprovalRequirement::Forbidden → 直接拒绝      │   │
│     │  ExecApprovalRequirement::NeedsApproval → 用户审批  │   │
│     └─────────────────────────────────────────────────────┘   │
│                          │                                     │
│                          ▼                                     │
│  2. First Attempt (with sandbox)                              │
│     ┌─────────────────────────────────────────────────────┐   │
│     │  SandboxManager::select_initial()                    │   │
│     │  → Landlock / macOS sandbox / None                   │   │
│     │  ToolRuntime::run(req, attempt, tool_ctx)            │   │
│     └──────────────┬──────────────────────────────────────┘   │
│                    │                                           │
│              ┌─────┴─────┐                                    │
│              │ 成功？     │                                    │
│              ├─── Yes ───▶ 返回 OrchestratorRunResult         │
│              └─── No ────▶ SandboxErr::Denied?                │
│                                │                               │
│                                ▼                               │
│  3. Retry (without sandbox, after user approval)              │
│     ┌─────────────────────────────────────────────────────┐   │
│     │  SandboxAttempt { sandbox: SandboxType::None }       │   │
│     │  ToolRuntime::run(req, escalated_attempt, tool_ctx)  │   │
│     └─────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

这种"先沙箱尝试，失败后升级"的策略确保了安全与可用性之间的平衡。

---

## 3 标准工具

以下详细描述每个内置工具的参数和行为。所有工具的定义和实现位于 `core/src/tools/handlers/` 目录。

### 3.1 Shell 执行工具

**shell / container.exec / local_shell**

三个工具名共享同一个 `ShellHandler`，提供 PTY 模式的 shell 命令执行。`container.exec` 用于容器化环境，`local_shell` 用于非容器化的本地执行。

`ShellHandler` 支持两种 payload 类型，通过 `matches_kind()` 声明兼容性：

```rust
impl ToolHandler for ShellHandler {
    type Output = FunctionToolOutput;

    fn kind(&self) -> ToolKind { ToolKind::Function }

    fn matches_kind(&self, payload: &ToolPayload) -> bool {
        matches!(
            payload,
            ToolPayload::Function { .. } | ToolPayload::LocalShell { .. }
        )
    }

    async fn is_mutating(&self, invocation: &ToolInvocation) -> bool {
        match &invocation.payload {
            ToolPayload::Function { arguments } => {
                serde_json::from_str::<ShellToolCallParams>(arguments)
                    .map(|params| !is_known_safe_command(&params.command))
                    .unwrap_or(true)
            }
            ToolPayload::LocalShell { params } => !is_known_safe_command(&params.command),
            _ => true, // unknown payloads => assume mutating
        }
    }

    // handle() 根据 payload 类型分别处理 ...
}
```

> 📌 **重点**：`is_mutating()` 通过 `is_known_safe_command()` 判断命令是否安全（如 `ls`、`cat`、`git status` 等只读命令会返回 `false`）。只有被判定为 mutating 的命令才需要经过审批 gate。

**exec_command（UnifiedExecHandler）**

统一命令执行工具，是最常用的命令执行入口。支持沙箱权限控制和输出截断。

完整参数定义（源自 `unified_exec.rs`）：

```rust
#[derive(Debug, Deserialize)]
pub(crate) struct ExecCommandArgs {
    cmd: String,                              // 要执行的命令字符串
    #[serde(default)]
    pub(crate) workdir: Option<String>,       // 工作目录
    #[serde(default)]
    shell: Option<String>,                    // shell 路径覆盖
    #[serde(default)]
    login: Option<bool>,                      // 是否使用 login shell
    #[serde(default = "default_tty")]
    tty: bool,                                // 是否启用 TTY（默认 false）
    #[serde(default = "default_exec_yield_time_ms")]
    yield_time_ms: u64,                       // 等待输出超时（默认 10,000ms）
    #[serde(default)]
    max_output_tokens: Option<usize>,         // 输出 token 上限
    #[serde(default)]
    sandbox_permissions: SandboxPermissions,  // 沙箱权限级别
    #[serde(default)]
    additional_permissions: Option<PermissionProfile>, // 附加权限配置
    #[serde(default)]
    justification: Option<String>,            // 权限请求理由
    #[serde(default)]
    prefix_rule: Option<Vec<String>>,         // 命令前缀规则
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cmd` | String | -- | 要执行的命令字符串 |
| `workdir` | String? | turn cwd | 工作目录 |
| `shell` | String? | session shell | shell 路径覆盖（如 `/bin/bash`） |
| `login` | Boolean? | config 决定 | 是否使用 login shell |
| `tty` | Boolean | `false` | 是否启用 PTY 模式 |
| `yield_time_ms` | Number | `10000` | 等待输出超时时间（ms） |
| `max_output_tokens` | Number? | 全局配置 | 输出 token 上限 |
| `sandbox_permissions` | Enum | `UseDefault` | `UseDefault` / `RequireEscalated` / `WithAdditionalPermissions` |
| `additional_permissions` | Object? | -- | 附加权限（网络、文件系统等） |
| `justification` | String? | -- | 权限提升的理由说明 |
| `prefix_rule` | Array? | -- | 命令前缀规则列表 |

**输出 Schema**（定义于 `spec.rs` 的 `unified_exec_output_schema()`）：

```json
{
  "type": "object",
  "properties": {
    "chunk_id": {
      "type": "string",
      "description": "Chunk identifier included when the response reports one."
    },
    "wall_time_seconds": {
      "type": "number",
      "description": "Elapsed wall time spent waiting for output in seconds."
    },
    "exit_code": {
      "type": "number",
      "description": "Process exit code when the command finished during this call."
    },
    "session_id": {
      "type": "number",
      "description": "Session identifier to pass to write_stdin when the process is still running."
    },
    "original_token_count": {
      "type": "number",
      "description": "Approximate token count before output truncation."
    },
    "output": {
      "type": "string",
      "description": "Command output text, possibly truncated."
    }
  },
  "required": ["wall_time_seconds", "output"],
  "additionalProperties": false
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `chunk_id` | String | 否 | 长输出分块时的 chunk 标识 |
| `wall_time_seconds` | Number | 是 | 实际执行耗时（秒） |
| `exit_code` | Number | 否 | 进程退出码（命令结束时出现） |
| `session_id` | Number | 否 | 进程会话 ID（进程仍在运行时出现，用于 `write_stdin`） |
| `original_token_count` | Number | 否 | 截断前的原始 token 数量 |
| `output` | String | 是 | 命令输出文本（可能被截断） |

**场景示例 — 成功执行只读命令**：

模型发送请求：

```json
{
  "type": "function_call",
  "name": "exec_command",
  "call_id": "call_abc123",
  "arguments": "{\"cmd\": \"ls -la /workspace/src\", \"workdir\": \"/workspace\"}"
}
```

运行时返回：

```json
{
  "type": "function_call_output",
  "call_id": "call_abc123",
  "output": {
    "body": "Command: /bin/zsh -c 'ls -la /workspace/src'\nWall time: 0.0312 seconds\nProcess exited with code 0\nOutput:\ntotal 24\ndrwxr-xr-x  5 user staff  160 Mar 10 09:00 .\ndrwxr-xr-x  8 user staff  256 Mar 10 08:55 ..\n-rw-r--r--  1 user staff 1234 Mar 10 09:00 main.rs\n-rw-r--r--  1 user staff  567 Mar 10 08:55 lib.rs\n-rw-r--r--  1 user staff  890 Mar 10 09:00 utils.rs",
    "success": true
  }
}
```

**场景示例 — 长时间运行的进程**：

```json
{
  "type": "function_call",
  "name": "exec_command",
  "call_id": "call_def456",
  "arguments": "{\"cmd\": \"cargo build --release\", \"yield_time_ms\": 30000}"
}
```

如果进程在 `yield_time_ms` 内未结束，返回中间结果：

```json
{
  "type": "function_call_output",
  "call_id": "call_def456",
  "output": {
    "body": "Wall time: 30.0001 seconds\nProcess running with session ID 42\nOutput:\n   Compiling serde v1.0.210\n   Compiling tokio v1.40.0\n   Compiling ...",
    "success": true
  }
}
```

模型随后可用 `write_stdin` 工具通过 `session_id: 42` 继续交互。

**场景示例 — 命令执行失败**：

```json
{
  "type": "function_call_output",
  "call_id": "call_err789",
  "output": {
    "body": "exec_command failed for `cargo test`: process exited with non-zero code",
    "success": false
  }
}
```

> 💡 **最佳实践**：`exec_command` 会自动拦截 `apply_patch` 命令。如果模型尝试通过 `exec_command` 执行 `apply_patch`，`intercept_apply_patch()` 会将其重定向到专用的 `ApplyPatchHandler`，并记录一条模型警告：`"apply_patch was requested via exec_command. Use the apply_patch tool instead."`

**write_stdin（UnifiedExecHandler）**

向仍在运行的进程 stdin 写入数据。通过 `session_id`（来自 `exec_command` 输出）标识目标进程。

```rust
#[derive(Debug, Deserialize)]
struct WriteStdinArgs {
    session_id: i32,                          // 目标进程的 session ID
    #[serde(default)]
    chars: String,                            // 要写入的字符串
    #[serde(default = "default_write_stdin_yield_time_ms")]
    yield_time_ms: u64,                       // 等待输出超时（默认 250ms）
    #[serde(default)]
    max_output_tokens: Option<usize>,         // 输出 token 上限
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `session_id` | Number | -- | 目标进程的会话 ID（来自 `exec_command` 输出） |
| `chars` | String | `""` | 要写入 stdin 的字符串 |
| `yield_time_ms` | Number | `250` | 写入后等待输出的时间（ms） |
| `max_output_tokens` | Number? | 全局配置 | 输出 token 上限 |

---

### 3.2 文件操作工具

**read_file（ReadFileHandler）**

文件读取工具，支持两种模式：简单切片（slice）和缩进感知（indentation）。

完整参数定义（源自 `read_file.rs`）：

```rust
#[derive(Deserialize)]
struct ReadFileArgs {
    file_path: String,                    // 绝对路径
    #[serde(default = "defaults::offset")]
    offset: usize,                        // 1-indexed 起始行号（默认 1）
    #[serde(default = "defaults::limit")]
    limit: usize,                         // 最大读取行数（默认 2000）
    #[serde(default)]
    mode: ReadMode,                       // 读取模式
    #[serde(default)]
    indentation: Option<IndentationArgs>, // 缩进配置
}

#[derive(Deserialize, Default)]
#[serde(rename_all = "snake_case")]
enum ReadMode {
    #[default]
    Slice,        // 简单行切片
    Indentation,  // 缩进感知读取
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `file_path` | String | -- | 必须为绝对路径 |
| `offset` | Number | `1` | 1-indexed 起始行号 |
| `limit` | Number | `2000` | 最大读取行数 |
| `mode` | Enum | `slice` | `slice`（简单切片）或 `indentation`（缩进感知） |
| `indentation` | Object? | -- | 缩进模式的配置参数 |

Indentation 模式的附加参数：

```rust
#[derive(Deserialize, Clone)]
struct IndentationArgs {
    anchor_line: Option<usize>,   // 锚定行号（默认使用 offset）
    max_levels: usize,            // 最大缩进层级（0 = 无限制，默认 0）
    include_siblings: bool,       // 是否包含同级块（默认 false）
    include_header: bool,         // 是否包含头部注释行（默认 true）
    max_lines: Option<usize>,     // 返回行数硬上限
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `anchor_line` | Number? | offset | 缩进锚定行（哪一行作为参考点） |
| `max_levels` | Number | `0` | 最大缩进层级（0 表示不限制） |
| `include_siblings` | Boolean | `false` | 是否包含同级代码块 |
| `include_header` | Boolean | `true` | 是否包含块上方的注释头 |
| `max_lines` | Number? | limit | 返回行数的硬上限 |

关键常量：

| 常量 | 值 | 说明 |
|------|----|------|
| `MAX_LINE_LENGTH` | 500 | 单行最大字符数，超出截断 |
| `TAB_WIDTH` | 4 | Tab 字符的等价空格数 |

**场景示例 — Slice 模式读取**：

请求：

```json
{
  "type": "function_call",
  "name": "read_file",
  "call_id": "call_rf001",
  "arguments": "{\"file_path\": \"/workspace/src/main.rs\", \"offset\": 1, \"limit\": 5}"
}
```

返回：

```json
{
  "type": "function_call_output",
  "call_id": "call_rf001",
  "output": {
    "body": "L1: use std::collections::HashMap;\nL2: use std::sync::Arc;\nL3: \nL4: mod tools;\nL5: mod registry;",
    "success": true
  }
}
```

输出格式为 `L{行号}: {内容}`，每行以换行分隔。

**场景示例 — 文件不存在**：

```json
{
  "type": "function_call_output",
  "call_id": "call_rf002",
  "output": {
    "body": "failed to read file: No such file or directory (os error 2)",
    "success": false
  }
}
```

**场景示例 — 路径不是绝对路径**：

```json
{
  "type": "function_call_output",
  "call_id": "call_rf003",
  "output": {
    "body": "file_path must be an absolute path",
    "success": false
  }
}
```

> 📌 **重点**：`read_file` 强制要求绝对路径，`offset` 必须 >= 1（1-indexed）。这些输入验证在 handler 开头以 guard clause 形式实现：

```rust
if offset == 0 {
    return Err(FunctionCallError::RespondToModel(
        "offset must be a 1-indexed line number".to_string(),
    ));
}
if !path.is_absolute() {
    return Err(FunctionCallError::RespondToModel(
        "file_path must be an absolute path".to_string(),
    ));
}
```

**grep_files（GrepFilesHandler）**

文件内容搜索工具，底层调用 `ripgrep`（`rg`）。

```rust
#[derive(Deserialize)]
struct GrepFilesArgs {
    pattern: String,          // 正则表达式搜索模式
    #[serde(default)]
    include: Option<String>,  // glob 过滤（如 "*.rs"）
    #[serde(default)]
    path: Option<String>,     // 搜索路径
    #[serde(default = "default_limit")]
    limit: usize,             // 结果数量上限（默认 100）
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pattern` | String | -- | 正则表达式搜索模式（不能为空） |
| `include` | String? | -- | glob 过滤模式（如 `"*.rs"`、`"*.py"`） |
| `path` | String? | turn cwd | 搜索路径（文件或目录） |
| `limit` | Number | `100` | 结果数量上限 |

关键常量：

| 常量 | 值 | 说明 |
|------|----|------|
| `DEFAULT_LIMIT` | 100 | 默认返回 100 个匹配文件 |
| `MAX_LIMIT` | 2000 | 最大允许 2000 个结果 |
| `COMMAND_TIMEOUT` | 30 秒 | `rg` 命令超时时间 |

底层执行的 `rg` 命令：

```bash
rg --files-with-matches --sortr=modified --regexp <pattern> --no-messages [--glob <include>] -- <path>
```

**场景示例 — 搜索成功**：

请求：

```json
{
  "type": "function_call",
  "name": "grep_files",
  "call_id": "call_gf001",
  "arguments": "{\"pattern\": \"ToolHandler\", \"include\": \"*.rs\", \"limit\": 5}"
}
```

返回：

```json
{
  "type": "function_call_output",
  "call_id": "call_gf001",
  "output": {
    "body": "src/tools/registry.rs\nsrc/tools/handlers/unified_exec.rs\nsrc/tools/handlers/shell.rs\nsrc/tools/handlers/read_file.rs\nsrc/tools/handlers/grep_files.rs",
    "success": true
  }
}
```

**场景示例 — 无匹配结果**：

```json
{
  "type": "function_call_output",
  "call_id": "call_gf002",
  "output": {
    "body": "No matches found.",
    "success": false
  }
}
```

**场景示例 — rg 未安装**：

```json
{
  "type": "function_call_output",
  "call_id": "call_gf003",
  "output": {
    "body": "failed to launch rg: No such file or directory (os error 2). Ensure ripgrep is installed and on PATH.",
    "success": false
  }
}
```

**list_dir（ListDirHandler）**

目录列表工具，返回指定目录下的文件和子目录信息。支持递归深度控制和分页。

```rust
#[derive(Deserialize)]
struct ListDirArgs {
    dir_path: String,                       // 绝对路径
    #[serde(default = "default_offset")]
    offset: usize,                          // 1-indexed 起始条目（默认 1）
    #[serde(default = "default_limit")]
    limit: usize,                           // 返回条目数上限（默认 25）
    #[serde(default = "default_depth")]
    depth: usize,                           // 递归深度（默认 2）
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `dir_path` | String | -- | 必须为绝对路径 |
| `offset` | Number | `1` | 1-indexed 起始条目编号 |
| `limit` | Number | `25` | 返回条目数上限 |
| `depth` | Number | `2` | 递归深度 |

目录条目后缀标识：

| 后缀 | 含义 |
|------|------|
| `/` | 目录 |
| `@` | 符号链接 |
| `?` | 其他类型 |
| （无后缀） | 普通文件 |

**场景示例 — 列出目录**：

```json
{
  "type": "function_call_output",
  "call_id": "call_ld001",
  "output": {
    "body": "Absolute path: /workspace/src\nmain.rs\nlib.rs\ntools/\n  handlers/\n    mod.rs\n    shell.rs\n  registry.rs\nutils.rs\nMore than 8 entries found",
    "success": true
  }
}
```

子目录条目按 `depth` 层缩进（每层 2 个空格），超出 `limit` 时追加 `"More than N entries found"` 提示。

**view_image（ViewImageHandler）**

图片查看工具，支持多种图片格式，将图片内容编码为模型可理解的格式。

```rust
#[derive(Deserialize)]
struct ViewImageArgs {
    path: String,             // 图片文件路径
    detail: Option<String>,   // 仅支持 "original"（或省略）
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | String | -- | 图片文件路径 |
| `detail` | String? | -- | 图片精度，仅支持 `"original"`（不设则自动缩放） |

> ⚠️ **注意**：`view_image` 需要模型支持图片输入（`InputModality::Image`）。如果模型不支持，handler 返回错误：`"view_image is not allowed because you do not support image inputs"`。`detail` 仅接受 `"original"` 值，其他值会报错。

---

### 3.3 代码编辑工具

**apply_patch（ApplyPatchHandler）**

结构化代码补丁工具，支持两种输入格式：
- **Freeform Lark 语法**：自然语言风格的补丁描述（GPT-5 模型使用）
- **JSON 结构化格式**：精确的文件位置和替换内容（GPT-OSS 模型使用）

`ApplyPatchHandler` 同时接受 `Function` 和 `Custom` 两种 payload：

```rust
impl ToolHandler for ApplyPatchHandler {
    type Output = FunctionToolOutput;

    fn kind(&self) -> ToolKind { ToolKind::Function }

    fn matches_kind(&self, payload: &ToolPayload) -> bool {
        matches!(payload, ToolPayload::Function { .. } | ToolPayload::Custom { .. })
    }

    async fn is_mutating(&self, _invocation: &ToolInvocation) -> bool {
        true  // 文件修改操作，始终为 true
    }
}
```

**Patch 语法示例**：

```
*** Begin Patch
*** Add File: hello.txt
+Hello world
*** Update File: src/app.py
*** Move to: src/main.py
@@ def greet():
-print("Hi")
+print("Hello, world!")
*** Delete File: obsolete.txt
*** End Patch
```

Patch 操作类型：

| 操作 | 语法 | 说明 |
|------|------|------|
| 新建文件 | `*** Add File: <path>` | 后续行均以 `+` 开头 |
| 更新文件 | `*** Update File: <path>` | 可选 `*** Move to:` 重命名 |
| 删除文件 | `*** Delete File: <path>` | 无后续内容 |

Hunk 行标记：

| 前缀 | 含义 |
|------|------|
| 空格 | 上下文行（不修改） |
| `-` | 删除行 |
| `+` | 新增行 |
| `@@` | Hunk 头（可选函数/类名锚定） |

**场景示例 — Patch 验证失败**：

```json
{
  "type": "function_call_output",
  "call_id": "call_ap001",
  "output": {
    "body": "apply_patch verification failed: context lines do not match file content at line 42",
    "success": false
  }
}
```

与 Claude Code 的 `Edit` 工具类似，但 `apply_patch` 更接近传统的 patch/diff 概念，支持多文件批量修改。内部使用 `codex-apply-patch` crate，基于 Tree-sitter 进行代码解析。

> 💡 **最佳实践**：文件路径在 patch 中只能使用相对路径，不能使用绝对路径。`apply_patch` 的上下文行应默认显示变更前后各 3 行，如果 3 行不足以唯一定位代码片段，应使用 `@@` 锚定到类名或函数名。

---

### 3.4 JavaScript REPL 工具

**js_repl（JsReplHandler）**

内置 JavaScript REPL，运行在持久化的 Node.js 内核中。

**关键特性**：
- 变量绑定在会话内持久化
- `codex.tool()` API — 从 JS 代码中调用其他 Codex 工具
- `codex.emitImage()` API — 在 REPL 中生成和展示图片
- 适合数据分析、快速原型验证等场景

**js_repl_reset（JsReplResetHandler）**

重置 REPL 状态，清除所有变量绑定。

> ⚠️ **注意**：当 `js_repl_tools_only` 配置为 `true` 时，模型只能使用 `js_repl` 和 `js_repl_reset` 两个工具，其他所有工具必须通过 `codex.tool(...)` 在 REPL 中间接调用。ToolRouter 会检查此配置并拒绝直接工具调用：

```rust
if source == ToolCallSource::Direct
    && turn.tools_config.js_repl_tools_only
    && !matches!(tool_name.as_str(), "js_repl" | "js_repl_reset")
{
    return Err(FunctionCallError::RespondToModel(
        "direct tool calls are disabled; use js_repl and codex.tool(...) instead"
            .to_string(),
    ));
}
```

---

### 3.5 计划工具

**plan / update_plan（PlanHandler）**

协作模式（Collaboration Mode）中的计划管理工具。当 `collaboration_mode` 设为 `plan` 时，模型先制定计划（plan），用户审批后再执行。`plan` 创建新计划，`update_plan` 更新已有计划。

---

## 4 多代理协作工具

当配置中 `collab_tools` 启用时，Codex 注册一组多代理协作工具。这些工具允许主代理（orchestrator）动态创建、通信和管理子代理（sub-agents），每个子代理运行在独立的线程/会话中。

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Multi-Agent Collaboration Flow                    │
│                                                                      │
│  Orchestrator (主代理)                                                │
│       │                                                              │
│       ├── spawn_agent(message="修复 auth 模块的测试")                  │
│       │       │                                                      │
│       │       ▼                                                      │
│       │   ┌──────────────────┐                                       │
│       │   │  Sub-Agent A      │  agent_id: "a1b2c3d4-..."           │
│       │   │  role: "coder"    │  depth: 1                           │
│       │   └──────────────────┘                                       │
│       │                                                              │
│       ├── spawn_agent(message="更新 API 文档")                        │
│       │       │                                                      │
│       │       ▼                                                      │
│       │   ┌──────────────────┐                                       │
│       │   │  Sub-Agent B      │  agent_id: "e5f6g7h8-..."           │
│       │   │  role: "writer"   │  depth: 1                           │
│       │   └──────────────────┘                                       │
│       │                                                              │
│       ├── wait_agent(ids=["a1b2c3d4-...", "e5f6g7h8-..."])           │
│       │       │                                                      │
│       │       ▼                                                      │
│       │   等待子代理完成（超时 30s，可配置）                             │
│       │                                                              │
│       ├── send_input(id="a1b2c3d4-...", message="增加边界测试")        │
│       │       │                                                      │
│       │       ▼                                                      │
│       │   向已有代理发送新任务                                         │
│       │                                                              │
│       └── close_agent(id="e5f6g7h8-...")                             │
│               │                                                      │
│               ▼                                                      │
│           释放子代理资源                                               │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.1 spawn_agent（SpawnAgentHandler）

创建新的子代理。

完整参数定义（源自 `multi_agents/spawn.rs`）：

```rust
#[derive(Debug, Deserialize)]
struct SpawnAgentArgs {
    message: Option<String>,                  // 初始任务文本（与 items 二选一）
    items: Option<Vec<UserInput>>,            // 初始输入项列表（多模态）
    agent_type: Option<String>,               // 代理角色名称
    model: Option<String>,                    // 模型覆盖
    reasoning_effort: Option<ReasoningEffort>,// 推理强度覆盖
    #[serde(default)]
    fork_context: bool,                       // 是否分叉当前线程历史
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `message` | String? | 初始纯文本任务描述（与 `items` 二选一） |
| `items` | Array? | 初始输入项列表（支持图片等多模态） |
| `agent_type` | String? | 代理角色名称（映射到 `AgentRoleConfig`） |
| `model` | String? | 模型覆盖 |
| `reasoning_effort` | Enum? | 推理强度覆盖 |
| `fork_context` | Boolean | 是否分叉当前线程历史（默认 false） |

**输出**（`SpawnAgentResult`）：

```rust
#[derive(Debug, Serialize)]
pub(crate) struct SpawnAgentResult {
    agent_id: String,           // 新子代理的 ThreadId（UUID）
    nickname: Option<String>,   // 友好名称（可能为 null）
}
```

**场景示例 — 成功创建子代理**：

请求：

```json
{
  "type": "function_call",
  "name": "spawn_agent",
  "call_id": "call_sa001",
  "arguments": "{\"message\": \"修复 src/auth.rs 中的单元测试\", \"agent_type\": \"coder\"}"
}
```

返回：

```json
{
  "type": "function_call_output",
  "call_id": "call_sa001",
  "output": {
    "body": "{\"agent_id\":\"a1b2c3d4-5678-9abc-def0-123456789abc\",\"nickname\":\"coder-1\"}",
    "success": true
  }
}
```

**场景示例 — 超出深度限制**：

```json
{
  "type": "function_call_output",
  "call_id": "call_sa002",
  "output": {
    "body": "Agent depth limit reached. Solve the task yourself.",
    "success": false
  }
}
```

子代理深度由 `config.agent_max_depth` 控制。每次 spawn 时调用 `next_thread_spawn_depth()` 计算子代理层级，超限时拒绝创建。

### 4.2 send_input（SendInputHandler）

向已存在的子代理发送消息。

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | String | 子代理 ID |
| `message` | String? | 纯文本消息 |
| `items` | Array? | 输入项列表 |
| `interrupt` | Boolean | 是否中断当前任务（默认 false） |

当 `interrupt=true` 时，子代理会立即停止当前工作并处理新输入。文档建议：如果新任务高度依赖之前的上下文，应通过 `send_input` 复用已有代理，而非创建新代理。

### 4.3 wait_agent（WaitAgentHandler）

等待一个或多个子代理完成。

完整参数定义（源自 `multi_agents/wait.rs`）：

```rust
#[derive(Debug, Deserialize)]
struct WaitArgs {
    ids: Vec<String>,          // 子代理 ID 列表（不能为空）
    timeout_ms: Option<i64>,   // 超时毫秒数
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `ids` | Array | 子代理 ID 列表（不能为空） |
| `timeout_ms` | Number? | 超时毫秒数（自动 clamp 到允许范围） |

**超时常量**：

| 常量 | 值 | 说明 |
|------|----|------|
| `MIN_WAIT_TIMEOUT_MS` | 10,000 | 最小 10 秒 |
| `DEFAULT_WAIT_TIMEOUT_MS` | 30,000 | 默认 30 秒 |
| `MAX_WAIT_TIMEOUT_MS` | 3,600,000 | 最大 1 小时 |

`timeout_ms` 会被 `clamp(MIN, MAX)` 限制在合法范围内。小于等于 0 时返回错误。

**输出**（`WaitAgentResult`）：

```rust
#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
pub(crate) struct WaitAgentResult {
    pub(crate) status: HashMap<ThreadId, AgentStatus>,  // 每个代理的状态
    pub(crate) timed_out: bool,                         // 是否超时
}
```

**AgentStatus 状态机**：

```
                    ┌──────────────┐
                    │ pending_init │  刚创建，尚未初始化
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
            ┌──────│   running    │──────┐
            │      └──────────────┘      │
            │                            │
            ▼                            ▼
     ┌──────────────┐           ┌──────────────┐
     │  completed   │           │   errored    │
     │ (附带最终输出)│           │ (附带错误信息)│
     └──────────────┘           └──────────────┘
            │                            │
            └────────────┬───────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │   shutdown   │  代理已关闭
                  └──────────────┘

     特殊状态：not_found（代理 ID 不存在）
```

`AgentStatus` 的输出 schema：

```json
{
  "oneOf": [
    { "type": "string", "enum": ["pending_init", "running", "shutdown", "not_found"] },
    {
      "type": "object",
      "properties": { "completed": { "type": ["string", "null"] } },
      "required": ["completed"]
    },
    {
      "type": "object",
      "properties": { "errored": { "type": ["string", "null"] } },
      "required": ["errored"]
    }
  ]
}
```

**场景示例 — 等待成功**：

```json
{
  "type": "function_call_output",
  "call_id": "call_wa001",
  "output": {
    "body": "{\"status\":{\"a1b2c3d4-5678-9abc-def0-123456789abc\":{\"completed\":\"Tests fixed: 3 failures resolved\"}},\"timed_out\":false}",
    "success": true
  }
}
```

**场景示例 — 等待超时**：

```json
{
  "type": "function_call_output",
  "call_id": "call_wa002",
  "output": {
    "body": "{\"status\":{},\"timed_out\":true}",
    "success": true
  }
}
```

### 4.4 close_agent（CloseAgentHandler）

关闭不再需要的子代理并返回其最终状态。文档提醒："Don't keep agents open for too long if they are not needed anymore."

### 4.5 resume_agent（ResumeAgentHandler）

恢复之前已关闭的子代理，使其重新接受 `send_input` 和 `wait_agent` 调用。

> 💡 **最佳实践**：多代理协作模式适合将复杂任务分解为独立子任务并行执行。orchestrator 负责任务分配和结果汇总，子代理各自独立工作。每个子代理有独立的 rollout 文件（`SessionSource::SubAgent(ThreadSpawn)`），包含 `parent_thread_id` 和 `depth` 信息用于追踪层级关系。

---

## 5 用户交互与发现工具

### 5.1 request_user_input（RequestUserInputHandler）

向用户发出问题并等待回答。用于模型在执行过程中需要用户确认或提供额外信息的场景。

### 5.2 request_permissions（RequestPermissionsHandler）

请求沙箱权限提升。当工具需要超出当前沙箱策略的权限时（如写入工作区外的目录、访问网络），通过此工具请求临时权限扩展。权限扩展仅在当前命令范围内生效，不改变全局沙箱策略。

**权限配置结构**：

```json
{
  "additional_permissions": {
    "network": {
      "enabled": true
    },
    "file_system": {
      "read": [],
      "write": ["/tmp/output"]
    }
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `network.enabled` | Boolean | 是否允许网络访问 |
| `file_system.read` | Array | 额外的可读路径列表 |
| `file_system.write` | Array | 额外的可写路径列表 |

### 5.3 _tool_search / _tool_suggest

工具发现机制。前缀 `_` 表示这些是内部工具，不直接暴露给用户。`_tool_search` 搜索可用工具，`_tool_suggest` 根据当前上下文推荐合适的工具。

---

## 6 MCP 与动态工具

### 6.1 MCP 工具

通过 MCP（Model Context Protocol）协议，Codex 可以动态加载外部工具。MCP 工具由 `McpHandler` 统一处理，每个 MCP 服务器提供的工具自动注册到 `ToolRegistry` 中。

`McpHandler` 的完整实现非常简洁，仅做 payload 解包和委托：

```rust
pub struct McpHandler;

#[async_trait]
impl ToolHandler for McpHandler {
    type Output = CallToolResult;

    fn kind(&self) -> ToolKind { ToolKind::Mcp }

    async fn handle(&self, invocation: ToolInvocation)
        -> Result<Self::Output, FunctionCallError>
    {
        let (server, tool, raw_arguments) = match invocation.payload {
            ToolPayload::Mcp { server, tool, raw_arguments } => {
                (server, tool, raw_arguments)
            }
            _ => return Err(FunctionCallError::RespondToModel(
                "mcp handler received unsupported payload".to_string(),
            )),
        };

        let output = handle_mcp_tool_call(
            Arc::clone(&invocation.session),
            &invocation.turn,
            invocation.call_id.clone(),
            server, tool, raw_arguments,
        ).await;

        Ok(output)
    }
}
```

MCP 工具名通过命名空间隔离。`tool_handler_key()` 函数负责生成 `"namespace:tool_name"` 格式的查找键：

```rust
pub(crate) fn tool_handler_key(tool_name: &str, namespace: Option<&str>) -> String {
    if let Some(namespace) = namespace {
        format!("{namespace}:{tool_name}")
    } else {
        tool_name.to_string()
    }
}
```

**场景示例 — MCP 工具调用**：

```json
{
  "type": "function_call",
  "name": "github__create_issue",
  "namespace": "mcp_github",
  "call_id": "call_mcp001",
  "arguments": "{\"title\": \"Fix auth bug\", \"body\": \"Users cannot login...\"}"
}
```

handler key 为 `"mcp_github:github__create_issue"`，由 `McpHandler` 统一处理。

MCP 资源操作由 `McpResourceHandler` 处理：
- `list_mcp_resources` — 列出可用资源
- `list_mcp_resource_templates` — 列出资源模板
- `read_mcp_resource` — 读取特定资源

### 6.2 DynamicToolSpec

Codex 支持通过 `DynamicToolSpec` 在运行时注册自定义工具。这些工具存储在 `thread_dynamic_tools` 数据库表中，可以跨会话持久化。动态工具由 `DynamicToolHandler` 执行，支持延迟加载（`defer_loading`）。

### 6.3 批量任务工具

- `spawn_agents_on_csv`（BatchJobHandler）— 基于 CSV 文件批量创建 Agent 任务
- `report_agent_job_result`（BatchJobHandler）— 报告批量任务执行结果

任务状态存储在 `agent_jobs` 和 `agent_job_items` 表中。

---

## 7 工具模块组织

### 7.1 目录结构

`core/src/tools/` 目录下的完整模块组织：

```
tools/
├── mod.rs                     # 顶层模块声明
├── registry.rs                # ToolHandler trait + ToolRegistry + ToolRegistryBuilder
├── router.rs                  # ToolRouter（ResponseItem → ToolCall 路由）
├── context.rs                 # ToolInvocation + ToolPayload + ToolOutput trait
├── spec.rs                    # ToolsConfig + output schema 定义
├── orchestrator.rs            # ToolOrchestrator（审批 + 沙箱编排）
├── parallel.rs                # ToolCallRuntime（并行工具执行）
├── sandboxing.rs              # ApprovalStore + ToolRuntime trait
├── discoverable.rs            # DiscoverableTool（延迟加载工具）
├── events.rs                  # ToolEmitter（事件广播）
├── network_approval.rs        # 网络审批逻辑
│
├── handlers/                  # 工具 handler 实现
│   ├── mod.rs                 # 模块声明 + parse_arguments 辅助函数
│   ├── unified_exec.rs        # UnifiedExecHandler (exec_command / write_stdin)
│   ├── shell.rs               # ShellHandler + ShellCommandHandler
│   ├── apply_patch.rs         # ApplyPatchHandler
│   ├── read_file.rs           # ReadFileHandler
│   ├── grep_files.rs          # GrepFilesHandler
│   ├── list_dir.rs            # ListDirHandler
│   ├── view_image.rs          # ViewImageHandler
│   ├── js_repl.rs             # JsReplHandler
│   ├── plan.rs                # PlanHandler
│   ├── artifacts.rs           # ArtifactsHandler
│   ├── mcp.rs                 # McpHandler
│   ├── mcp_resource.rs        # McpResourceHandler
│   ├── dynamic.rs             # DynamicToolHandler
│   ├── request_permissions.rs # RequestPermissionsHandler
│   ├── request_user_input.rs  # RequestUserInputHandler
│   ├── tool_search.rs         # ToolSearchHandler
│   ├── tool_suggest.rs        # ToolSuggestHandler
│   ├── agent_jobs.rs          # BatchJobHandler
│   ├── test_sync.rs           # TestSyncHandler（测试用）
│   └── multi_agents/          # 多代理工具
│       ├── spawn.rs           # spawn_agent
│       ├── send_input.rs      # send_input
│       ├── wait.rs            # wait_agent
│       ├── close_agent.rs     # close_agent
│       └── resume_agent.rs    # resume_agent
│
├── runtimes/                  # 工具运行时（沙箱执行层）
│   ├── mod.rs                 # ToolRuntime trait 实现
│   ├── shell.rs               # ShellRuntime（沙箱内 shell 执行）
│   ├── apply_patch.rs         # ApplyPatchRuntime（沙箱内 patch 执行）
│   └── unified_exec.rs        # UnifiedExecRuntime
│
├── code_mode/                 # Code Mode（代码执行模式）
│   ├── mod.rs                 # CodeModeExecuteHandler + CodeModeWaitHandler
│   ├── execute_handler.rs     # 执行逻辑
│   ├── wait_handler.rs        # 等待结果
│   ├── protocol.rs            # 内部协议
│   ├── process.rs             # 进程管理
│   ├── service.rs             # 服务层
│   └── worker.rs              # 工作线程
│
└── js_repl/                   # JS REPL 内核
    └── mod.rs                 # Node.js 内核管理
```

### 7.2 handler 与 runtime 的关系

handler 和 runtime 的分层设计是 Codex 工具系统的重要架构决策：

```
┌──────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│    ToolHandler    │────▶│  ToolOrchestrator  │────▶│   ToolRuntime     │
│  (参数解析、验证)  │     │  (审批、沙箱选择)   │     │  (实际执行)        │
└──────────────────┘     └───────────────────┘     └───────────────────┘
       例如：                     例如：                     例如：
   ShellHandler          ToolOrchestrator::run()     ShellRuntime::run()
   ApplyPatchHandler     - ExecApprovalRequirement   ApplyPatchRuntime::run()
   ReadFileHandler       - SandboxAttempt
   (直接执行，无需
    orchestrator)
```

| 层级 | 职责 | 是否所有工具都有 |
|------|------|-----------------|
| Handler | 解析参数、输入验证、业务逻辑 | 是（每个工具一个） |
| Orchestrator | 审批流程、沙箱策略选择、重试 | 否（仅 shell、apply_patch 等需要沙箱的工具） |
| Runtime | 在选定的沙箱环境中实际执行命令 | 否（仅需要沙箱执行的工具） |

> 📌 **重点**：像 `ReadFileHandler`、`GrepFilesHandler` 这样的只读工具直接在 handler 中执行，不经过 orchestrator 和 runtime 层。只有可能修改文件系统或执行外部命令的工具才需要沙箱编排。

---

## 8 与 Claude Code 工具系统的对比

了解两个系统的工具设计差异，有助于理解不同的 AI 代理架构理念：

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **工具调用格式** | OpenAI `function_call` / `function_call_output` | Anthropic `tool_use` / `tool_result` |
| **命令执行** | `shell` / `exec_command`（统一入口） | `Bash`（独立工具） |
| **文件读取** | `read_file`（offset/limit/mode） | `Read`（offset/limit） |
| **文件编辑** | `apply_patch`（Tree-sitter patch） | `Edit`（精确字符串替换） |
| **文件写入** | 通过 `apply_patch` | `Write`（完整文件写入） |
| **文件搜索** | `grep_files` + `list_dir` | `Grep` + `Glob` |
| **代码搜索** | `file-search`（nucleo BM25） | 无独立搜索引擎 |
| **多代理** | `spawn_agent` / `wait_agent` 等 5 个工具 | `Agent` 工具（启动子代理） |
| **MCP 支持** | `McpHandler`（客户端）+ `mcp-server`（服务端） | 内置 MCP 支持 |
| **JS REPL** | `js_repl`（持久 Node.js 内核） | 无 |
| **计划工具** | `plan` / `update_plan` | `EnterPlanMode` / `ExitPlanMode` |
| **权限请求** | `request_permissions`（沙箱扩展） | 无独立工具（由用户授权） |
| **工具发现** | `_tool_search` / `_tool_suggest` | 无（固定工具集） |
| **工具注册** | `ToolRegistryBuilder`（编译期 + 运行时） | 固定注册 |
| **动态工具** | `DynamicToolSpec`（数据库持久化） | 无 |

**架构层对比**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Codex CLI                                     │
│                                                                      │
│  Model Output → ToolRouter → ToolRegistry → ToolHandler              │
│                                                    │                 │
│                                              ToolOrchestrator        │
│                                                    │                 │
│                                              ToolRuntime             │
│                                              (沙箱执行)               │
│                                                                      │
│  特点：多层抽象、Builder 注册、沙箱编排、                               │
│        hook 系统、namespace 隔离                                      │
├─────────────────────────────────────────────────────────────────────┤
│                        Claude Code                                   │
│                                                                      │
│  Model Output → tool_use → 固定 handler 映射 → 直接执行               │
│                                                                      │
│  特点：扁平结构、固定工具集、                                           │
│        用户授权替代沙箱编排                                             │
└─────────────────────────────────────────────────────────────────────┘
```

> ⚠️ **注意**：虽然两个系统的工具名称和参数不同，但核心能力高度相似——都支持文件读写、命令执行、代码搜索和多代理协作。主要差异在于抽象层级：Codex 倾向于更底层、更灵活的工具设计（如 `apply_patch` 的 patch 语义），Claude Code 倾向于更直觉、更用户友好的设计（如 `Edit` 的精确替换语义）。Codex 的沙箱编排系统（Orchestrator + Runtime 分层）是 Claude Code 没有的独特设计，它允许工具在沙箱中先尝试执行、失败后升级权限重试。

---

## Reference

- [Codex CLI GitHub 仓库 — tools 目录](https://github.com/openai/codex/tree/main/codex-rs/core/src/tools)
- [OpenAI Function Calling 文档](https://platform.openai.com/docs/guides/function-calling)
- [Model Context Protocol 规范](https://modelcontextprotocol.io/)
- [Codex CLI 官方文档](https://developers.openai.com/codex/cli/)

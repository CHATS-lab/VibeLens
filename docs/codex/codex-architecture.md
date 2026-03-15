# Codex CLI Rust 架构总览

| 条目 | 内容 |
|------|------|
| **主题** | OpenAI Codex CLI 的 Rust 实现架构与 crate 组织 |
| **源码仓库** | [github.com/openai/codex](https://github.com/openai/codex)（Apache-2.0 许可证） |
| **语言** | Rust 2024 edition（workspace resolver 2） |
| **构建系统** | Cargo workspace，70+ crate，`lto = "fat"` Release 优化 |

---

## 1 背景与演进

OpenAI 的 Codex CLI 最初以 TypeScript 实现（`codex-cli/` 目录），运行在 Node.js 之上。随着功能复杂度的增长——特别是沙箱隔离、多代理协作、本地文件搜索等系统级需求——团队将核心重写为 Rust，形成了 `codex-rs/` 目录下的庞大工作区。Rust 重写带来了显著的性能提升、更严格的类型安全，以及通过 Landlock/Seatbelt/seccomp 实现的原生平台沙箱能力。

当前 `codex-rs/` 工作区包含 70+ 个 crate，覆盖从 CLI 入口、协议定义、核心引擎、终端 UI、沙箱实现到 SDK 客户端的完整技术栈。理解这些 crate 的职责划分和依赖关系，是深入阅读 Codex 源码的第一步。

下图展示了从 TypeScript 到 Rust 的演进路径以及架构层次之间的依赖关系：

```
                          Codex CLI 架构演进
  ┌─────────────────────────────────────────────────────────────┐
  │  Phase 1: TypeScript (codex-cli/)                           │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
  │  │ Node.js  │  │  Ink UI  │  │  JSON    │  │ 进程级   │   │
  │  │ 运行时   │  │  (React) │  │  通信    │  │ 隔离     │   │
  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
  └──────────────────────┬──────────────────────────────────────┘
                         │ 重写
                         ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Phase 2: Rust (codex-rs/)                                  │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
  │  │ tokio    │  │ ratatui  │  │ SQ/EQ    │  │ 原生     │   │
  │  │ 异步     │  │ TUI      │  │ 协议     │  │ 沙箱     │   │
  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
  │                                                             │
  │  70+ crate │ LTO 优化 │ 编译期 SQL 检查 │ ts-rs 类型互操作  │
  └─────────────────────────────────────────────────────────────┘
```

---

## 2 工作区结构

Codex 的 Rust 代码组织为一个 Cargo workspace，根配置文件为 `codex-rs/Cargo.toml`。工作区使用 `resolver = "2"`（统一依赖解析），Release 构建启用 `lto = "fat"`、`codegen-units = 1`、`strip = "symbols"` 以获得最小二进制体积和最优性能。

按职责划分，这 70+ 个 crate 可归入以下六大类别：

```
codex-rs/
├── 核心层       cli, core, protocol, config, state, tui, exec
├── 工具层       apply-patch, skills, hooks, mcp-server, rmcp-client
├── 平台层       linux-sandbox, process-hardening, windows-sandbox-rs, network-proxy
├── 连接层       connectors, codex-api, codex-client, app-server
├── 实用层       utils/*, async-utils, file-search, shell-command, ...
└── 辅助层       otel, feedback, login, lmstudio, ollama, ...
```

下图展示了各层之间的依赖方向（箭头指向被依赖方）：

```
┌─────────────────────────────────────────────────────────┐
│                       CLI 入口层                         │
│              cli (codex-cli) / exec (headless)           │
└──────────┬──────────────────────┬────────────────────────┘
           │                      │
           ▼                      ▼
┌─────────────────┐    ┌─────────────────────┐
│  TUI (ratatui)  │    │  App Server (axum)  │
└────────┬────────┘    └─────────┬───────────┘
         │                       │
         ▼                       ▼
┌────────────────────────────────────────────────────────┐
│                     Core (codex-core)                   │
│   Session │ ToolRouter │ RolloutRecorder │ Memories     │
└──────┬───────────┬──────────────┬──────────────────────┘
       │           │              │
       ▼           ▼              ▼
┌────────────┐ ┌──────────┐ ┌──────────────────────────┐
│  Protocol  │ │  Config  │ │  State (SQLite + sqlx)   │
│  (类型定义) │ │ (TOML)   │ │  (持久化层)              │
└──────┬─────┘ └────┬─────┘ └──────────────────────────┘
       │            │
       ▼            ▼
┌──────────────────────────────────────────────────────┐
│                      平台层                           │
│  linux-sandbox │ process-hardening │ windows-sandbox  │
│                │ network-proxy                        │
└──────────────────────────────────────────────────────┘
```

> 📌 **重点**：所有上层 crate 都依赖 `codex-protocol`，它是整个工作区的"类型中枢"。`codex-core` 是唯一同时编排 tools、sandbox、rollout、memories 等子系统的 crate，其他 crate 只通过 SQ/EQ 协议与它交互。

---

## 3 核心 Crate 详解

### 3.1 cli（codex-cli）

CLI crate 是整个系统的二进制入口点。它使用 `clap` 解析命令行参数，初始化日志（`tracing`）、异步运行时（`tokio` full features），然后将控制权交给 `codex-core` 和 `codex-tui`。

**关键依赖**：`codex-core`、`codex-protocol`、`codex-tui`、`codex-config`、`codex-state`、`codex-exec`、`codex-execpolicy`、`codex-mcp-server`、`codex-rmcp-client`、`clap`、`tokio`。

### 3.2 core（codex-core）

Core crate 是整个系统中最大、最核心的 crate，包含 100+ 个模块，承担会话管理、工具编排、rollout 记录、沙箱调度、记忆系统、技能管理、配置加载、项目文档（`AGENTS.md`）发现等核心职责。

**关键模块：**

| 模块 | 职责 |
|------|------|
| `codex` | 主 `Session` 结构体和事件循环，`Codex` 高层接口 |
| `codex_thread` | `CodexThread` 双向消息流包装 |
| `thread_manager` | `ThreadManager` 多线程/代理管理 |
| `tools` | `ToolRouter`、`ToolRegistry`、30+ 工具 handler |
| `rollout` | `RolloutRecorder`、会话持久化 |
| `memories` | 两阶段 ML 记忆流水线 |
| `skills` | `SkillsManager`、技能加载与注入 |
| `project_doc` | `AGENTS.md` 发现与合并 |
| `sandboxing` | 跨平台沙箱调度 |
| `config_loader` | 多层配置加载 |
| `exec` / `exec_env` / `exec_policy` | 命令执行与策略 |
| `mcp` / `mcp_connection_manager` | MCP 协议管理 |
| `api_bridge` | API 桥接 |
| `auth` | 认证 |
| `web_search` | 网络搜索 |
| `agent` | 子代理控制（`AgentControl`、角色、状态、深度守卫） |
| `models_manager` | 模型管理 |

以下是 `core/src/lib.rs` 中的模块注册结构，可以看到 clippy lint 策略和 re-export 的设计——库代码禁止直接输出到 stdout/stderr，所有用户可见内容必须经过 TUI 或 tracing 抽象层：

```rust
// codex-rs/core/src/lib.rs（节选）

// 禁止库代码直接写入 stdout/stderr
#![deny(clippy::print_stdout, clippy::print_stderr)]

mod analytics_client;
pub mod api_bridge;
mod apply_patch;
pub mod codex;               // Codex + Session 主结构体
mod codex_thread;
pub use codex_thread::CodexThread;
mod agent;
mod codex_delegate;
pub mod config;
pub mod config_loader;
mod context_manager;
pub mod error;
pub mod exec;
pub mod exec_env;
mod exec_policy;
mod memories;
pub mod mcp;
mod mcp_connection_manager;
pub mod models_manager;
mod rollout;
pub use rollout::RolloutRecorder;
pub use rollout::SessionMeta;
pub mod sandboxing;
pub mod skills;
mod tools;
mod thread_manager;
pub use thread_manager::ThreadManager;
// ... 共 100+ 模块
```

**核心数据结构**（定义于 `core/src/codex.rs`）：

```rust
// High-level bidirectional interface
pub struct Codex {
    tx_sub: Sender<Submission>,       // Submission Queue (SQ)
    rx_event: Receiver<Event>,        // Event Queue (EQ)
    agent_status: watch::Receiver<AgentStatus>,
    session: Arc<Session>,
    session_loop_termination: SessionLoopTermination,
}

// Internal session state
struct Session {
    conversation_id: ThreadId,
    tx_event: Sender<Event>,
    agent_status: watch::Sender<AgentStatus>,
    state: Mutex<SessionState>,
    features: ManagedFeatures,
    conversation: Arc<RealtimeConversationManager>,
    active_turn: Mutex<Option<ActiveTurn>>,
    services: SessionServices,
    js_repl: Arc<JsReplHandle>,
}
```

`Codex` 结构体采用 **SQ/EQ 模式**（Submission Queue / Event Queue）：外部通过 `tx_sub` 发送 `Submission`（包含 `Op` 操作），`Session` 处理后通过 `tx_event` 发射 `Event` 事件。这种异步消息驱动架构使得 TUI、MCP Server、App Server 等多种前端可以统一接入同一个核心引擎。

**`Codex` 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `tx_sub` | `Sender<Submission>` | Submission Queue 的发送端，容量 512，外部通过此通道向引擎提交操作请求 |
| `rx_event` | `Receiver<Event>` | Event Queue 的接收端，unbounded，引擎产生的所有事件通过此通道推送给前端 |
| `agent_status` | `watch::Receiver<AgentStatus>` | Agent 生命周期状态的观察端，可被多个消费者同时 watch |
| `session` | `Arc<Session>` | 内部 Session 的共享引用，持有全部运行时状态 |
| `session_loop_termination` | `Shared<BoxFuture<'static, ()>>` | 后台 submission 循环的完成信号，多个调用方可共享等待 shutdown |

以下是 `Session` 内部持有的三大状态组件的详细结构：

```rust
// core/src/state/session.rs — 会话级可变状态
pub(crate) struct SessionState {
    pub(crate) session_configuration: SessionConfiguration,
    pub(crate) history: ContextManager,            // 上下文窗口管理
    pub(crate) latest_rate_limits: Option<RateLimitSnapshot>,
    pub(crate) server_reasoning_included: bool,
    pub(crate) dependency_env: HashMap<String, String>,
    previous_turn_settings: Option<PreviousTurnSettings>,
    pub(crate) startup_regular_task: Option<JoinHandle<CodexResult<RegularTask>>>,
    pub(crate) active_connector_selection: HashSet<String>,
    granted_permissions: Option<PermissionProfile>,
}

// core/src/state/turn.rs — Turn 级运行时状态
pub(crate) struct ActiveTurn {
    pub(crate) tasks: IndexMap<String, RunningTask>,
    pub(crate) turn_state: Arc<Mutex<TurnState>>,
}

// core/src/state/service.rs — 会话级服务注册表
pub(crate) struct SessionServices {
    pub(crate) mcp_connection_manager: Arc<RwLock<McpConnectionManager>>,
    pub(crate) unified_exec_manager: UnifiedExecProcessManager,
    pub(crate) hooks: Hooks,
    pub(crate) rollout: Mutex<Option<RolloutRecorder>>,
    pub(crate) user_shell: Arc<Shell>,
    pub(crate) exec_policy: ExecPolicyManager,
    pub(crate) auth_manager: Arc<AuthManager>,
    pub(crate) models_manager: Arc<ModelsManager>,
    pub(crate) skills_manager: Arc<SkillsManager>,
    pub(crate) plugins_manager: Arc<PluginsManager>,
    pub(crate) mcp_manager: Arc<McpManager>,
    pub(crate) agent_control: AgentControl,
    pub(crate) network_proxy: Option<StartedNetworkProxy>,
    pub(crate) network_approval: Arc<NetworkApprovalService>,
    pub(crate) state_db: Option<StateDbHandle>,
    pub(crate) model_client: ModelClient,
    // ... 其他服务
}
```

> 💡 **最佳实践**：`Session` 将状态拆分为三个正交组件——`SessionState`（可变会话数据）、`ActiveTurn`（当前 turn 的临时数据）、`SessionServices`（不可变服务注册表）。这种分离确保了锁的粒度最小化：修改会话历史不需要锁定 tool 服务，处理 approval 回调不需要锁定 rollout recorder。

**Agent 生命周期状态机**——`AgentStatus` 定义了 agent 的完整生命周期：

```rust
// protocol/src/protocol.rs
pub enum AgentStatus {
    PendingInit,              // 等待初始化
    Running,                  // 正在执行 turn
    Completed(Option<String>),// 已完成（附带最终消息）
    Errored(String),          // 遇到错误
    Shutdown,                 // 已关闭
    NotFound,                 // 未找到
}
```

```
    ┌─────────────┐
    │ PendingInit │
    └──────┬──────┘
           │ Codex::spawn() 成功
           ▼
    ┌─────────────┐ ◄──────────────────────┐
    │   Running   │   Op::UserTurn 到达    │
    └──────┬──────┘────────────────────────┘
           │
     ┌─────┼──────────┐
     │     │          │
     ▼     ▼          ▼
┌─────────┐ ┌────────┐ ┌──────────┐
│Completed│ │Errored │ │ Shutdown │
│(msg)    │ │(err)   │ │          │
└─────────┘ └────────┘ └──────────┘
```

| 状态 | 触发条件 | 说明 |
|------|----------|------|
| `PendingInit` | `Codex` 构造时的默认值 | Agent 尚未完成 session 初始化 |
| `Running` | 收到 `Op::UserTurn` 或 `Op::UserInput` | Agent 正在处理用户请求 |
| `Completed(msg)` | Turn 正常完成，无更多待执行操作 | 附带最终 assistant 消息文本 |
| `Errored(err)` | 不可恢复的错误（context window exceeded 等） | 附带错误描述字符串 |
| `Shutdown` | 收到 `Op::Shutdown` 并完成清理 | Agent 已关闭，不再接受请求 |

### 3.3 protocol（codex-protocol）

Protocol crate 定义了系统中所有共享的数据类型，是 core、cli、tui、state 等 crate 的公共依赖基础。它不包含业务逻辑，纯粹是类型定义和序列化/反序列化规则。

**关键模块：**

| 模块 | 核心类型 |
|------|----------|
| `protocol` | `RolloutItem`、`EventMsg`（60+ 变体）、`Op`（20+ 操作）、`Submission`、`SessionMeta`、`TurnContextItem`、`SandboxPolicy`、`AskForApproval`、`SessionSource` |
| `items` | `TurnItem`、`AgentMessageItem`、`ReasoningItem`、`WebSearchItem` |
| `models` | `ResponseItem`（19 变体）、`ContentItem`、`SandboxPermissions`、`BaseInstructions` |
| `config_types` | `CollaborationMode`、`Personality`、`SandboxMode`、`ApprovalsReviewer`、`WindowsSandboxLevel` |
| `approvals` | `GuardianRiskLevel`、`GuardianAssessmentStatus` |
| `permissions` | `FileSystemSandboxPolicy`、`PermissionProfile` |
| `mcp` | MCP 协议类型 |
| `openai_models` | `ModelInfo`、`ReasoningEffort` |

**特殊依赖**：`ts-rs`（自动生成 TypeScript 类型定义）、`schemars`（JSON Schema 生成），确保 Rust 类型与 TypeScript SDK 和 JSON API 的一致性。

#### 3.3.1 Submission 与 Op 详解

`Submission` 是 SQ 中每个条目的结构，它包装了一个 `Op` 操作和关联的 trace context：

```rust
// protocol/src/protocol.rs
pub struct Submission {
    pub id: String,                           // 唯一 ID，用于与 Event 关联
    pub op: Op,                               // 操作载荷
    pub trace: Option<W3cTraceContext>,        // 可选的 W3C trace 传播
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `String` | 提交的唯一标识符，Event 通过此 ID 与对应的 Submission 关联 |
| `op` | `Op` | 具体的操作类型（见下方 Op 枚举） |
| `trace` | `Option<W3cTraceContext>` | 可选的 W3C `traceparent`/`tracestate`，用于跨异步边界的分布式追踪 |

`Op` 枚举定义了所有可能的操作类型。以下是源码中的完整变体列表（按功能分组）：

```rust
// protocol/src/protocol.rs
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Op {
    // ─── 用户输入 ───
    UserInput { items: Vec<UserInput>, final_output_json_schema: Option<Value> },
    UserTurn {
        items: Vec<UserInput>,
        cwd: PathBuf,
        approval_policy: AskForApproval,
        sandbox_policy: SandboxPolicy,
        model: String,
        effort: Option<ReasoningEffortConfig>,
        summary: Option<ReasoningSummaryConfig>,
        service_tier: Option<Option<ServiceTier>>,
        final_output_json_schema: Option<Value>,
        collaboration_mode: Option<CollaborationMode>,
        personality: Option<Personality>,
    },
    OverrideTurnContext { cwd: Option<PathBuf>, approval_policy: Option<AskForApproval>, ... },

    // ─── 流程控制 ───
    Interrupt,                     // 中断当前 turn
    Shutdown,                      // 关闭整个 session
    Compact,                       // 触发上下文压缩
    Undo,                          // 撤销上一轮
    ThreadRollback { num_turns: u32 },

    // ─── 审批与交互 ───
    ExecApproval { id: String, turn_id: Option<String>, decision: ReviewDecision },
    PatchApproval { id: String, decision: ReviewDecision },
    ResolveElicitation { server_name: String, request_id: RequestId, decision: ElicitationAction, ... },
    UserInputAnswer { id: String, response: RequestUserInputResponse },
    RequestPermissionsResponse { id: String, response: RequestPermissionsResponse },
    DynamicToolResponse { id: String, response: DynamicToolResponse },

    // ─── 查询与管理 ───
    ListMcpTools,
    RefreshMcpServers { config: McpServerRefreshConfig },
    ListCustomPrompts,
    ListSkills { cwds: Vec<PathBuf>, force_reload: bool },
    ListModels,
    SetThreadName { name: String },
    Review { review_request: ReviewRequest },
    RunUserShellCommand { command: String },

    // ─── 记忆管理 ───
    DropMemories,
    UpdateMemories,

    // ─── Realtime 语音对话 ───
    RealtimeConversationStart(ConversationStartParams),
    RealtimeConversationAudio(ConversationAudioParams),
    RealtimeConversationText(ConversationTextParams),
    RealtimeConversationClose,
    // ... 其他变体
}
```

**序列化后的 JSON 示例** —— 当 TUI 构造一个 `Op::UserTurn` 提交时，其 JSON 表示如下：

```json
{
  "id": "sub_01HX9K3M2N4P5Q6R7S8T9U0V",
  "op": {
    "type": "user_turn",
    "items": [
      { "type": "text", "text": "请帮我实现一个 HTTP server" }
    ],
    "cwd": "/Users/dev/my-project",
    "approval_policy": "on-request",
    "sandbox_policy": {
      "type": "workspace-write",
      "writable_roots": [],
      "network_access": false
    },
    "model": "o3",
    "effort": "high",
    "summary": "auto",
    "final_output_json_schema": null
  },
  "trace": {
    "traceparent": "00-abcdef1234567890abcdef1234567890-abcdef1234567890-01"
  }
}
```

| 字段 | 说明 |
|------|------|
| `type: "user_turn"` | serde tag 标识 `Op::UserTurn` 变体 |
| `items` | 用户输入数组，支持 text、image、local_image 三种类型 |
| `cwd` | 当前工作目录，sandbox 和工具调用基于此路径解析 |
| `approval_policy` | 命令审批策略，此处为 `on-request`（模型决定何时请求审批） |
| `sandbox_policy.type` | 沙箱策略，`workspace-write` 表示 cwd 可写 |
| `model` | 模型标识符 |
| `effort` | Reasoning effort（仅 reasoning 模型生效） |

#### 3.3.2 Event 与 EventMsg 详解

`Event` 是 EQ 中的每个条目，包含一个 `EventMsg` 载荷和关联的 Submission ID：

```rust
// protocol/src/protocol.rs
pub struct Event {
    pub id: String,       // 关联的 Submission ID
    pub msg: EventMsg,    // 事件载荷
}
```

`EventMsg` 是一个包含 60+ 变体的大型 tagged enum，按功能分为以下几组：

```rust
// protocol/src/protocol.rs（按功能分组展示）
#[serde(tag = "type", rename_all = "snake_case")]
pub enum EventMsg {
    // ─── 错误与警告 ───
    Error(ErrorEvent),
    Warning(WarningEvent),
    StreamError(StreamErrorEvent),
    DeprecationNotice(DeprecationNoticeEvent),

    // ─── Turn 生命周期 ───
    TurnStarted(TurnStartedEvent),          // serde 别名: task_started
    TurnComplete(TurnCompleteEvent),        // serde 别名: task_complete
    TurnAborted(TurnAbortedEvent),
    TokenCount(TokenCountEvent),

    // ─── Agent 消息 ───
    AgentMessage(AgentMessageEvent),
    AgentMessageDelta(AgentMessageDeltaEvent),
    UserMessage(UserMessageEvent),

    // ─── Reasoning ───
    AgentReasoning(AgentReasoningEvent),
    AgentReasoningDelta(AgentReasoningDeltaEvent),
    AgentReasoningRawContent(AgentReasoningRawContentEvent),
    AgentReasoningSectionBreak(AgentReasoningSectionBreakEvent),

    // ─── 会话管理 ───
    SessionConfigured(SessionConfiguredEvent),
    ThreadNameUpdated(ThreadNameUpdatedEvent),
    ContextCompacted(ContextCompactedEvent),
    ThreadRolledBack(ThreadRolledBackEvent),
    ModelReroute(ModelRerouteEvent),

    // ─── 命令执行 ───
    ExecCommandBegin(ExecCommandBeginEvent),
    ExecCommandOutputDelta(ExecCommandOutputDeltaEvent),
    ExecCommandEnd(ExecCommandEndEvent),
    ExecApprovalRequest(ExecApprovalRequestEvent),

    // ─── 补丁应用 ───
    PatchApplyBegin(PatchApplyBeginEvent),
    PatchApplyEnd(PatchApplyEndEvent),
    ApplyPatchApprovalRequest(ApplyPatchApprovalRequestEvent),

    // ─── MCP 与工具 ───
    McpStartupUpdate(McpStartupUpdateEvent),
    McpStartupComplete(McpStartupCompleteEvent),
    McpToolCallBegin(McpToolCallBeginEvent),
    McpToolCallEnd(McpToolCallEndEvent),
    McpListToolsResponse(McpListToolsResponseEvent),
    DynamicToolCallRequest(DynamicToolCallRequest),

    // ─── 协作代理 (Collab) ───
    CollabAgentSpawnBegin(CollabAgentSpawnBeginEvent),
    CollabAgentSpawnEnd(CollabAgentSpawnEndEvent),
    CollabAgentInteractionBegin(CollabAgentInteractionBeginEvent),
    CollabAgentInteractionEnd(CollabAgentInteractionEndEvent),

    // ─── 其他 ───
    WebSearchBegin(WebSearchBeginEvent),
    WebSearchEnd(WebSearchEndEvent),
    ImageGenerationBegin(ImageGenerationBeginEvent),
    ImageGenerationEnd(ImageGenerationEndEvent),
    BackgroundEvent(BackgroundEventEvent),
    ShutdownComplete,
    // ... 共 60+ 变体
}
```

**`SessionConfigured` 事件 JSON 示例** —— Session 初始化完成后发出的第一个 Event：

```json
{
  "id": "",
  "msg": {
    "type": "session_configured",
    "session_id": "t_01HX9K3M2N4P5Q6R7S8T9U0V",
    "thread_name": null,
    "model": "o3",
    "model_provider_id": "openai",
    "service_tier": null,
    "approval_policy": "on-request",
    "approvals_reviewer": "user",
    "sandbox_policy": {
      "type": "workspace-write",
      "network_access": false
    },
    "cwd": "/Users/dev/my-project",
    "reasoning_effort": "high",
    "history_log_id": 12345678,
    "history_entry_count": 0,
    "initial_messages": null,
    "network_proxy": null,
    "rollout_path": "/Users/dev/.codex/sessions/2026/03/15/t_01HX9K3M.jsonl"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | `ThreadId` | 会话唯一标识符 |
| `model` | `String` | 当前使用的模型标识 |
| `model_provider_id` | `String` | 模型提供商 ID（`openai`、`ollama` 等） |
| `approval_policy` | `AskForApproval` | 命令审批策略 |
| `sandbox_policy` | `SandboxPolicy` | 沙箱执行策略 |
| `cwd` | `PathBuf` | 会话工作目录 |
| `reasoning_effort` | `Option<ReasoningEffortConfig>` | Reasoning effort 配置 |
| `history_log_id` | `u64` | 历史日志文件标识（Unix inode） |
| `rollout_path` | `Option<PathBuf>` | Rollout JSONL 文件路径 |

**命令执行事件 JSON 示例** —— 当 agent 请求执行 shell 命令时产生的事件对：

```json
// ExecCommandBegin — 命令开始执行
{
  "id": "sub_turn_01",
  "msg": {
    "type": "exec_command_begin",
    "call_id": "call_abc123",
    "turn_id": "turn_01HX9K",
    "command": ["bash", "-c", "cargo build --release"],
    "cwd": "/Users/dev/my-project",
    "parsed_cmd": [{ "program": "cargo", "args": ["build", "--release"] }],
    "source": "agent"
  }
}

// ExecCommandEnd — 命令执行完成
{
  "id": "sub_turn_01",
  "msg": {
    "type": "exec_command_end",
    "call_id": "call_abc123",
    "turn_id": "turn_01HX9K",
    "command": ["bash", "-c", "cargo build --release"],
    "cwd": "/Users/dev/my-project",
    "parsed_cmd": [{ "program": "cargo", "args": ["build", "--release"] }],
    "source": "agent",
    "stdout": "   Compiling my-project v0.1.0\n    Finished release [optimized] target(s) in 12.34s\n",
    "stderr": "",
    "aggregated_output": "   Compiling my-project v0.1.0\n    Finished release ...",
    "exit_code": 0,
    "duration": { "secs": 12, "nanos": 340000000 },
    "formatted_output": "Exit code: 0\nOutput:\n   Compiling my-project v0.1.0...",
    "status": "completed"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `call_id` | `String` | 工具调用唯一标识，用于配对 Begin/End 事件 |
| `turn_id` | `String` | 所属 turn 的标识符 |
| `command` | `Vec<String>` | 要执行的命令（argv 形式） |
| `cwd` | `PathBuf` | 命令执行的工作目录 |
| `parsed_cmd` | `Vec<ParsedCommand>` | 解析后的命令结构（program + args） |
| `source` | `ExecCommandSource` | 命令来源：`agent`（模型发起）或 `user`（用户 `!cmd` 发起） |
| `exit_code` | `i32` | 进程退出码 |
| `duration` | `Duration` | 命令执行耗时 |
| `status` | `ExecCommandStatus` | 完成状态：`completed`、`failed`、`declined` |

#### 3.3.3 TurnItem 层次结构

`TurnItem` 是 turn 级别的内容单元，用于在前端渲染完整的对话流：

```rust
// protocol/src/items.rs
#[serde(tag = "type")]
pub enum TurnItem {
    UserMessage(UserMessageItem),
    AgentMessage(AgentMessageItem),
    Plan(PlanItem),
    Reasoning(ReasoningItem),
    WebSearch(WebSearchItem),
    ImageGeneration(ImageGenerationItem),
    ContextCompaction(ContextCompactionItem),
}

pub struct AgentMessageItem {
    pub id: String,
    pub content: Vec<AgentMessageContent>,
    pub phase: Option<MessagePhase>,  // 区分 mid-turn 评论和 final answer
}

pub struct ReasoningItem {
    pub id: String,
    pub summary_text: Vec<String>,    // Reasoning 摘要
    pub raw_content: Vec<String>,     // 原始 chain-of-thought
}
```

| 变体 | 说明 |
|------|------|
| `UserMessage` | 用户输入消息（文本、图片） |
| `AgentMessage` | Agent 的文本回复，`phase` 区分中间评论和最终答案 |
| `Plan` | Agent 生成的执行计划 |
| `Reasoning` | Reasoning 模型的思考过程（摘要 + 原始内容） |
| `WebSearch` | 网络搜索操作及结果 |
| `ImageGeneration` | 图片生成操作及结果 |
| `ContextCompaction` | 上下文压缩标记 |

#### 3.3.4 RolloutItem 持久化格式

`RolloutItem` 是写入 JSONL rollout 文件的每一行的类型。它是一个 tagged enum，将所有可持久化的数据统一封装：

```rust
// protocol/src/protocol.rs
#[serde(tag = "type", content = "payload", rename_all = "snake_case")]
pub enum RolloutItem {
    SessionMeta(SessionMetaLine),    // 会话元数据（首行）
    ResponseItem(ResponseItem),      // 模型响应项
    Compacted(CompactedItem),        // 压缩后的上下文摘要
    TurnContext(TurnContextItem),    // Turn 上下文快照
    EventMsg(EventMsg),              // 原始事件消息
}
```

**Rollout JSONL 文件内容示例**（每行一个 `RolloutItem`）：

```jsonl
{"type":"session_meta","payload":{"session_id":"t_01HX9K3M","model":"o3","cwd":"/Users/dev/my-project","sandbox_policy":{"type":"workspace-write"}}}
{"type":"turn_context","payload":{"turn_id":"turn_001","cwd":"/Users/dev/my-project","approval_policy":"on-request","sandbox_policy":{"type":"workspace-write","network_access":false},"model":"o3","summary":"auto"}}
{"type":"event_msg","payload":{"type":"task_started","turn_id":"turn_001","model_context_window":200000,"collaboration_mode_kind":"default"}}
{"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"我来帮你实现一个 HTTP server..."}]}}
{"type":"event_msg","payload":{"type":"task_complete"}}
```

> 📌 **重点**：Rollout 文件的第一行始终是 `SessionMeta`，包含会话的初始配置。后续每个 turn 先写入 `TurnContext`（记录该 turn 的完整上下文快照），再写入 `ResponseItem` 和 `EventMsg`。这种结构使得 session 恢复、fork 和 replay 成为可能。

**TurnContextItem 完整结构**——每个 turn 开始时持久化的上下文快照：

```rust
// protocol/src/protocol.rs
pub struct TurnContextItem {
    pub turn_id: Option<String>,
    pub trace_id: Option<String>,
    pub cwd: PathBuf,
    pub current_date: Option<String>,
    pub timezone: Option<String>,
    pub approval_policy: AskForApproval,
    pub sandbox_policy: SandboxPolicy,
    pub network: Option<TurnContextNetworkItem>,
    pub model: String,
    pub personality: Option<Personality>,
    pub collaboration_mode: Option<CollaborationMode>,
    pub realtime_active: Option<bool>,
    pub effort: Option<ReasoningEffortConfig>,
    pub summary: ReasoningSummaryConfig,
    pub user_instructions: Option<String>,
    pub developer_instructions: Option<String>,
    pub final_output_json_schema: Option<Value>,
    pub truncation_policy: Option<TruncationPolicy>,
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `turn_id` | `Option<String>` | Turn 唯一标识符 |
| `trace_id` | `Option<String>` | OpenTelemetry trace ID |
| `cwd` | `PathBuf` | 该 turn 的工作目录 |
| `approval_policy` | `AskForApproval` | 审批策略 |
| `sandbox_policy` | `SandboxPolicy` | 沙箱策略 |
| `network` | `Option<TurnContextNetworkItem>` | 网络访问域名白/黑名单 |
| `model` | `String` | 使用的模型 |
| `effort` | `Option<ReasoningEffortConfig>` | Reasoning effort |
| `user_instructions` | `Option<String>` | 用户指令（AGENTS.md 内容） |
| `truncation_policy` | `Option<TruncationPolicy>` | 上下文截断策略 |

#### 3.3.5 SandboxPolicy 详解

`SandboxPolicy` 枚举定义了四种沙箱执行策略，控制 agent 执行 shell 命令时的隔离级别：

```rust
// protocol/src/protocol.rs
#[serde(tag = "type", rename_all = "kebab-case")]
pub enum SandboxPolicy {
    /// 无任何限制，慎用
    DangerFullAccess,

    /// 只读访问
    ReadOnly {
        access: ReadOnlyAccess,      // FullAccess 或 Restricted
        network_access: bool,
    },

    /// 外部沙箱（进程已在容器/VM 中运行）
    ExternalSandbox {
        network_access: NetworkAccess,
    },

    /// cwd 可写 + 额外可写路径
    WorkspaceWrite {
        writable_roots: Vec<AbsolutePathBuf>,
        read_only_access: ReadOnlyAccess,
        network_access: bool,
        exclude_tmpdir_env_var: bool,
        exclude_slash_tmp: bool,
    },
}
```

**四种策略的对比：**

| 策略 | 文件读取 | 文件写入 | 网络访问 | 典型场景 |
|------|----------|----------|----------|----------|
| `DangerFullAccess` | 全部 | 全部 | 全部 | 开发测试，非生产环境 |
| `ReadOnly` | 配置化 | 禁止 | 可选 | 代码审查、只读分析 |
| `ExternalSandbox` | 全部 | 全部 | 可选 | Docker/VM 内运行 |
| `WorkspaceWrite` | 配置化 | cwd + 指定路径 | 可选 | **默认策略**，日常开发 |

**不同场景下的 SandboxPolicy JSON 配置示例：**

```json
// 场景 1: 日常开发 — workspace-write（默认）
{
  "type": "workspace-write",
  "writable_roots": [],
  "network_access": false
}

// 场景 2: 需要网络访问的开发（如安装依赖）
{
  "type": "workspace-write",
  "writable_roots": ["/Users/dev/.npm", "/Users/dev/.cargo"],
  "network_access": true
}

// 场景 3: CI/CD 只读代码审查
{
  "type": "read-only",
  "network_access": false
}

// 场景 4: Docker 容器内运行
{
  "type": "external-sandbox",
  "network_access": "enabled"
}
```

> ⚠️ **注意**：`DangerFullAccess` 策略完全绕过沙箱，agent 执行的命令拥有与用户进程相同的权限。仅在受信环境（如隔离的 CI runner）中使用此策略。

#### 3.3.6 AskForApproval 审批策略

`AskForApproval` 控制何时需要用户审批 agent 提出的命令执行请求：

```rust
// protocol/src/protocol.rs
#[serde(rename_all = "kebab-case")]
pub enum AskForApproval {
    /// 仅 "已知安全" 的只读命令自动放行，其余都需审批
    UnlessTrusted,

    /// [已弃用] 命令在沙箱中失败时才询问用户
    OnFailure,

    /// 模型决定何时请求用户审批（默认）
    #[default]
    OnRequest,

    /// 细粒度控制各类审批流程
    Granular(GranularApprovalConfig),

    /// 从不询问用户（适用于非交互式模式）
    Never,
}

pub struct GranularApprovalConfig {
    pub sandbox_approval: bool,     // 是否允许沙箱命令审批提示
    pub rules: bool,                // 是否允许 execpolicy 规则触发的审批
    pub skill_approval: bool,       // 是否允许技能脚本执行审批
    pub request_permissions: bool,  // 是否允许权限请求工具审批
    pub mcp_elicitations: bool,     // 是否允许 MCP elicitation 审批
}
```

**审批请求事件 JSON 示例：**

```json
{
  "id": "sub_turn_01",
  "msg": {
    "type": "exec_approval_request",
    "call_id": "call_def456",
    "turn_id": "turn_01HX9K",
    "command": ["bash", "-c", "rm -rf ./build/"],
    "cwd": "/Users/dev/my-project",
    "reason": null,
    "proposed_execpolicy_amendment": {
      "command_pattern": "rm -rf ./build/",
      "action": "allow"
    },
    "parsed_cmd": [{ "program": "rm", "args": ["-rf", "./build/"] }],
    "available_decisions": ["approved", "approved_with_amendment", "rejected"]
  }
}
```

### 3.4 config（codex-config）

Config crate 处理 TOML 配置文件的解析、多层合并和约束验证。

**配置层级**（从低到高优先级）：系统级 `/etc/codex/config.toml` → 用户级 `~/.codex/config.toml` → 项目级 `.codex/config.toml` → 托管配置（MDM）→ CLI 覆盖。

**关键组件**：
- `merge_toml_values()` — 递归合并 TOML 表，高层覆盖低层
- `Constrained<T>` — 带验证器和归一化器的受约束值，用于强制执行组织策略
- `ConfigLayerStack` — 按优先级排列的配置层栈

**依赖**：`toml`、`toml_edit`、`codex-protocol`、`codex-execpolicy`。

#### 3.4.1 Constrained<T> 类型系统

`Constrained<T>` 是 Codex 配置系统中的核心类型，它将值与验证逻辑绑定在一起，确保组织策略能够在运行时强制执行：

```rust
// config/src/constraint.rs
pub struct Constrained<T> {
    value: T,
    validator: Arc<dyn Fn(&T) -> ConstraintResult<()> + Send + Sync>,
    normalizer: Option<Arc<dyn Fn(T) -> T + Send + Sync>>,
}

impl<T: Send + Sync> Constrained<T> {
    /// 创建带验证器的受约束值
    pub fn new(
        initial_value: T,
        validator: impl Fn(&T) -> ConstraintResult<()> + Send + Sync + 'static,
    ) -> ConstraintResult<Self> { ... }

    /// 创建带归一化器的受约束值（自动转换为合规值）
    pub fn normalized(
        initial_value: T,
        normalizer: impl Fn(T) -> T + Send + Sync + 'static,
    ) -> ConstraintResult<Self> { ... }

    /// 创建允许任意值的约束（无验证）
    pub fn allow_any(initial_value: T) -> Self { ... }

    /// 创建仅允许单一值的约束（锁定值）
    pub fn allow_only(only_value: T) -> Self { ... }
}

// 通过 Deref 透明访问内部值
impl<T> std::ops::Deref for Constrained<T> {
    type Target = T;
    fn deref(&self) -> &T { &self.value }
}
```

| 方法 | 说明 | 使用场景 |
|------|------|----------|
| `Constrained::new(val, validator)` | 创建时即验证，后续 `set` 时也验证 | 企业策略限制模型列表 |
| `Constrained::normalized(val, normalizer)` | 自动归一化为合规值 | 强制小写、路径规范化 |
| `Constrained::allow_any(val)` | 无限制 | 用户级配置项 |
| `Constrained::allow_only(val)` | 锁定为固定值，任何 `set` 都被拒绝 | MDM 强制策略 |

#### 3.4.2 ConfigLayerStack 多层合并

配置层栈按优先级从低到高排列，高层覆盖低层。每层都有明确的来源标识：

```rust
// config/src/state.rs
pub struct ConfigLayerStack {
    /// 层列表按 lowest-precedence-first 排列
    layers: Vec<ConfigLayerEntry>,
    /// 用户配置层的索引位置
    user_layer_index: Option<usize>,
    /// 从 requirements.toml / MDM 加载的约束规则
    requirements: ConfigRequirements,
    requirements_toml: ConfigRequirementsToml,
}
```

```
配置层合并顺序（低 → 高优先级）：

┌──────────────────────────────┐
│  5. CLI 覆盖（SessionFlags） │  ← 最高优先级
├──────────────────────────────┤
│  4. MDM 托管配置             │
├──────────────────────────────┤
│  3. 项目级 .codex/config.toml│
├──────────────────────────────┤
│  2. 用户级 ~/.codex/config.toml│
├──────────────────────────────┤
│  1. 系统级 /etc/codex/config.toml│  ← 最低优先级
└──────────────────────────────┘
```

#### 3.4.3 Config 结构体核心字段

合并后的最终配置由 `Config` 结构体承载，以下是其关键字段（源码定义于 `core/src/config/mod.rs`，共 50+ 字段）：

```rust
// core/src/config/mod.rs（节选）
pub struct Config {
    pub config_layer_stack: ConfigLayerStack,
    pub startup_warnings: Vec<String>,

    // ─── 模型相关 ───
    pub model: Option<String>,
    pub service_tier: Option<ServiceTier>,
    pub review_model: Option<String>,
    pub model_context_window: Option<i64>,
    pub model_auto_compact_token_limit: Option<i64>,
    pub model_provider_id: String,
    pub model_provider: ModelProviderInfo,
    pub personality: Option<Personality>,

    // ─── 权限与审批 ───
    pub permissions: Permissions,
    pub approvals_reviewer: ApprovalsReviewer,
    pub enforce_residency: Constrained<Option<ResidencyRequirement>>,

    // ─── 指令系统 ───
    pub user_instructions: Option<String>,     // AGENTS.md 内容
    pub base_instructions: Option<String>,     // 基础指令覆盖
    pub developer_instructions: Option<String>,// 开发者指令
    pub compact_prompt: Option<String>,

    // ─── TUI 配置 ───
    pub animations: bool,
    pub show_tooltips: bool,
    pub tui_alternate_screen: AltScreenMode,
    pub tui_theme: Option<String>,

    // ─── 运行时 ───
    pub cwd: PathBuf,                          // 会话工作目录
    pub commit_attribution: Option<String>,     // Git commit 署名
    pub notify: Option<Vec<String>>,           // 外部通知命令
    // ... 50+ 字段
}
```

**配置文件示例**（`~/.codex/config.toml`）：

```toml
# 模型配置
model = "o3"
model_provider = "openai"

# 审批策略
[permissions]
approval_policy = "on-request"

# TUI 配置
[tui]
alternate_screen = "auto"
theme = "monokai"
animations = true
show_tooltips = true

# 通知
notify = ["notify-send", "Codex"]

# Git commit 署名
commit_attribution = "Codex <noreply@openai.com>"
```

### 3.5 state（codex-state）

State crate 管理 SQLite 持久化层，使用 `sqlx` 库的编译期查询检查确保 SQL 类型安全。

**核心职责**：线程元数据持久化（`threads` 表）、记忆阶段输出（`stage1_outputs`）、后台任务队列（`jobs`）、批量 Agent 任务（`agent_jobs` / `agent_job_items`）、动态工具注册（`thread_dynamic_tools`）、数据回填（`backfill_state`）、日志存储（`logs`）。

Schema 由 19 个增量迁移文件（`0001` 至 `0019`）构建。详细 schema 见 `CODEX_LOCAL_STRUCTURE.md` 第 5 节。

### 3.6 tui（codex-tui）

TUI crate 实现终端用户界面，基于 `ratatui`（自定义补丁版本）和 `crossterm` 构建。

**功能特性**：
- 语法高亮：`syntect` + `two-face`
- 图片渲染：支持 JPEG、PNG、GIF、WebP
- 语音输入：可选 `voice-input` feature（`cpal` + `hound` 音频库）
- Markdown 渲染：富文本终端输出

### 3.7 exec（codex-exec）

Exec crate 提供非交互式（headless）执行模式，适用于 CI/CD 场景和脚本集成。它封装 `codex-core`，提供简化的命令行接口和 TypeScript schema 输出。

---

## 4 工具与集成 Crate

掌握了核心层的架构之后，下一步是了解围绕核心引擎构建的工具与集成层。这些 crate 扩展了 Codex 的能力边界——从代码编辑、技能系统到 MCP 协议支持。

### 4.1 apply-patch（codex-apply-patch）

实现结构化代码补丁应用。与简单的文本替换不同，`apply-patch` 使用 Tree-sitter 解析和自定义 Lark 语法，支持精确的代码位置定位和多文件批量修改。

### 4.2 skills（codex-skills）

技能系统的分发层。使用 `include_dir` 宏在编译时嵌入系统技能文件，运行时安装到 `~/.codex/skills/.system/`。通过指纹（fingerprint）机制实现版本化缓存，避免重复解压。

**内置系统技能**：`skill-creator`（创建新技能的引导）、`skill-installer`（从 GitHub 安装技能）、`openai-docs`（OpenAI 文档参考）。

### 4.3 hooks（codex-hooks）

会话生命周期钩子系统，允许用户在特定事件（如工具调用前后）触发自定义 shell 命令。

### 4.4 mcp-server（codex-mcp-server）

MCP（Model Context Protocol）服务器实现，使 Codex 可以作为 MCP 工具提供者，供其他 AI 应用调用。基于 `rmcp` 库的 server features。

### 4.5 rmcp-client（codex-rmcp-client）

MCP 客户端实现，使 Codex 可以调用外部 MCP 工具。支持 OAuth2 认证（`oauth2` 库）和平台密钥链存储（`keyring` 库），完整的传输层支持（stdio、HTTP SSE、WebSocket）。

### 4.6 connectors（codex-connectors）

外部服务连接器，抽象不同模型提供者的 API 差异。

### 4.7 file-search（codex-file-search）

基于 `nucleo`（来自 Helix 编辑器的模糊匹配引擎）的文件搜索系统。使用 `ignore` 库实现 gitignore-aware 的目录遍历，`crossbeam-channel` 实现多线程并行搜索。

---

## 5 平台 Crate

Codex 的一大技术亮点是其跨平台沙箱系统。每个目标平台都有独立的 crate 实现隔离机制，由 core 层的 `SandboxManager` 统一调度。

```
                    SandboxPolicy（协议层定义）
                            │
                            ▼
                ┌───────────────────────┐
                │   SandboxManager      │
                │   (core 层统一调度)    │
                └───┬───────┬───────┬───┘
                    │       │       │
         ┌──────────┘       │       └──────────┐
         ▼                  ▼                  ▼
┌─────────────────┐ ┌──────────────┐ ┌─────────────────┐
│ linux-sandbox   │ │ process-     │ │ windows-sandbox │
│                 │ │ hardening    │ │                 │
│ Bubblewrap      │ │ Seatbelt     │ │ Restricted      │
│ + Landlock LSM  │ │ (.sbpl)      │ │ Token + ACL     │
│ + seccomp       │ │ default-deny │ │ + Firewall      │
└────────┬────────┘ └──────┬───────┘ └────────┬────────┘
         │                 │                   │
         ▼                 ▼                   ▼
┌────────────────────────────────────────────────────────┐
│              network-proxy (rama)                       │
│     HTTP/HTTPS/SOCKS 流量拦截与域名级访问控制            │
└────────────────────────────────────────────────────────┘
```

### 5.1 linux-sandbox（codex-linux-sandbox）

Linux 平台沙箱，结合 Bubblewrap（文件系统隔离）+ Landlock LSM（内核级文件访问控制）+ seccomp（系统调用过滤）。支持传统 Landlock-only 模式作为 fallback。

**依赖**：`landlock`、`seccompiler`、`libc`。

### 5.2 process-hardening（codex-process-hardening）

macOS 平台沙箱，基于 Seatbelt（`.sbpl` 配置文件）。通过 `/usr/bin/sandbox-exec` 启动受限进程，使用 `default-deny` 策略，动态生成网络和文件系统访问规则。

### 5.3 windows-sandbox-rs（codex-windows-sandbox）

Windows 平台沙箱，采用两层架构：
- **受限令牌模式**（Restricted Token）：文件系统 ACL、令牌降权
- **提升模式**（Elevated）：两阶段协调，隔离用户创建

**安全特性**：`token.rs`（令牌操作）、`firewall.rs`（Windows 防火墙网络策略）、`sandbox_users.rs`（隔离用户）、`audit.rs`（安全审计日志）。

**依赖**：`windows` crate（Win32 API）、`windows-sys`。

### 5.4 network-proxy（codex-network-proxy）

基于 `rama`（HTTP/TCP/SOCKS5 代理框架）的网络流量代理。拦截并管控沙箱内进程的网络访问，支持 HTTP/HTTPS/SOCKS 协议和 globset 模式匹配。

---

## 6 实用 Crate

工作区中有大量小型实用 crate，每个专注于单一职责。以下以表格形式概述：

| Crate | 包名 | 职责 |
|-------|------|------|
| `utils/absolute-path` | — | 绝对路径处理 |
| `utils/cache` | — | 通用缓存工具 |
| `utils/git` | — | Git 操作（commit SHA、branch、origin URL） |
| `utils/pty` | — | 伪终端处理 |
| `utils/string` | — | 字符串工具 |
| `utils/cli` | — | CLI 辅助工具 |
| `utils/elapsed` | — | 耗时格式化 |
| `utils/image` | — | 图片处理工具 |
| `async-utils` | — | 异步工具（channel、timeout 等） |
| `shell-command` | `codex-shell-command` | Shell 命令封装 |
| `ansi-escape` | — | ANSI 转义码处理 |
| `arg0` | — | 进程 argv[0] 管理 |
| `artifacts` | — | 制品管理 |
| `package-manager` | — | 包管理器检测 |
| `otel` | — | OpenTelemetry 遥测集成 |
| `feedback` | — | 用户反馈与分析 |
| `login` | — | OAuth/设备授权/API 密钥认证 |
| `lmstudio` | — | LM Studio 本地模型连接 |
| `ollama` | — | Ollama 本地模型连接 |
| `secrets` | — | 密钥管理 |
| `keyring-store` | — | 系统密钥链存储 |
| `stdio-to-uds` | — | stdio 到 Unix 域套接字转换 |
| `stream-parser` | — | 流式解析器 |

---

## 7 SDK 与服务器 Crate

为了支持不同的集成场景（Web 应用、IDE 插件、programmatic API），Codex 提供了一组 SDK 和服务器 crate。

| Crate | 包名 | 职责 |
|-------|------|------|
| `codex-api` | `codex-api` | 公共 API 层，WebSocket + SSE 传输 |
| `codex-client` | `codex-client` | HTTP 客户端库（`reqwest`、`rustls`） |
| `app-server` | `codex-app-server` | Web 服务器接口（`axum`、WebSocket） |
| `app-server-client` | — | App Server 客户端 |
| `app-server-protocol` | — | App Server 通信协议 |
| `app-server-test-client` | — | App Server 测试客户端 |
| `backend-client` | — | 后端客户端 |
| `debug-client` | — | 调试客户端 |
| `responses-api-proxy` | — | Responses API 代理 |

---

## 8 数据流与通信模型

在理解了各 crate 的职责之后，下面梳理一个典型用户交互的数据流，展示这些组件如何协同工作：

```
用户输入
    │
    ▼
┌──────────┐    Submission (Op::UserTurn)    ┌──────────────┐
│   TUI    │ ──────────────────────────────▶ │   Protocol   │
│ (ratatui)│                                 │  (SQ → EQ)   │
└──────────┘                                 └──────┬───────┘
    ▲                                               │
    │ Event (EventMsg::AgentMessage, etc.)           ▼
    │                                        ┌──────────────┐
    └─────────────────────────────────────── │     Core     │
                                             │  (Session)   │
                                             └──────┬───────┘
                                                    │
                            ┌───────────────────────┼───────────────────────┐
                            │                       │                       │
                            ▼                       ▼                       ▼
                    ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
                    │    Tools     │        │   Memories   │        │   Rollout    │
                    │  (Registry)  │        │  (2-Phase)   │        │  (Recorder)  │
                    └──────┬───────┘        └──────────────┘        └──────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
      ┌────────────┐ ┌──────────┐ ┌──────────────┐
      │  Sandbox   │ │   MCP    │ │  Sub-Agent   │
      │ (Platform) │ │ (Client) │ │  (Collab)    │
      └────────────┘ └──────────┘ └──────────────┘
```

**流程概要**：

1. 用户在 TUI 输入消息，TUI 构造 `Submission`（包含 `Op::UserTurn`）发送到 Submission Queue
2. Core 的 `Session` 接收 `Submission`，构建 `TurnContext`，调用模型 API
3. 模型返回的工具调用通过 `ToolRegistry` 分发到对应的 handler
4. Handler 执行（可能经过 `SandboxManager` 沙箱化），结果写回模型上下文
5. 整个对话过程由 `RolloutRecorder` 实时记录到 JSONL 文件
6. 会话结束后，`Memories` 模块异步提取记忆
7. 所有事件通过 Event Queue 推送回 TUI 渲染

> 📌 **重点**：SQ/EQ 模式的设计使得多种前端（TUI、MCP Server、App Server、Exec 模式）可以共享同一个 Core 引擎，只需实现不同的 `Submission` 发送端和 `Event` 接收端。

### 8.1 Agentic Loop 详细流程

以下是 Codex 核心的 agentic loop（代理循环）的详细状态机。每个 turn 中，Session 在"调用模型 → 处理工具调用 → 再次调用模型"之间循环，直到模型不再产生工具调用为止：

```
                          ┌──────────────────────────────┐
                          │      Submission 到达          │
                          │   (Op::UserTurn / UserInput) │
                          └──────────────┬───────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────┐
                          │  1. 构建 TurnContext          │
                          │  - 解析 cwd, model, sandbox  │
                          │  - 加载 user_instructions    │
                          │  - 构建 tool_specs           │
                          └──────────────┬───────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────┐
                          │  2. 发射 TurnStarted 事件     │
                          │  - 持久化 TurnContextItem    │
                          └──────────────┬───────────────┘
                                         │
                                         ▼
                    ┌────────────────────────────────────────┐
                    │  3. 调用模型 API（Responses API）       │
                    │  - 发送 conversation history           │
                    │  - 附加 tool definitions               │
                    │  - 流式接收 ResponseItem               │
                    └────────────────┬───────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────────────┐
                    │  4. 处理 ResponseItem 流               │
                    │                                        │
                    │  ┌───────────────────────────────────┐ │
                    │  │ Message?  → 发射 AgentMessage     │ │
                    │  │ Reasoning? → 发射 AgentReasoning  │ │
                    │  │ ToolCall?  → 进入步骤 5           │ │
                    │  │ EndTurn?   → 进入步骤 7           │ │
                    │  └───────────────────────────────────┘ │
                    └────────────────┬───────────────────────┘
                                     │ ToolCall
                                     ▼
                    ┌────────────────────────────────────────┐
                    │  5. ToolRouter 分发工具调用             │
                    │                                        │
                    │  ┌───────────────────────────────────┐ │
                    │  │ local_shell → SandboxManager      │ │
                    │  │ apply_patch → ApplyPatch           │ │
                    │  │ mcp_*      → McpConnectionManager │ │
                    │  │ collab_*   → AgentControl          │ │
                    │  └───────────────────────────────────┘ │
                    └────────────────┬───────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────────────┐
                    │  6. 需要审批？                          │
                    │                                        │
                    │  是 → 发射 ExecApprovalRequest          │
                    │       等待 Op::ExecApproval 回复        │
                    │       ┌─ Approved → 执行命令            │
                    │       └─ Rejected → 返回拒绝给模型      │
                    │                                        │
                    │  否 → 直接在沙箱中执行                   │
                    └────────────────┬───────────────────────┘
                                     │
                                     │ 工具结果写回 context
                                     │ 返回步骤 3（再次调用模型）
                                     │
                                     ▼
                    ┌────────────────────────────────────────┐
                    │  7. Turn 完成                           │
                    │  - 发射 TurnComplete 事件               │
                    │  - 持久化 ResponseItem 到 rollout       │
                    │  - 更新 TokenUsage 统计                 │
                    │  - 触发 hooks (stop event)              │
                    │  - 异步提取 memories                    │
                    └────────────────────────────────────────┘
```

> 💡 **最佳实践**：理解 agentic loop 的关键在于步骤 3-6 之间的循环——模型可能在一个 turn 中发起多次工具调用（如先搜索文件、再编辑代码、最后运行测试），每次工具调用的结果都会追加到 conversation history 中，供模型在下一次 API 调用时参考。这种 multi-step 工具调用是 Codex 实现复杂代码编辑任务的核心机制。

### 8.2 工具调用路由架构

`ToolRouter` 和 `ToolRegistry` 共同构成了工具分发系统。`ToolRouter` 持有可见的 tool spec 列表（发送给模型），`ToolRegistry` 持有实际的 handler 映射：

```rust
// core/src/tools/router.rs
pub struct ToolRouter {
    registry: ToolRegistry,
    specs: Vec<ConfiguredToolSpec>,        // 完整工具规格
    model_visible_specs: Vec<ToolSpec>,    // 发送给模型的工具定义
}

// core/src/tools/registry.rs
pub struct ToolRegistry {
    handlers: HashMap<String, Arc<dyn AnyToolHandler>>,
}

impl ToolRegistry {
    /// 根据工具名和可选命名空间分发调用
    pub(crate) async fn dispatch_any(
        &self,
        invocation: ToolInvocation,
    ) -> Result<AnyToolResult, FunctionCallError> { ... }
}
```

```
模型返回 ToolCall
       │
       ▼
┌──────────────┐
│  ToolRouter  │
│  .dispatch() │
└──────┬───────┘
       │ 查找 handler key = "{namespace}:{tool_name}"
       ▼
┌──────────────┐      ┌───────────────────────────────────────┐
│ ToolRegistry │ ───▶ │ HashMap<String, Arc<dyn AnyToolHandler>>│
│ .dispatch_any│      │                                       │
└──────────────┘      │ "local_shell"    → ShellToolHandler   │
                      │ "apply_patch"    → PatchToolHandler   │
                      │ "view_image"     → ImageToolHandler   │
                      │ "file_search"    → SearchToolHandler  │
                      │ "web_search"     → WebSearchHandler   │
                      │ "mcp:server:tool"→ McpToolHandler     │
                      │ "collab:spawn"   → CollabSpawnHandler │
                      │ "request_user_*" → UserInputHandler   │
                      └───────────────────────────────────────┘
```

### 8.3 场景示例：用户提交工具调用的完整消息流

以下场景描述了用户请求"帮我创建一个 hello.py 文件"时，从 TUI 到 sandbox 执行的完整消息流：

```
 用户                TUI              Codex::tx_sub         Session           ToolRouter         Sandbox
  │                  │                     │                   │                  │                 │
  │  "创建 hello.py" │                     │                   │                  │                 │
  │ ────────────────▶│                     │                   │                  │                 │
  │                  │ Op::UserTurn        │                   │                  │                 │
  │                  │ {items: [Text(...)],│                   │                  │                 │
  │                  │  model: "o3",       │                   │                  │                 │
  │                  │  sandbox: WkspWrite}│                   │                  │                 │
  │                  │ ───────────────────▶│                   │                  │                 │
  │                  │                     │ TurnStarted       │                  │                 │
  │                  │ ◀─ ─ ─ ─ ─ ─ ─ ─ ─ ┤                   │                  │                 │
  │                  │                     │ Responses API call│                  │                 │
  │                  │                     │ ─────────────────▶│                  │                 │
  │                  │                     │                   │ (模型返回         │                 │
  │                  │                     │                   │  ToolCall:        │                 │
  │                  │                     │                   │  local_shell)     │                 │
  │                  │                     │                   │ ─────────────────▶│                 │
  │                  │                     │                   │                  │  approval_policy│
  │                  │                     │                   │                  │  == OnRequest   │
  │                  │ ExecApprovalRequest │                   │                  │  模型决定: 安全  │
  │                  │ ◀─ ─ ─ ─ ─ ─ ─ ─ ─ ┤                   │                  │ (auto-approve)  │
  │  [Y] Approve     │                     │                   │                  │                 │
  │ ────────────────▶│                     │                   │                  │                 │
  │                  │ Op::ExecApproval    │                   │                  │                 │
  │                  │ {decision: Approved}│                   │                  │                 │
  │                  │ ───────────────────▶│                   │                  │                 │
  │                  │                     │                   │                  │ SandboxManager  │
  │                  │                     │                   │                  │ .run_sandboxed()│
  │                  │                     │                   │                  │ ───────────────▶│
  │                  │ ExecCommandBegin    │                   │                  │                 │
  │                  │ ◀─ ─ ─ ─ ─ ─ ─ ─ ─ ┤                   │                  │ Seatbelt exec  │
  │                  │                     │                   │                  │ cat > hello.py  │
  │                  │ ExecCommandEnd      │                   │                  │ ◀───────────────│
  │                  │ {exit_code: 0}      │                   │                  │                 │
  │                  │ ◀─ ─ ─ ─ ─ ─ ─ ─ ─ ┤                   │                  │                 │
  │                  │                     │ (工具结果写回 ctx) │                  │                 │
  │                  │                     │ ─────────────────▶│ (再次调用模型)     │                 │
  │                  │                     │                   │                  │                 │
  │                  │ AgentMessage        │                   │                  │                 │
  │                  │ "已创建 hello.py"    │                   │                  │                 │
  │                  │ ◀─ ─ ─ ─ ─ ─ ─ ─ ─ ┤                   │                  │                 │
  │                  │ TurnComplete        │                   │                  │                 │
  │                  │ ◀─ ─ ─ ─ ─ ─ ─ ─ ─ ┤                   │                  │                 │
  │  "已创建 hello.py│"                    │                   │                  │                 │
  │ ◀────────────────│                     │                   │                  │                 │
```

> ⚠️ **注意**：上图中的审批流程取决于 `approval_policy` 的配置。当设置为 `Never`（如 CI/CD 场景下的 `codex-exec`），审批步骤会被跳过，命令直接在沙箱中执行。当设置为 `UnlessTrusted`，只有被 `is_safe_command()` 判定为安全的只读命令才会自动放行。

### 8.4 Token 使用量追踪

每个 turn 完成后，Session 会发射 `TokenCount` 事件，报告本次 turn 和累计的 token 使用量：

```rust
// protocol/src/protocol.rs
pub struct TokenUsage {
    pub input_tokens: i64,
    pub cached_input_tokens: i64,
    pub output_tokens: i64,
    pub reasoning_output_tokens: i64,
    pub total_tokens: i64,
}

pub struct TokenUsageInfo {
    pub total_token_usage: TokenUsage,   // 会话累计
    pub last_token_usage: TokenUsage,    // 本次 turn
    pub model_context_window: Option<i64>,
}
```

**TokenCount 事件 JSON 示例：**

```json
{
  "id": "sub_turn_01",
  "msg": {
    "type": "token_count",
    "token_usage": {
      "total_token_usage": {
        "input_tokens": 15230,
        "cached_input_tokens": 8000,
        "output_tokens": 2450,
        "reasoning_output_tokens": 1200,
        "total_tokens": 17680
      },
      "last_token_usage": {
        "input_tokens": 5230,
        "cached_input_tokens": 3000,
        "output_tokens": 850,
        "reasoning_output_tokens": 400,
        "total_tokens": 6080
      },
      "model_context_window": 200000
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `input_tokens` | 发送给模型的 token 总数 |
| `cached_input_tokens` | 其中命中 prompt cache 的 token 数（计费优化） |
| `output_tokens` | 模型生成的 token 总数 |
| `reasoning_output_tokens` | 其中用于 reasoning 的 token 数 |
| `total_tokens` | 总 token 消耗（input + output） |
| `model_context_window` | 模型的最大上下文窗口大小 |

> 💡 **最佳实践**：当 `total_token_usage.total_tokens` 接近 `model_context_window` 时，Codex 会自动触发 context compaction（上下文压缩），通过 `Op::Compact` 将历史对话摘要化，释放 token 空间以继续对话。阈值由 `Config.model_auto_compact_token_limit` 控制。

---

## 9 构建配置与优化

Codex 的 Release 构建采用激进的优化策略：

```toml
[profile.release]
lto = "fat"                # 全链接时优化
split-debuginfo = "off"    # 不拆分调试信息
strip = "symbols"          # 移除符号表
codegen-units = 1          # 单代码生成单元（最佳 LTO 效果）
```

这些配置牺牲了编译速度，换取最小的二进制体积和最优的运行时性能——对于分发给终端用户的 CLI 工具来说，这是合理的权衡。

---

## 10 与 Claude Code 架构的对比

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **实现语言** | Rust（2024 edition） | TypeScript / Node.js |
| **crate/包数量** | 70+ Rust crate | 单一 npm 包 |
| **异步运行时** | tokio（full features） | Node.js 事件循环 |
| **TUI 框架** | ratatui + crossterm | Ink（React for CLI） |
| **序列化** | serde + ts-rs（自动 TS 类型生成） | 原生 JSON |
| **数据库** | SQLite（sqlx 编译期检查） | 纯文件系统 |
| **沙箱** | 平台原生（Seatbelt/Landlock/seccomp/Win32） | 进程级隔离 |
| **API 格式** | OpenAI Responses API | Anthropic Messages API |
| **编译优化** | LTO、strip symbols | N/A（解释型语言） |
| **通信模型** | SQ/EQ（Submission Queue / Event Queue） | 直接函数调用 |

> 💡 **最佳实践**：Codex 的 Rust 重写展示了"性能敏感型 CLI 工具应使用系统级语言"的工程决策。TypeScript 原型适合快速迭代，但当需要平台级沙箱、高性能 TUI 和精细的内存控制时，Rust 是更合适的选择。Claude Code 目前保持 TypeScript 实现，依靠 Node.js 生态的丰富性和快速迭代能力。

---

## Reference

- [Codex CLI GitHub 仓库](https://github.com/openai/codex)
- [Codex CLI 官方文档](https://developers.openai.com/codex/cli/)
- [Cargo Workspace 文档](https://doc.rust-lang.org/cargo/reference/workspaces.html)
- [ratatui TUI 框架](https://ratatui.rs/)
- [tokio 异步运行时](https://tokio.rs/)
- [sqlx Rust SQL 工具包](https://github.com/launchbadge/sqlx)

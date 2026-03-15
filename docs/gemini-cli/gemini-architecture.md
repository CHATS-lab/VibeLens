# Gemini CLI 架构全景

| 条目 | 内容 |
|------|------|
| **主题** | Gemini CLI 源码架构深度解析 |
| **版本** | v0.35.0-nightly (2026-03-13) |
| **仓库** | `github.com/google-gemini/gemini-cli` |
| **技术栈** | TypeScript + Node.js 20+ / React (Ink) / ESM modules |
| **构建** | esbuild + npm workspaces (monorepo) |
| **协议** | Apache-2.0 |
| **分析日期** | 2026-03-14 |

---

## 1 Monorepo 整体布局

Gemini CLI 采用 **npm workspaces** 管理的 monorepo 架构，根目录 `package.json` 声明 `"workspaces": ["packages/*"]`，包含 7 个子包：

```
gemini-cli/
├── packages/
│   ├── core/          # 核心引擎：agent loop、tool 调度、prompt 组装、telemetry
│   ├── cli/           # 终端 UI：React/Ink 渲染、slash commands、交互式/非交互式入口
│   ├── sdk/           # 外部扩展 SDK：供第三方注册 agent/tool/skill
│   ├── a2a-server/    # Agent-to-Agent 服务器：基于 A2A 协议的 HTTP 网关
│   ├── devtools/      # 开发者工具：WebSocket + React 实时调试面板
│   ├── vscode-ide-companion/  # VS Code 扩展：IDE diff 预览、MCP 桥接
│   └── test-utils/    # 测试工具：共享 mock、node-pty 集成测试辅助
├── evals/             # 评估套件
├── integration-tests/ # 端到端集成测试
├── schemas/           # JSON Schema 定义
├── scripts/           # 构建/发布/代码生成脚本
└── docs/              # 官方文档
```

### 各包职责

| 包名 | npm 名 | 核心职责 | 主要依赖 |
|------|--------|---------|---------|
| **core** | `@google/gemini-cli-core` | Agent loop、ContentGenerator、Tool Registry、Policy Engine、Hook System、Telemetry | `@google/genai`, `@modelcontextprotocol/sdk`, `zod`, OpenTelemetry 全家桶 |
| **cli** | `@google/gemini-cli` | 终端入口 (`gemini` 命令)、React/Ink UI、slash command 框架、settings 加载 | `@google/gemini-cli-core`, `ink`, `react`, `yargs`, `chalk` |
| **sdk** | `@google/gemini-cli-sdk` | 供扩展作者使用的公共 API：注册 agent/tool/skill/session | `@google/gemini-cli-core`, `zod`, `zod-to-json-schema` |
| **a2a-server** | `@google/gemini-cli-a2a-server` | Agent-to-Agent HTTP 服务器，暴露 Gemini CLI 能力为远程 agent | `@a2a-js/sdk`, `express`, `@google/gemini-cli-core` |
| **devtools** | `@google/gemini-cli-devtools` | WebSocket 调试面板，实时展示 agent 思维链与 tool 调用 | `ws`, `react`, `react-dom` |
| **vscode-ide-companion** | `gemini-cli-vscode-ide-companion` | VS Code 扩展：MCP server、diff 编辑器、workspace context 桥接 | `@modelcontextprotocol/sdk`, `express`, `zod` |
| **test-utils** | `@google/gemini-cli-test-utils` (private) | 共享测试基础设施 | `@google/gemini-cli-core`, `vitest`, `node-pty` |

> 📌 所有子包共享同一版本号 (`0.35.0-nightly.20260313.bb060d7a9`)，通过根目录 `scripts/version.js` 统一管理。

---

## 2 Core 包内部架构

`packages/core/src/` 是整个系统的心脏，包含超过 30 个子目录。以下按功能域分组解析：

### 2.1 核心引擎 (`core/`)

| 文件 | 职责 |
|------|------|
| `client.ts` | **GeminiClient** — 顶层 agent loop 控制器，管理 chat session 生命周期、history compression、loop detection、model routing |
| `geminiChat.ts` | **GeminiChat** — 封装 Gemini API 的 chat session，处理 streaming、retry with backoff、mid-stream error recovery、thought signature 管理 |
| `contentGenerator.ts` | **ContentGenerator** interface + 工厂函数 — 抽象 LLM 调用层，支持 API Key / OAuth / Vertex AI / Gateway 等多种认证方式 |
| `coreToolScheduler.ts` | **CoreToolScheduler** — tool 执行调度器，管理 tool call 的完整生命周期：Validating → Scheduled → Executing → Success/Error/Cancelled |
| `turn.ts` | **Turn** — 单轮对话管理，将 streaming chunks 解析为 typed events (Content/Thought/ToolCallRequest/Error/Finished 等) |
| `loggingContentGenerator.ts` | **LoggingContentGenerator** — ContentGenerator 装饰器，添加 telemetry 日志 |
| `recordingContentGenerator.ts` | **RecordingContentGenerator** — 录制 API 响应，用于测试 replay |
| `baseLlmClient.ts` | **BaseLlmClient** — 轻量 LLM 客户端，用于辅助任务 (如 next-speaker check) |
| `prompts.ts` | System prompt 入口，委托给 `PromptProvider` |
| `tokenLimits.ts` | 各模型的 token limit 映射 |

### 2.2 Agent 系统 (`agents/`)

支持 **Local Agent** 和 **Remote Agent** 两种模式：

| 文件 | 职责 |
|------|------|
| `types.ts` | `AgentDefinition`、`LocalAgentDefinition`、`RemoteAgentDefinition` 类型定义 |
| `agentLoader.ts` | 从 `.gemini/agents/` 目录加载 agent 定义 (YAML/JSON) |
| `local-executor.ts` | **LocalAgentExecutor** — 本地 agent 执行引擎：独立 GeminiChat + ToolRegistry + ReAct loop |
| `local-invocation.ts` | 本地 agent 调用封装 |
| `remote-invocation.ts` | 远程 agent 调用 (通过 A2A 协议) |
| `agent-scheduler.ts` | Agent tool call 调度 |
| `subagent-tool.ts` | 将 agent 包装为 tool，供主 agent 调用 |
| `registry.ts` | Agent 注册表 |
| 内置 agents | `codebase-investigator.ts` (代码库探索)、`cli-help-agent.ts` (CLI 帮助)、`generalist-agent.ts` (通用) |

> 💡 Local Agent 拥有完全独立的 ReAct loop：自己的 `GeminiChat` 实例、独立的 `ToolRegistry`、独立的 system prompt。通过 `complete_task` tool 终止执行并返回结果给父 agent。

### 2.3 配置系统 (`config/`)

| 文件 | 职责 |
|------|------|
| `config.ts` | **Config** 类 — 全局运行时配置中心 (~800+ 行)，注册所有 tool、初始化 content generator、管理 auth 状态 |
| `agent-loop-context.ts` | **AgentLoopContext** interface — 每个 agent turn 的执行上下文，包含 `Config`、`ToolRegistry`、`MessageBus`、`GeminiClient`、`SandboxManager` |
| `models.ts` | 模型名称常量与解析逻辑 (auto model routing) |
| `defaultModelConfigs.ts` | 各模型的默认 GenerateContentConfig |
| `memory.ts` | GEMINI.md 记忆文件加载 |
| `storage.ts` | 持久化存储管理 |
| `constants.ts` | 全局常量 |

### 2.4 工具系统 (`tools/`)

内置工具集合，每个 tool 都是 `BaseDeclarativeTool` 的子类：

| 工具 | 文件 | 功能 |
|------|------|------|
| `ReadFile` | `read-file.ts` | 读取单个文件 |
| `ReadManyFiles` | `read-many-files.ts` | 批量读取多个文件 |
| `WriteFile` | `write-file.ts` | 写入文件 |
| `Edit` | `edit.ts` | 精确编辑 (old_string → new_string 替换) |
| `Shell` | `shell.ts` | 执行 shell 命令 (支持 sandbox) |
| `Glob` | `glob.ts` | 文件模式匹配搜索 |
| `Grep` / `RipGrep` | `grep.ts` / `ripGrep.ts` | 内容搜索 (优先使用 ripgrep) |
| `Ls` | `ls.ts` | 目录列表 |
| `WebSearch` | `web-search.ts` | 网页搜索 |
| `WebFetch` | `web-fetch.ts` | 获取网页内容 |
| `Memory` | `memoryTool.ts` | 读写 GEMINI.md 记忆文件 |
| `WriteTodos` | `write-todos.ts` | 创建 TODO 清单 |
| `ActivateSkill` | `activate-skill.ts` | 激活 skill |
| `AskUser` | `ask-user.ts` | 向用户提问 |
| `EnterPlanMode` / `ExitPlanMode` | `enter-plan-mode.ts` / `exit-plan-mode.ts` | 计划模式切换 |
| MCP Tools | `mcp-tool.ts` / `mcp-client.ts` | 动态发现的 MCP 外部工具 |
| Tracker Tools | `trackerTools.ts` | 任务跟踪 (create/update/get task) |

核心抽象：

- `tools.ts` — `BaseDeclarativeTool`、`BaseToolInvocation` 基类；`Kind` 枚举区分 tool 类别
- `tool-registry.ts` — **ToolRegistry** 管理所有已注册 tool，生成 `FunctionDeclaration` 数组
- `tool-names.ts` — 所有 tool name 和 parameter name 常量
- `tool-error.ts` — Tool 错误类型枚举

### 2.5 调度器 (`scheduler/`)

| 文件 | 职责 |
|------|------|
| `scheduler.ts` | **Scheduler** — 新版调度器 (与 `CoreToolScheduler` 并存)，支持 confirmation bus 集成 |
| `types.ts` | Tool call 状态机类型：`Validating` → `Scheduled` → `Executing` → `Success/Error/Cancelled` |
| `tool-executor.ts` | **ToolExecutor** — 实际执行 tool invocation |
| `tool-modifier.ts` | Tool 修改处理：支持外部编辑器修改 tool 参数 |
| `confirmation.ts` | Confirmation 决策逻辑 |
| `policy.ts` | 调度层的 policy 检查 |
| `state-manager.ts` | 调度器状态管理 |

### 2.6 Hook 系统 (`hooks/`)

Gemini CLI 的 Hook 系统支持在 agent 生命周期的关键节点插入自定义逻辑：

| 文件 | 职责 |
|------|------|
| `hookSystem.ts` | **HookSystem** — Hook 系统入口，触发各类 hook event |
| `hookRegistry.ts` | **HookRegistry** — 注册和管理 hook 定义 |
| `hookRunner.ts` | **HookRunner** — 执行 hook (支持 command 和 runtime 两种类型) |
| `hookEventHandler.ts` | Hook event 分发逻辑 |
| `hookAggregator.ts` | 聚合多个 hook 的输出 |
| `hookPlanner.ts` | Hook 执行计划 |
| `hookTranslator.ts` | Hook I/O 格式转换 |
| `trustedHooks.ts` | 受信任 hook 验证 |
| `types.ts` | Hook 类型定义 |

支持的 Hook Event：

```
SessionStart / SessionEnd
BeforeAgent / AfterAgent
BeforeTool / AfterTool
BeforeModel / AfterModel
BeforeToolSelection
Notification
PreCompress
```

配置来源优先级：`Runtime > Project > User > System > Extensions`

### 2.7 Policy 引擎 (`policy/`)

| 文件 | 职责 |
|------|------|
| `policy-engine.ts` | **PolicyEngine** — 核心决策引擎，对每个 tool call 返回 `ALLOW` / `DENY` / `ASK_USER` |
| `toml-loader.ts` | 从 `.gemini/policies/` 加载 TOML 策略文件 |
| `config.ts` | Policy 配置类型 |
| `types.ts` | `PolicyDecision` 枚举、`ApprovalMode` (default/autoEdit/yolo/plan) |
| `integrity.ts` | 策略文件完整性验证 |

Policy Engine 支持三种决策模式：
- **ALLOW** — 自动执行，无需用户确认
- **DENY** — 拒绝执行，返回错误
- **ASK_USER** — 等待用户确认

### 2.8 Prompt 系统 (`prompts/`)

| 文件 | 职责 |
|------|------|
| `promptProvider.ts` | **PromptProvider** — 组装完整 system prompt，注入 tool 描述、memory、approval mode 上下文 |
| `snippets.ts` | 现代 prompt 片段 (针对 Gemini 2.5+ 模型) |
| `snippets.legacy.ts` | 旧版 prompt 片段 (兼容 Gemini 2.0 模型) |
| `prompt-registry.ts` | Prompt 注册表 (MCP prompt 支持) |
| `mcp-prompts.ts` | MCP prompt 集成 |
| `utils.ts` | Prompt 模板变量替换、section 开关 |

### 2.9 模型路由 (`routing/`)

| 文件 | 职责 |
|------|------|
| `routingStrategy.ts` | **RoutingStrategy** / **TerminalStrategy** interface 定义 |
| `modelRouterService.ts` | **ModelRouterService** — 路由服务，串联多个 strategy |

内置路由策略 (`strategies/`)：

| Strategy | 功能 |
|----------|------|
| `overrideStrategy` | 用户手动指定模型时的覆盖策略 |
| `approvalModeStrategy` | 基于 approval mode 选择模型 |
| `classifierStrategy` | LLM 分类器路由 |
| `gemmaClassifierStrategy` | Gemma 本地分类器路由 |
| `numericalClassifierStrategy` | 数值分类器路由 |
| `fallbackStrategy` | 降级策略 |
| `defaultStrategy` | 默认模型选择 |
| `compositeStrategy` | 组合策略链 |

### 2.10 安全子系统 (`safety/`)

| 文件 | 职责 |
|------|------|
| `protocol.ts` | Safety check 协议定义 |
| `built-in.ts` | 内置安全检查器 |
| `checker-runner.ts` | Safety checker 执行器 |
| `registry.ts` | Safety checker 注册表 |
| `context-builder.ts` | Safety 上下文构建 |
| `conseca/` | CONSECA (CONtext-based SECurity Analysis) 子模块 |

### 2.11 服务层 (`services/`)

| 服务 | 功能 |
|------|------|
| `chatCompressionService.ts` | Chat history 压缩 (当 token 接近上限时) |
| `chatRecordingService.ts` | 会话录制 (记录所有消息、tool call、token 使用) |
| `loopDetectionService.ts` | Agent loop 检测 (防止无限循环) |
| `shellExecutionService.ts` | Shell 命令执行 (支持 PTY、sandbox) |
| `sandboxManager.ts` | Docker/Podman 沙箱管理 |
| `modelConfigService.ts` | 模型配置服务 (GenerateContentConfig 解析) |
| `contextManager.ts` | JIT (Just-In-Time) 上下文管理 |
| `fileDiscoveryService.ts` | 文件发现 |
| `gitService.ts` | Git 操作封装 |
| `toolOutputMaskingService.ts` | Tool 输出脱敏 (防止 token 膨胀) |
| `sessionSummaryService.ts` | Session 摘要生成 |
| `trackerService.ts` | 任务跟踪服务 |
| `keychainService.ts` | 密钥链管理 |

### 2.12 遥测 (`telemetry/`)

基于 **OpenTelemetry** 的完整遥测栈：

| 文件 | 功能 |
|------|------|
| `index.ts` | 遥测初始化 |
| `loggers.ts` | 结构化日志记录器 (26000+ 行测试覆盖) |
| `metrics.ts` | 指标收集 (prompt/response tokens、latency、tool call duration) |
| `semantic.ts` | 语义遥测 |
| `sdk.ts` | 遥测 SDK 封装 |
| `trace.ts` | 分布式追踪 |
| `types.ts` | 遥测事件类型 (71000+ 行) |
| `billingEvents.ts` | 计费事件 |
| `startupProfiler.ts` | 启动性能分析 |
| `uiTelemetry.ts` | UI 遥测 |
| `activity-monitor.ts` | 活动监控 |
| `memory-monitor.ts` | 内存监控 |

支持的导出目标：GCP Cloud Monitoring、Cloud Trace、OTLP (gRPC/HTTP)、文件导出。

### 2.13 其他子系统

| 目录 | 功能 |
|------|------|
| `mcp/` | MCP (Model Context Protocol) 集成：OAuth provider、token storage |
| `ide/` | IDE 集成：detect-ide、IDE client、workspace context |
| `skills/` | Skill 系统：`SkillManager` 发现和管理 skills |
| `commands/` | Slash command 核心逻辑 (extensions, restore, init, memory) |
| `confirmation-bus/` | 用户确认消息总线 (`MessageBus`) |
| `fallback/` | 模型降级处理 (persistent 429 → fallback model) |
| `billing/` | 用量计费管理 |
| `output/` | JSON 输出格式化 (非交互式模式) |
| `voice/` | 语音响应格式化 |
| `resources/` | MCP resource 注册 |
| `availability/` | 模型可用性策略 |
| `code_assist/` | Google Code Assist 集成 (OAuth、admin controls) |
| `utils/` | 160+ 工具文件：retry、error handling、git、file、token estimation 等 |

---

## 3 数据流：从用户输入到响应渲染

### 3.1 启动流程

```
gemini.tsx::main()
  │
  ├── loadSettings()              # 加载 settings.json (user/workspace/system)
  ├── parseArguments()            # 解析 CLI 参数
  ├── loadCliConfig()             # 创建 Config 对象
  ├── refreshAuth()               # 认证 (OAuth/API Key/Vertex AI)
  ├── loadSandboxConfig()         # 沙箱配置
  │   └── start_sandbox()         # 如果启用，进入 Docker 沙箱子进程
  ├── initializeApp()             # 初始化 app (tool registry, agents, MCP clients)
  │
  ├── [interactive?]
  │   └── startInteractiveUI()    # React/Ink 渲染
  │       └── App.tsx → AppContainer.tsx
  │
  └── [non-interactive?]
      └── runNonInteractive()     # 直接处理 prompt 并输出
```

### 3.2 交互式主循环

```
用户输入 (Ink TextInput)
  │
  ├── Slash Command 检测 (/help, /model, /memory, /clear, /bug, ...)
  │   └── 直接执行对应 command handler
  │
  └── 普通消息
      │
      ├── Hook: SessionStart (首次)
      ├── Hook: BeforeAgent
      │
      ├── System Prompt 组装 (PromptProvider)
      │   ├── Core rules + safety guidelines
      │   ├── Tool descriptions
      │   ├── GEMINI.md memory content
      │   ├── Approval mode context
      │   ├── IDE context (if VS Code companion connected)
      │   └── Skill descriptions
      │
      ├── Model Routing (ModelRouterService)
      │   └── CompositeStrategy → [Override → Classifier → Default]
      │
      ├── GeminiClient.sendMessageStream()
      │   ├── Context window overflow check
      │   ├── Chat compression (if needed)
      │   ├── Loop detection
      │   ├── Turn.run() → GeminiChat.sendMessageStream()
      │   │   ├── Hook: BeforeModel
      │   │   ├── Hook: BeforeToolSelection
      │   │   ├── ContentGenerator.generateContentStream()
      │   │   │   └── Gemini API call (with retry + backoff)
      │   │   ├── Stream processing (chunks → events)
      │   │   ├── Hook: AfterModel
      │   │   └── Yield: Content / Thought / ToolCallRequest / Error / Finished
      │   │
      │   ├── [if ToolCallRequest]
      │   │   ├── CoreToolScheduler.schedule()
      │   │   │   ├── ToolRegistry.getTool()
      │   │   │   ├── tool.build(args) → ToolInvocation
      │   │   │   ├── PolicyEngine.check() → ALLOW/DENY/ASK_USER
      │   │   │   ├── Hook: BeforeTool
      │   │   │   ├── [if ASK_USER] → 渲染确认 UI → 等待用户
      │   │   │   ├── ToolExecutor.execute()
      │   │   │   ├── Hook: AfterTool
      │   │   │   └── Return function_response
      │   │   │
      │   │   └── 将 tool results 作为新 user message 送回 → 下一轮 Turn
      │   │
      │   ├── [if no pending tools + next-speaker check]
      │   │   └── BaseLlmClient check → "model" → auto-continue
      │   │
      │   └── Hook: AfterAgent
      │
      └── UI 渲染 (React/Ink)
          ├── Markdown 渲染 (lowlight 高亮)
          ├── Thought bubble 展示
          ├── Tool call 进度条
          ├── Diff 预览 (edit/write-file)
          └── Token 使用量显示
```

### 3.3 非交互式流程

```
gemini --prompt "..."  (或 stdin pipe)
  │
  └── runNonInteractive()
      ├── Config.initialize()
      ├── GeminiClient.sendMessageStream()
      │   └── (同上 agentic loop)
      └── JSON/text 格式输出到 stdout
```

---

## 4 Agentic ReAct Loop 深度解析

Gemini CLI 的核心是一个 **ReAct (Reasoning + Acting) 循环**，由以下组件协作完成：

### 4.1 循环架构

```
GeminiClient (client.ts)
  │  管理完整 session 生命周期
  │  负责 loop detection、chat compression、model routing
  │
  ├── GeminiChat (geminiChat.ts)
  │     管理 API 通信
  │     维护 conversation history
  │     处理 streaming + retry
  │     记录 chat recording
  │
  ├── Turn (turn.ts)
  │     单轮对话：解析 stream → typed events
  │     收集 pending tool calls
  │
  ├── ContentGenerator (contentGenerator.ts)
  │     抽象 LLM API 调用
  │     支持多种 auth backend
  │     LoggingContentGenerator 装饰器添加遥测
  │
  └── CoreToolScheduler (coreToolScheduler.ts)
        Tool call 生命周期管理
        状态机: Validating → Scheduled → Executing → Terminal
        Policy check + user confirmation
        Sequential execution (一次一个 tool)
```

### 4.2 状态机

每个 Tool Call 经历以下状态转换：

```
                    ┌──────────────┐
                    │  Validating  │  ← tool.build(args) + policy check
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
         ┌────▼────┐  ┌───▼────┐  ┌───▼───┐
         │  Error  │  │Scheduled│  │ Await │  ← PolicyDecision.ASK_USER
         └─────────┘  └───┬────┘  │Approval│
                           │      └───┬────┘
                           │          │ user confirms
                           │    ┌─────▼──────┐
                           │    │  Scheduled  │
                           │    └─────┬───────┘
                           │          │
                      ┌────▼──────────▼─┐
                      │    Executing    │  ← ToolExecutor.execute()
                      └────┬───────┬───┘
                           │       │
                    ┌──────▼─┐  ┌──▼──────┐
                    │Success │  │  Error   │
                    └────────┘  └─────────┘
```

### 4.3 ReAct 循环的终止条件

| 条件 | 触发机制 |
|------|---------|
| 模型返回纯文本 (无 function call) | 自然终止，yield `Finished` event |
| `MAX_TURNS` (100) 达到 | 强制终止 |
| `MaxSessionTurns` (用户配置) | 强制终止 |
| Loop detected | `LoopDetectionService` 检测到重复模式 → 中断或尝试恢复 |
| Context window overflow | Token 预算耗尽 |
| User abort (Ctrl+C) | `AbortSignal` 传播 |
| Hook 阻断 | `BeforeAgent` / `AfterAgent` hook 返回 stop 指令 |
| 错误 | API 错误 / 认证失败 / 网络中断 |
| Next-speaker check → "user" | `BaseLlmClient` 判断下一个应该说话的是用户 |

### 4.4 Chat Compression

当 prompt token count 接近模型的 token limit 时，`ChatCompressionService` 会：

1. 使用 Gemini Flash 模型对历史对话进行摘要压缩
2. 用压缩后的 summary 替换原始 history
3. 如果压缩失败 (token 反而增加)，回退到 content truncation
4. 在 `toolOutputMaskingService` 中将长 tool output 替换为占位符

---

## 5 关键入口点与连接关系

### 5.1 包间依赖图

```
                        ┌──────────┐
                        │   cli    │  ← 终端入口
                        └─────┬────┘
                              │ depends on
                        ┌─────▼────┐
                   ┌────│   core   │────┐
                   │    └─────┬────┘    │
                   │          │         │
            ┌──────▼──┐  ┌───▼──┐  ┌───▼────────┐
            │   sdk   │  │  a2a │  │  devtools   │
            └─────────┘  └──────┘  └─────────────┘

            ┌──────────────────────┐
            │  vscode-companion    │  (独立, 通过 MCP 协议通信)
            └──────────────────────┘

            ┌──────────────────────┐
            │    test-utils        │  (开发依赖)
            └──────────────────────┘
```

### 5.2 CLI 入口到 Core 的连接

```typescript
// packages/cli/src/gemini.tsx — main()
const config = await loadCliConfig(settings, sessionId, argv);
const initResult = await initializeApp(config, settings);

// Interactive mode:
await startInteractiveUI(config, settings, startupWarnings, ...);
  // → interactiveCli.ts → AppContainer.tsx (React)
  //   内部创建 GeminiClient, CoreToolScheduler
  //   用户输入 → GeminiClient.sendMessageStream()

// Non-interactive mode:
await runNonInteractive({ config, settings, input, prompt_id });
  // → 直接调用 GeminiClient
```

### 5.3 SDK 入口

```typescript
// packages/sdk/src/index.ts
export * from './agent.js';    // 注册自定义 agent
export * from './session.js';  // session 管理
export * from './tool.js';     // 注册自定义 tool
export * from './skills.js';   // 注册 skill
export * from './types.js';    // 类型定义
```

### 5.4 A2A Server 入口

```typescript
// packages/a2a-server/src/
├── http/server.ts      // Express HTTP 服务器
├── agent/              // Agent task 执行
├── commands/           // 命令处理
├── config/             // 服务器配置
├── persistence/        // 状态持久化
└── utils/              // 工具函数
```

A2A Server 基于 Google 的 **Agent-to-Agent (A2A) 协议**，将 Gemini CLI 的 agent 能力通过 HTTP API 暴露，允许远程 agent 调用。

---

## 6 与 Claude Code 架构对比

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **语言** | TypeScript (Node.js) | TypeScript (Node.js) |
| **UI 框架** | React + Ink (terminal React renderer) | React + Ink (terminal React renderer) |
| **包管理** | npm workspaces monorepo (7 packages) | 单包架构 |
| **LLM API** | `@google/genai` SDK (Gemini API / Vertex AI) | Anthropic SDK (Claude API) |
| **Agent Loop** | `GeminiClient` → `Turn` → `GeminiChat` (多层封装) | 较扁平的 agentic loop |
| **Tool 调度** | `CoreToolScheduler` / `Scheduler` (状态机驱动, 单工具串行) | Tool execution pipeline |
| **Tool 注册** | `ToolRegistry` + `BaseDeclarativeTool` 继承体系 | Tool 定义 + registry |
| **内置工具** | ReadFile, WriteFile, Edit, Shell, Glob, Grep/RipGrep, WebSearch, WebFetch, Memory, AskUser, WriteTodos, ActivateSkill, PlanMode tools, Tracker tools | Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, TodoWrite, Notebook |
| **Sub-Agent** | Local Agent (独立 loop) + Remote Agent (A2A 协议) | Agent tool (内联调用) |
| **Model Routing** | `ModelRouterService` + 多策略组合 (Override/Classifier/Gemma/Fallback) | 单模型 (可配置) |
| **Policy** | TOML-based `PolicyEngine` (ALLOW/DENY/ASK_USER) | Permission system |
| **Hook 系统** | 完整生命周期 hook (Session/Agent/Tool/Model 级别, command + runtime 两种实现) | 无对应 hook 系统 |
| **安全** | Safety checker registry + CONSECA + Policy Engine + Sandbox (Docker/Podman) | Permission-based 安全模型 |
| **MCP 支持** | 完整 MCP client + OAuth provider + resource/prompt registry | MCP client 集成 |
| **IDE 集成** | VS Code extension (`vscode-ide-companion`) 通过 MCP 桥接 | 内置 VS Code 上下文 |
| **A2A 协议** | 内置 A2A server package | 无 |
| **Telemetry** | OpenTelemetry 全栈 (metrics/traces/logs) + GCP 导出器 | 内置遥测 |
| **Memory** | `GEMINI.md` 分层记忆 (user/project/workspace) | `CLAUDE.md` |
| **Context Window** | 自动 compression + tool output masking + content truncation | Context management |
| **Approval Mode** | default / autoEdit / yolo / plan | Auto-accept / confirm |
| **Session 管理** | `ChatRecordingService` 持久化 + `--resume` 恢复 | 会话持久化 |
| **Sandbox** | Docker / Podman 沙箱 (可选) | 无独立沙箱 |
| **Devtools** | WebSocket 实时调试面板 (`@google/gemini-cli-devtools`) | 无 |
| **扩展 SDK** | `@google/gemini-cli-sdk` (agent/tool/skill/session 注册) | Extension 系统 |

> ⚠️ Gemini CLI 的架构显著比 Claude Code 更加模块化和分层。其 monorepo 包含 7 个独立包，核心包内有 30+ 子目录。这种分层带来了更强的可扩展性 (SDK, A2A, hooks)，但也增加了理解和维护的复杂度。Claude Code 采用相对扁平的单包架构，更加紧凑。

---

## 7 关键设计模式

### 7.1 Decorator Pattern

`ContentGenerator` 接口通过装饰器链增强：

```
GoogleGenAI.models (原始 SDK)
  └── LoggingContentGenerator (添加 telemetry)
      └── RecordingContentGenerator (录制 API 响应, 可选)
```

### 7.2 Strategy Pattern

Model routing 使用策略模式：

```
CompositeStrategy
  ├── OverrideStrategy      (用户手动指定)
  ├── ApprovalModeStrategy  (基于 approval mode)
  ├── ClassifierStrategy    (LLM 分类器)
  └── DefaultStrategy       (终端策略, 保底)
```

### 7.3 Observer Pattern

`CoreEvent` 事件总线 (`coreEvents`) 解耦核心逻辑与 UI 层：

```
CoreEvent.Output / ConsoleLog / UserFeedback / ModelChanged / RetryAttempt
```

`MessageBus` 用于 tool confirmation 的异步通信：

```
ToolConfirmationRequest → [用户决策] → ToolConfirmationResponse
```

### 7.4 State Machine

Tool call 生命周期通过显式状态机管理 (`CoreToolCallStatus`)：

```typescript
enum CoreToolCallStatus {
  Validating,
  Scheduled,
  Executing,
  AwaitingApproval,
  Success,
  Error,
  Cancelled,
}
```

### 7.5 Abstract Factory

`createContentGenerator()` 根据 `AuthType` 创建不同的 content generator 实例：

```
AuthType.LOGIN_WITH_GOOGLE  → CodeAssistContentGenerator (OAuth)
AuthType.USE_GEMINI         → GoogleGenAI.models (API Key)
AuthType.USE_VERTEX_AI      → GoogleGenAI.models (Vertex AI)
AuthType.COMPUTE_ADC        → CodeAssistContentGenerator (ADC)
```

---

## 8 扩展性入口点

| 扩展方式 | 机制 | 配置位置 |
|---------|------|---------|
| **自定义 Tool** | SDK `tool.ts` / MCP server | `settings.json` mcpServers / extensions |
| **自定义 Agent** | YAML 定义 + SDK `agent.ts` | `.gemini/agents/` 目录 |
| **自定义 Skill** | Skill YAML 定义 + SDK | `.gemini/skills/` 目录 |
| **Hook** | command 或 runtime hook | `.gemini/settings.json` hooks 配置 |
| **Policy** | TOML 策略文件 | `.gemini/policies/` 目录 |
| **MCP Server** | Model Context Protocol | `settings.json` mcpServers |
| **Memory** | GEMINI.md | `~/.gemini/GEMINI.md` + `.gemini/GEMINI.md` |
| **VS Code 集成** | IDE Companion 扩展 | VS Code 扩展市场安装 |
| **远程 Agent** | A2A 协议 | agent 定义中的 `agentCardUrl` |

---

## 9 Gemini API 请求/响应数据结构

Gemini CLI 与 Gemini API 之间的通信遵循 `@google/genai` SDK 定义的 `GenerateContentParameters` 结构。理解这些数据结构对于调试 API 交互、编写 Hook 或开发 extension 至关重要。

### 9.1 API 请求结构 (GenerateContentParameters)

当 `GeminiChat.sendMessageStream()` 发起一次 API 调用时，最终传递给 `ContentGenerator.generateContentStream()` 的参数如下：

```json
{
  "model": "gemini-2.5-pro",
  "contents": [
    {
      "role": "user",
      "parts": [
        { "text": "请帮我重构 src/utils/retry.ts 中的 retryWithBackoff 函数" }
      ]
    },
    {
      "role": "model",
      "parts": [
        { "thought": true, "text": "**分析重构需求**\n用户希望重构 retry 逻辑..." },
        { "text": "我来查看一下这个文件的内容。" },
        {
          "functionCall": {
            "name": "ReadFile",
            "args": { "path": "src/utils/retry.ts" }
          },
          "thoughtSignature": "skip_thought_signature_validator"
        }
      ]
    },
    {
      "role": "user",
      "parts": [
        {
          "functionResponse": {
            "id": "ReadFile_1710000000_0",
            "name": "ReadFile",
            "response": {
              "content": "export async function retryWithBackoff<T>(...) { ... }"
            }
          }
        }
      ]
    }
  ],
  "config": {
    "systemInstruction": "You are an interactive CLI assistant...",
    "tools": [
      {
        "functionDeclarations": [
          {
            "name": "ReadFile",
            "description": "Read a file from the local filesystem.",
            "parameters": {
              "type": "object",
              "properties": {
                "path": { "type": "string", "description": "The file path to read" }
              },
              "required": ["path"]
            }
          }
        ]
      }
    ],
    "thinkingConfig": {
      "thinkingBudget": 8192
    },
    "temperature": 1.0,
    "topP": 0.95
  }
}
```

**GenerateContentParameters 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `model` | `string` | 目标模型 ID，经 `resolveModel()` 解析后的具体模型名称 |
| `contents` | `Content[]` | 完整的对话历史，包含所有 user/model 轮次 |
| `config.systemInstruction` | `string` | 由 `PromptProvider` 组装的系统指令，包含 core rules、tool descriptions、GEMINI.md 内容等 |
| `config.tools` | `Tool[]` | 注册的工具声明数组，包含 `functionDeclarations` |
| `config.thinkingConfig` | `object` | 思考模式配置，`thinkingBudget` 默认为 `8192` tokens |
| `config.abortSignal` | `AbortSignal` | 用于取消请求的信号 |

**Content 结构中的 Part 类型：**

| Part 类型 | 关键字段 | 说明 |
|-----------|---------|------|
| 文本 | `{ text: "..." }` | 普通文本内容 |
| 思考 | `{ thought: true, text: "..." }` | 模型的内部思考过程 |
| 函数调用 | `{ functionCall: { name, args } }` | 模型请求调用工具 |
| 函数响应 | `{ functionResponse: { id, name, response } }` | 工具执行结果 |
| 内联数据 | `{ inlineData: { mimeType, data } }` | 图片等二进制数据 |

> 📌 **重点**：每个 model turn 中第一个 `functionCall` part 必须包含 `thoughtSignature` 属性。若缺失，`GeminiChat.ensureActiveLoopHasThoughtSignatures()` 会自动注入合成签名 `skip_thought_signature_validator`，否则 API 会返回 400 错误。

### 9.2 API 响应结构 (GenerateContentResponse)

Streaming 模式下，API 返回多个 chunk，每个 chunk 都是一个 `GenerateContentResponse` 对象：

```json
{
  "candidates": [
    {
      "content": {
        "role": "model",
        "parts": [
          { "text": "这个函数可以通过以下方式重构..." }
        ]
      },
      "finishReason": "STOP"
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 4523,
    "candidatesTokenCount": 1287,
    "totalTokenCount": 5810,
    "cachedContentTokenCount": 0,
    "thoughtsTokenCount": 2048,
    "toolUsePromptTokenCount": 856
  },
  "modelVersion": "gemini-2.5-pro-preview-05-06",
  "responseId": "resp_abc123def456"
}
```

**usageMetadata 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `promptTokenCount` | `number` | 输入 prompt（含 system instruction + history + tools）消耗的 token 数 |
| `candidatesTokenCount` | `number` | 模型输出消耗的 token 数 |
| `totalTokenCount` | `number` | 总 token 消耗 |
| `cachedContentTokenCount` | `number` | 被缓存命中的 token 数（Gemini API 的 context caching 特性） |
| `thoughtsTokenCount` | `number` | 模型思考过程消耗的 token 数 |
| `toolUsePromptTokenCount` | `number` | 工具定义占用的 prompt token 数 |

**finishReason 枚举值：**

| 值 | 说明 |
|----|------|
| `STOP` | 正常结束 |
| `MAX_TOKENS` | 达到输出 token 上限 |
| `SAFETY` | 触发安全过滤 |
| `RECITATION` | 触发引用检测 |
| `MALFORMED_FUNCTION_CALL` | 模型生成了格式错误的函数调用 |
| `UNEXPECTED_TOOL_CALL` | 模型生成了意外的工具调用 |

### 9.3 Tool Call 请求/响应结构 (ToolCallRequestInfo / ToolCallResponseInfo)

当模型返回 `functionCall` 时，`Turn` 将其解析为 `ToolCallRequestInfo`，交给 `CoreToolScheduler` 执行：

```json
{
  "callId": "ReadFile_1710000000_0",
  "name": "ReadFile",
  "args": {
    "path": "src/utils/retry.ts"
  },
  "isClientInitiated": false,
  "prompt_id": "a1b2c3d4########1",
  "traceId": "resp_abc123def456"
}
```

**ToolCallRequestInfo 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `callId` | `string` | 唯一标识，格式为 `{name}_{timestamp}_{counter}` 或 API 返回的 `id` |
| `name` | `string` | 工具名称，必须与 `ToolRegistry` 中注册的名称完全匹配 |
| `args` | `Record<string, unknown>` | 工具参数 |
| `isClientInitiated` | `boolean` | 是否由客户端（而非模型）发起的工具调用 |
| `prompt_id` | `string` | 关联的 prompt ID，用于遥测追踪 |
| `traceId` | `string` | API 响应 ID，用于分布式追踪 |

执行完成后生成 `ToolCallResponseInfo`：

```json
{
  "callId": "ReadFile_1710000000_0",
  "responseParts": [
    {
      "functionResponse": {
        "id": "ReadFile_1710000000_0",
        "name": "ReadFile",
        "response": {
          "content": "export async function retryWithBackoff<T>(\n  fn: () => Promise<T>,\n  options?: Partial<RetryOptions>,\n): Promise<T> { ... }"
        }
      }
    }
  ],
  "resultDisplay": "src/utils/retry.ts (245 lines)",
  "contentLength": 8923
}
```

> 💡 **最佳实践**：当 tool 执行失败时，`responseParts` 中的 `functionResponse.response` 会包含 `{ error: "错误信息" }` 字段，而非 `content`。`CoreToolScheduler` 通过 `createErrorResponse()` 统一生成错误响应格式。

### 9.4 会话录制数据结构 (ConversationRecord)

`ChatRecordingService` 将完整会话持久化到 `~/.gemini/tmp/<project_hash>/chats/` 目录：

```json
{
  "sessionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "projectHash": "f8a3b2c1d4e5",
  "startTime": "2026-03-14T10:30:00.000Z",
  "lastUpdated": "2026-03-14T10:35:42.123Z",
  "kind": "main",
  "messages": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2026-03-14T10:30:01.234Z",
      "type": "user",
      "content": [
        { "text": "请帮我重构 retry 函数" }
      ]
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "timestamp": "2026-03-14T10:30:05.567Z",
      "type": "gemini",
      "content": "我来查看一下这个文件...",
      "model": "gemini-2.5-pro",
      "thoughts": [
        {
          "subject": "分析重构需求",
          "description": "用户希望重构 retry 逻辑，需要先读取文件内容",
          "timestamp": "2026-03-14T10:30:03.456Z"
        }
      ],
      "toolCalls": [
        {
          "id": "ReadFile_1710000000_0",
          "name": "ReadFile",
          "displayName": "Read File",
          "args": { "path": "src/utils/retry.ts" },
          "result": [{ "functionResponse": { "..." : "..." } }],
          "status": "success",
          "timestamp": "2026-03-14T10:30:05.123Z",
          "description": "Reading src/utils/retry.ts"
        }
      ],
      "tokens": {
        "input": 4523,
        "output": 1287,
        "cached": 0,
        "thoughts": 2048,
        "tool": 856,
        "total": 5810
      }
    }
  ]
}
```

**MessageRecord (type: "gemini") 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 消息唯一 ID（UUID v4） |
| `type` | `"user" \| "gemini" \| "info" \| "error"` | 消息类型 |
| `content` | `PartListUnion` | 消息内容（文本或 Part 数组） |
| `model` | `string` | 使用的模型名称（仅 gemini 类型） |
| `thoughts` | `ThoughtSummary[]` | 模型的思考记录数组 |
| `toolCalls` | `ToolCallRecord[]` | 工具调用记录数组 |
| `tokens` | `TokensSummary` | 该消息的 token 用量统计 |

---

## 10 错误处理与重试机制

Gemini CLI 的错误处理采用**分层防御策略**：连接阶段由 `retryWithBackoff` 处理，流式传输阶段由 `GeminiChat` 的 mid-stream retry 机制处理，应用层由 `Turn` 将错误转换为友好的 `GeminiEventType.Error` 事件。

### 10.1 错误分类体系

源码中定义了严格的错误分类层次结构（参见 `utils/errors.ts` 和 `utils/googleQuotaErrors.ts`）：

```
Error (基类)
├── FatalError                          # 致命错误，程序终止
│   ├── FatalAuthenticationError        # exitCode=41  认证失败
│   ├── FatalInputError                 # exitCode=42  输入错误
│   ├── FatalSandboxError               # exitCode=44  沙箱错误
│   ├── FatalConfigError                # exitCode=52  配置错误
│   ├── FatalTurnLimitedError           # exitCode=53  turn 次数耗尽
│   ├── FatalToolExecutionError         # exitCode=54  工具执行致命错误
│   └── FatalCancellationError          # exitCode=130 用户中断 (SIGINT)
│
├── InvalidStreamError                  # Stream 验证失败（可重试）
│   ├── type: NO_FINISH_REASON          #   stream 无 finish reason
│   ├── type: NO_RESPONSE_TEXT          #   stream 无文本内容
│   ├── type: MALFORMED_FUNCTION_CALL   #   格式错误的函数调用
│   └── type: UNEXPECTED_TOOL_CALL      #   意外的工具调用
│
├── TerminalQuotaError                  # 配额硬上限（不可重试，触发 fallback）
├── RetryableQuotaError                 # 临时配额限制（可重试）
├── ValidationRequiredError             # 需要用户验证
│
├── UnauthorizedError                   # 401 认证过期
├── ForbiddenError                      # 403 权限不足
│   └── AccountSuspendedError           #   账户被暂停 (TOS_VIOLATION)
├── BadRequestError                     # 400 请求格式错误
├── CanceledError                       # 用户取消操作
│
├── AgentExecutionStoppedError          # Hook 停止 agent 执行
└── AgentExecutionBlockedError          # Hook 阻断 agent 执行
```

### 10.2 错误处理完整流程图

以下是从 API 调用到最终用户可见错误的完整流程：

```
用户发送消息
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  GeminiClient.sendMessageStream()                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Turn.run()                                          │   │
│  │                                                      │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │  GeminiChat.sendMessageStream()              │    │   │
│  │  │                                              │    │   │
│  │  │  ┌────────────────────────────────────┐      │    │   │
│  │  │  │  makeApiCallAndProcessStream()     │      │    │   │
│  │  │  │                                    │      │    │   │
│  │  │  │  ┌──────────────────────────┐      │      │    │   │
│  │  │  │  │  retryWithBackoff()      │      │      │    │   │
│  │  │  │  │  (连接阶段重试)           │      │      │    │   │
│  │  │  │  │                          │      │      │    │   │
│  │  │  │  │  429 RetryableQuota ──┐  │      │      │    │   │
│  │  │  │  │  5xx ServerError ──┐  │  │      │      │    │   │
│  │  │  │  │  Network Error ──┐ │  │  │      │      │    │   │
│  │  │  │  │                  │ │  │  │      │      │    │   │
│  │  │  │  │  ┌───────────┐   │ │  │  │      │      │    │   │
│  │  │  │  │  │ 指数退避   │◄──┘ │  │  │      │      │    │   │
│  │  │  │  │  │ + jitter  │◄─────┘  │  │      │      │    │   │
│  │  │  │  │  │ 最多10次  │◄────────┘  │      │      │    │   │
│  │  │  │  │  └───────────┘            │      │      │    │   │
│  │  │  │  │                           │      │      │    │   │
│  │  │  │  │  TerminalQuota ──► fallback│      │      │    │   │
│  │  │  │  │  400 BadRequest ──► throw │      │      │    │   │
│  │  │  │  │  401 Unauth ──────► throw │      │      │    │   │
│  │  │  │  └──────────────────────────┘      │      │    │   │
│  │  │  │                                    │      │    │   │
│  │  │  │  processStreamResponse()           │      │    │   │
│  │  │  │  (流式传输阶段)                     │      │    │   │
│  │  │  │  ┌──────────────────────────┐      │      │    │   │
│  │  │  │  │ Mid-stream retry         │      │      │    │   │
│  │  │  │  │ maxAttempts=4            │      │      │    │   │
│  │  │  │  │ initialDelayMs=500       │      │      │    │   │
│  │  │  │  │                          │      │      │    │   │
│  │  │  │  │ InvalidStream ──► retry  │      │      │    │   │
│  │  │  │  │ SSL Error ──────► retry  │      │      │    │   │
│  │  │  │  │ ECONNRESET ────► retry   │      │      │    │   │
│  │  │  │  └──────────────────────────┘      │      │    │   │
│  │  │  └────────────────────────────────────┘      │    │   │
│  │  │                                              │    │   │
│  │  │  Hook: AgentExecutionStopped ──► yield stop  │    │   │
│  │  │  Hook: AgentExecutionBlocked ──► yield block │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  │                                                      │   │
│  │  catch: InvalidStreamError ──► yield InvalidStream   │   │
│  │  catch: UnauthorizedError ──► throw (冒泡到顶层)       │   │
│  │  catch: other ──► yield Error (友好错误消息)           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  Loop detection ──► 检测到循环 → 中断或恢复                   │
│  Context overflow ──► Chat compression → 继续              │
└─────────────────────────────────────────────────────────────┘
```

### 10.3 retryWithBackoff 源码解析

连接阶段的重试由 `retryWithBackoff()` 处理（源码位于 `core/src/utils/retry.ts`），采用**指数退避 + 随机抖动**策略：

```typescript
// 默认重试参数
const DEFAULT_RETRY_OPTIONS: RetryOptions = {
  maxAttempts: 10,           // 最多 10 次尝试
  initialDelayMs: 5000,      // 初始延迟 5 秒
  maxDelayMs: 30000,         // 最大延迟 30 秒
  shouldRetryOnError: isRetryableError,
};

// 可重试的网络错误码
const RETRYABLE_NETWORK_CODES = [
  'ECONNRESET',              // 连接被重置
  'ETIMEDOUT',               // 连接超时
  'EPIPE',                   // 管道断裂
  'ENOTFOUND',               // DNS 解析失败
  'EAI_AGAIN',               // DNS 暂时失败
  'ECONNREFUSED',            // 连接被拒绝
  'ERR_SSL_SSLV3_ALERT_BAD_RECORD_MAC',  // SSL 错误
  'ERR_SSL_WRONG_VERSION_NUMBER',         // SSL 版本错误
  'EPROTO',                  // 协议错误
];
```

**重试决策逻辑** (`isRetryableError`)：

```typescript
export function isRetryableError(error: Error | unknown, retryFetchErrors?: boolean): boolean {
  // 1. 检查网络错误码 (遍历 cause chain 寻找错误码)
  const errorCode = getNetworkErrorCode(error);
  if (errorCode && RETRYABLE_NETWORK_CODES.includes(errorCode)) return true;

  // 2. 检查 fetch 失败 (仅当 retryFetchErrors=true)
  if (retryFetchErrors && error instanceof Error) {
    if (error.message.includes('fetch failed') ||
        error.message.includes('incomplete json segment')) return true;
  }

  // 3. ApiError 状态码判断
  if (error instanceof ApiError) {
    if (error.status === 400) return false;  // Bad Request 不重试
    return error.status === 429 || error.status === 499 ||
           (error.status >= 500 && error.status < 600);
  }

  // 4. 通用 HTTP 状态码检查
  const status = getErrorStatus(error);
  if (status !== undefined) {
    return status === 429 || status === 499 || (status >= 500 && status < 600);
  }

  return false;
}
```

> ⚠️ **注意**：`retryWithBackoff` 对 `TerminalQuotaError` 和 `ModelNotFoundError` 会触发 **模型降级**（fallback）而非简单重试。降级逻辑由 `handleFallback()` 处理，通过 `ModelAvailabilityService` 选择可用的备选模型。

### 10.4 Mid-Stream Retry 机制

在 stream 已经建立后发生的错误，由 `GeminiChat.sendMessageStream()` 内部的 mid-stream retry 逻辑处理：

```typescript
// Mid-stream 重试参数（独立于连接阶段）
const MID_STREAM_RETRY_OPTIONS: MidStreamRetryOptions = {
  maxAttempts: 4,         // 1 次初始调用 + 3 次重试
  initialDelayMs: 500,    // 线性退避，延迟 = 500ms * (attempt + 1)
};
```

Mid-stream retry 的触发条件：
1. `InvalidStreamError` — stream 结束但内容无效（仅 Gemini 2.x 模型）
2. `isRetryableError` 返回 `true` — 网络中断、SSL 错误等

当 mid-stream retry 发生时，`GeminiChat` 会 yield 一个 `StreamEventType.RETRY` 事件，通知 UI 层丢弃当前部分内容：

```typescript
// GeminiChat.sendMessageStream() 中的 retry 信号
if (attempt > 0) {
  yield { type: StreamEventType.RETRY };  // UI 应丢弃之前的部分内容
}
```

### 10.5 模型降级 (Fallback) 机制

当持续收到 429 错误或模型不可用时，`handleFallback()` 启动降级流程：

```
持续 429 / TerminalQuotaError / ModelNotFoundError
  │
  ▼
handleFallback(config, failedModel, authType, error)
  │
  ├── resolvePolicyChain(config)          # 获取模型策略链
  ├── buildFallbackPolicyContext()        # 构建降级上下文
  ├── classifyFailureKind(error)          # 分类错误类型
  │
  ├── availability.selectFirstAvailable() # 选择可用备选模型
  │
  ├── resolvePolicyAction()               # 决定降级动作
  │   ├── 'silent' ──► 静默切换，自动重试
  │   └── 其他 ──► 通知用户选择
  │
  └── processIntent(config, intent, fallbackModel)
      ├── 'retry_always' ──► config.activateFallbackMode() 永久切换
      ├── 'retry_once' ──► 单次使用备选模型
      ├── 'retry_with_credits' ──► 使用付费额度重试
      ├── 'stop' ──► 停止，保留当前模型
      ├── 'retry_later' ──► 稍后重试
      └── 'upgrade' ──► 打开升级页面
```

> 💡 **最佳实践**：当使用免费 API Key 遇到频繁 429 错误时，Gemini CLI 会自动从 `gemini-2.5-pro` 降级到 `gemini-2.5-flash`，在终端中提示用户确认。可通过 `--model flash` 参数直接使用 Flash 模型避免降级延迟。

---

## 11 场景追踪：用户发送一条消息的完整生命周期

以下通过一个具体场景，追踪一条用户消息在 Gemini CLI 中的完整处理路径。

### 场景：用户在交互模式下输入 "读取 package.json 的 name 字段"

```
步骤 1: 用户输入捕获
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [Ink TextInput] 用户键入 "读取 package.json 的 name 字段" 并按回车
        │
        ▼
  AppContainer.tsx → 检查是否为 slash command → 否
        │
        ▼
  logUserPrompt() → 记录遥测事件 UserPromptEvent
        │   { input_length: 22, prompt_id: "a1b2c3d4########1", auth_type: "gemini-api-key" }

步骤 2: Hook 触发 + System Prompt 组装
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
  GeminiClient.fireBeforeAgentHookSafe()
        │   → hookSystem.fireBeforeAgentEvent("读取 package.json 的 name 字段")
        │   → 如果 hook 返回 additionalContext，注入到消息中
        │
        ▼
  GeminiClient.updateSystemInstruction()
        │   → PromptProvider.buildSystemPrompt()
        │     ├── Core rules + safety guidelines
        │     ├── Tool descriptions (ReadFile, Edit, Shell, Glob, ...)
        │     ├── GEMINI.md 内容 (user + project 层)
        │     ├── Approval mode context ("默认模式: 需要确认危险操作")
        │     └── IDE context (如果 VS Code companion 已连接)

步骤 3: Model Routing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
  ModelRouterService.selectModel()
        │   CompositeStrategy 链式评估:
        │   ├── OverrideStrategy → 检查 --model 参数 → 无覆盖
        │   ├── ApprovalModeStrategy → 检查 approval mode → 默认
        │   ├── ClassifierStrategy → LLM 分类器 → 跳过(简单查询)
        │   └── DefaultStrategy → 返回 "gemini-2.5-pro"
        │
        ▼
  resolveModel("gemini-2.5-pro") → "gemini-2.5-pro"

步骤 4: Context Window 检查 + Chat Compression
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
  GeminiClient.sendMessageStream()
        │   → 计算当前 history token 数
        │   → tokenLimit("gemini-2.5-pro") = 1,048,576
        │   → 如果 lastPromptTokenCount > limit * 0.8:
        │     └── ChatCompressionService.compress() → 使用 Flash 模型压缩 history
        │   → LoopDetectionService.check() → 无循环

步骤 5: API 调用 (第一轮 Turn)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
  Turn.run(modelConfigKey, "读取 package.json 的 name 字段", signal)
        │
        ▼
  GeminiChat.sendMessageStream()
        │   → history.push({ role: "user", parts: [{ text: "读取..." }] })
        │   → chatRecordingService.recordMessage({ type: "user", content: [...] })
        │
        ▼
  makeApiCallAndProcessStream()
        │   → hookSystem.fireBeforeModelEvent() → 无阻断
        │   → hookSystem.fireBeforeToolSelectionEvent() → 无修改
        │
        ▼
  LoggingContentGenerator.generateContentStream()
        │   → 记录 ApiRequestEvent (遥测)
        │   → GoogleGenAI.models.generateContentStream(request)
        │   → 记录 ApiResponseEvent (遥测)
        │
        ▼
  processStreamResponse() — 解析 stream chunks
        │   chunk 1: { thought: true, text: "**分析请求**\n用户想读取..." }
        │     → recordThoughtFromContent() → 记录思考
        │     → yield Thought { subject: "分析请求", description: "..." }
        │
        │   chunk 2: { text: "好的，让我读取这个文件。" }
        │     → yield Content "好的，让我读取这个文件。"
        │
        │   chunk 3: { functionCall: { name: "ReadFile", args: { path: "package.json" } } }
        │     → yield ToolCallRequest { callId: "ReadFile_1710..._0", name: "ReadFile", ... }
        │
        │   chunk 4: { finishReason: "STOP", usageMetadata: { promptTokenCount: 2345, ... } }
        │     → recordMessageTokens(usageMetadata)
        │     → yield Finished { reason: "STOP", usageMetadata: {...} }

步骤 6: Tool 调度与执行
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
  CoreToolScheduler.schedule(toolCallRequest, signal)
        │
        ├── ToolRegistry.getTool("ReadFile") → ReadFileTool 实例
        ├── tool.build({ path: "package.json" }) → ReadFileInvocation
        ├── PolicyEngine.check({ name: "ReadFile", args: {...} })
        │     → PolicyDecision.ALLOW (ReadFile 是安全操作)
        │
        ├── hookSystem.fireBeforeToolEvent()
        │
        ├── setStatus(Validating → Scheduled → Executing)
        │
        ├── ToolExecutor.execute()
        │     → ReadFileInvocation.execute(signal)
        │     → fs.readFile("package.json") → 文件内容
        │     → 返回 ToolCallResponseInfo
        │
        ├── hookSystem.fireAfterToolEvent()
        │
        └── setStatus(Executing → Success)
              │
              ▼
        onAllToolCallsComplete(completedToolCalls)
              │
              ▼
        geminiChat.recordCompletedToolCalls("gemini-2.5-pro", toolCalls)

步骤 7: 将 Tool 结果返回给模型 (第二轮 Turn)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
  将 functionResponse 作为新的 user message:
  {
    role: "user",
    parts: [{
      functionResponse: {
        id: "ReadFile_1710..._0",
        name: "ReadFile",
        response: { content: '{\n  "name": "@google/gemini-cli"\n  ...\n}' }
      }
    }]
  }
        │
        ▼
  新的 Turn.run() → GeminiChat → API 调用
        │
        ▼
  模型返回纯文本 (无 functionCall):
  "package.json 的 name 字段值为 `@google/gemini-cli`。"
        │
        ▼
  yield Finished → 无 pending tool calls

步骤 8: Next-Speaker Check + AfterAgent Hook
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
  checkNextSpeaker() → BaseLlmClient 判断
        │   → "user" (模型已完成回答，轮到用户)
        │
        ▼
  fireAfterAgentHookSafe() → hookSystem.fireAfterAgentEvent(request, response)
        │
        ▼
  GeminiClient 结束 sendMessageStream generator

步骤 9: UI 渲染
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
  React/Ink UI 处理 events:
        ├── Thought → 思考气泡展示 "分析请求..."
        ├── Content → Markdown 渲染 "好的，让我读取这个文件。"
        ├── ToolCallRequest → 显示工具调用进度条 "ReadFile: package.json"
        ├── Content → Markdown 渲染最终回答
        └── Finished → 显示 token 用量
              Input: 2,345 tokens | Output: 156 tokens | Total: 2,501 tokens
```

---

## 12 Token 用量追踪机制

Gemini CLI 通过多层协作实现精确的 token 用量追踪和报告。

### 12.1 Token 追踪数据流

```
Gemini API Response (stream)
  │
  │  每个 chunk 的 usageMetadata
  ▼
┌──────────────────────────────────────────────┐
│  GeminiChat.processStreamResponse()          │
│  ├── chatRecordingService.recordMessageTokens│ ──► 持久化到会话文件
│  └── lastPromptTokenCount = promptTokenCount │ ──► 用于 context window 管理
└───────────────────┬──────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│  LoggingContentGenerator                     │
│  ├── ApiResponseEvent (遥测)                  │ ──► OpenTelemetry 指标
│  └── estimateContextBreakdown()              │ ──► 上下文分布统计
└───────────────────┬──────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│  uiTelemetryService                          │
│  └── setLastPromptTokenCount()               │ ──► UI 展示
└──────────────────────────────────────────────┘
```

### 12.2 TokensSummary 结构

`ChatRecordingService` 将 API 返回的 `usageMetadata` 转换为 `TokensSummary` 结构：

```typescript
// chatRecordingService.ts — recordMessageTokens()
recordMessageTokens(respUsageMetadata: GenerateContentResponseUsageMetadata): void {
  const tokens = {
    input: respUsageMetadata.promptTokenCount ?? 0,
    output: respUsageMetadata.candidatesTokenCount ?? 0,
    cached: respUsageMetadata.cachedContentTokenCount ?? 0,
    thoughts: respUsageMetadata.thoughtsTokenCount ?? 0,
    tool: respUsageMetadata.toolUsePromptTokenCount ?? 0,
    total: respUsageMetadata.totalTokenCount ?? 0,
  };
  // 尝试附加到最后一条 gemini 消息，否则暂存到 queuedTokens
  const lastMsg = this.getLastMessage(conversation);
  if (lastMsg && lastMsg.type === 'gemini' && !lastMsg.tokens) {
    lastMsg.tokens = tokens;
  } else {
    this.queuedTokens = tokens;  // 暂存，等下一条 gemini 消息时附加
  }
}
```

### 12.3 上下文分布估算 (Context Breakdown)

`LoggingContentGenerator.estimateContextBreakdown()` 对每次 API 请求进行上下文分布统计，用于遥测分析：

```typescript
// loggingContentGenerator.ts — estimateContextBreakdown()
export function estimateContextBreakdown(
  contents: Content[],
  config?: GenerateContentConfig,
): ContextBreakdown {
  // 分类统计各部分 token 消耗：
  return {
    system_instructions: number,  // system prompt 占用
    tool_definitions: number,     // 非 MCP 工具定义占用
    history: number,              // 对话历史（不含 tool call）占用
    tool_calls: Record<string, number>,  // 各工具调用/响应的 token 占用
    mcp_servers: number,          // MCP 工具定义 + 调用占用
  };
}
```

**估算方法**：对于 `Part` 类型的内容使用 `estimateTokenCountSync()` 精确估算；对于配置对象（system instruction、tool definitions）使用 `JSON.stringify(value).length / 4` 粗略估算。

### 12.4 Token Limit 与模型映射

所有支持的模型共享相同的 token limit（源码位于 `core/src/core/tokenLimits.ts`）：

```typescript
export const DEFAULT_TOKEN_LIMIT = 1_048_576;  // 1M tokens

export function tokenLimit(model: Model): TokenCount {
  switch (model) {
    case 'gemini-3-pro-preview':
    case 'gemini-3-flash-preview':
    case 'gemini-2.5-pro':
    case 'gemini-2.5-flash':
    case 'gemini-2.5-flash-lite':
      return 1_048_576;       // 1,048,576 tokens (1M)
    default:
      return DEFAULT_TOKEN_LIMIT;
  }
}
```

当 `lastPromptTokenCount` 接近 `tokenLimit` 时，`ChatCompressionService` 会自动触发对话压缩以保持在 context window 之内。

### 12.5 思考 Budget 控制

模型的思考过程受 `thinkingBudget` 参数控制，默认为 `8192` tokens：

```typescript
// config/models.ts
export const DEFAULT_THINKING_MODE = 8192;  // 防止失控的思考循环
```

该参数通过 `GenerateContentConfig.thinkingConfig.thinkingBudget` 传递给 API，限制模型在每次响应中用于内部思考（`thought: true` 的 Part）的 token 数量。

---

## 13 关键源码片段

### 13.1 GeminiChat — Stream 验证逻辑

`processStreamResponse()` 在 stream 结束后执行严格验证，确保响应的完整性（源码位于 `core/src/core/geminiChat.ts`）：

```typescript
// Stream 验证：成功条件为存在 tool call 或
// (有 finish reason 且非 MALFORMED 且有文本内容)
if (!hasToolCall) {
  if (!finishReason) {
    throw new InvalidStreamError(
      'Model stream ended without a finish reason.',
      'NO_FINISH_REASON',
    );
  }
  if (finishReason === FinishReason.MALFORMED_FUNCTION_CALL) {
    throw new InvalidStreamError(
      'Model stream ended with malformed function call.',
      'MALFORMED_FUNCTION_CALL',
    );
  }
  if (finishReason === FinishReason.UNEXPECTED_TOOL_CALL) {
    throw new InvalidStreamError(
      'Model stream ended with unexpected tool call.',
      'UNEXPECTED_TOOL_CALL',
    );
  }
  if (!responseText) {
    throw new InvalidStreamError(
      'Model stream ended with empty response text.',
      'NO_RESPONSE_TEXT',
    );
  }
}
```

### 13.2 ContentGenerator — 认证工厂

`createContentGenerator()` 根据 `AuthType` 动态选择后端（源码位于 `core/src/core/contentGenerator.ts`）：

```typescript
export async function createContentGenerator(
  config: ContentGeneratorConfig,
  gcConfig: Config,
  sessionId?: string,
): Promise<ContentGenerator> {
  const generator = await (async () => {
    // 测试模式：使用 FakeContentGenerator
    if (gcConfig.fakeResponses) {
      return new LoggingContentGenerator(
        await FakeContentGenerator.fromFile(gcConfig.fakeResponses), gcConfig);
    }

    // OAuth / ADC 模式：通过 Google Code Assist 服务器
    if (config.authType === AuthType.LOGIN_WITH_GOOGLE ||
        config.authType === AuthType.COMPUTE_ADC) {
      return new LoggingContentGenerator(
        await createCodeAssistContentGenerator(httpOptions, config.authType, gcConfig),
        gcConfig);
    }

    // API Key / Vertex AI / Gateway 模式：直接使用 GoogleGenAI SDK
    if (config.authType === AuthType.USE_GEMINI ||
        config.authType === AuthType.USE_VERTEX_AI ||
        config.authType === AuthType.GATEWAY) {
      const googleGenAI = new GoogleGenAI({
        apiKey: config.apiKey,
        vertexai: config.vertexai,
        httpOptions: { headers, baseUrl },
      });
      return new LoggingContentGenerator(googleGenAI.models, gcConfig);
    }

    throw new Error(`Unsupported authType: ${config.authType}`);
  })();

  // 可选：包装 RecordingContentGenerator 用于测试录制
  if (gcConfig.recordResponses) {
    return new RecordingContentGenerator(generator, gcConfig.recordResponses);
  }
  return generator;
}
```

### 13.3 CoreToolScheduler — Tool 调度核心流程

`_schedule()` 方法展示了 tool call 从接收到执行的完整调度逻辑（源码位于 `core/src/core/coreToolScheduler.ts`）：

```typescript
private async _schedule(
  request: ToolCallRequestInfo | ToolCallRequestInfo[],
  signal: AbortSignal,
): Promise<void> {
  const requestsToProcess = Array.isArray(request) ? request : [request];
  const currentApprovalMode = this.context.config.getApprovalMode();

  const newToolCalls: ToolCall[] = requestsToProcess.map((reqInfo): ToolCall => {
    // 1. 查找工具
    const toolInstance = this.context.toolRegistry.getTool(reqInfo.name);
    if (!toolInstance) {
      const suggestion = getToolSuggestion(reqInfo.name, /* allNames */);
      return { status: CoreToolCallStatus.Error, /* errorResponse */ };
    }

    // 2. 构建 invocation
    const invocationOrError = this.buildInvocation(toolInstance, reqInfo.args);
    if (invocationOrError instanceof Error) {
      return { status: CoreToolCallStatus.Error, /* errorResponse */ };
    }

    // 3. 初始状态：Validating
    return {
      status: CoreToolCallStatus.Validating,
      request: reqInfo,
      tool: toolInstance,
      invocation: invocationOrError,
      startTime: Date.now(),
      approvalMode: currentApprovalMode,
    };
  });

  // 4. 进入串行处理队列
  this.toolCallQueue.push(...newToolCalls);
  await this._processNextInQueue(signal);
}
```

### 13.4 Turn — 事件解析引擎

`Turn.run()` 将 raw stream 解析为类型化事件，是 UI 层与核心引擎的桥梁（源码位于 `core/src/core/turn.ts`）：

```typescript
async *run(
  modelConfigKey: ModelConfigKey,
  req: PartListUnion,
  signal: AbortSignal,
  displayContent?: PartListUnion,
  role: LlmRole = LlmRole.MAIN,
): AsyncGenerator<ServerGeminiStreamEvent> {
  try {
    const responseStream = await this.chat.sendMessageStream(
      modelConfigKey, req, this.prompt_id, signal, role, displayContent);

    for await (const streamEvent of responseStream) {
      if (signal?.aborted) {
        yield { type: GeminiEventType.UserCancelled };
        return;
      }

      if (streamEvent.type === 'retry') {
        yield { type: GeminiEventType.Retry };
        continue;
      }

      const resp = streamEvent.value;
      const parts = resp.candidates?.[0]?.content?.parts ?? [];

      // 解析思考、文本、函数调用
      for (const part of parts) {
        if (part.thought) {
          yield { type: GeminiEventType.Thought, value: parseThought(part.text) };
        }
      }
      const text = getResponseText(resp);
      if (text) yield { type: GeminiEventType.Content, value: text };

      for (const fnCall of resp.functionCalls ?? []) {
        yield this.handlePendingFunctionCall(fnCall);  // → ToolCallRequest
      }

      if (resp.candidates?.[0]?.finishReason) {
        yield { type: GeminiEventType.Finished, value: { reason, usageMetadata } };
      }
    }
  } catch (e) {
    if (e instanceof InvalidStreamError) {
      yield { type: GeminiEventType.InvalidStream };
    } else if (e instanceof UnauthorizedError) {
      throw e;  // 冒泡到顶层处理
    } else {
      await reportError(e, 'Error when talking to Gemini API', ...);
      yield { type: GeminiEventType.Error, value: { error: structuredError } };
    }
  }
}
```

### 13.5 GeminiEventType 事件类型完整枚举

`Turn.run()` 产生的所有事件类型（源码位于 `core/src/core/turn.ts`）：

```typescript
export enum GeminiEventType {
  Content = 'content',                              // 文本内容
  ToolCallRequest = 'tool_call_request',            // 工具调用请求
  ToolCallResponse = 'tool_call_response',          // 工具调用响应
  ToolCallConfirmation = 'tool_call_confirmation',  // 工具调用确认
  UserCancelled = 'user_cancelled',                 // 用户取消
  Error = 'error',                                  // 错误
  ChatCompressed = 'chat_compressed',               // 对话已压缩
  Thought = 'thought',                              // 模型思考
  MaxSessionTurns = 'max_session_turns',            // 达到最大 turn 数
  Finished = 'finished',                            // 单轮完成
  LoopDetected = 'loop_detected',                   // 检测到循环
  Citation = 'citation',                            // 引用信息
  Retry = 'retry',                                  // 重试信号
  ContextWindowWillOverflow = 'context_window_will_overflow',  // 即将溢出
  InvalidStream = 'invalid_stream',                 // 无效 stream
  ModelInfo = 'model_info',                         // 模型信息
  AgentExecutionStopped = 'agent_execution_stopped',  // Hook 停止执行
  AgentExecutionBlocked = 'agent_execution_blocked',  // Hook 阻断执行
}
```

---

## References

| 资源 | 链接 |
|------|------|
| 源码仓库 | `github.com/google-gemini/gemini-cli` |
| 核心包入口 | `packages/core/src/index.ts` |
| CLI 入口 | `packages/cli/src/gemini.tsx` |
| Agent loop | `packages/core/src/core/client.ts` |
| GeminiChat | `packages/core/src/core/geminiChat.ts` |
| ContentGenerator | `packages/core/src/core/contentGenerator.ts` |
| CoreToolScheduler | `packages/core/src/core/coreToolScheduler.ts` |
| Turn | `packages/core/src/core/turn.ts` |
| ToolRegistry | `packages/core/src/tools/tool-registry.ts` |
| PolicyEngine | `packages/core/src/policy/policy-engine.ts` |
| HookSystem | `packages/core/src/hooks/hookSystem.ts` |
| PromptProvider | `packages/core/src/prompts/promptProvider.ts` |
| ModelRouterService | `packages/core/src/routing/modelRouterService.ts` |
| AgentLoopContext | `packages/core/src/config/agent-loop-context.ts` |
| SDK | `packages/sdk/src/index.ts` |
| A2A Server | `packages/a2a-server/src/index.ts` |
| VS Code Extension | `packages/vscode-ide-companion/package.json` |

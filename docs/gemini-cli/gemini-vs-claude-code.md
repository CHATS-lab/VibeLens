# Gemini CLI vs Claude Code 全维度对比分析

| 条目 | 内容 |
|------|------|
| **主题** | Gemini CLI 与 Claude Code 的架构、配置、工具链全维度对比 |
| **Gemini CLI 版本** | 基于 2025-2026 年开源代码（packages/core + packages/cli） |
| **Claude Code 版本** | 基于 2025 年 Claude Code CLI |
| **分析方法** | 直接阅读 Gemini CLI TypeScript 源码 + Claude Code 使用经验 |
| **目标读者** | 需要在两种 AI 编程工具之间做技术选型或深入理解差异的工程师 |
| **创建日期** | 2026-03-14 |

---

## 1 架构设计：Monorepo vs 单包

Gemini CLI 采用典型的 **monorepo 多包架构**，通过 `packages/` 目录组织代码。Claude Code 则是一个**封闭的单包发行版**，用户只通过 npm 安装一个 `@anthropic-ai/claude-code` 包。

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **仓库结构** | Monorepo（7 个 packages） | 单包 |
| **核心包** | `@google/gemini-cli-core` | 内嵌于主包 |
| **CLI 包** | `packages/cli`（React/Ink TUI） | 主包即 CLI |
| **SDK** | `packages/sdk`（可嵌入） | 无独立 SDK |
| **IDE 支持** | `packages/vscode-ide-companion` | 独立 VS Code 扩展 |
| **A2A Server** | `packages/a2a-server`（Agent-to-Agent 协议服务端） | 无 |
| **DevTools** | `packages/devtools` | 无 |
| **测试工具** | `packages/test-utils` | 内嵌 |

Gemini CLI 的 `packages/core/src/index.ts` 导出超过 200 个模块，覆盖 config、tools、agents、routing、hooks、policy、billing、telemetry、MCP、voice 等完整子系统。这种模块化设计使第三方可以直接导入 `@google/gemini-cli-core` 构建自定义 CLI 或 IDE 插件。

> 💡 **关键差异**：Gemini CLI 的 core 包是一个可独立使用的库，暴露了完整的 API surface。Claude Code 更像一个 opinionated 的终端应用，不提供可编程的核心库。

---

## 2 配置系统：7 层层级 vs 扁平设置

Gemini CLI 的配置系统是一个**多层合并**架构，配置源按优先级从低到高依次覆盖。Claude Code 的配置则相对扁平，主要依赖环境变量和少量配置文件。

### Gemini CLI 的 7 层配置层级

根据 `packages/cli/src/config/settings.ts` 中的 `SettingScope` enum 和实际加载逻辑：

| 优先级 | 层级 | 路径 | 说明 |
|--------|------|------|------|
| 1（最低） | SystemDefaults | `/etc/gemini-cli/system-defaults.json` | 系统默认值 |
| 2 | System | `/etc/gemini-cli/settings.json` (Linux) | IT 管理员级别的系统策略 |
|   |        | `/Library/Application Support/GeminiCli/settings.json` (macOS) | |
| 3 | Extension | 通过 extension manifest 注入 | 扩展贡献的配置 |
| 4 | User | `~/.gemini/settings.json` | 用户全局设置 |
| 5 | Workspace | `.gemini/settings.json`（项目根目录） | 项目级设置 |
| 6 | Environment | `GEMINI_*` 环境变量 | 环境变量覆盖 |
| 7（最高） | CLI Flags | 命令行参数 `--model`, `--yolo` 等 | 运行时参数覆盖 |

配置合并使用 `customDeepMerge` 函数，并支持多种合并策略（`MergeStrategy` enum）：`REPLACE`、`CONCAT`、`UNION`、`SHALLOW_MERGE`。不同的配置键可以声明自己的合并策略。

### Claude Code 的配置层级

| 优先级 | 层级 | 路径 |
|--------|------|------|
| 1（最低） | 用户全局 | `~/.claude/settings.json` |
| 2 | 项目级 | `.claude/settings.json` |
| 3 | 环境变量 | `ANTHROPIC_*`, `CLAUDE_*` |
| 4（最高） | CLI Flags | `--model`, `--allowedTools` 等 |

> ⚠️ **重要差异**：Gemini CLI 有完整的 System 和 SystemDefaults 层级，支持企业 IT 管理员通过系统级配置文件统一管控策略，这是 Claude Code 不具备的。Extension 层也是独立的配置源。

---

## 3 Model Routing：多策略链 vs 直接模型指定

Gemini CLI 实现了一个**复杂的多策略路由链**（`ModelRouterService`），可以根据用户输入、上下文和策略自动选择模型。Claude Code 采用**直接模型指定**方式。

### Gemini CLI 路由策略链（Chain of Responsibility）

`ModelRouterService.initializeDefaultStrategy()` 构建的策略链如下（优先级从高到低）：

| 策略 | 类名 | 作用 |
|------|------|------|
| Fallback | `FallbackStrategy` | 处理 quota/error 后的降级路由 |
| Override | `OverrideStrategy` | 用户手动指定模型时跳过路由 |
| ApprovalMode | `ApprovalModeStrategy` | 基于 approval mode 选择模型 |
| Gemma Classifier | `GemmaClassifierStrategy` | 使用本地 Gemma 模型分类请求 |
| Generic Classifier | `ClassifierStrategy` | 通用分类器 |
| Numerical Classifier | `NumericalClassifierStrategy` | 数值型分类器 |
| Default | `DefaultStrategy` | **终端策略**，兜底使用默认模型 |

所有策略通过 `CompositeStrategy` 组合，每个策略可以返回 `RoutingDecision | null`，`null` 表示让下一个策略处理。路由决策包含 `model`、`source`、`latencyMs`、`reasoning` 等元信息，完整记录选择过程。

支持的模型别名：

| 别名 | 解析结果 |
|------|---------|
| `auto` | `auto-gemini-2.5`（自动路由 Pro/Flash） |
| `pro` | `gemini-2.5-pro` |
| `flash` | `gemini-2.5-flash` |
| `flash-lite` | `gemini-2.5-flash-lite` |

### Claude Code 的模型选择

Claude Code 使用简单的 `--model` flag 直接指定模型。没有自动路由机制，用户手动选择 Opus/Sonnet/Haiku。

> 📌 **核心差异**：Gemini CLI 的 `auto` 模式可以在 Pro 和 Flash 之间动态切换以优化成本和延迟。这是一个 Claude Code 完全没有的智能路由层。

---

## 4 工具系统：Registry + Discovery + MCP vs 内建 + MCP

两者都支持 MCP（Model Context Protocol），但 Gemini CLI 的工具系统更加模块化和可扩展。

### Gemini CLI 工具架构

```
ToolRegistry
├── 内置工具（Built-in）
│   ├── ReadFileTool, EditTool, WriteFileTool
│   ├── GrepTool, RipGrepTool, GlobTool, LSTool
│   ├── ShellTool
│   ├── WebFetchTool, WebSearchTool
│   ├── MemoryTool, AskUserTool
│   ├── WriteTodosTool
│   ├── TrackerTools (Create/Update/Get/List/AddDependency/Visualize)
│   ├── ActivateSkillTool
│   └── EnterPlanModeTool, ExitPlanModeTool
├── Discovered 工具（通过 toolDiscoveryCommand 外部发现）
└── MCP 工具（DiscoveredMCPTool，来自 MCP servers）
```

`ToolRegistry` 的核心特性：
- **动态发现**：通过 `toolDiscoveryCommand` 配置一个外部命令，该命令输出 JSON 格式的工具定义。调用时通过 `toolCallCommand` 执行
- **工具排序**：内置 > Discovered > MCP（按 server name 排序）
- **工具排除**：支持 `excludeTools` 配置和 policy engine 联动
- **Legacy 别名**：`TOOL_LEGACY_ALIASES` 保持向后兼容
- **Model-specific schemas**：`getSchema(modelId)` 支持不同模型使用不同的工具定义
- **Plan Mode 感知**：在 Plan Mode 下自动限制 `write_file` 和 `edit` 只能操作 plans 目录

### Claude Code 工具

Claude Code 的工具是硬编码在主包中的：

| 工具名 | 对应 Gemini CLI |
|--------|----------------|
| Read | ReadFileTool |
| Edit | EditTool |
| Write | WriteFileTool |
| Bash | ShellTool |
| Grep | GrepTool/RipGrepTool |
| Glob | GlobTool |
| WebFetch | WebFetchTool |
| WebSearch | WebSearchTool |
| NotebookEdit | 无对应 |
| Agent | SubagentTool |
| Skill | ActivateSkillTool |
| EnterWorktree | 无对应 |

> 💡 **关键差异**：Gemini CLI 的 `toolDiscoveryCommand` 机制允许项目自定义工具而无需编写扩展，只需配置一个脚本。Claude Code 没有这种外部工具发现机制。Gemini CLI 还内置了 `TrackerTools`（任务追踪）和 `WriteTodosTool`，这是 Claude Code 没有的。

---

## 5 Agent 系统：Local/Remote + A2A vs Agent Tool

这是两者差异最大的维度之一。Gemini CLI 构建了一个完整的 **Agent Registry + A2A（Agent-to-Agent）协议** 系统，而 Claude Code 使用单一的 Agent Tool 来 spawn 子代理。

### Gemini CLI Agent 架构

```
AgentRegistry
├── 内置 Agent
│   ├── CodebaseInvestigatorAgent  — 代码库分析
│   ├── CliHelpAgent              — CLI 帮助
│   ├── GeneralistAgent           — 通用任务
│   └── BrowserAgentDefinition    — 浏览器自动化（可选）
├── 用户 Agent（~/.gemini/agents/）
├── 项目 Agent（.gemini/agents/）
└── 扩展 Agent（通过 Extension 注册）
```

Agent 定义分为两种类型（`AgentDefinition`）：

**Local Agent**（`LocalAgentDefinition`）：
- 包含 `promptConfig`（system prompt + initial messages + query template）
- 包含 `modelConfig`（可以继承或覆盖主模型）
- 包含 `runConfig`（maxTurns 默认 30、maxTimeMinutes 默认 10）
- 包含 `toolConfig`（可以限制 agent 可用的工具子集）
- 包含 `inputConfig`（AJV JSON Schema 验证输入参数）
- 包含 `outputConfig`（Zod schema 验证输出结构）

**Remote Agent**（`RemoteAgentDefinition`）：
- 通过 `agentCardUrl` 连接远程 A2A 服务
- 支持 OAuth/Google Credentials/Service Account 认证
- 从 AgentCard 自动获取 description 和 skills 列表
- 需要用户 acknowledge 后才能使用

安全机制：
- 项目级 Agent 需要 **acknowledgment**（通过 hash 校验），防止恶意 agent 注入
- Agent 自动注册到 Policy Engine，local 默认 `ALLOW`，remote 默认 `ASK_USER`
- 支持通过 settings 中的 `agents.overrides` 覆盖配置

### Claude Code Agent 系统

Claude Code 的 Agent Tool 是一个简单的子进程 spawn 机制：
- 无 Agent Registry
- 无远程 Agent/A2A 支持
- 无 Agent 发现机制
- 无 Agent 认证体系
- 子代理继承父代理的工具和权限

> ⚠️ **重要差异**：Gemini CLI 的 A2A 协议支持使其可以连接到任意远程 AI 服务，形成多 Agent 协作网络。Claude Code 的 Agent 只是本地子进程。

---

## 6 会话格式：JSON vs JSONL

两者的会话存储格式有本质区别，影响数据分析和工具生态。

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **格式** | 单个 JSON 文件（`ConversationRecord`） | JSONL（每行一个事件） |
| **文件名** | `session-{timestamp}-{id-prefix}.json` | JSONL per session |
| **索引** | `logs.json`（按项目） | `projects.jsonl` + `history.jsonl` |
| **项目隔离** | `~/.gemini/tmp/{project-slug}/chats/` | `~/.claude/projects/{path-encoded}/` |
| **项目标识** | SHA-256 hash + 短名映射（`projects.json`） | 路径编码（`/` -> `-`） |

### Gemini CLI 会话结构（`ConversationRecord`）

```typescript
interface ConversationRecord {
  sessionId: string;
  projectHash: string;
  startTime: string;
  lastUpdated: string;
  // messages 数组包含完整对话
}

interface MessageRecord {
  id: string;
  timestamp: string;
  content: PartListUnion;
  type: 'user' | 'gemini' | 'info' | 'error' | 'warning';
  // Gemini 消息特有字段
  toolCalls?: ToolCallRecord[];  // 工具调用内嵌
  thoughts?: ThoughtSummary[];   // 思考过程内嵌
  tokens?: TokensSummary;        // Token 用量内嵌
  model?: string;                // 使用的模型
}
```

### Token 用量记录差异

| 字段 | Gemini CLI (`TokensSummary`) | Claude Code |
|------|------------------------------|-------------|
| 输入 | `input` (promptTokenCount) | `input_tokens` |
| 输出 | `output` (candidatesTokenCount) | `output_tokens` |
| 缓存 | `cached` (cachedContentTokenCount) | `cache_creation_input_tokens` + `cache_read_input_tokens` |
| 思考 | `thoughts` (thoughtsTokenCount) | 无独立字段 |
| 工具 | `tool` (toolUsePromptTokenCount) | 无独立字段 |
| 总计 | `total` (totalTokenCount) | 计算所得 |

> 📌 **关键差异**：Gemini CLI 使用**扁平 6 字段**结构记录 token，其中 `cached` 是单一数值。Claude Code 将 cache 分为 `cache_creation` 和 `cache_read` 两个字段，提供更精细的 cache 分析能力。Gemini CLI 额外追踪 `thoughts` 和 `tool` 两个 Claude Code 没有独立追踪的维度。

---

## 7 Memory 系统：GEMINI.md vs CLAUDE.md

两者都使用 Markdown 文件存储项目/用户级指令，但 Gemini CLI 的 memory 系统远比 Claude Code 复杂。

### Gemini CLI 的分层 Memory（`HierarchicalMemory`）

```typescript
interface HierarchicalMemory {
  global?: string;     // 来自 ~/.gemini/GEMINI.md 或 memory.md
  extension?: string;  // 来自活跃扩展的 contextFiles
  project?: string;    // 来自项目目录中的 GEMINI.md（多层级）
}
```

Memory 发现机制（`memoryDiscovery.ts`）：

1. **全局 Memory**：`~/.gemini/GEMINI.md` 或 `~/.gemini/memory.md`
2. **扩展 Memory**：每个活跃扩展声明的 `contextFiles`
3. **项目 Memory**：
   - **向上遍历**：从 CWD 向上直到 project root 的父目录，收集每层的 GEMINI.md
   - **向下搜索**：通过 BFS 在子目录中查找 GEMINI.md（受 `discoveryMaxDirs` 限制）
   - **JIT 加载**：工具访问新子目录时动态加载该路径上的 GEMINI.md

**@import 机制**：GEMINI.md 文件支持 `@path/to/file` 语法导入其他文件内容（`memoryImportProcessor.ts`）。导入处理器：
- 防止循环导入（`processedFiles` Set 追踪）
- 限制最大深度（`maxDepth`）
- 排除代码块内的 `@` 引用
- 支持 `tree` 和 `flat` 两种导入格式
- 路径安全检查（必须在 project root 内）

Memory 拼接格式：
```
--- Context from: relative/path/GEMINI.md ---
[文件内容]
--- End of Context from: relative/path/GEMINI.md ---
```

### Claude Code 的 CLAUDE.md

- **全局**：`~/.claude/CLAUDE.md`
- **项目**：项目根目录 `CLAUDE.md` + `.claude/CLAUDE.md`
- 无 `@import` 支持
- 无向下搜索
- 无 Extension memory 层
- 无 JIT 动态加载
- 简单拼接，无分层标注

> 💡 **核心差异**：Gemini CLI 的 Memory 系统是三层分层的（global/extension/project），支持 `@import` 文件导入、多目录 BFS 发现、JIT 加载。Claude Code 的 CLAUDE.md 是简单的两层拼接。Gemini CLI 还有自动去重机制（基于 inode 而非路径字符串），处理大小写不敏感的文件系统。

---

## 8 自定义命令：TOML Commands + Skills vs Skills

### Gemini CLI Custom Commands

Gemini CLI 有两套自定义命令机制：

**1. TOML Commands**：
- 存储位置：`~/.gemini/commands/` 和 `.gemini/commands/`
- 格式：TOML 文件定义 command 名称、描述和 prompt 模板
- 触发方式：`/command-name` slash command

**2. Skills**：
- 存储位置：`~/.gemini/skills/`、`.gemini/skills/`、`.agents/skills/`
- 格式：独立的文件定义
- 发现优先级：Built-in < Extension < User < Workspace
- 通过 `ActivateSkillTool` 触发
- `SkillManager` 管理发现和生命周期
- 管理员可以通过 `adminSkillsEnabled` 控制启用状态

### Claude Code Skills

- 通过 Skill tool 触发
- 通过项目配置定义
- 无 TOML command 对应物
- 无分层优先级系统

> 📌 **差异**：Gemini CLI 同时支持 TOML Commands（简单、声明式）和 Skills（复杂、可编程），并且有完整的优先级链。Claude Code 的 Skill 系统功能更集中但更简单。

---

## 9 Sandbox：多后端声明 vs 内置沙箱

### Gemini CLI Sandbox 配置

Gemini CLI 在 `SandboxConfig` 中声明式地支持多种容器/沙箱后端：

```typescript
interface SandboxConfig {
  enabled: boolean;
  allowedPaths?: string[];
  networkAccess?: boolean;
  command?: 'docker' | 'podman' | 'sandbox-exec' | 'runsc' | 'lxc';
  image?: string;
}
```

| 后端 | 类型 | 平台 |
|------|------|------|
| `docker` | 容器 | 全平台 |
| `podman` | 容器 | Linux/macOS |
| `sandbox-exec` | macOS 内置沙箱 | macOS only |
| `runsc` (gVisor) | 用户态内核沙箱 | Linux only |
| `lxc` | Linux Containers | Linux only |

当前实际实现中，`LocalSandboxManager.prepareCommand()` 抛出 `"Tool sandboxing is not yet implemented."`，表明 **sandbox 功能仍在开发中**。目前生效的是 `NoopSandboxManager`，仅执行**环境变量清洗**（`sanitizeEnvironment`）。

### Claude Code Sandbox

- 内置的命令执行沙箱
- 无需配置容器后端
- 限制文件系统访问和网络访问
- 开箱即用

> ⚠️ **注意**：Gemini CLI 的 sandbox 配置虽然设计了丰富的后端选项，但截至源码分析时实际的沙箱化尚未实现。Claude Code 的沙箱虽然配置选项少，但实际可用。

---

## 10 Hooks 系统：11 事件类型 vs Claude Hooks

### Gemini CLI Hook 事件（`HookEventName` enum）

| 事件名 | 触发时机 | 特殊能力 |
|--------|---------|---------|
| `BeforeTool` | 工具执行前 | 可修改 `tool_input`，可 block/deny |
| `AfterTool` | 工具执行后 | 可注入 `additionalContext`，可触发 `tailToolCallRequest` |
| `BeforeAgent` | Agent 循环开始前 | 可注入上下文 |
| `AfterAgent` | Agent 循环结束后 | 可 `clearContext` 清除上下文 |
| `BeforeModel` | LLM 调用前 | 可修改 `llm_request`，可返回合成 `llm_response` |
| `AfterModel` | LLM 调用后 | 可修改 `llm_response` |
| `BeforeToolSelection` | 工具选择前 | 可修改 `toolConfig` |
| `Notification` | 通知事件（如工具权限请求） | 支持 `ToolPermission` 类型 |
| `SessionStart` | 会话开始 | 区分 `startup`/`resume`/`clear` |
| `SessionEnd` | 会话结束 | 区分 `exit`/`clear`/`logout` |
| `PreCompress` | 上下文压缩前 | 区分 `manual`/`auto` |

Hook 实现分为两种：
- **CommandHookConfig**：执行外部命令，接收 JSON stdin，输出 JSON stdout
- **RuntimeHookConfig**：直接执行 TypeScript 函数（`HookAction`）

Hook 配置来源（`ConfigSource` enum）：`System > Project > User > Extensions > Runtime`

Hook 通用输入（`HookInput`）：
```typescript
interface HookInput {
  session_id: string;
  transcript_path: string;
  cwd: string;
  hook_event_name: string;
  timestamp: string;
}
```

Hook 通用输出（`HookOutput`）：
```typescript
interface HookOutput {
  continue?: boolean;       // false = 停止执行
  stopReason?: string;
  suppressOutput?: boolean;
  systemMessage?: string;   // 注入系统消息
  decision?: 'ask' | 'block' | 'deny' | 'approve' | 'allow';
  reason?: string;
  hookSpecificOutput?: Record<string, unknown>;
}
```

### Claude Code Hooks

Claude Code 的 hooks 系统覆盖以下事件：
- `PreToolUse` — 工具使用前
- `PostToolUse` — 工具使用后
- `Notification` — 通知
- `Stop` — 停止

> 💡 **关键差异**：Gemini CLI 的 hooks 有 11 种事件类型，包括 `BeforeModel`/`AfterModel`（拦截 LLM 请求/响应）、`BeforeToolSelection`（动态修改工具配置）等 Claude Code 没有的深层 hook 点。Gemini CLI 的 hook 还支持 `tailToolCallRequest`（工具执行后自动触发另一个工具）。

---

## 11 Extension 系统：完整打包系统 vs 无

Gemini CLI 有一套完整的 **Extension 打包和生命周期管理** 系统，Claude Code 没有对应的扩展系统。

### Gemini CLI Extension（`GeminiCLIExtension`）

```typescript
interface GeminiCLIExtension {
  name: string;
  version: string;
  isActive: boolean;
  path: string;
  id: string;
  installMetadata?: ExtensionInstallMetadata;
  // 扩展可贡献的资源
  mcpServers?: Record<string, MCPServerConfig>;
  contextFiles: string[];       // Memory 贡献
  excludeTools?: string[];      // 排除特定工具
  hooks?: { [K in HookEventName]?: HookDefinition[] };
  settings?: ExtensionSetting[];
  skills?: SkillDefinition[];
  agents?: AgentDefinition[];
  themes?: CustomTheme[];       // 自定义主题
  rules?: PolicyRule[];         // 策略规则贡献
  checkers?: SafetyCheckerRule[];
  plan?: { directory?: string };
}
```

安装来源类型（`ExtensionInstallMetadata`）：
- `git` — Git 仓库克隆
- `local` — 本地目录链接
- `link` — 符号链接
- `github-release` — GitHub Release 下载

Extension 存储目录：`.gemini/extensions/`，配置文件：`gemini-extension.json`

一个扩展可以同时贡献 MCP servers、memory files、hooks、skills、agents、themes、policy rules、safety checkers——这是一个**全栈插件系统**。

### Claude Code

Claude Code 不具备独立的扩展系统。定制能力主要通过 MCP servers、CLAUDE.md、和 settings.json 实现。

> 📌 **核心差异**：Gemini CLI 的 Extension 系统是一个完整的插件平台，一个扩展可以贡献从 UI 主题到安全策略的任何东西。Claude Code 的可定制性分散在多个不同的配置机制中。

---

## 12 安全策略：Policy Engine + Trusted Folders vs 简单策略

### Gemini CLI Policy Engine（`PolicyEngine`）

Policy Engine 是 Gemini CLI 安全架构的核心组件：

```typescript
class PolicyEngine {
  private rules: PolicyRule[];        // 工具执行策略规则
  private checkers: SafetyCheckerRule[];  // 安全检查器
  private hookCheckers: HookCheckerRule[]; // Hook 执行检查器
}
```

**PolicyRule** 结构：
- `toolName` — 匹配工具名（支持 `*` 通配符、`mcp_serverName_*` MCP 通配符）
- `argsPattern` — 正则匹配工具参数
- `decision` — `ALLOW` / `DENY` / `ASK_USER`
- `priority` — 数值优先级（越高越先匹配）
- `modes` — 限制规则适用的 `ApprovalMode`（`default`/`autoEdit`/`yolo`/`plan`）
- `mcpName` — 限制 MCP server 来源
- `subagent` — 限制特定子代理
- `toolAnnotations` — 基于工具注解匹配
- `source` — 规则来源标识
- `allowRedirection` — Shell 命令重定向控制

**Shell 命令安全**：Policy Engine 对 Shell 工具有特殊处理——自动解析复合命令（`&&`、`||`、`;`、`|`），对每个子命令递归检查策略。检测重定向操作（`>`、`>>`）自动提升为 `ASK_USER`。

**Safety Checkers**：
- `allowed-path` — 检查文件路径是否在允许范围内
- `conseca` — Google 内部安全检查器
- External checkers — 可扩展的外部检查器

**Folder Trust 机制**：
- `trustedFolders.json` 存储受信任目录列表
- 不受信任的目录中不加载 project agents 和 workspace skills
- 通过 `FolderTrustDiscoveryService` 管理

**Policy 来源**：
- System policies（`/etc/gemini-cli/policies/`）
- User policies（`~/.gemini/policies/`）
- Workspace policies（`.gemini/policies/`）
- Extension 贡献的 rules
- Agent Registry 动态注册的规则
- Auto-saved policies（`auto-saved.toml`）
- TOML 格式定义

**ApprovalMode** enum：
- `default` — 修改操作需要确认
- `autoEdit` — 自动批准文件编辑
- `yolo` — 自动批准所有操作
- `plan` — 规划模式，限制只能写入 plans 目录

### Claude Code 安全模型

- 简单的工具白名单/黑名单
- `allowedTools` / `disallowedTools`
- 权限提示机制
- 无优先级规则引擎
- 无 TOML 策略文件
- 无安全检查器框架

> ⚠️ **关键差异**：Gemini CLI 的 PolicyEngine 是一个企业级的规则引擎，支持优先级排序、通配符匹配、正则参数匹配、多层策略来源合并、Shell 命令深度解析。Claude Code 的安全模型更简单直接。

---

## 13 Token 追踪：扁平 6 字段 vs 嵌套 Cache 拆分

### Gemini CLI（`TokensSummary`）

```typescript
interface TokensSummary {
  input: number;     // promptTokenCount
  output: number;    // candidatesTokenCount
  cached: number;    // cachedContentTokenCount（单一数值）
  thoughts?: number; // thoughtsTokenCount（Gemini 特有）
  tool?: number;     // toolUsePromptTokenCount
  total: number;     // totalTokenCount
}
```

### Claude Code Token 结构

```json
{
  "input_tokens": 1234,
  "output_tokens": 567,
  "cache_creation_input_tokens": 100,
  "cache_read_input_tokens": 200
}
```

| 对比维度 | Gemini CLI | Claude Code |
|----------|-----------|-------------|
| Cache 粒度 | 单一 `cached` 值 | 区分 `creation` 和 `read` |
| 思考 Token | 独立 `thoughts` 字段 | 无独立字段 |
| 工具 Token | 独立 `tool` 字段 | 无独立字段 |
| 总计 | API 直接返回 `total` | 需自行计算 |
| 嵌套深度 | 扁平结构 | 扁平结构 |

> 💡 **总结**：Gemini CLI 追踪更多 token 维度（thoughts、tool），但 cache 粒度较粗。Claude Code 的 cache 拆分对成本优化分析更有价值。

---

## 14 认证体系：多源认证 vs Anthropic API/OAuth

### Gemini CLI 认证方式（`AuthType` enum）

| 认证类型 | enum 值 | 适用场景 |
|----------|---------|---------|
| Google OAuth（个人） | `oauth-personal` | 个人用户，浏览器登录 |
| Gemini API Key | `gemini-api-key` | `GEMINI_API_KEY` 环境变量 |
| Vertex AI | `vertex-ai` | Google Cloud Vertex AI |
| Cloud Shell | `cloud-shell` | Google Cloud Shell 环境 |
| Compute ADC | `compute-default-credentials` | GCE/GKE 默认凭证 |
| Gateway | `gateway` | 企业网关代理 |

认证检测优先级（`getAuthTypeFromEnv()`）：
1. `GOOGLE_GENAI_USE_GCA=true` -> OAuth
2. `GOOGLE_GENAI_USE_VERTEXAI=true` -> Vertex AI
3. `GEMINI_API_KEY` 存在 -> API Key
4. `CLOUD_SHELL=true` 或 `GEMINI_CLI_USE_COMPUTE_ADC=true` -> Compute ADC

凭证存储：
- OAuth 凭证：`~/.gemini/oauth_creds.json`
- API Key：通过环境变量或 keychain service
- 账号管理：`~/.gemini/google_accounts.json`

### Claude Code 认证方式

| 认证类型 | 适用场景 |
|----------|---------|
| Anthropic API Key | `ANTHROPIC_API_KEY` 环境变量 |
| Claude Pro/Team OAuth | 浏览器登录 |
| AWS Bedrock | 通过 AWS 凭证 |
| Google Vertex AI | 通过 GCP 凭证 |

> 📌 **差异**：Gemini CLI 的认证更紧密地集成 Google Cloud 生态（OAuth、Vertex AI、Cloud Shell、ADC、Gateway），适合企业 GCP 用户。Claude Code 支持 Anthropic 原生和多云部署（Bedrock、Vertex）。

---

## 15 UI 架构：React/Ink TUI vs 终端输出

### Gemini CLI UI 技术栈

Gemini CLI 使用 **React + Ink** 构建终端 UI：

- `packages/cli/src/ui/App.tsx` — 根组件
- 使用 JSX/TSX 编写 TUI 组件
- 支持 **alternate buffer**（类似 vim 的全屏模式）
- 支持 **screen reader** 无障碍布局（`ScreenReaderAppLayout`）
- 完整的组件化架构：
  - `contexts/` — React Context（UIState、Streaming 等）
  - `components/` — 可复用组件
  - `layouts/` — 布局组件
  - `hooks/` — React hooks
  - `themes/` — 主题系统（支持 dark/light + 自定义主题）
  - `editors/` — 内嵌编辑器
  - `key/` — 键盘绑定

主题系统支持：
- 内置 Default Light / Default Dark
- Extension 贡献的 `CustomTheme`
- 完整的色彩语义系统（`semantic-colors.ts`）
- 支持 vim mode 键绑定
- 自定义 keybindings（`~/.gemini/keybindings.json`）

### Claude Code UI

- 纯终端输出（非 React TUI）
- Markdown 渲染
- 无主题系统
- 无 alternate buffer 模式
- 简洁的提示符交互

> 💡 **关键差异**：Gemini CLI 的 React/Ink TUI 是一个完整的终端 UI 框架，支持组件化、主题、无障碍、键绑定。Claude Code 采用更传统的终端输出方式，启动更快、资源占用更低。

---

## 综合对比总结

| 维度 | Gemini CLI | Claude Code | 优势方 |
|------|-----------|-------------|--------|
| 架构 | Monorepo 7 包 | 单包 | Gemini CLI（可扩展性） |
| 配置层级 | 7 层（含 System） | 4 层 | Gemini CLI（企业管控） |
| Model Routing | 7 策略链 + auto 模式 | 手动选择 | Gemini CLI（智能路由） |
| 工具系统 | Registry + Discovery + MCP | 内置 + MCP | Gemini CLI（可扩展性） |
| Agent 系统 | Local + Remote + A2A | Agent Tool | Gemini CLI（多 Agent 协作） |
| 会话格式 | JSON | JSONL | Claude Code（流式分析） |
| Memory | 3 层 + @import + JIT | 2 层拼接 | Gemini CLI（精细控制） |
| 自定义命令 | TOML + Skills | Skills | Gemini CLI（双轨制） |
| Sandbox | 5 后端（未实现） | 内置可用 | Claude Code（实际可用） |
| Hooks | 11 事件类型 | 4 事件类型 | Gemini CLI（覆盖面） |
| Extension | 全栈插件系统 | 无 | Gemini CLI（生态潜力） |
| 安全策略 | PolicyEngine 规则引擎 | 简单白黑名单 | Gemini CLI（企业级安全） |
| Token 追踪 | 6 字段 + thoughts/tool | Cache 拆分 | 各有侧重 |
| 认证 | 6 种 Google 认证 | API Key + OAuth + 多云 | 各有侧重 |
| UI | React/Ink TUI | 纯终端 | 取决于偏好 |

> 📌 **总体评价**：Gemini CLI 在架构层面显著更复杂、更模块化、更面向企业和扩展生态。它本质上是一个**可编程的 AI Agent 平台**，而不仅仅是一个终端工具。Claude Code 则追求**开箱即用的简洁体验**，配置少、启动快、核心功能完善。两者的设计哲学差异反映了 Google（平台化、可定制）和 Anthropic（产品化、直接可用）不同的工程文化。

---

## 16 迁移指南：CLAUDE.md → GEMINI.md 格式转换

从 Claude Code 迁移到 Gemini CLI（或反向迁移）时，核心 memory 文件的格式需要做适配。两者都使用 Markdown 格式定义项目指令，但在文件位置、加载机制和特殊语法上存在差异。

### 16.1 CLAUDE.md vs GEMINI.md 并排对比

```
┌─────────────────────────────────────┬──────────────────────────────────────┐
│         CLAUDE.md                   │          GEMINI.md                   │
├─────────────────────────────────────┼──────────────────────────────────────┤
│ # CLAUDE.md                        │ # GEMINI.md                          │
│                                     │                                      │
│ Write code that is correct,         │ Write code that is correct,          │
│ readable, and maintainable.         │ readable, and maintainable.          │
│                                     │                                      │
│ ## General Rules                    │ ## General Rules                     │
│                                     │                                      │
│ - One function does one thing.      │ - One function does one thing.       │
│ - No magic numbers or strings.      │ - No magic numbers or strings.       │
│ - Fail fast, fail loud.             │ - Fail fast, fail loud.              │
│                                     │                                      │
│ ## Python Conventions               │ ## Python Conventions                │
│                                     │                                      │
│ - **Linter:** Ruff.                 │ - **Linter:** Ruff.                  │
│ - **Types:** Annotate all sigs.     │ - **Types:** Annotate all sigs.      │
│                                     │                                      │
│ ## ❌ 无 @import 支持               │ ## ✅ 支持 @import                   │
│ ## ❌ 无子目录发现                   │ @docs/coding-standards.md            │
│ ## ❌ 无 Extension memory           │ @configs/team-rules.md               │
│                                     │                                      │
│ 位置：                              │ 位置：                               │
│   ~/.claude/CLAUDE.md (全局)        │   ~/.gemini/GEMINI.md (全局)         │
│   项目根/CLAUDE.md (项目)           │   项目根/GEMINI.md (项目)            │
│   项目根/.claude/CLAUDE.md (项目)   │   任意子目录/GEMINI.md (自动发现)    │
└─────────────────────────────────────┴──────────────────────────────────────┘
```

### 16.2 迁移操作步骤

从 Claude Code 迁移到 Gemini CLI 时，按以下步骤转换 memory 文件：

```bash
# 步骤 1：复制全局 memory
cp ~/.claude/CLAUDE.md ~/.gemini/GEMINI.md

# 步骤 2：复制项目级 memory
cp ./CLAUDE.md ./GEMINI.md
cp ./.claude/CLAUDE.md ./.gemini/GEMINI.md 2>/dev/null

# 步骤 3（可选）：利用 @import 拆分大文件
# 将 GEMINI.md 中的独立章节拆分为子文件
# 然后在主 GEMINI.md 中使用 @import 引用
```

> 💡 **迁移提示**：Markdown 语法本身完全兼容，无需修改内容格式。主要工作是调整文件路径和利用 Gemini CLI 的 `@import` 特性重构组织方式。反向迁移时需要将 `@import` 引用的内容内联回主文件。

### 16.3 Memory 加载机制差异表

| 特性 | CLAUDE.md | GEMINI.md |
|------|-----------|-----------|
| **全局路径** | `~/.claude/CLAUDE.md` | `~/.gemini/GEMINI.md` 或 `~/.gemini/memory.md` |
| **项目路径** | 项目根 `CLAUDE.md` + `.claude/CLAUDE.md` | 项目根 `GEMINI.md`（多层级） |
| **子目录发现** | 不支持 | BFS 自动发现，受 `discoveryMaxDirs` 限制 |
| **JIT 加载** | 不支持 | 工具访问新目录时动态加载 |
| **@import** | 不支持 | 支持 `@path/to/file` 语法，含循环检测 |
| **拼接标注** | 简单拼接 | 带 `--- Context from: ... ---` 分层标注 |
| **Extension memory** | 不支持 | 扩展通过 `contextFiles` 贡献 |
| **去重机制** | 无 | 基于 inode 去重 |

---

## 17 会话格式转换：JSONL vs JSON

Claude Code 和 Gemini CLI 的会话存储格式有本质区别。转换会话数据需要理解两种格式的字段映射关系。

### 17.1 Claude Code JSONL 会话条目

Claude Code 使用 **JSONL 流式格式**，每行一个事件（用户消息、助手回复、工具调用等）。以下是一个包含工具调用的助手消息：

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
        "text": "Let me search for the configuration file..."
      },
      {
        "type": "tool_use",
        "id": "toolu_01DAWALsTf6siYK1fiZfh8AK",
        "name": "Grep",
        "input": {
          "pattern": "settings",
          "path": "src/config"
        }
      }
    ],
    "usage": {
      "input_tokens": 512,
      "output_tokens": 128,
      "cache_creation_input_tokens": 4022,
      "cache_read_input_tokens": 19532
    }
  }
}
```

### 17.2 Gemini CLI JSON 会话结构

Gemini CLI 使用**单个 JSON 文件**，包含完整的 `ConversationRecord`。工具调用内嵌于 `gemini` 类型的消息中：

```json
{
  "sessionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "projectHash": "3f7a2b1c",
  "startTime": "2026-03-14T10:30:00.000Z",
  "lastUpdated": "2026-03-14T10:35:22.456Z",
  "kind": "main",
  "messages": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2026-03-14T10:30:05.123Z",
      "type": "user",
      "content": "Search for the configuration file in the project."
    },
    {
      "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "timestamp": "2026-03-14T10:30:08.456Z",
      "type": "gemini",
      "content": "Let me search for the configuration file...",
      "model": "gemini-2.5-pro",
      "toolCalls": [
        {
          "id": "call_001",
          "name": "grep",
          "args": { "pattern": "settings", "path": "src/config" },
          "result": "Found 3 matches in src/config/settings.ts",
          "status": "completed",
          "timestamp": "2026-03-14T10:30:09.000Z",
          "displayName": "Grep",
          "description": "Search for pattern in files"
        }
      ],
      "thoughts": [
        {
          "subject": "Planning",
          "description": "User wants to find config files, grep is the best tool.",
          "timestamp": "2026-03-14T10:30:07.500Z"
        }
      ],
      "tokens": {
        "input": 456,
        "output": 89,
        "cached": 200,
        "thoughts": 32,
        "tool": 15,
        "total": 792
      }
    }
  ]
}
```

### 17.3 会话字段映射表

| 概念 | Claude Code (JSONL) | Gemini CLI (JSON) |
|------|--------------------|--------------------|
| **会话标识** | `sessionId`（UUID v4） | `sessionId`（UUID v4） |
| **项目标识** | 路径编码（`/` → `-`）作为目录名 | `projectHash`（SHA-256 短哈希） |
| **消息 ID** | `uuid`（UUID v4） | `id`（UUID v4） |
| **消息类型** | `type: "user" \| "assistant"` | `type: "user" \| "gemini" \| "info" \| "error" \| "warning"` |
| **时间戳** | `timestamp`（毫秒 Unix epoch） | `timestamp`（ISO 8601 字符串） |
| **模型信息** | `message.model` | `model`（消息顶层字段） |
| **消息内容** | `message.content`（Anthropic Content Block 数组） | `content`（PartListUnion） |
| **工具调用** | `content` 数组中的 `tool_use` 块 | 独立 `toolCalls` 数组 |
| **工具结果** | 下一条 user 消息中的 `tool_result` 块 | `toolCalls[].result` 内嵌 |
| **思考过程** | `content` 数组中的 `thinking` 块 | 独立 `thoughts` 数组 |
| **Token 统计** | `message.usage` 对象 | `tokens`（`TokensSummary`） |
| **消息链接** | `parentUuid` 链式引用 | 数组索引顺序 |
| **停止原因** | `message.stop_reason` | 无显式字段 |
| **请求 ID** | `requestId`（Anthropic API ID） | 无 |
| **工作目录** | `cwd` | 无（全局记录） |
| **Git 分支** | `gitBranch` | 无 |

> ⚠️ **转换注意**：Claude Code 将工具结果放在**下一条 user 消息**中（`tool_result` 块），而 Gemini CLI 将工具结果**内嵌在同一条 gemini 消息的 `toolCalls[].result`** 中。这是最关键的结构差异，转换时需要合并/拆分消息边界。

---

## 18 Tool Call 格式对比：tool_use vs functionCall

两个平台的工具调用格式反映了 Anthropic API 和 Google Gemini API 各自的设计哲学。

### 18.1 Claude Code：tool_use Content Block

Claude Code 使用 Anthropic Messages API 的 `tool_use` content block 格式。工具调用和文本输出混合在同一个 `content` 数组中：

```json
{
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Let me read that file for you."
    },
    {
      "type": "tool_use",
      "id": "toolu_01DAWALsTf6siYK1fiZfh8AK",
      "name": "Read",
      "input": {
        "file_path": "/Users/dev/project/src/config.ts"
      }
    }
  ],
  "stop_reason": "tool_use"
}
```

工具结果作为**下一轮 user 消息**返回：

```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01DAWALsTf6siYK1fiZfh8AK",
      "content": [
        {
          "type": "text",
          "text": "export const CONFIG = { port: 3000, host: 'localhost' };"
        }
      ],
      "is_error": false
    }
  ]
}
```

### 18.2 Gemini CLI：functionCall Part

Gemini CLI 使用 Google Gemini API 的 `functionCall` part 格式。工具调用作为 `Part` 对象存在于 `parts` 数组中：

```json
{
  "role": "model",
  "parts": [
    {
      "text": "Let me read that file for you."
    },
    {
      "functionCall": {
        "name": "read_file",
        "args": {
          "file_path": "/Users/dev/project/src/config.ts"
        },
        "id": "call_001"
      }
    }
  ]
}
```

工具结果通过 `functionResponse` part 返回：

```json
{
  "role": "user",
  "parts": [
    {
      "functionResponse": {
        "id": "call_001",
        "name": "read_file",
        "response": {
          "output": "export const CONFIG = { port: 3000, host: 'localhost' };"
        }
      }
    }
  ]
}
```

### 18.3 Tool Call 格式字段映射表

| 维度 | Claude Code (Anthropic API) | Gemini CLI (Gemini API) |
|------|----------------------------|------------------------|
| **调用封装** | `content[]` 中的 `tool_use` 对象 | `parts[]` 中含 `functionCall` 的 Part |
| **调用 ID** | `id`（`toolu_` 前缀） | `functionCall.id`（自定义格式） |
| **工具名** | `name` | `functionCall.name` |
| **参数** | `input`（JSON 对象） | `functionCall.args`（JSON 对象） |
| **结果类型** | `tool_result` content block | `functionResponse` Part |
| **结果关联** | `tool_use_id` 引用调用 ID | `functionResponse.id` 引用调用 ID |
| **错误标记** | `is_error: true` | `response` 中携带错误信息 |
| **停止信号** | `stop_reason: "tool_use"` | 无显式停止信号 |
| **多工具并行** | 多个 `tool_use` 块在同一 `content` 数组 | 多个 `functionCall` Part 在同一 `parts` 数组 |
| **思考过程** | `thinking` content block | `thought: true` 标记的 text Part |

> 📌 **格式本质**：两种格式都支持在单条消息中混合文本和工具调用，也都支持并行工具调用。核心区别在于命名约定（`tool_use`/`tool_result` vs `functionCall`/`functionResponse`）和嵌套层级（Claude Code 的 `input` 对应 Gemini 的 `functionCall.args`，多了一层包装）。

---

## 19 配置迁移：settings.json 格式转换

两个平台的 `settings.json` 配置文件在结构和功能上有显著差异。以下是一个典型的迁移对照示例。

### 19.1 Claude Code settings.json

Claude Code 的配置文件结构扁平，主要关注权限和工具管控：

```json
{
  "permissions": {
    "allow": [
      "Bash(npm run *)",
      "Bash(git *)",
      "Read",
      "Write",
      "Edit",
      "Grep",
      "Glob"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Bash(curl * | bash)"
    ]
  },
  "env": {
    "ANTHROPIC_MODEL": "claude-sonnet-4-20250514",
    "CLAUDE_CODE_MAX_TURNS": "50"
  },
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/dev/project"]
    }
  }
}
```

### 19.2 Gemini CLI settings.json

Gemini CLI 的配置文件采用分层嵌套结构，覆盖 UI、模型、工具、安全等多个维度：

```json
{
  "general": {
    "defaultApprovalMode": "default",
    "vimMode": false,
    "sessionRetention": {
      "enabled": true,
      "maxAge": "30d"
    }
  },
  "ui": {
    "theme": "default-dark",
    "showLineNumbers": true,
    "inlineThinkingMode": "off"
  },
  "model": {
    "name": "gemini-2.5-pro",
    "maxSessionTurns": -1,
    "compressionThreshold": 0.5
  },
  "tools": {
    "shell": {
      "environmentVariables": {
        "NODE_ENV": "development"
      }
    }
  },
  "security": {
    "allowedPaths": ["/Users/dev/project"],
    "disableYoloMode": false
  },
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/dev/project"]
    }
  },
  "agents": {
    "overrides": {
      "codebase_investigator": {
        "disabled": false
      }
    }
  }
}
```

### 19.3 配置项映射表

| 功能 | Claude Code 配置 | Gemini CLI 配置 |
|------|-----------------|----------------|
| **模型选择** | `env.ANTHROPIC_MODEL` 或 `--model` flag | `model.name` |
| **MCP Servers** | `mcpServers`（结构相同） | `mcpServers`（结构相同） |
| **工具白名单** | `permissions.allow` | PolicyEngine TOML 规则 |
| **工具黑名单** | `permissions.deny` | PolicyEngine TOML 规则或 `excludeTools` |
| **审批模式** | 无（默认逐个确认） | `general.defaultApprovalMode`（`default`/`auto_edit`/`yolo`/`plan`） |
| **环境变量** | `env` 对象 | `tools.shell.environmentVariables` |
| **主题** | 不支持 | `ui.theme`（含自定义主题） |
| **Vim 模式** | 不支持 | `general.vimMode` |
| **会话保留** | 不支持自动清理 | `general.sessionRetention` |
| **上下文压缩** | 自动管理 | `model.compressionThreshold` |
| **Agent 覆盖** | 不支持 | `agents.overrides` |
| **Sandbox** | 内置不可配 | `tools.sandbox`（多后端） |

> 💡 **迁移提示**：MCP Servers 配置是两个平台之间**最容易迁移**的部分，格式几乎完全一致。权限/安全策略迁移最复杂——Claude Code 的 `permissions.allow/deny` 列表需要转换为 Gemini CLI 的 TOML PolicyRule 格式。

---

## 20 终端输出对比：相同操作的 CLI 呈现

以下对比两个工具在执行相同操作时的终端输出样式差异。

### 20.1 文件搜索操作

**Claude Code 终端输出：**

```
$ claude "search for all Python test files"

● I'll search for Python test files in your project.

  ● Glob  **/*.py pattern matching

    Found 12 files:
    src/tests/test_api.py
    src/tests/test_models.py
    src/tests/test_utils.py
    src/tests/test_integration.py
    ...

  I found 12 Python test files across the project. They are
  organized in the src/tests/ directory following the standard
  pytest naming convention (test_*.py).
```

**Gemini CLI 终端输出：**

```
$ gemini "search for all Python test files"

✦ Searching for Python test files in the project...

  ┌─ glob ──────────────────────────────────────┐
  │ Pattern: **/*.py                            │
  │                                             │
  │ Found 12 files:                             │
  │   src/tests/test_api.py                     │
  │   src/tests/test_models.py                  │
  │   src/tests/test_utils.py                   │
  │   src/tests/test_integration.py             │
  │   ...                                       │
  └─────────────────────────────────────────────┘

I found 12 Python test files across the project. They are organized
in the src/tests/ directory following the standard pytest naming
convention (test_*.py).

╭─ gemini-2.5-pro ──── 456 input · 89 output · 200 cached ────╮
╰──────────────────────────────────────────────────────────────╯
```

### 20.2 文件编辑操作

**Claude Code 终端输出：**

```
$ claude "add a docstring to the calculate_tax function"

● I'll read the file first to find the function.

  ● Read  src/utils/tax.py

  ● Edit  src/utils/tax.py
    1 change:
    + def calculate_tax(amount: float, rate: float) -> float:
    +     """Calculate the tax for a given amount and rate.
    +
    +     Args:
    +         amount: The base amount to calculate tax on.
    +         rate: The tax rate as a decimal.
    +
    +     Returns:
    +         The calculated tax amount.
    +     """

  Done. Added a Google-style docstring to the calculate_tax function.
```

**Gemini CLI 终端输出：**

```
$ gemini "add a docstring to the calculate_tax function"

✦ I'll read the file first to find the function.

  ┌─ read_file ─────────────────────────────────┐
  │ src/utils/tax.py                            │
  └─────────────────────────────────────────────┘

  ┌─ edit ─── src/utils/tax.py ────── ✋ ───────┐
  │  def calculate_tax(amount, rate):           │
  │ +    """Calculate the tax for a given       │
  │ +    amount and rate.                       │
  │ +                                           │
  │ +    Args:                                  │
  │ +        amount: The base amount.           │
  │ +        rate: The tax rate as a decimal.   │
  │ +                                           │
  │ +    Returns:                               │
  │ +        The calculated tax amount.         │
  │ +    """                                    │
  │                                             │
  │         [Y]es / [N]o / [A]lways             │
  └─────────────────────────────────────────────┘

Done. Added a Google-style docstring to the calculate_tax function.
```

### 20.3 终端输出差异总结

| 维度 | Claude Code | Gemini CLI |
|------|-------------|-----------|
| **工具显示** | `● ToolName` 内联标记 | `┌─ tool_name ─┐` 边框面板 |
| **状态指示** | `●` 圆点 | `✦`（工作中）/ `✋`（需确认）/ `◇`（就绪） |
| **Token 信息** | 不显示在输出中 | Footer 区域实时显示 |
| **审批交互** | 自动询问 yes/no | 框内 `[Y]es / [N]o / [A]lways` |
| **Diff 格式** | 内联 `+/-` 差异 | 框内 `+/-` 差异 |
| **上下文面板** | 无 | 底部 Footer 显示模型名、token 用量、CWD |
| **主题** | 固定暗色 | 支持 dark/light/自定义主题切换 |
| **渲染引擎** | 标准终端输出 | React/Ink TUI 渲染 |

> 📌 **体验差异**：Claude Code 的输出风格更接近传统 CLI 工具——简洁、线性、快速。Gemini CLI 的 React/Ink TUI 提供了更丰富的视觉层次（边框、面板、Footer 状态栏），但也带来了更高的终端兼容性要求和启动开销。

---

## 21 使用场景决策树

根据项目需求和团队情况，可以按以下决策树选择工具：

```
                    ┌─────────────────────┐
                    │  需要 AI 编程助手？  │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │ 需要企业级管控？     │
                    │ (IT 策略/审计/合规)  │
                    └────┬──────────┬─────┘
                         │          │
                    Yes  │          │ No
                         │          │
                ┌────────▼──┐  ┌───▼───────────────┐
                │ Gemini CLI │  │ 需要多 Agent 协作？│
                │ (7层配置+  │  │ (A2A/远程Agent)    │
                │  Policy    │  └──┬──────────┬─────┘
                │  Engine)   │     │          │
                └────────────┘  Yes│          │No
                                   │          │
                          ┌────────▼──┐  ┌───▼───────────────┐
                          │ Gemini CLI │  │ 使用 Google Cloud？│
                          │ (A2A +     │  └──┬──────────┬─────┘
                          │  Agent     │     │          │
                          │  Registry) │  Yes│          │No
                          └────────────┘     │          │
                                    ┌────────▼──┐  ┌───▼───────────────┐
                                    │ Gemini CLI │  │ 需要插件生态？     │
                                    │ (Vertex +  │  │ (扩展/主题/DevTools│
                                    │  OAuth +   │  │  /Browser Agent)  │
                                    │  ADC)      │  └──┬──────────┬─────┘
                                    └────────────┘     │          │
                                                    Yes│          │No
                                              ┌────────▼──┐  ┌───▼───────────────┐
                                              │ Gemini CLI │  │ 追求开箱即用？     │
                                              │ (Extension │  │ (快速上手/低配置)  │
                                              │  System)   │  └──┬──────────┬─────┘
                                              └────────────┘     │          │
                                                              Yes│          │No
                                                    ┌────────────▼──┐  ┌───▼──────────┐
                                                    │  Claude Code   │  │ 按模型偏好选择│
                                                    │  (简洁/快速/   │  └──┬───────┬───┘
                                                    │   开箱即用)    │     │       │
                                                    └───────────────┘  Claude  Gemini
                                                                       模型     模型
                                                                        │       │
                                                              ┌─────────▼─┐ ┌───▼────────┐
                                                              │Claude Code │ │ Gemini CLI  │
                                                              └───────────┘ └────────────┘
```

> 💡 **选择建议**：
> - **个人开发者 + 快速上手** → Claude Code
> - **企业团队 + GCP 生态** → Gemini CLI
> - **需要可编程 Agent 平台** → Gemini CLI
> - **需要稳定的 Sandbox** → Claude Code（Gemini CLI sandbox 尚未实现）
> - **重视 Claude 模型质量** → Claude Code
> - **需要成本优化（auto 路由）** → Gemini CLI

---

## 22 成本对比：Token 定价与优化策略

### 22.1 模型定价对比表（2026 年 3 月）

| 模型 | 输入价格 ($/1M tokens) | 输出价格 ($/1M tokens) | 上下文窗口 | 备注 |
|------|----------------------|----------------------|-----------|------|
| **Claude Opus 4** | $15.00 | $75.00 | 200K | Anthropic 旗舰 |
| **Claude Sonnet 4** | $3.00 | $15.00 | 200K | 性价比推荐 |
| **Claude Haiku 3.5** | $0.80 | $4.00 | 200K | 最经济 |
| **Gemini 2.5 Pro** | $1.25 ~ $2.50 | $10.00 ~ $15.00 | 1M | 按 token 量阶梯定价 |
| **Gemini 2.5 Flash** | $0.15 ~ $0.30 | $1.50 ~ $3.50 | 1M | auto 路由默认选择 |
| **Gemini 2.5 Flash Lite** | $0.075 | $0.30 | 1M | 最经济 |

> ⚠️ **定价说明**：以上价格基于公开 API 定价，实际费用取决于使用方式。Gemini CLI 通过 Google 账号登录可使用免费额度；Claude Code 通过 Claude Pro/Team 订阅包含一定用量。两者都支持通过各自的企业级渠道（Vertex AI / AWS Bedrock）获取批量折扣。

### 22.2 Cache 机制成本优势

| 维度 | Claude Code | Gemini CLI |
|------|-------------|-----------|
| **Cache 类型** | Prompt caching（自动） | Context caching（自动） |
| **Cache 粒度** | 拆分为 creation + read | 单一 cached 数值 |
| **Cache 创建费** | 原价的 25% | 原价的 25% |
| **Cache 读取费** | 原价的 10% | 原价的 10% |
| **Cache TTL** | 5 分钟 / 1 小时（ephemeral） | 取决于配置 |
| **Cache 分析** | `cache_creation_input_tokens` + `cache_read_input_tokens` 独立追踪 | `cached` 单一数值 |

### 22.3 成本优化策略对比

| 策略 | Claude Code | Gemini CLI |
|------|-------------|-----------|
| **模型降级** | 手动切换 `--model` | `auto` 路由自动在 Pro/Flash 间切换 |
| **上下文压缩** | 自动管理 | `model.compressionThreshold` 可配置阈值 |
| **工具输出摘要** | 不支持 | `model.summarizeToolOutput` 可按工具配置 token budget |
| **会话 Turn 限制** | `CLAUDE_CODE_MAX_TURNS` 环境变量 | `model.maxSessionTurns` 配置项 |
| **Cache 优化** | Cache TTL 分级（5min/1h） | 基于内容自动 cache |
| **额度管理** | API key 额度 | `billing.overageStrategy`（`ask`/`always`/`never`） |

> 📌 **成本关键差异**：Gemini CLI 的 `auto` 模型路由是其最大的成本优化优势——简单查询自动使用 Flash（约 Pro 1/10 价格），复杂任务自动升级 Pro。Claude Code 没有自动路由，需要用户手动在 Opus/Sonnet/Haiku 之间切换。此外 Gemini 2.5 Flash 的定价显著低于 Claude Haiku，使 Gemini CLI 在大批量、简单任务场景下成本优势明显。

---

## References

| 源码路径 | 对应分析维度 |
|----------|-------------|
| `packages/core/src/index.ts` | 架构总览（导出 200+ 模块） |
| `packages/core/src/config/config.ts` | Config class、ConfigParameters |
| `packages/cli/src/config/settings.ts` | 7 层配置加载（SettingScope enum） |
| `packages/cli/src/config/settingsSchema.ts` | 配置 schema 定义 |
| `packages/core/src/routing/modelRouterService.ts` | 7 策略路由链 |
| `packages/core/src/routing/strategies/compositeStrategy.ts` | Chain of Responsibility 模式 |
| `packages/core/src/config/models.ts` | 模型别名和解析 |
| `packages/core/src/tools/tool-registry.ts` | ToolRegistry + DiscoveredTool |
| `packages/core/src/agents/registry.ts` | AgentRegistry + local/remote agent |
| `packages/core/src/agents/types.ts` | AgentDefinition 类型定义 |
| `packages/core/src/hooks/types.ts` | 11 种 HookEventName |
| `packages/core/src/policy/policy-engine.ts` | PolicyEngine 规则引擎 |
| `packages/core/src/policy/types.ts` | PolicyRule、ApprovalMode、SafetyCheckerConfig |
| `packages/core/src/config/storage.ts` | Storage 路径管理 |
| `packages/core/src/config/memory.ts` | HierarchicalMemory 接口 |
| `packages/core/src/utils/memoryDiscovery.ts` | Memory 发现和加载 |
| `packages/core/src/utils/memoryImportProcessor.ts` | @import 处理 |
| `packages/core/src/services/sandboxManager.ts` | Sandbox 多后端配置 |
| `packages/core/src/services/chatRecordingService.ts` | 会话记录格式 |
| `packages/core/src/skills/skillManager.ts` | Skill 发现和管理 |
| `packages/core/src/utils/extensionLoader.ts` | Extension 加载器 |
| `packages/core/src/core/contentGenerator.ts` | AuthType enum |
| `packages/cli/src/ui/App.tsx` | React/Ink TUI 入口 |

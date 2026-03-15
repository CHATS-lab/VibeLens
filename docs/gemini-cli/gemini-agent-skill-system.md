# Gemini CLI Agent & Skill System

| 条目 | 内容 |
|------|------|
| **主题** | Gemini CLI 的 Agent 与 Skill 可扩展体系深度解析 |
| **版本** | 基于 gemini-cli 源码 (2026-03 快照) |
| **核心路径** | `packages/core/src/agents/` / `packages/core/src/skills/` / `packages/core/src/utils/memoryDiscovery.ts` |
| **关联系统** | GEMINI.md 层级记忆、Custom Commands (TOML)、A2A 远程 Agent 协议 |
| **目标读者** | 需要理解 Gemini CLI 内部架构以便对比分析或二次开发的工程师 |

---

## 1 体系总览

Gemini CLI 构建了一套围绕 **Agent / Skill / Custom Command / Memory** 四层可扩展架构。其核心思想是：

- **Agent** = 拥有独立 system prompt、tool 列表、model 配置的 _自治子任务执行器_；主 agent 通过 `delegate_to_agent` 工具将任务委派给 sub-agent。
- **Skill** = 轻量级的 _领域知识注入包_；由 `activate_skill` 工具按需加载到当前 context window。
- **Custom Command** = 用户自定义的 _TOML slash 命令_；通过 `/command_name` 触发，将预定义的 prompt 模板注入对话。
- **GEMINI.md** = 层级化的 _持久化记忆文件_；在每次会话启动时自动发现并拼接进 system prompt。

> 📌 与 Claude Code 的核心差异：Claude Code 以 `TodoWrite` / `Agent` tool 驱动多步执行，没有原生 skill 或 custom command 体系；而 Gemini CLI 通过 Markdown+YAML frontmatter 声明式定义 agent/skill，并提供完善的四级发现层次和 A2A 远程 agent 协议。

---

## 2 Agent 定义格式

### 2.1 Markdown + YAML Frontmatter

Gemini CLI 中自定义 agent 以 `.md` 文件声明，文件头部使用 YAML frontmatter，Markdown body 作为 system prompt 内容。

**Local Agent 示例：**

```markdown
---
name: my-reviewer
description: Reviews code changes for quality and correctness.
tools:
  - read_file
  - grep
  - glob
model: gemini-2.5-flash
temperature: 0.2
max_turns: 15
timeout_mins: 5
---

You are a code review expert...
(此处的 Markdown body 即为 system_prompt)
```

**Frontmatter 字段说明（Local Agent）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `string` (slug) | 是 | Agent 唯一标识，只允许 `[a-z0-9-_]` |
| `description` | `string` | 是 | 描述何时应调用此 agent |
| `display_name` | `string` | 否 | 人类可读的显示名称 |
| `kind` | `'local'` | 否 | 默认 `'local'`，可省略 |
| `tools` | `string[]` | 否 | 可用工具列表，支持 `*` 通配符和 `mcp:*` |
| `model` | `string` | 否 | 指定模型名，缺省为 `'inherit'`（继承主会话模型） |
| `temperature` | `number` | 否 | 模型温度，默认 `1` |
| `max_turns` | `number` | 否 | 最大对话轮次，默认 `30` |
| `timeout_mins` | `number` | 否 | 超时分钟数，默认 `10` |

> 💡 Frontmatter 的解析与校验通过 `agentLoader.ts` 中的 Zod schema 完成。`localAgentSchema` 使用 `.strict()` 模式，任何多余字段都会导致验证失败。

**Remote Agent 示例：**

```markdown
---
name: deep-researcher
kind: remote
description: A remote research agent via A2A protocol.
agent_card_url: https://example.com/.well-known/agent.json
auth:
  type: http
  scheme: Bearer
  token: ${MY_API_TOKEN}
---
```

支持在单个 `.md` 文件中以 YAML array 形式定义多个 remote agent：

```markdown
---
- name: agent-a
  kind: remote
  agent_card_url: https://a.example.com/agent.json
- name: agent-b
  kind: remote
  agent_card_url: https://b.example.com/agent.json
---
```

### 2.2 TypeScript 类型体系

源码中的核心类型定义位于 `packages/core/src/agents/types.ts`：

```typescript
// 基础定义（Local 与 Remote 共享）
interface BaseAgentDefinition<TOutput> {
  name: string;
  displayName?: string;
  description: string;
  experimental?: boolean;
  inputConfig: InputConfig;       // JSON Schema 定义输入参数
  outputConfig?: OutputConfig<TOutput>;  // Zod schema 定义输出结构
  metadata?: { hash?: string; filePath?: string };
}

// Local Agent = 在本地执行的 sub-agent
interface LocalAgentDefinition extends BaseAgentDefinition {
  kind: 'local';
  promptConfig: PromptConfig;   // systemPrompt + query 模板
  modelConfig: ModelConfig;     // model 名 + generateContentConfig
  runConfig: RunConfig;         // maxTurns + maxTimeMinutes
  toolConfig?: ToolConfig;      // 可用工具列表
  processOutput?: (output) => string;
}

// Remote Agent = 通过 A2A 协议调用的远程 agent
interface RemoteAgentDefinition extends BaseAgentDefinition {
  kind: 'remote';
  agentCardUrl: string;
  auth?: A2AAuthConfig;
}
```

> 📌 `promptConfig.query` 支持 `${variable_name}` 模板语法，在执行时由 `templateString()` 函数替换为实际输入值。

### 2.3 完整自定义 Agent 示例

以下是一个完整的自定义 local agent 定义文件，展示了所有可配置项和 system prompt 编写最佳实践。将此文件保存为 `.gemini/agents/security-auditor.md`（项目级）或 `~/.gemini/agents/security-auditor.md`（用户级）。

```markdown
---
name: security-auditor
display_name: Security Auditor
description: >
  Performs a comprehensive security audit of the codebase. Invoke this agent
  when the user asks about security vulnerabilities, dependency risks, or
  wants a security review of specific files or the entire project.
tools:
  - read_file
  - grep
  - glob
  - ls
  - web_search
  - mcp:npm-audit/*
model: gemini-2.5-pro
temperature: 0.1
max_turns: 20
timeout_mins: 8
---

You are **Security Auditor**, a specialized AI agent focused on identifying
security vulnerabilities in software projects.

## Your Capabilities
- Static code analysis for common vulnerability patterns (SQL injection,
  XSS, CSRF, path traversal, etc.)
- Dependency vulnerability assessment using available MCP tools
- Configuration security review (exposed secrets, weak permissions, etc.)
- Authentication and authorization flow analysis

## Operating Rules
1. **Systematic scanning**: Start with high-risk entry points (API routes,
   authentication handlers, file upload endpoints) before broadening scope.
2. **Evidence-based**: Every finding must reference specific file paths and
   line numbers. Never speculate without supporting code evidence.
3. **Severity classification**: Use CVSS-like severity levels:
   CRITICAL / HIGH / MEDIUM / LOW / INFORMATIONAL.
4. **Actionable output**: Each finding must include a concrete remediation
   recommendation.

## Scratchpad
Maintain a running scratchpad to track:
- [ ] Files scanned
- [ ] Vulnerabilities found (with severity)
- [ ] Areas still to investigate

## Termination
When your audit is complete, call `complete_task` with a structured JSON
report containing all findings, their severities, affected files, and
recommended fixes.
```

**Agent 加载后的内部 representation：**

```json
{
  "name": "security-auditor",
  "kind": "local",
  "displayName": "Security Auditor",
  "description": "Performs a comprehensive security audit...",
  "promptConfig": {
    "systemPrompt": "You are **Security Auditor**, a specialized AI agent...",
    "query": "Get Started!"
  },
  "modelConfig": {
    "model": "gemini-2.5-pro",
    "generateContentConfig": { "temperature": 0.1 }
  },
  "runConfig": {
    "maxTurns": 20,
    "maxTimeMinutes": 8
  },
  "toolConfig": {
    "tools": ["read_file", "grep", "glob", "ls", "web_search", "mcp:npm-audit/*"]
  },
  "metadata": {
    "hash": "a3f2...b7c1",
    "filePath": "/project/.gemini/agents/security-auditor.md"
  }
}
```

> 💡 `tools` 字段中的 `mcp:npm-audit/*` 使用了 MCP server 通配符语法——它会注册名为 `npm-audit` 的 MCP server 提供的所有工具。如果该 MCP server 未连接，这些工具会被静默忽略，不会导致 agent 注册失败。

> ⚠️ 如果此文件存放在 `.gemini/agents/`（项目级），首次加载时 `AgentRegistry` 会计算文件的 SHA-256 hash 并检查 `acknowledged_agents.json`。用户必须在 UI 中确认后 agent 才会真正注册。修改文件内容后 hash 变化，需要重新确认。

---

## 3 内置 Agent

Gemini CLI 注册了 4 个内置 Agent，均在 `AgentRegistry.loadBuiltInAgents()` 中硬编码注册：

### 3.1 CodebaseInvestigator (`codebase_investigator`)

**文件**: `agents/codebase-investigator.ts`

| 特性 | 值 |
|------|---|
| 模型 | Preview Flash（若主模型支持 modern features），否则 Default Pro |
| 工具 | `ls`, `read_file`, `glob`, `grep`（仅只读工具） |
| maxTurns | 10 |
| maxTimeMinutes | 3 |
| temperature | 0.1 |
| 输出 schema | `{ SummaryOfFindings, ExplorationTrace, RelevantLocations }` |

设计目标是为主 agent 提供深度的代码库探索与架构分析。它拥有详尽的 system prompt，要求维护 scratchpad，系统性地追踪所有相关文件并记录探索过程。

### 3.2 CliHelp (`cli_help`)

**文件**: `agents/cli-help-agent.ts`

| 特性 | 值 |
|------|---|
| 模型 | Gemini Flash (alias) |
| 工具 | `get_internal_docs`（查阅 Gemini CLI 自身文档） |
| maxTurns | 10 |
| maxTimeMinutes | 3 |
| 输出 schema | `{ answer, sources }` |

专门回答用户关于 Gemini CLI 自身功能、配置和用法的问题。system prompt 中注入了运行时上下文变量 `${cliVersion}`, `${activeModel}`, `${today}`。

### 3.3 Generalist (`generalist`)

**文件**: `agents/generalist-agent.ts`

| 特性 | 值 |
|------|---|
| 模型 | `'inherit'`（继承主会话模型） |
| 工具 | 所有可用工具（通过 `context.toolRegistry.getAllToolNames()` 动态获取） |
| maxTurns | 20 |
| maxTimeMinutes | 10 |
| 输出 schema | `{ response }` |

通用 sub-agent，适用于 turn-intensive 或数据量大的任务。使用与主 agent 相同的 core system prompt（但以非交互模式运行）。其 `toolConfig` 和 `promptConfig` 使用 `get` accessor 实现懒加载。

### 3.4 BrowserAgent (`browser_agent`)

**文件**: `agents/browser/browserAgentDefinition.ts`

| 特性 | 值 |
|------|---|
| 模型 | Preview Flash 或 Default Flash |
| 工具 | 动态配置（通过 `browserAgentFactory` 在调用时设置 MCP 工具） |
| maxTurns | 50 |
| maxTimeMinutes | 10 |
| experimental | `true`（需要在 settings 中显式启用） |

自主 Web 浏览器自动化 agent，通过 Accessibility Tree 感知页面结构，支持 click、fill、navigate 等语义操作。system prompt 包含详细的 overlay/popup 处理指南和 terminal failure 检测逻辑。

> ⚠️ `experimental: true` 意味着 BrowserAgent 默认不会注册，必须在 settings 中配置 `browserAgentConfig.enabled = true` 才会生效。

### 内置 Agent 对比表

| Agent | 模型策略 | 工具范围 | 只读 | 典型场景 |
|-------|---------|---------|------|---------|
| `codebase_investigator` | Flash (thinking HIGH) | 4 个只读工具 | 是 | Bug 根因分析、架构理解 |
| `cli_help` | Flash | 1 个文档工具 | 是 | "如何配置 MCP？"等 CLI 问题 |
| `generalist` | 继承主模型 | 全部工具 | 否 | 批量重构、命令执行 |
| `browser_agent` | Flash | 浏览器 MCP 工具 | 否 | Web 自动化、表单填写 |

---

## 4 Agent 发现与注册层次

`AgentRegistry.loadAgents()` 方法按以下顺序发现并注册 agent：

```
1. Built-in Agents (硬编码)          ← 最低优先级
2. User Agents   (~/.gemini/agents/)
3. Project Agents (.gemini/agents/)
4. Extension Agents (extensions)     ← 最高优先级
```

> 💡 同名 agent 按 "后注册者覆盖" 原则处理。这意味着 Extension Agent 可以覆盖同名的 Project Agent，Project Agent 可以覆盖 User Agent，以此类推。

### 4.1 User Agents

从 `~/.gemini/agents/` 目录加载。只扫描 `.md` 文件（忽略 `_` 前缀的文件），由 `loadAgentsFromDirectory()` 解析。

### 4.2 Project Agents（含安全审查）

从 `.gemini/agents/`（相对于 project root）加载。项目级 agent 引入了 **acknowledgement 机制**：

1. 读取 `.md` 文件后计算其 SHA-256 hash
2. 查询 `AcknowledgedAgentsService` 是否已确认该 agent
3. 未确认的 agent 不会注册，而是通过 `coreEvents.emitAgentsDiscovered()` 通知 UI
4. 用户在 UI 中确认后，hash 被持久化到 `~/.gemini/acknowledged_agents.json`

> ⚠️ 如果 `folderTrust` 功能启用但当前文件夹不受信任，所有 project agent 都会被跳过。

### 4.3 Extension Agents

从各活跃 extension 的 `agents` 属性中加载。Extension 可以通过编程接口直接提供 `AgentDefinition[]`。

### 4.4 Agent Policy 自动注册

注册每个 agent 时，`AgentRegistry` 还会自动向 `PolicyEngine` 添加策略规则：

- **Local Agent** → 默认 `PolicyDecision.ALLOW`（自动允许）
- **Remote Agent** → 默认 `PolicyDecision.ASK_USER`（需用户确认）

如果用户已在 TOML 策略文件中为该 agent 定义了自定义规则，则不会覆盖。

### 与 Claude Code 的对比

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| Agent 定义格式 | Markdown + YAML frontmatter | 无原生 agent 定义格式 |
| 发现层次 | Built-in → User → Project → Extension | 无层次化发现 |
| 安全审查 | Hash-based acknowledgement 机制 | 无（依赖 CLAUDE.md 信任） |
| 覆盖机制 | 后注册者覆盖同名 agent | N/A |
| 远程 agent | A2A 协议原生支持 | 无原生支持 |

---

## 5 LocalAgentExecutor：Agent 执行引擎

`LocalAgentExecutor` 是 local agent 的核心执行引擎，实现了完整的 ReAct (Reasoning + Acting) 循环。

### 5.1 创建阶段 (`LocalAgentExecutor.create()`)

```
AgentDefinition
     │
     ▼
create() ──→ 构建隔离的 ToolRegistry
             │ - 从父 registry 中按 toolConfig 筛选工具
             │ - 排除所有 sub-agent 工具（防止递归）
             │ - 支持 '*' 和 'mcp:server_name/*' 通配符
             │ - 创建 subagent-aware MessageBus
             ▼
         new LocalAgentExecutor(...)
```

关键设计：
- 每个 agent 实例拥有 **隔离的 ToolRegistry**，只能访问定义中声明的工具
- **禁止递归**：agent 无法调用其他 agent（所有 agent 名称会从工具列表中排除）
- 工具通配符支持：`*`（所有工具）、`mcp:*`（所有 MCP 工具）、`mcp:server_name/*`（特定 MCP server 的所有工具）

### 5.2 执行循环 (`run()` 方法)

```
run(inputs, signal)
  │
  ├─ 1. 构建 augmentedInputs（注入 cliVersion, activeModel, today）
  ├─ 2. 准备 tool declarations
  ├─ 3. 创建 GeminiChat（包含 system prompt + initial messages）
  ├─ 4. 通过 templateString() 渲染 query
  │
  └─ 5. LOOP (while true):
       │
       ├─ checkTermination() ── maxTurns 检查
       ├─ combinedSignal.aborted 检查 ── timeout / 用户取消
       │
       ├─ executeTurn():
       │    ├─ tryCompressChat()     ← 自动压缩超长对话
       │    ├─ callModel()           ← 调用 Gemini API
       │    ├─ 解析 functionCalls
       │    │
       │    ├─ 若无 functionCalls 且未调用 complete_task
       │    │   → ERROR_NO_COMPLETE_TASK_CALL
       │    │
       │    ├─ processFunctionCalls():
       │    │   ├─ 检测 complete_task 调用 → GOAL 终止
       │    │   ├─ 检测未授权工具调用 → 返回错误
       │    │   └─ 并行执行授权工具 → 收集结果
       │    │
       │    └─ 返回 AgentTurnResult
       │
       ├─ 处理 user hints（实时注入用户引导）
       │
       └─ 若 status == 'stop':
            ├─ GOAL → 返回最终结果
            ├─ TIMEOUT / MAX_TURNS / ERROR_NO_COMPLETE_TASK_CALL
            │   → executeFinalWarningTurn()
            │     (给予 1 分钟 grace period 调用 complete_task)
            └─ ABORTED → 直接返回
```

### 5.3 终止模式 (`AgentTerminateMode`)

| 模式 | 含义 | 可恢复 |
|------|------|--------|
| `GOAL` | Agent 调用了 `complete_task` 工具 | N/A（正常完成） |
| `TIMEOUT` | 超过 `maxTimeMinutes` 限制 | 是（grace period） |
| `MAX_TURNS` | 超过 `maxTurns` 限制 | 是（grace period） |
| `ERROR_NO_COMPLETE_TASK_CALL` | Model 停止调用工具但未调用 `complete_task` | 是（grace period） |
| `ABORTED` | 用户取消操作 | 否 |
| `ERROR` | 未知错误 | 否 |

> 📌 `complete_task` 是 agent 的 **唯一正常退出方式**。即使遇到 timeout，executor 也会给 agent 一个 1 分钟的 grace period，要求它立即调用 `complete_task` 总结已完成的工作。

### 5.4 Activity 事件流

Agent 执行过程通过 `SubagentActivityEvent` 向父级报告进度：

```typescript
type SubagentActivityEvent = {
  type: 'TOOL_CALL_START' | 'TOOL_CALL_END' | 'THOUGHT_CHUNK' | 'ERROR';
  agentName: string;
  data: Record<string, unknown>;
};
```

`LocalSubagentInvocation` 将这些事件转换为 `SubagentProgress` 结构，通过 `updateOutput` 回调推送至 UI，仅保留最近 3 条 activity。

### 5.5 Agent 执行 Trace 示例

以下是 `codebase_investigator` agent 接收到一个 bug 排查任务时的完整执行 trace，展示从主 agent 委派到 sub-agent 完成的每一步：

```
═══════════════════════════════════════════════════════════════
 Agent Execution Trace: codebase_investigator
 Task: "Find the root cause of the race condition in updateUser"
═══════════════════════════════════════════════════════════════

[T+0ms] SubagentToolWrapper.createInvocation()
  │ definition.kind === 'local' → new LocalSubagentInvocation(...)
  │
[T+5ms] LocalAgentExecutor.create()
  │ 构建隔离 ToolRegistry:
  │   ├─ 注册 ls         (from parent registry)
  │   ├─ 注册 read_file  (from parent registry)
  │   ├─ 注册 glob       (from parent registry)
  │   ├─ 注册 grep       (from parent registry)
  │   ├─ 跳过 generalist       ← agent tool, 防止递归
  │   ├─ 跳过 cli_help         ← agent tool, 防止递归
  │   └─ 跳过 browser_agent    ← agent tool, 防止递归
  │ agentId = "parent-prompt-42-codebase_investigator-a3f2k1"
  │
[T+12ms] LocalAgentExecutor.run()
  │ augmentedInputs = {
  │   objective: "Find the root cause of the race condition...",
  │   cliVersion: "1.2.3",
  │   activeModel: "gemini-2.5-pro",
  │   today: "3/15/2026"
  │ }
  │ templateString(query, augmentedInputs) → 渲染 ${objective}
  │ DeadlineTimer started: 3 minutes (180000ms)
  │
[T+15ms] ═══ Turn 0 ═══
  │ executeTurn() → tryCompressChat() → 无需压缩
  │ callModel() → sendMessageStream()
  │   ├─ THOUGHT_CHUNK: "需要先搜索 updateUser 函数定义..."
  │   └─ functionCalls: [
  │        { name: "grep", args: { pattern: "updateUser", path: "src/" } }
  │      ]
  │ TOOL_CALL_START: { name: "grep", callId: "...#0-0" }
  │ 执行 grep → 返回 3 个匹配文件
  │ TOOL_CALL_END: { name: "grep", callId: "...#0-0" }
  │ AgentTurnResult: { status: 'continue', nextMessage: [...] }
  │
[T+2100ms] ═══ Turn 1 ═══
  │ executeTurn() → tryCompressChat() → 无需压缩
  │ callModel() → sendMessageStream()
  │   ├─ THOUGHT_CHUNK: "找到了 userController.js，需要读取..."
  │   └─ functionCalls: [
  │        { name: "read_file", args: { path: "src/controllers/userController.js" } },
  │        { name: "read_file", args: { path: "src/services/userService.js" } }
  │      ]
  │ 并行执行 2 个 read_file 工具
  │ AgentTurnResult: { status: 'continue' }
  │
[T+4800ms] ═══ Turn 2 ═══
  │ ... (继续探索 User.js model 层)
  │
[T+8500ms] ═══ Turn 3 ═══
  │ callModel() → functionCalls: [
  │   { name: "complete_task", args: {
  │       report: {
  │         SummaryOfFindings: "The core issue is a race condition...",
  │         ExplorationTrace: ["Used grep to search...", ...],
  │         RelevantLocations: [
  │           { FilePath: "src/controllers/userController.js", ... },
  │           { FilePath: "src/services/userService.js", ... }
  │         ]
  │       }
  │     }
  │   }
  │ ]
  │ processFunctionCalls():
  │   ├─ 检测到 complete_task 调用
  │   ├─ outputConfig.schema.safeParse(report) → success
  │   └─ processOutput(report) → JSON.stringify(report, null, 2)
  │ AgentTurnResult: { status: 'stop', terminateReason: 'GOAL' }
  │
[T+8510ms] logAgentFinish():
  │ AgentFinishEvent {
  │   agentId: "parent-prompt-42-codebase_investigator-a3f2k1",
  │   agentName: "codebase_investigator",
  │   durationMs: 8510,
  │   turnCount: 4,
  │   terminateReason: "GOAL"
  │ }
  │
[T+8515ms] → 返回 OutputObject { result: "{...}", terminate_reason: "GOAL" }
  │ → 主 agent 收到结构化调查报告
```

> 💡 这个 trace 清晰展示了 agent 执行的关键节点：隔离 ToolRegistry 构建、template 渲染、ReAct 循环中的多轮 tool 调用、`complete_task` 正常退出。整个流程由 `DeadlineTimer` 计时器监控，防止超时。

### 5.6 Agent 失败场景与调试指南

实际使用中 agent 可能以多种非正常方式终止。以下是三种最常见的失败模式、对应的内部处理逻辑，以及调试建议。

#### 场景 A：Timeout（超时终止）

```
═══ Failure Trace: TIMEOUT ═══

[T+0ms]     run() 启动, maxTimeMinutes=3
[T+180000ms] DeadlineTimer.signal → aborted
            combinedSignal.aborted === true
            deadlineTimer.signal.aborted === true
            → terminateReason = AgentTerminateMode.TIMEOUT

            ┌─────────────────────────────────────────────┐
            │ 进入 Recovery Block:                         │
            │ executeFinalWarningTurn(chat, turnCounter,   │
            │   AgentTerminateMode.TIMEOUT, signal)        │
            │                                             │
            │ Warning message 注入:                        │
            │ "You have exceeded the time limit. You have │
            │  one final chance... You MUST call           │
            │  complete_task immediately..."               │
            │                                             │
            │ Grace Period: 60 seconds (GRACE_PERIOD_MS)  │
            └─────────────────────────────────────────────┘

            ├─ 恢复成功 → terminateReason = GOAL
            │   返回 "Task completed during grace period."
            │
            └─ 恢复失败 → 最终输出:
                OutputObject {
                  result: "Agent timed out after 3 minutes.",
                  terminate_reason: "TIMEOUT"
                }
```

**调试建议：**
- 检查 `runConfig.maxTimeMinutes` 是否设置得太低（默认 10 分钟）
- 使用 settings override 增加超时时间：`"runConfig": { "maxTimeMinutes": 15 }`
- 注意 `DeadlineTimer` 在用户确认等待期间会 **暂停计时**，所以超时通常确实是 agent 执行时间过长
- 启用 `--debug` 模式查看 `[LocalAgentExecutor]` 日志以定位哪个 tool call 耗时最长

#### 场景 B：MAX_TURNS 超限

```
═══ Failure Trace: MAX_TURNS ═══

[Turn 29] executeTurn() → status: 'continue'
[Turn 30] checkTermination(30, maxTurns=30)
          → return AgentTerminateMode.MAX_TURNS
          → break out of loop

          ┌─────────────────────────────────────────────┐
          │ 进入 Recovery Block:                         │
          │ Warning: "You have exceeded the maximum     │
          │ number of turns..."                         │
          │ Grace Period: 60 seconds                    │
          └─────────────────────────────────────────────┘

          ├─ 恢复成功 → GOAL, 返回部分结果
          └─ 恢复失败 →
              OutputObject {
                result: "Agent reached max turns limit (30).",
                terminate_reason: "MAX_TURNS"
              }
```

> ⚠️ `MAX_TURNS` 失败通常意味着 agent 的 system prompt 不够聚焦，导致 agent 反复探索不相关的路径。考虑：(1) 缩小 `tools` 列表以减少决策空间；(2) 优化 system prompt 中的 termination 指导；(3) 适当增加 `maxTurns`（不推荐作为首选方案）。

#### 场景 C：Tool 执行期间错误

```
═══ Failure Trace: Tool Error During Execution ═══

[Turn 5] callModel() → functionCalls: [
           { name: "read_file", args: { path: "/etc/shadow" } },
           { name: "unknown_tool", args: {} }
         ]

         processFunctionCalls():
           ├─ read_file:
           │   tool 存在于 agentToolRegistry ✓
           │   执行 → ToolResult { error: "Permission denied" }
           │   结果注入下一轮 message（不终止循环）
           │
           └─ unknown_tool:
               allowedToolNames.has("unknown_tool") → false
               → 返回 error response:
               {
                 functionResponse: {
                   name: "unknown_tool",
                   response: {
                     error: "Unauthorized tool call: 'unknown_tool'
                             is not available to this agent."
                   }
                 }
               }
               ACTIVITY: { type: 'ERROR', error: "Unauthorized..." }

         → Agent 收到错误 response，在下一个 turn 可以选择:
           a) 调用其他合法工具继续工作
           b) 调用 complete_task 提交已有成果

[Turn 6] callModel() → functionCalls: []  ← 模型停止调用
         → ERROR_NO_COMPLETE_TASK_CALL

         ┌─────────────────────────────────────────────┐
         │ 进入 Recovery Block:                         │
         │ "You have stopped calling tools without     │
         │  finishing..."                              │
         │ Grace Period: 60 seconds                    │
         └─────────────────────────────────────────────┘
```

**调试建议：**
- Tool 执行错误 **不会直接终止** agent，错误信息会作为 `functionResponse` 注入下一轮对话，让模型决定如何恢复
- 如果模型反复调用不存在的工具，检查 agent 定义的 `tools` 列表是否完整
- 如果 `complete_task` 的 output 校验失败（`safeParse` 返回 `success: false`），completion 会被 **撤回**（`taskCompleted = false`），agent 继续执行
- 使用 `SubagentActivityEvent` 中的 `type: 'ERROR'` 事件追踪具体哪些 tool call 失败

#### 终止后恢复机制总结

```
                    ┌──────────────────────────┐
                    │  Agent Loop 正常退出检查   │
                    └──────────┬───────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
           GOAL           ABORTED            ERROR
         (正常完成)       (用户取消)         (未知异常)
           │                │                  │
           ▼                ▼                  ▼
         返回结果          直接返回           抛出异常

          ┌────────────────────────────────────┐
          │ 可恢复的终止原因:                    │
          │  TIMEOUT / MAX_TURNS /             │
          │  ERROR_NO_COMPLETE_TASK_CALL        │
          └────────────────┬───────────────────┘
                           ▼
              executeFinalWarningTurn()
              Grace Period = 60 seconds
                     │
              ┌──────┼──────┐
              ▼             ▼
          recovery      recovery
          成功            失败
              │             │
              ▼             ▼
        GOAL + 结果    原始 reason
                       + 错误消息
```

> 📌 `executeFinalWarningTurn()` 的 grace period 使用独立的 `AbortController`，与主 `DeadlineTimer` 互不影响。即使原始超时已触发，recovery turn 仍有完整的 60 秒执行窗口。`logRecoveryAttempt()` 会记录恢复尝试的 telemetry 数据，包括 agent 名称、原始终止原因、恢复耗时和是否成功。

---

## 6 Remote Agents：A2A 协议

### 6.1 Agent Card 发现

Remote agent 通过 [A2A (Agent-to-Agent) 协议](https://google.github.io/a2a/) 实现跨服务通信。定义中的 `agent_card_url` 指向一个标准的 Agent Card JSON：

```json
{
  "name": "deep-researcher",
  "description": "An AI research agent",
  "url": "https://api.example.com/a2a",
  "skills": [
    { "name": "web_research", "description": "Deep web research" }
  ],
  "securitySchemes": { ... }
}
```

`A2AClientManager` 负责：
1. 通过 `DefaultAgentCardResolver` 获取并解析 Agent Card
2. 根据 card 的 `additionalInterfaces` 选择传输协议（REST / JSON-RPC / gRPC）
3. 缓存 client 实例以复用连接

### 6.2 认证体系

Agent 定义支持四种认证方式：

| 类型 | 字段 | 说明 |
|------|------|------|
| `apiKey` | `key`, `name` | API Key 认证 |
| `http` | `scheme` (`Bearer`/`Basic`), `token`/`username`+`password` | HTTP 认证 |
| `google-credentials` | `scopes` | Google ADC 认证 |
| `oauth2` | `client_id`, `client_secret`, `scopes`, URLs | OAuth 2.0 流程 |

`A2AAuthProviderFactory` 会校验用户配置的 auth 信息是否满足 Agent Card 中 `securitySchemes` 的要求，不匹配时发出 warning。

### 6.3 通信流程

```
RemoteAgentInvocation.execute()
  │
  ├─ 1. 获取 / 复用 auth handler
  ├─ 2. 确保 agent 已加载（loadAgent）
  ├─ 3. 调用 sendMessageStream()
  │      └─ 构建 A2A Message: { role: 'user', parts: [{text}] }
  │      └─ 发送并接收 SSE 流
  ├─ 4. 逐 chunk 更新 UI（通过 A2AResultReassembler 重组）
  ├─ 5. 提取 contextId / taskId 维持会话状态
  └─ 6. 返回最终 ToolResult
```

> 📌 Remote agent 始终需要用户确认（`PolicyDecision.ASK_USER`），并且 session state（contextId, taskId）通过 static Map 在同一进程的多次调用间持久化。

### 6.4 A2A 协议交互完整示例

以下是 Gemini CLI 与一个远程 research agent 通过 A2A 协议完成一次完整交互的 step-by-step 过程，包括 Agent Card 发现、client 创建、消息发送和状态维持。

#### Step 1: Agent Card 发现与解析

主 agent 首次调用 `delegate_to_agent(name: "deep-researcher", query: "Research quantum computing trends")`，触发 `A2AClientManager.loadAgent()`：

```
GET https://example.com/.well-known/agent.json
Authorization: (无 — 先尝试无认证请求)

Response 200 OK:
```

```json
{
  "name": "deep-researcher",
  "description": "An AI agent specializing in deep web research and report generation.",
  "url": "https://api.example.com/a2a",
  "version": "1.0.0",
  "skills": [
    {
      "name": "web_research",
      "description": "Performs deep, multi-step web research with source verification."
    },
    {
      "name": "report_generation",
      "description": "Generates structured research reports with citations."
    }
  ],
  "additionalInterfaces": [
    {
      "transport": "REST",
      "url": "https://api.example.com/a2a"
    },
    {
      "transport": "GRPC",
      "url": "grpcs://api.example.com:443"
    }
  ],
  "securitySchemes": {
    "bearer_auth": {
      "type": "http",
      "scheme": "bearer"
    }
  }
}
```

> 💡 `normalizeAgentCard()` 会处理 proto field name alias 差异（`supportedInterfaces` → `additionalInterfaces`，`protocolBinding` → `transport`），确保与不同版本的 A2A server 兼容。

#### Step 2: Client 创建与传输协议协商

```
A2AClientManager 内部流程:
  │
  ├─ 1. DefaultAgentCardResolver.resolve(agentCardUrl)
  │     → 获取并解析 Agent Card JSON
  │
  ├─ 2. normalizeAgentCard(rawCard)
  │     → 标准化字段名称
  │
  ├─ 3. ClientFactoryOptions 配置:
  │     transports: [
  │       RestTransportFactory   { fetchImpl: authFetch },
  │       JsonRpcTransportFactory { fetchImpl: authFetch },
  │       GrpcTransportFactory   { grpcChannelCredentials: ssl }
  │     ]
  │
  ├─ 4. ClientFactory.createFromAgentCard(agentCard)
  │     → 根据 additionalInterfaces 选择最优传输:
  │        REST available  ✓ → 优先使用
  │        GRPC available  ✓ → 备选
  │
  └─ 5. 缓存 client 和 agentCard:
        clients.set("deep-researcher", client)
        agentCards.set("deep-researcher", agentCard)
```

#### Step 3: 消息发送 (SSE Stream)

```
RemoteAgentInvocation.execute() 构建 A2A Message:

POST https://api.example.com/a2a
Content-Type: application/json
Authorization: Bearer <token>
```

```json
{
  "message": {
    "kind": "message",
    "role": "user",
    "messageId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "parts": [
      {
        "kind": "text",
        "text": "Research quantum computing trends"
      }
    ]
  }
}
```

```
Response (SSE Stream):

event: task-status-update
data: {"kind":"status","taskId":"task-001","contextId":"ctx-abc",
       "status":{"state":"working","message":"Searching..."}}

event: task-artifact-update
data: {"kind":"artifact","taskId":"task-001",
       "artifact":{"parts":[{"kind":"text","text":"## Preliminary Findings\n..."}]}}

event: task-status-update
data: {"kind":"status","taskId":"task-001","contextId":"ctx-abc",
       "status":{"state":"completed","message":"Research complete."}}

event: message
data: {"kind":"message","role":"agent","messageId":"resp-xyz",
       "contextId":"ctx-abc","taskId":"task-001",
       "parts":[{"kind":"text","text":"## Quantum Computing Trends 2026\n\n..."}]}
```

#### Step 4: 状态持久化

```
RemoteAgentInvocation 状态维持:

  // 从 response 中提取 IDs
  extractIdsFromResponse(chunk):
    contextId = "ctx-abc"    ← 会话级 ID（跨多次调用）
    taskId = "task-001"      ← 任务级 ID（可清除）

  // 持久化到 static Map
  RemoteAgentInvocation.sessionState.set("deep-researcher", {
    contextId: "ctx-abc",
    taskId: "task-001"
  })

  // 下次调用同一 agent 时自动附加 contextId:
  POST /a2a
  { "message": { ..., "contextId": "ctx-abc" } }
  → 远程 agent 恢复之前的对话上下文
```

> ⚠️ 如果远程 agent 返回 `clearTaskId: true`（任务已完成并关闭），`taskId` 会被清除（`this.taskId = undefined`），而 `contextId` 会保留以支持后续对话。即使调用失败，`sessionState` 也会在 `finally` 块中持久化，以保持对话连续性。

#### 错误处理

Remote agent 调用中常见的错误场景和对应的用户提示：

| 错误类型 | 触发条件 | 用户看到的消息 |
|---------|---------|--------------|
| `A2AAgentError` (404) | Agent Card URL 无法访问 | `[deep-researcher] Could not find agent card at URL...` |
| `A2AAgentError` (401/403) | 认证失败 | `[deep-researcher] Authentication failed...` |
| `AgentAuthConfigMissingError` | 缺少认证配置 | `[deep-researcher] Agent requires authentication: Bearer token` |
| 网络错误 | 连接超时（A2A_TIMEOUT=30min） | `Error calling remote agent: fetch failed` |
| `No response` | Stream 未返回任何数据 | `Error calling remote agent: No response from remote agent.` |

---

## 7 Skill System

### 7.1 Skill 定义格式

Skill 以 `SKILL.md` 文件定义，存放在特定目录结构中：

```
skill-name/
├── SKILL.md          ← 必须
├── scripts/          ← 可选：可执行脚本
├── references/       ← 可选：参考文档
└── assets/           ← 可选：模板/资源文件
```

**SKILL.md 格式：**

```markdown
---
name: my-skill
description: Does X when user asks about Y.
---

# My Skill Instructions

(Markdown body - 仅在 skill 被激活后加载)
```

Frontmatter 仅支持两个字段：
- `name`：Skill 唯一标识
- `description`：触发条件描述（**非常重要**，因为这是模型判断是否使用该 skill 的唯一依据）

### 7.2 SkillLoader

`skillLoader.ts` 负责从目录中发现 skill：

1. 搜索模式：`['SKILL.md', '*/SKILL.md']`（当前目录或一级子目录）
2. 使用 `js-yaml` 解析 frontmatter，失败时回退到简单 key-value parser
3. 将 `name` 中的特殊字符（`:\\/<>*?"|`）替换为 `-`

### 7.3 SkillManager

`SkillManager` 管理 skill 的完整生命周期：

**发现层次（优先级从低到高）：**

```
1. Built-in Skills                              ← 最低优先级
   (packages/core/src/skills/builtin/)
2. Extension Skills
   (extension.skills[])
3. User Skills
   (~/.gemini/skills/)
   (~/.gemini/agents/skills/)                   ← 别名目录
4. Workspace Skills                             ← 最高优先级
   (.gemini/skills/)
   (.gemini/agents/skills/)                     ← 别名目录
```

同名 skill 按优先级覆盖，并在日志中发出 warning。

**内置 Skill：**
- `skill-creator`：指导用户创建新的 skill，提供完整的 skill 编写最佳实践、progressive disclosure 设计原则、以及 init/package/install 脚本。

### 7.4 `activate_skill` 工具

`activate_skill` 是 LLM 可调用的工具，实现 skill 的按需激活：

```
Model 调用 activate_skill(name: "my-skill")
  │
  ├─ 1. 查找 skill（大小写不敏感匹配）
  ├─ 2. 若非 built-in → 弹出确认对话框（显示 description + 资源目录结构）
  ├─ 3. 标记 skill 为 active
  ├─ 4. 将 skill 目录添加到 WorkspaceContext（授予文件读取权限）
  └─ 5. 返回 XML 结构：
       <activated_skill name="my-skill">
         <instructions>SKILL.md body</instructions>
         <available_resources>目录结构</available_resources>
       </activated_skill>
```

这实现了 **progressive disclosure** 的三级加载：
1. **Metadata** (name + description) — 始终在 context 中 (~100 words)
2. **SKILL.md body** — skill 被激活后加载 (<5k words)
3. **Bundled resources** — agent 按需读取（无限制）

### 7.5 Skill 激活流程完整示例

以下展示从用户提出需求到 skill 完全加载的完整链路。假设项目 `.gemini/skills/` 下有一个 `docker-deploy` skill。

**Skill 目录结构：**

```
.gemini/skills/docker-deploy/
├── SKILL.md
├── scripts/
│   ├── build.sh
│   └── deploy.sh
├── references/
│   └── best-practices.md
└── assets/
    ├── Dockerfile.template
    └── docker-compose.template.yml
```

**SKILL.md 内容：**

```markdown
---
name: docker-deploy
description: >
  Guides the user through containerizing and deploying their application
  with Docker. Activate this skill when the user asks about Docker,
  containerization, deployment pipelines, or CI/CD with containers.
---

# Docker Deployment Skill

## Instructions
You are now equipped with Docker deployment expertise. Follow these steps:

1. Analyze the project structure to determine the appropriate base image
2. Generate a Dockerfile using the template in `assets/Dockerfile.template`
3. If multi-service, create docker-compose.yml from the template
4. Run the build script to verify the image builds successfully
5. Provide deployment instructions for the target environment

## Available Resources
- `scripts/build.sh` — Build and test the Docker image locally
- `scripts/deploy.sh` — Deploy to the configured environment
- `references/best-practices.md` — Docker security and performance guidelines
- `assets/Dockerfile.template` — Base Dockerfile template
- `assets/docker-compose.template.yml` — Multi-service compose template
```

**激活流程 Trace：**

```
═══════════════════════════════════════════════════════════
 Skill Activation Flow: docker-deploy
═══════════════════════════════════════════════════════════

[1] 用户: "Help me containerize this Python app with Docker"

[2] LLM 接收到 system prompt 中的 skill 列表:
    "Available skills: docker-deploy (Guides the user through
     containerizing and deploying their application with Docker...)"
    → LLM 判断该 skill 与用户需求匹配

[3] LLM 调用: activate_skill(name: "docker-deploy")

[4] ActivateSkillToolInvocation 处理:
    │
    ├─ getSkill("docker-deploy")
    │   → SkillManager.getSkill() 大小写不敏感匹配
    │   → 返回 SkillDefinition {
    │       name: "docker-deploy",
    │       description: "Guides the user through...",
    │       location: "/project/.gemini/skills/docker-deploy/SKILL.md",
    │       body: "# Docker Deployment Skill\n\n## Instructions...",
    │       isBuiltin: false
    │   }
    │
    ├─ skill.isBuiltin === false
    │   → 需要用户确认
    │
    ├─ getConfirmationDetails():
    │   弹出确认对话框:
    │   ┌────────────────────────────────────────────────┐
    │   │ Activate Skill: docker-deploy                  │
    │   │                                                │
    │   │ Description:                                   │
    │   │ Guides the user through containerizing and     │
    │   │ deploying their application with Docker...     │
    │   │                                                │
    │   │ Resources to be shared with the model:         │
    │   │ docker-deploy/                                 │
    │   │ ├── SKILL.md                                   │
    │   │ ├── scripts/                                   │
    │   │ │   ├── build.sh                               │
    │   │ │   └── deploy.sh                              │
    │   │ ├── references/                                │
    │   │ │   └── best-practices.md                      │
    │   │ └── assets/                                    │
    │   │     ├── Dockerfile.template                    │
    │   │     └── docker-compose.template.yml            │
    │   │                                                │
    │   │              [Allow]  [Deny]                   │
    │   └────────────────────────────────────────────────┘
    │
    ├─ 用户点击 [Allow]
    │
    ├─ execute():
    │   ├─ skillManager.activateSkill("docker-deploy")
    │   │   → activeSkillNames.add("docker-deploy")
    │   │
    │   ├─ config.getWorkspaceContext().addDirectory(
    │   │     "/project/.gemini/skills/docker-deploy"
    │   │   )
    │   │   → Agent 获得读取 skill 目录中文件的权限
    │   │
    │   └─ 返回 ToolResult:
    │
    └─ LLM 收到的 tool response:

<activated_skill name="docker-deploy">
  <instructions>
    # Docker Deployment Skill

    ## Instructions
    You are now equipped with Docker deployment expertise...
    (完整的 SKILL.md body)
  </instructions>

  <available_resources>
    docker-deploy/
    ├── SKILL.md
    ├── scripts/
    │   ├── build.sh
    │   └── deploy.sh
    ├── references/
    │   └── best-practices.md
    └── assets/
        ├── Dockerfile.template
        └── docker-compose.template.yml
  </available_resources>
</activated_skill>

[5] LLM 后续行为:
    → System prompt 被增强，包含 skill instructions
    → LLM 可通过 read_file 读取 assets/Dockerfile.template
    → LLM 可根据 references/best-practices.md 优化建议
    → LLM 可指导用户运行 scripts/build.sh
```

**Skill 未找到的错误处理：**

如果 LLM 调用了不存在的 skill，`activate_skill` 工具会返回详细的错误信息和可用 skill 列表：

```json
{
  "llmContent": "Error: Skill \"kubernetes-deploy\" not found. Available skills are: docker-deploy, skill-creator",
  "returnDisplay": "Error: Skill \"kubernetes-deploy\" not found...",
  "error": {
    "message": "Skill \"kubernetes-deploy\" not found...",
    "type": "INVALID_TOOL_PARAMS"
  }
}
```

> 📌 Skill 激活是 **会话级** 的——`activeSkillNames` 存储在 `SkillManager` 实例中，不跨会话持久化。每次新会话开始时，所有 skill 都处于未激活状态，LLM 需要根据用户需求重新决定是否激活。

### Skill 系统对比

| 维度 | Gemini CLI Skill | Claude Code |
|------|-----------------|-------------|
| 定义格式 | SKILL.md + YAML frontmatter | 无原生 skill 系统 |
| 激活方式 | `activate_skill` 工具（LLM 自主决定） | N/A |
| 发现层次 | Built-in → Extension → User → Workspace | N/A |
| 资源打包 | scripts/ + references/ + assets/ | N/A |
| Progressive disclosure | 3 级加载 | CLAUDE.md 全量加载 |

---

## 8 Custom Commands

### 8.1 TOML 格式

Custom commands 以 `.toml` 文件定义，通过 `/command_name` 在交互式会话中触发。

```toml
prompt = "Review the following code for security vulnerabilities: {{args}}"
description = "Security-focused code review"
```

**字段说明：**
- `prompt` (必填)：prompt 模板，支持以下占位符：
  - `{{args}}`：用户输入的参数
  - `$(!command)`：Shell 命令注入（执行命令并替换结果）
  - `@file_path`：文件内容注入
- `description` (可选)：命令描述，显示在帮助列表中

### 8.2 命名规则

文件路径通过 `:` 命名空间分隔符转换为命令名：

```
commands/
├── review.toml          → /review
├── git/
│   ├── status.toml      → /git:status
│   └── commit.toml      → /git:commit
```

Extension 来源的命令会自动添加 `[extension_name]` 前缀到 description。

### 8.3 发现层次

```
1. User Commands    (~/.gemini/commands/)
2. Project Commands (.gemini/commands/)
3. Extension Commands (extension.path/commands/)
```

> ⚠️ 与 agent/skill 的 "后注册者覆盖" 不同，command 的冲突处理由 `CommandService` 的 "last wins" 策略和 extension 重命名机制完成。

---

## 9 GEMINI.md：层级化记忆系统

### 9.1 文件发现

GEMINI.md 是 Gemini CLI 的持久化上下文记忆文件（类比 Claude Code 的 `CLAUDE.md`）。文件名可通过配置自定义，默认为 `GEMINI.md`。

**发现策略：**

1. **Global 层**：`~/.gemini/GEMINI.md`
2. **Project 层**：从 CWD 向上遍历至 project root（`.git` 目录所在处），收集所有路径上的 `GEMINI.md`
3. **Downward 层**：从 CWD 向下进行 BFS 搜索（`bfsFileSearch`），在子目录中发现额外的 `GEMINI.md`
4. **Extension 层**：从活跃 extension 的 `contextFiles` 中收集

> 📌 Gemini CLI 使用 **inode-based 去重**（`deduplicatePathsByFileIdentity`）处理大小写不敏感文件系统上的重复文件。

### 9.1.1 GEMINI.md 发现过程详解与输出示例

以下以一个典型的 monorepo 项目结构为例，展示 `loadServerHierarchicalMemory()` 如何发现、去重和分类 GEMINI.md 文件。

**项目结构：**

```
~/.gemini/
└── GEMINI.md                          ← Global 层

/workspace/my-monorepo/                ← project root (.git 在此)
├── .git/
├── GEMINI.md                          ← Project 层 (upward)
├── packages/
│   ├── frontend/
│   │   ├── GEMINI.md                  ← Downward 层 (BFS)
│   │   └── src/
│   │       └── components/
│   │           └── GEMINI.md          ← Downward 层 (BFS)
│   ├── backend/
│   │   ├── GEMINI.md                  ← Downward 层 (BFS)
│   │   └── src/
│   └── shared/
│       └── GEMINI.md                  ← Downward 层 (BFS)
└── docs/
    └── GEMINI.md                      ← Downward 层 (BFS)
```

**CWD = `/workspace/my-monorepo/packages/frontend/src`**

**Step 1: Upward 遍历（CWD → project root）**

```
搜索路径（从 CWD 向上）:
  /workspace/my-monorepo/packages/frontend/src/GEMINI.md  → 不存在
  /workspace/my-monorepo/packages/frontend/GEMINI.md      → 找到 ✓
  /workspace/my-monorepo/packages/GEMINI.md               → 不存在
  /workspace/my-monorepo/GEMINI.md                        → 找到 ✓
  (到达 project root, 停止向上遍历)

upward 结果（root-to-leaf 顺序）:
  [0] /workspace/my-monorepo/GEMINI.md
  [1] /workspace/my-monorepo/packages/frontend/GEMINI.md
```

**Step 2: Downward BFS 搜索（从 CWD 开始）**

```
bfsFileSearch(rootDir="/workspace/my-monorepo/packages/frontend/src",
              options={ fileName: "GEMINI.md", maxDirs: 200 })

BFS Queue 处理顺序:
  [Batch 1] 扫描 /workspace/my-monorepo/packages/frontend/src/
            → 发现子目录: components/
            → 未找到 GEMINI.md

  [Batch 2] 扫描 .../src/components/
            → 找到 GEMINI.md ✓
            → 无更多子目录

  (BFS 完成, scannedDirCount=2, maxDirs=200)

downward 结果:
  [0] /workspace/my-monorepo/packages/frontend/src/components/GEMINI.md
```

> 💡 BFS 搜索使用并行 batch 处理（`PARALLEL_BATCH_SIZE=15`），每批最多同时读取 15 个目录。`maxDirs` 默认 200，防止在超大项目中无限扫描。搜索会跳过被 `.gitignore` 和 `.geminiignore` 匹配的目录。

**Step 3: Global 层发现**

```
检查 ~/.gemini/GEMINI.md → 存在且可读 ✓

global 结果:
  [0] /Users/username/.gemini/GEMINI.md
```

**Step 4: Inode-based 去重**

```
deduplicatePathsByFileIdentity([
  "/Users/username/.gemini/GEMINI.md",
  "/workspace/my-monorepo/GEMINI.md",
  "/workspace/my-monorepo/packages/frontend/GEMINI.md",
  "/workspace/my-monorepo/packages/frontend/src/components/GEMINI.md"
])

stat() 结果:
  ~/.gemini/GEMINI.md                    → dev:16777220 ino:12345678
  .../my-monorepo/GEMINI.md              → dev:16777220 ino:23456789
  .../frontend/GEMINI.md                 → dev:16777220 ino:34567890
  .../components/GEMINI.md               → dev:16777220 ino:45678901

所有 inode 唯一 → 保留全部 4 个文件
```

**Step 5: 分类与拼接**

```
categorizeAndConcatenate() 输出:

HierarchicalMemory {
  global: """
    --- Context from: ../../../../.gemini/GEMINI.md ---
    (全局 GEMINI.md 的内容)
    --- End of Context from: ../../../../.gemini/GEMINI.md ---
  """,

  extension: "",   ← 本例无活跃 extension

  project: """
    --- Context from: ../../GEMINI.md ---
    (项目根目录 GEMINI.md 的内容)
    --- End of Context from: ../../GEMINI.md ---

    --- Context from: GEMINI.md ---
    (frontend 目录 GEMINI.md 的内容)
    --- End of Context from: GEMINI.md ---

    --- Context from: src/components/GEMINI.md ---
    (components 目录 GEMINI.md 的内容)
    --- End of Context from: src/components/GEMINI.md ---
  """
}

LoadServerHierarchicalMemoryResponse {
  memoryContent: { global: "...", extension: "", project: "..." },
  fileCount: 4,
  filePaths: [
    "/Users/username/.gemini/GEMINI.md",
    "/workspace/my-monorepo/GEMINI.md",
    "/workspace/my-monorepo/packages/frontend/GEMINI.md",
    "/workspace/my-monorepo/packages/frontend/src/components/GEMINI.md"
  ]
}
```

> ⚠️ 如果 CWD 恰好是用户 home 目录（`realCwd === realHome`），`loadServerHierarchicalMemory()` 会将 `currentWorkingDirectory` 设为空字符串，跳过所有 workspace 搜索（upward + downward），仅加载 global 层。这是为了避免在 home 目录下执行 BFS 扫描整个文件系统。

### 9.2 层级化拼接

发现的文件按来源分为三个层级：

```typescript
interface HierarchicalMemory {
  global: string;     // 全局 GEMINI.md
  extension: string;  // Extension 上下文文件
  project: string;    // 项目级 GEMINI.md（含 MCP instructions）
}
```

每个文件的内容以标记块形式拼接：

```
--- Context from: relative/path/GEMINI.md ---
(文件内容)
--- End of Context from: relative/path/GEMINI.md ---
```

### 9.3 @import 指令

GEMINI.md 支持 `@path/to/file` 语法导入其他文件内容。由 `memoryImportProcessor.ts` 处理。

**规则：**
- 必须以 `./`、`/` 或字母开头
- 不支持 URL（`http://`, `file://` 被拒绝）
- 路径必须在 project root 范围内（防止路径遍历攻击）
- 最大嵌套深度：5 层
- 自动检测循环引用
- 代码块（backtick 区域）内的 `@` 引用不会被处理

**两种导入格式：**

| 格式 | 说明 |
|------|------|
| `tree` (默认) | 内联替换，保留层次结构：`<!-- Imported from: path --> content <!-- End -->` |
| `flat` | 扁平化拼接所有导入的文件 |

### 9.4 JIT (Just-in-Time) 子目录记忆

`loadJitSubdirectoryMemory()` 支持在工具操作到新目录时动态加载该目录的 GEMINI.md。这确保了当 agent 导航到项目的深层子目录时，能够自动获取该区域的上下文指令。

### 与 Claude Code CLAUDE.md 的对比

| 维度 | Gemini CLI GEMINI.md | Claude Code CLAUDE.md |
|------|---------------------|----------------------|
| 文件名 | `GEMINI.md`（可配置） | `CLAUDE.md` |
| 发现范围 | 向上遍历 + BFS 向下搜索 | 向上遍历至 home |
| 层级分类 | Global / Extension / Project 三层 | User / Project 两层 |
| 导入指令 | `@path/to/file`（支持嵌套） | 无 |
| 去重策略 | inode-based 文件身份去重 | 路径字符串去重 |
| 动态加载 | JIT 子目录记忆 | 无 |
| 文件名自定义 | 支持（`setGeminiMdFilename()`） | 不支持 |

---

## 10 SubagentTool 与调用链路

主 agent 通过 `SubagentTool` 工具调用 sub-agent。完整的调用链如下：

```
主 Agent (LLM)
  │ 调用 delegate_to_agent(name, args)
  ▼
SubagentTool
  │ 验证输入 schema
  │ 添加 user hints
  ▼
SubagentToolWrapper
  │ 根据 agent kind 分发
  ├─ Local Agent:
  │    └─ LocalSubagentInvocation
  │         └─ LocalAgentExecutor.create() → run()
  │              └─ 独立的 tool loop (ReAct)
  │              └─ 通过 complete_task 返回结果
  │
  ├─ Remote Agent:
  │    └─ RemoteAgentInvocation
  │         └─ A2AClientManager.sendMessageStream()
  │              └─ 流式接收 A2A 响应
  │
  └─ Browser Agent:
       └─ BrowserAgentInvocation
            └─ 动态设置 MCP 工具后执行
```

**只读性判断**：`SubagentTool.isReadOnly` 遍历 agent 的所有工具，仅当全部工具都是只读时，agent 本身才被标记为只读。Remote agent 始终被视为非只读。

---

## 11 Agent 配置覆盖

用户可以通过 settings 文件覆盖 agent 的运行时配置：

```json
{
  "agents": {
    "overrides": {
      "codebase_investigator": {
        "enabled": true,
        "runConfig": {
          "maxTurns": 20,
          "maxTimeMinutes": 5
        },
        "modelConfig": {
          "model": "gemini-2.5-pro"
        }
      }
    }
  }
}
```

支持覆盖的字段：
- `enabled`：启用/禁用 agent
- `runConfig`：maxTurns, maxTimeMinutes
- `modelConfig`：model, generateContentConfig

`experimental: true` 的 agent 默认禁用，必须通过 `overrides.enabled = true` 显式启用。

---

## 12 架构总对比表

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **Agent 定义** | Markdown + YAML frontmatter 声明式 | 无原生 agent 定义 |
| **内置 Agent** | 4 个（Investigator, Help, Generalist, Browser） | 内置 Agent tool（单一） |
| **Agent 执行** | LocalAgentExecutor (ReAct loop + complete_task) | Agent tool（单次委派） |
| **远程 Agent** | A2A 协议原生支持 | 无 |
| **Skill 系统** | SKILL.md + activate_skill 工具 | 无原生 skill |
| **Custom Commands** | TOML 文件 + `/` 触发 | 无（通过 CLAUDE.md 间接实现） |
| **记忆文件** | GEMINI.md（层级化 + @import） | CLAUDE.md（简单层级） |
| **安全模型** | Hash-based acknowledgement + PolicyEngine + folder trust | 简化的信任模型 |
| **Tool 隔离** | 每个 agent 独立 ToolRegistry | 共享 tool 集 |
| **递归防护** | 硬编码禁止 agent 调用 agent | 无明确机制 |
| **对话压缩** | ChatCompressionService 自动压缩 | 上下文窗口截断 |
| **用户引导** | UserHintService 实时注入 | 无（需新消息） |

---

## References

| 文件 | 说明 |
|------|------|
| `packages/core/src/agents/types.ts` | Agent 类型定义：`BaseAgentDefinition`, `LocalAgentDefinition`, `RemoteAgentDefinition`, `AgentTerminateMode` |
| `packages/core/src/agents/registry.ts` | `AgentRegistry`：agent 发现、注册、覆盖、policy 集成 |
| `packages/core/src/agents/agentLoader.ts` | Markdown+YAML frontmatter 解析器、Zod schema 校验 |
| `packages/core/src/agents/local-executor.ts` | `LocalAgentExecutor`：ReAct 循环、tool 调度、压缩、恢复 |
| `packages/core/src/agents/local-invocation.ts` | `LocalSubagentInvocation`：桥接 executor 与 tool 框架 |
| `packages/core/src/agents/remote-invocation.ts` | `RemoteAgentInvocation`：A2A 协议客户端调用 |
| `packages/core/src/agents/subagent-tool.ts` | `SubagentTool`：将 agent 暴露为 LLM 可调用工具 |
| `packages/core/src/agents/subagent-tool-wrapper.ts` | `SubagentToolWrapper`：按 kind 分发 Local/Remote/Browser invocation |
| `packages/core/src/agents/a2a-client-manager.ts` | `A2AClientManager`：A2A 协议传输管理（REST/JSON-RPC/gRPC） |
| `packages/core/src/agents/codebase-investigator.ts` | CodebaseInvestigator Agent 定义 |
| `packages/core/src/agents/cli-help-agent.ts` | CliHelp Agent 定义 |
| `packages/core/src/agents/generalist-agent.ts` | Generalist Agent 定义 |
| `packages/core/src/agents/browser/browserAgentDefinition.ts` | BrowserAgent 定义 |
| `packages/core/src/agents/acknowledgedAgents.ts` | Project agent hash-based acknowledgement 持久化 |
| `packages/core/src/skills/skillLoader.ts` | Skill 发现与 SKILL.md 解析 |
| `packages/core/src/skills/skillManager.ts` | `SkillManager`：skill 生命周期管理与优先级覆盖 |
| `packages/core/src/skills/builtin/skill-creator/SKILL.md` | 内置 skill-creator skill |
| `packages/core/src/tools/activate-skill.ts` | `activate_skill` 工具实现 |
| `packages/core/src/utils/memoryDiscovery.ts` | GEMINI.md 层级发现、BFS 搜索、inode 去重 |
| `packages/core/src/utils/memoryImportProcessor.ts` | @import 指令处理（tree/flat 模式） |
| `packages/core/src/tools/memoryTool.ts` | GEMINI.md 文件名配置 |
| `packages/cli/src/services/FileCommandLoader.ts` | TOML custom command 发现与解析 |
| `packages/core/src/config/storage.ts` | 所有配置目录路径定义 |

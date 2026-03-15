# Gemini CLI Hook & Extension System 深度解析

| 条目 | 内容 |
|------|------|
| **主题** | Gemini CLI 的 Hook 事件系统与 Extension 扩展机制全面解析 |
| **版本** | 基于 gemini-cli 源码 (2025-2026, Apache-2.0) |
| **核心模块** | `packages/core/src/hooks/`, `packages/cli/src/config/extension-manager.ts` |
| **关键接口** | `HookSystem`, `HookEventName`, `GeminiCLIExtension`, `ExtensionManager` |
| **适用对象** | 需要理解 Gemini CLI 可扩展性架构的开发者和分析人员 |
| **日期** | 2026-03-14 |

---

## 1. 架构总览

Gemini CLI 的可扩展性分为两大子系统：**Hook 事件系统**和 **Extension 扩展机制**。Hook 系统提供对 agent 生命周期各阶段的拦截能力，Extension 则是一套完整的包管理体系，将 MCP servers、hooks、themes、skills、agents、policies 等能力打包分发。

核心架构组件：

```
┌─────────────────────────────────────────────────────────┐
│                     HookSystem                          │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────┐ │
│  │HookRegist│  │HookPlanne│  │ HookRunner │  │HookAggr│ │
│  │   ry     │  │    r     │  │            │  │egator  │ │
│  └──────────┘  └──────────┘  └───────────┘  └────────┘ │
│  ┌────────────────────────────────────────────────────┐ │
│  │              HookEventHandler                      │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                  ExtensionManager                       │
│  ┌────────────┐  ┌───────────────────┐  ┌────────────┐ │
│  │ExtensionLoa│  │ExtensionEnablement│  │ExtensionReg│ │
│  │   der      │  │    Manager        │  │istryClient │ │
│  └────────────┘  └───────────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────┘
```

> 📌 **关键设计原则**：Hook 系统采用 Registry → Planner → Runner → Aggregator 的管道模式，每个组件单一职责。Extension 系统继承自抽象类 `ExtensionLoader`，实现了 install/enable/disable/start/stop/uninstall 的完整生命周期。

---

## 2. Hook 事件类型全集

Gemini CLI 定义了 11 个 hook 事件，覆盖了 session、agent loop、model interaction、tool execution 的完整生命周期。每个事件都有专属的 Input/Output 类型定义。

源码位置：`packages/core/src/hooks/types.ts`

```typescript
export enum HookEventName {
  BeforeTool         = 'BeforeTool',
  AfterTool          = 'AfterTool',
  BeforeAgent        = 'BeforeAgent',
  AfterAgent         = 'AfterAgent',
  SessionStart       = 'SessionStart',
  SessionEnd         = 'SessionEnd',
  PreCompress        = 'PreCompress',
  BeforeModel        = 'BeforeModel',
  AfterModel         = 'AfterModel',
  BeforeToolSelection = 'BeforeToolSelection',
  Notification       = 'Notification',
}
```

### 2.1 事件详细说明

| 事件 | 触发时机 | Input 特有字段 | Output 能力 | 聚合策略 |
|------|----------|---------------|------------|---------|
| **SessionStart** | 会话启动/恢复/清空时 | `source: 'startup' \| 'resume' \| 'clear'` | `additionalContext` | OR decision |
| **SessionEnd** | 会话结束时 | `reason: 'exit' \| 'clear' \| 'logout' \| 'prompt_input_exit' \| 'other'` | - | Simple merge |
| **BeforeAgent** | agent loop 开始前 | `prompt: string` | `additionalContext`, block/deny | OR decision |
| **AfterAgent** | agent loop 结束后 | `prompt`, `prompt_response`, `stop_hook_active` | `clearContext: boolean` | OR decision |
| **BeforeModel** | LLM 请求发送前 | `llm_request: LLMRequest` | 修改请求参数、返回 synthetic response、block | Field replacement |
| **AfterModel** | LLM 响应返回后 | `llm_request`, `llm_response: LLMResponse` | 修改 response | Field replacement |
| **BeforeToolSelection** | tool 选择决策前 | `llm_request: LLMRequest` | 修改 `toolConfig`（mode/allowedFunctionNames） | Union merge |
| **BeforeTool** | tool 执行前 | `tool_name`, `tool_input`, `mcp_context?` | 修改 `tool_input`、block/deny/approve | OR decision |
| **AfterTool** | tool 执行后 | `tool_name`, `tool_input`, `tool_response`, `mcp_context?` | `additionalContext`, `tailToolCallRequest` | OR decision |
| **PreCompress** | 对话历史压缩前 | `trigger: 'manual' \| 'auto'` | `suppressOutput`, `systemMessage` | Simple merge |
| **Notification** | 工具权限确认等通知 | `notification_type`, `message`, `details` | `suppressOutput`, `systemMessage` | Simple merge |

> 💡 **所有事件共享的基础 Input 字段**：`session_id`、`transcript_path`、`cwd`、`hook_event_name`、`timestamp`。这些字段由 `HookEventHandler.createBaseInput()` 统一构建。

### 2.2 MCP 工具上下文

当 BeforeTool/AfterTool 事件涉及 MCP 工具时，input 会附带 `McpToolContext`：

```typescript
interface McpToolContext {
  server_name: string;
  tool_name: string;       // MCP 服务器原始工具名
  command?: string;        // stdio transport
  args?: string[];         // stdio transport
  cwd?: string;            // stdio transport
  url?: string;            // SSE/HTTP transport
  tcp?: string;            // WebSocket transport
}
```

---

## 3. Hook 类型：Command vs Runtime

源码定义了两种 hook 实现类型，通过 `HookType` enum 区分。

```typescript
export enum HookType {
  Command = 'command',
  Runtime = 'runtime',
}
```

### 3.1 Command Hook（外部进程）

Command hook 通过 shell 子进程执行外部命令。JSON 格式的 input 通过 stdin 传入，hook 通过 stdout 返回 JSON 格式的 output。

```typescript
interface CommandHookConfig {
  type: HookType.Command;
  command: string;         // Shell 命令
  name?: string;           // 可选标识名
  description?: string;    // 可选描述
  timeout?: number;        // 超时(ms)，默认 60000
  source?: ConfigSource;   // 配置来源
  env?: Record<string, string>;  // 额外环境变量
}
```

**执行机制**（`HookRunner.executeCommandHook`）：
- 使用 `spawn()` 在 shell 中执行命令
- 环境变量中注入 `GEMINI_PROJECT_DIR` 和 `CLAUDE_PROJECT_DIR`（兼容性别名）
- 命令中的 `$GEMINI_PROJECT_DIR` / `$CLAUDE_PROJECT_DIR` 变量会被自动展开
- stdout 输出优先尝试 JSON 解析，失败则转为纯文本结构化 output
- 超时后先发 SIGTERM，5 秒后发 SIGKILL
- Windows 环境使用 `taskkill` 替代信号

**Exit code 语义**：

| Exit Code | 含义 | 映射 Decision |
|-----------|------|--------------|
| 0 | 成功 | `allow` + systemMessage |
| 1 | 非阻塞错误 | `allow` + Warning systemMessage |
| >=2 | 阻塞错误 | `deny` + reason |

### 3.1.1 Command Hook stdin/stdout 数据流示例

Command hook 的通信协议非常直接：HookEventHandler 将结构化的 input 序列化为 JSON 写入子进程的 stdin，子进程通过 stdout 返回 JSON 格式的 output。以下是一个 `BeforeTool` 事件拦截 `run_shell_command` 工具的完整数据流。

**stdin（系统写入子进程）**：

```json
{
  "session_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "transcript_path": "/Users/dev/.gemini/history/2026-03-15T10-30-00.jsonl",
  "cwd": "/Users/dev/my-project",
  "hook_event_name": "BeforeTool",
  "timestamp": "2026-03-15T10:30:45.123Z",
  "tool_name": "run_shell_command",
  "tool_input": {
    "command": "rm -rf /tmp/build-cache",
    "description": "Clean build cache"
  }
}
```

**stdout（子进程返回 — 允许执行并附加上下文）**：

```json
{
  "decision": "allow",
  "systemMessage": "Shell command validated: rm targets /tmp only",
  "hookSpecificOutput": {
    "additionalContext": "Build cache cleanup approved by security hook"
  }
}
```

**stdout（子进程返回 — 阻塞危险命令）**：

```json
{
  "decision": "deny",
  "reason": "Command contains destructive pattern: rm -rf with wildcard expansion"
}
```

**stdout（子进程返回 — 修改 tool_input 参数）**：

```json
{
  "decision": "allow",
  "hookSpecificOutput": {
    "tool_input": {
      "command": "rm -rf /tmp/build-cache --interactive",
      "description": "Clean build cache (modified by safety hook)"
    }
  }
}
```

> 💡 **纯文本 fallback**：如果 stdout 输出不是合法 JSON，`HookRunner` 会调用 `convertPlainTextToHookOutput()` 将纯文本转换为结构化 output。Exit code 0 时文本变为 `systemMessage`，exit code 1 时变为 `Warning: <text>`，exit code >=2 时文本变为 deny 的 `reason`。

### 3.1.2 Hook 失败场景详解

Command hook 执行可能遭遇多种失败情况。`HookRunner` 对每种失败都有明确的处理路径，理解这些场景对调试至关重要。

**场景一：命令返回 non-zero exit code**

```
┌────────────────────────────────────────────────────────┐
│          Command Hook Exit Code 处理流程               │
│                                                        │
│  spawn(command) ──→ child process 执行                 │
│         │                                              │
│         ├── exit 0 ──→ success=true                    │
│         │              stdout 尝试 JSON parse          │
│         │              ├── 成功 → output=parsed JSON   │
│         │              └── 失败 → convertPlainText()   │
│         │                        decision='allow'      │
│         │                                              │
│         ├── exit 1 ──→ success=false                   │
│         │              stdout/stderr 尝试 JSON parse   │
│         │              ├── 成功 → output=parsed JSON   │
│         │              └── 失败 → convertPlainText()   │
│         │                        decision='allow'      │
│         │                        msg='Warning: <text>' │
│         │                                              │
│         └── exit ≥2 ─→ success=false                   │
│                        stdout/stderr 尝试 JSON parse   │
│                        ├── 成功 → output=parsed JSON   │
│                        └── 失败 → convertPlainText()   │
│                                  decision='deny'       │
│                                  reason=<text>         │
└────────────────────────────────────────────────────────┘
```

> 📌 **关键细节**：`success` 字段仅在 exit code 为 0 时为 `true`。但 exit code 1 虽然 `success=false`，其 decision 仍然是 `allow`，这意味着操作不会被阻塞——只是产生一条 warning。只有 exit code >= 2 才会真正阻塞操作。

**场景二：命令超时**

```python
# 模拟：hook 脚本执行超过 timeout（默认 60s）
# 实际行为序列：
# 1. HookRunner 发送 SIGTERM
# 2. 等待 5 秒
# 3. 如果进程仍在运行，发送 SIGKILL
# 4. 返回 HookExecutionResult:
#    {
#      success: false,
#      error: Error("Hook timed out after 60000ms"),
#      stdout: "<partial output if any>",
#      stderr: "<partial stderr if any>"
#    }
```

**场景三：命令不存在或无法执行**

当 `spawn()` 发生 error 事件（例如命令不存在），`HookRunner` 通过 `child.on('error')` 捕获：

```json
{
  "hookConfig": { "type": "command", "command": "nonexistent-validator" },
  "eventName": "BeforeTool",
  "success": false,
  "error": "Error: spawn nonexistent-validator ENOENT",
  "stdout": "",
  "stderr": "",
  "duration": 3
}
```

**场景四：stdout 返回非法 JSON**

```bash
# hook 脚本的 stdout 输出：
echo "This is not JSON, just plain text feedback"
exit 0
```

`HookRunner` 在 `JSON.parse` 失败后调用 `convertPlainTextToHookOutput()`：

```json
{
  "decision": "allow",
  "systemMessage": "This is not JSON, just plain text feedback"
}
```

**场景五：project hook 在 untrusted folder 中执行**

```typescript
// HookRunner.executeHook() 中的二次安全检查
if (hookConfig.source === ConfigSource.Project && !this.config.isTrustedFolder()) {
  return {
    success: false,
    error: new Error('Security: Blocked execution of project hook in untrusted folder'),
    duration: 0,
  };
}
```

> ⚠️ **失败后的全局行为**：无论哪种失败场景，`HookEventHandler.logHookExecution()` 都会通过 `coreEvents.emitFeedback('warning', ...)` 向用户显示警告消息：`Hook(s) [<name>] failed for event <eventName>. Press F12 to see the debug drawer for more details.`。同时每次执行结果都会通过 `logHookCall()` 写入 telemetry 日志。

### 3.2 Runtime Hook（进程内）

Runtime hook 是一个 TypeScript 异步函数，在 Gemini CLI 进程内直接执行。主要用于 extension 注册的编程式 hook。

```typescript
interface RuntimeHookConfig {
  type: HookType.Runtime;
  name: string;                // 必须，唯一标识
  action: HookAction;         // 异步执行函数
  timeout?: number;            // 超时(ms)，默认 60000
  source?: ConfigSource;
}

type HookAction = (
  input: HookInput,
  options?: { signal: AbortSignal },
) => Promise<HookOutput | void | null>;
```

Runtime hook 支持 `AbortSignal`，超时时会自动 abort。

> ⚠️ **安全约束**：当文件夹未被信任（untrusted）时，`source` 为 `Project` 的 hook 会被 `HookRunner` 在执行前二次拦截，即使已经注册到 registry 中也不会执行。

---

## 4. Hook 决策系统

### 4.1 HookDecision 类型

```typescript
type HookDecision = 'ask' | 'block' | 'deny' | 'approve' | 'allow' | undefined;
```

- `block` / `deny`：阻塞当前操作
- `allow` / `approve`：允许操作继续
- `ask`：请求用户确认
- `undefined`：无决策

### 4.2 HookOutput 基础结构

所有事件共享的 output 基础接口：

```typescript
interface HookOutput {
  continue?: boolean;        // false → 停止执行
  stopReason?: string;       // 停止原因
  suppressOutput?: boolean;  // 抑制输出
  systemMessage?: string;    // 系统消息
  decision?: HookDecision;   // 决策类型
  reason?: string;           // 决策原因
  hookSpecificOutput?: Record<string, unknown>;  // 事件特定输出
}
```

### 4.3 事件特定 Output 类

源码为每个需要特殊行为的事件定义了专属的 `DefaultHookOutput` 子类：

| 类 | 特殊能力 |
|----|---------|
| `BeforeToolHookOutput` | `getModifiedToolInput()` — 修改 tool 的 input 参数 |
| `BeforeModelHookOutput` | `getSyntheticResponse()` — 返回合成 LLM 响应绕过实际调用；`applyLLMRequestModifications()` — 修改请求参数 |
| `AfterModelHookOutput` | `getModifiedResponse()` — 修改 LLM 返回的 response |
| `BeforeToolSelectionHookOutput` | `applyToolConfigModifications()` — 修改工具选择配置（mode + allowedFunctionNames） |
| `AfterAgentHookOutput` | `shouldClearContext()` — 请求清除对话上下文 |
| `DefaultHookOutput` | `getAdditionalContext()` — 获取附加上下文（HTML 转义防注入）；`getTailToolCallRequest()` — 触发尾调用 |

---

## 5. Hook 系统内部架构

### 5.1 HookRegistry — 注册中心

`HookRegistry` 负责从多个配置源加载和管理 hook 注册条目。

**配置来源优先级**（`ConfigSource` enum，数字越小优先级越高）：

```typescript
enum ConfigSource {
  Runtime    = 'runtime',     // 优先级 0（最高）
  Project    = 'project',     // 优先级 1
  User       = 'user',        // 优先级 2
  System     = 'system',      // 优先级 3
  Extensions = 'extensions',  // 优先级 4（最低）
}
```

初始化流程：
1. 保留已存在的 Runtime hooks
2. 从合并后的 config 加载 hooks（需要 trusted folder）
3. 从所有活跃的 extensions 加载 hooks
4. 校验 hook 配置合法性（type 必须是 `command`/`plugin`/`runtime`）
5. 检查项目级 hook 的信任状态（`TrustedHooksManager`）

**注册条目结构**：

```typescript
interface HookRegistryEntry {
  config: HookConfig;
  source: ConfigSource;
  eventName: HookEventName;
  matcher?: string;        // 正则/精确匹配模式
  sequential?: boolean;    // 是否顺序执行
  enabled: boolean;        // 是否启用
}
```

### 5.2 HookPlanner — 执行计划器

`HookPlanner` 根据事件类型和上下文创建执行计划：

1. **过滤**：根据 `matcher` 筛选匹配的 hook（支持正则表达式和精确匹配）
2. **去重**：通过 `getHookKey(name:command)` 去除重复 hook
3. **排序**：按 ConfigSource 优先级排序
4. **策略决定**：如果任何 hook 定义了 `sequential: true`，则所有 hook 顺序执行

```typescript
interface HookExecutionPlan {
  eventName: HookEventName;
  hookConfigs: HookConfig[];
  sequential: boolean;
}
```

> 💡 **Matcher 机制**：对于 BeforeTool/AfterTool 事件，matcher 匹配 `toolName`；对于 SessionStart/SessionEnd 等事件，matcher 匹配 `trigger`/`source`。空 matcher 或 `*` 匹配所有。

### 5.3 HookRunner — 执行器

`HookRunner` 负责实际执行 hook，支持两种执行策略：

- **并行执行**（`executeHooksParallel`）：所有 hook 通过 `Promise.all` 并发执行
- **顺序执行**（`executeHooksSequential`）：逐个执行，前一个 hook 的 output 会通过 `applyHookOutputToInput` 方法修改下一个 hook 的 input

顺序执行时的 input 链式修改逻辑：
- `BeforeAgent`：`additionalContext` 追加到 `prompt`
- `BeforeModel`：`llm_request` 字段合并覆盖
- `BeforeTool`：`tool_input` 字段合并覆盖

### 5.4 HookAggregator — 结果聚合器

`HookAggregator` 根据事件类型采用不同的合并策略：

| 策略 | 适用事件 | 逻辑 |
|------|---------|------|
| **OR Decision** | BeforeTool, AfterTool, BeforeAgent, AfterAgent, SessionStart | 任一 block/deny → 整体 block；消息拼接；`suppressOutput`/`clearContext` 任一 true 即 true |
| **Field Replacement** | BeforeModel, AfterModel | 后续 hook 的输出字段覆盖前面的 |
| **Union Merge** | BeforeToolSelection | mode 取最严格（NONE > ANY > AUTO）；functionNames 取并集 |
| **Simple Merge** | SessionEnd, PreCompress, Notification | 简单对象展开合并 |

### 5.5 HookTranslator — 类型转换层

`HookTranslator` 在 GenAI SDK 的原生类型和 hook 的稳定 API 类型之间进行转换，确保 hook 接口不受 SDK 版本变化影响。

```typescript
// Hook 稳定 API 类型
interface LLMRequest {
  model: string;
  messages: Array<{ role: 'user' | 'model' | 'system'; content: string | ... }>;
  config?: { temperature?, maxOutputTokens?, topP?, topK?, ... };
  toolConfig?: { mode?: 'AUTO' | 'ANY' | 'NONE'; allowedFunctionNames?: string[] };
}

interface LLMResponse {
  text?: string;
  candidates: Array<{ content: { role: 'model'; parts: string[] }; finishReason?; ... }>;
  usageMetadata?: { promptTokenCount?; candidatesTokenCount?; totalTokenCount? };
}
```

> 📌 当前实现 `HookTranslatorGenAIv1` 仅提取文本 parts，非文本内容（图片、function call 等）会被过滤。这是有意为之，为 hook 提供简化的稳定接口。

---

## 6. Hook 配置分层与 Settings

### 6.1 配置文件位置

Hook 配置可以写在 Gemini CLI 的 settings.json 中，支持多层覆盖：

| 层级 | 路径 | 说明 |
|------|------|------|
| Project | `.gemini/settings.json` | 项目级配置，需要 trusted folder |
| User | `~/.gemini/settings.json` | 用户全局配置 |
| System | 系统级配置路径 | 管理员配置 |
| Extension | `<extension>/hooks/hooks.json` | Extension 内嵌 hooks |

### 6.2 settings.json 中的 hooks 配置

```json
{
  "hooksConfig": {
    "enabled": true,
    "disabled": ["hook-name-to-disable"],
    "notifications": true
  },
  "hooks": {
    "BeforeTool": [
      {
        "matcher": "run_shell_command",
        "sequential": true,
        "hooks": [
          {
            "type": "command",
            "name": "validate-shell",
            "command": "node /path/to/validate.js",
            "timeout": 5000,
            "env": { "CUSTOM_VAR": "value" }
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Session started'"
          }
        ]
      }
    ]
  }
}
```

**配置合并策略**：hook 数组使用 `CONCAT` 策略，即多层配置的同事件 hooks 会被拼接而非覆盖。`disabled` 数组使用 `UNION` 策略。

### 6.3 Trusted Hooks 机制

`TrustedHooksManager` 维护一个持久化的信任列表（`~/.gemini/trusted_hooks.json`），记录每个项目路径下已信任的 hook。

当检测到项目级 hook 配置中存在未信任的 command hook 时，系统会显示警告并自动标记为已信任。Runtime hook 不参与信任检查。

---

## 7. GeminiCLIExtension 接口

Extension 是 Gemini CLI 扩展能力的核心单位。每个 extension 对应磁盘上的一个目录，包含 `gemini-extension.json` 配置文件。

源码位置：`packages/core/src/config/config.ts`

```typescript
interface GeminiCLIExtension {
  name: string;
  version: string;
  isActive: boolean;
  path: string;
  id: string;
  installMetadata?: ExtensionInstallMetadata;

  // 功能模块
  mcpServers?: Record<string, MCPServerConfig>;
  contextFiles: string[];
  excludeTools?: string[];
  hooks?: { [K in HookEventName]?: HookDefinition[] };
  settings?: ExtensionSetting[];
  resolvedSettings?: ResolvedExtensionSetting[];
  skills?: SkillDefinition[];
  agents?: AgentDefinition[];
  themes?: CustomTheme[];
  rules?: PolicyRule[];
  checkers?: SafetyCheckerRule[];
  plan?: { directory?: string };
  migratedTo?: string;
}
```

### 7.1 各功能模块说明

| 模块 | 说明 | 配置来源 |
|------|------|---------|
| **mcpServers** | MCP 服务器定义，支持 stdio/SSE/HTTP transport | `gemini-extension.json` |
| **contextFiles** | 上下文文件路径列表，注入到 agent memory 中 | `gemini-extension.json` → `contextFileName` |
| **excludeTools** | 排除特定工具 pattern 列表 | `gemini-extension.json` |
| **hooks** | 事件 hooks 定义，从 `hooks/hooks.json` 加载 | `<extension>/hooks/hooks.json` |
| **skills** | agent 技能定义（Markdown frontmatter 格式） | `<extension>/skills/` 目录 |
| **agents** | sub-agent 定义 | `<extension>/agents/` 目录 |
| **themes** | 自定义 UI 主题 | `gemini-extension.json` → `themes` |
| **rules** | Policy Engine 规则 | `<extension>/policies/` 目录 |
| **checkers** | 安全检查规则 | `<extension>/policies/` 目录 |
| **settings** | 可配置的设置项（支持 env var 注入） | `gemini-extension.json` → `settings` |

### 7.2 Extension 配置文件 (`gemini-extension.json`)

```typescript
interface ExtensionConfig {
  name: string;                        // 必须
  version: string;                     // 必须
  mcpServers?: Record<string, MCPServerConfig>;
  contextFileName?: string | string[];
  excludeTools?: string[];
  settings?: ExtensionSetting[];
  themes?: CustomTheme[];
  plan?: { directory?: string };
  migratedTo?: string;
}
```

**变量水合（Hydration）**：配置文件中支持变量替换：
- `${extensionPath}` — extension 目录绝对路径
- `${workspacePath}` — 当前工作区路径
- `${/}` 或 `${pathSeparator}` — 平台路径分隔符
- 自定义 env var（来自 extension settings）

示例 MCP 配置：
```json
{
  "name": "mcp-server-example",
  "version": "1.0.0",
  "mcpServers": {
    "nodeServer": {
      "command": "node",
      "args": ["${extensionPath}${/}example.js"],
      "cwd": "${extensionPath}"
    }
  }
}
```

### 7.2.1 Extension Manifest 完整示例与字段说明

以下是一个功能完整的 `gemini-extension.json` 示例，包含 MCP server、themes、settings 和上下文文件等核心模块。

```json
{
  "name": "my-devtools-extension",
  "version": "2.1.0",
  "mcpServers": {
    "code-analyzer": {
      "command": "node",
      "args": ["${extensionPath}${/}servers${/}analyzer.js"],
      "cwd": "${extensionPath}",
      "env": {
        "LOG_LEVEL": "info",
        "API_KEY": "${MY_API_KEY}"
      }
    },
    "remote-linter": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer ${LINTER_TOKEN}"
      }
    }
  },
  "contextFileName": ["GEMINI.md", "docs/CONTRIBUTING.md"],
  "excludeTools": ["dangerous_tool_*", "internal_debug_*"],
  "settings": [
    {
      "name": "MY_API_KEY",
      "description": "API key for the code analyzer service",
      "required": true,
      "scope": "user"
    },
    {
      "name": "LINTER_TOKEN",
      "description": "Authentication token for remote linter",
      "required": false,
      "scope": "workspace"
    }
  ],
  "themes": [
    {
      "name": "devtools-dark",
      "type": "custom",
      "background": { "primary": "#1e1e2e" },
      "text": {
        "primary": "#cdd6f4",
        "secondary": "#a6adc8",
        "link": "#89b4fa",
        "accent": "#cba6f7",
        "response": "#cdd6f4"
      },
      "status": {
        "success": "#a6e3a1",
        "warning": "#f9e2af",
        "error": "#f38ba8"
      },
      "border": { "default": "#585b70" },
      "ui": {
        "comment": "#6c7086",
        "symbol": "#94e2d5",
        "active": "#89b4fa",
        "focus": "#a6e3a1",
        "gradient": ["#89b4fa", "#cba6f7", "#f38ba8"]
      },
      "background": {
        "primary": "#1e1e2e",
        "diff": { "added": "#1e3a2c", "removed": "#3a1e2c" }
      }
    }
  ],
  "plan": {
    "directory": "plans"
  }
}
```

**`gemini-extension.json` 字段说明表**：

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `name` | `string` | 是 | Extension 唯一名称，用于安装目录名和 UI 显示 |
| `version` | `string` | 是 | 语义化版本号（SemVer） |
| `mcpServers` | `Record<string, MCPServerConfig>` | 否 | MCP 服务器定义，key 为服务器名称 |
| `contextFileName` | `string \| string[]` | 否 | 上下文文件路径，注入到 agent 的 hierarchical memory |
| `excludeTools` | `string[]` | 否 | 排除工具的 glob pattern 列表，匹配的工具不会暴露给 model |
| `settings` | `ExtensionSetting[]` | 否 | 可配置设置项，支持 `user` / `workspace` 作用域 |
| `themes` | `CustomTheme[]` | 否 | 自定义 UI 主题数组 |
| `plan` | `{ directory?: string }` | 否 | 计划目录配置 |
| `migratedTo` | `string` | 否 | 迁移目标，标记此 extension 已被替代 |

**变量水合支持的占位符**：

| 变量 | 含义 | 示例展开值 |
|------|------|-----------|
| `${extensionPath}` | Extension 目录的绝对路径 | `/Users/dev/.gemini/extensions/my-ext` |
| `${workspacePath}` | 当前工作区路径 | `/Users/dev/my-project` |
| `${/}` 或 `${pathSeparator}` | 平台路径分隔符 | `/`（macOS/Linux）或 `\`（Windows） |
| `${SETTING_NAME}` | Extension settings 中定义的环境变量 | 由用户配置的实际值 |

> 📌 **Settings 生命周期**：安装时如果 extension 定义了 `settings` 且启用了 `experimental.extensionConfig`，系统会通过 `maybePromptForSettings()` 提示用户逐个配置。未配置的 required settings 会产生 warning 消息：`Extension "name" has missing settings: ...`。设置值持久化在 `.env` 文件中，按作用域区分 user-level 和 workspace-level。

### 7.3 Extension Hooks 配置 (`hooks/hooks.json`)

Extension 内的 hooks 使用独立的 JSON 文件：

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${extensionPath}/scripts/on-start.js"
          }
        ]
      }
    ]
  }
}
```

Extension hooks 的 env 变量会自动注入 extension 的 resolved settings 值。

---

## 8. ExtensionManager 生命周期

### 8.1 安装来源

```typescript
interface ExtensionInstallMetadata {
  source: string;
  type: 'git' | 'local' | 'link' | 'github-release';
  releaseTag?: string;   // github-release 专用
  ref?: string;          // git ref
  autoUpdate?: boolean;
  allowPreRelease?: boolean;
}
```

| 来源类型 | 说明 | 安装方式 |
|---------|------|---------|
| `git` | GitHub/其他 Git 仓库 | `git clone` 到临时目录后复制 |
| `github-release` | GitHub Release 资产 | 下载 release 压缩包解压 |
| `local` | 本地目录 | 复制到 extensions 目录 |
| `link` | 符号链接 | 不复制，直接引用源路径 |

> ⚠️ **安全控制**：`settings.security.blockGitExtensions` 可以禁止从远程源安装。`settings.security.allowedExtensions` 支持正则白名单过滤。

### 8.2 完整生命周期

```
install → loadExtension → enable → start → (running) → disable → stop → uninstall
                                                          ↕
                                                       restart
```

**Install**（`installOrUpdateExtension`）：
1. 安全检查：allowedExtensions 白名单、blockGitExtensions、workspace trust
2. 下载/克隆/复制源码到临时目录
3. 加载 `gemini-extension.json` 配置
4. 用户同意确认（consent）
5. 提示配置 settings（如有）
6. 复制到 `~/.gemini/extensions/<name>/`
7. 写入 `install-metadata.json`
8. 自动 enable

**Start**（`ExtensionLoader.startExtension`）：
1. 启动 MCP servers
2. 刷新 Gemini tools 列表（如果有 excludeTools）
3. 注册 policy rules 和 safety checkers 到 PolicyEngine
4. 注册 themes 到 ThemeManager
5. 刷新 hierarchical memory（上下文文件）
6. 重新初始化 hook system
7. 重新加载 skills 和 agents

**Stop**（`ExtensionLoader.stopExtension`）：
1. 停止 MCP servers
2. 刷新工具列表
3. 从 PolicyEngine 注销 rules 和 checkers
4. 从 ThemeManager 注销 themes
5. 刷新 memory 和 hook system

### 8.3 启用/禁用范围

Extension 的启用状态通过 `ExtensionEnablementManager` 管理，支持多层级作用域：

| Scope | 说明 | 持久化 |
|-------|------|--------|
| `User` | 用户全局（`~/`） | 写入 `extension-enablement.json` |
| `Workspace` | 工作区级别 | 写入 `extension-enablement.json`（路径 override） |
| `Session` | 仅当前会话 | 内存态 |

启用规则基于路径 override 列表：
- 每条 override 是一个路径规则，`!` 前缀表示禁用
- 支持 `*` 通配子目录
- 最后匹配的规则胜出
- Extension 默认启用

命令行 `-e` 参数可覆盖所有配置：`-e none` 禁用全部，`-e ext1,ext2` 仅启用指定 extension。

### 8.4 Extension Registry

Gemini CLI 提供了一个在线 extension 注册表，默认地址为 `https://geminicli.com/extensions.json`：

```typescript
interface RegistryExtension {
  id: string;
  rank: number;
  url: string;
  fullName: string;
  repoDescription: string;
  stars: number;
  extensionName: string;
  extensionVersion: string;
  extensionDescription: string;
  hasMCP: boolean;
  hasContext: boolean;
  hasHooks: boolean;
  hasSkills: boolean;
  hasCustomCommands: boolean;
  isGoogleOwned: boolean;
  licenseKey: string;
}
```

支持模糊搜索（fzf 算法）、分页、按 ranking 或字母排序。

---

## 9. Theme 系统

Extension 可以通过 `themes` 字段贡献自定义主题。

### 9.1 CustomTheme 接口

```typescript
interface CustomTheme {
  type: 'custom';
  name: string;
  text?: { primary?; secondary?; link?; accent?; response? };
  background?: { primary?; diff?: { added?; removed? } };
  border?: { default? };
  ui?: { comment?; symbol?; active?; focus?; gradient?: string[] };
  status?: { error?; success?; warning? };
  // Legacy 兼容字段
  Background?; Foreground?; LightBlue?; AccentBlue?; ...
}
```

### 9.2 ThemeManager 多源管理

`ThemeManager` 维护三个主题注册表：

| 注册表 | 来源 | 命名规则 |
|--------|------|---------|
| `settingsThemes` | 用户 settings.json 中的自定义主题 | 原名 |
| `extensionThemes` | Extension 贡献的主题 | `<themeName> (<extensionName>)` |
| `fileThemes` | 从文件路径加载的主题 | 文件 canonical path |

Extension 主题采用命名空间前缀避免冲突。内置主题包括 16 个预设：Ayu Dark/Light、Atom One Dark、Dracula、GitHub Dark/Light、Google Code、Holiday、Default Dark/Light、Shades of Purple、Solarized Dark/Light、XCode、ANSI Dark/Light。

主题切换时会自动检测终端背景色以选择兼容的 light/dark 变体。

**Extension 主题示例**：
```json
{
  "name": "themes-example",
  "version": "1.0.0",
  "themes": [
    {
      "name": "shades-of-green",
      "type": "custom",
      "background": { "primary": "#1a362a" },
      "text": { "primary": "#a6e3a1", "secondary": "#6e8e7a", "link": "#89e689" },
      "status": { "success": "#76c076", "warning": "#d9e689", "error": "#b34e4e" },
      "ui": { "comment": "#6e8e7a" }
    }
  ]
}
```

### 9.3 CustomTheme 完整字段详解

`CustomTheme` 接口定义了 5 个语义化颜色分组和若干 legacy 兼容字段。以下是每个字段的用途映射关系。

**语义化字段（推荐使用）**：

| 分组 | 字段 | 用途 | 示例值 |
|------|------|------|--------|
| `text` | `primary` | 主文本色，agent 回复正文 | `#cdd6f4` |
| `text` | `secondary` | 辅助文本色，注释、元信息 | `#a6adc8` |
| `text` | `link` | 链接色，URL 和超链接 | `#89b4fa` |
| `text` | `accent` | 强调色，变量名高亮 | `#cba6f7` |
| `text` | `response` | 回复文本色（默认等于 `primary`） | `#cdd6f4` |
| `background` | `primary` | 主背景色 | `#1e1e2e` |
| `background.diff` | `added` | Diff 新增行背景色 | `#1e3a2c` |
| `background.diff` | `removed` | Diff 删除行背景色 | `#3a1e2c` |
| `border` | `default` | 默认边框色 | `#585b70` |
| `ui` | `comment` | 代码注释色 | `#6c7086` |
| `ui` | `symbol` | 装饰符号色（bullet、icon） | `#94e2d5` |
| `ui` | `active` | 活跃状态高亮色 | `#89b4fa` |
| `ui` | `focus` | 聚焦/选中色 | `#a6e3a1` |
| `ui` | `gradient` | 渐变色数组（用于 loading 动画等） | `["#4796E4", "#847ACE", "#C3677F"]` |
| `status` | `success` | 成功状态色 | `#a6e3a1` |
| `status` | `warning` | 警告状态色 | `#f9e2af` |
| `status` | `error` | 错误状态色 | `#f38ba8` |

**Legacy 兼容字段（旧格式，仍受支持）**：

| Legacy 字段 | 对应的语义化字段 | 说明 |
|-------------|-----------------|------|
| `Background` | `background.primary` | 主背景色 |
| `Foreground` | `text.primary` | 主前景色 |
| `LightBlue` | `text.link` | 链接色 |
| `AccentBlue` | `text.link` | 蓝色强调 |
| `AccentPurple` | `text.accent` | 紫色强调 |
| `AccentCyan` | `text.link` | 青色强调 |
| `AccentGreen` | `status.success` | 绿色 |
| `AccentYellow` | `status.warning` | 黄色 |
| `AccentRed` | `status.error` | 红色 |
| `DiffAdded` | `background.diff.added` | Diff 新增背景 |
| `DiffRemoved` | `background.diff.removed` | Diff 删除背景 |
| `Comment` | `ui.comment` | 注释色 |
| `Gray` | `text.secondary` | 灰色 |
| `GradientColors` | `ui.gradient` | 渐变色数组 |

> 💡 **颜色解析规则**：`createCustomTheme()` 在构建主题时，语义化字段优先于 legacy 字段。例如 `text.primary` 存在时忽略 `Foreground`。颜色值支持：hex 格式（`#ff0000`、`#f00`）、CSS 颜色名（`darkkhaki`、`tomato`）、以及 Ink 内置颜色名（`red`、`bluebright`）。所有颜色通过 `resolveColor()` 统一解析，无法解析的颜色值会被忽略并回退到默认值。

**自动派生的颜色**：

以下颜色不需要手动指定，`createCustomTheme()` 会根据基础颜色自动计算：

| 派生颜色 | 计算方式 | 说明 |
|---------|---------|------|
| `DarkGray` | `interpolateColor(background.primary, text.secondary, 0.2)` | 边框色 |
| `InputBackground` | `interpolateColor(background.primary, text.secondary, 0.15)` | 输入区域背景 |
| `MessageBackground` | `interpolateColor(background.primary, text.secondary, 0.15)` | 消息区域背景 |
| `FocusBackground` | `interpolateColor(background.primary, status.success, 0.1)` | 聚焦选中背景 |

### 9.4 主题兼容性检测

`ThemeManager` 通过 `isThemeCompatible()` 方法自动检测当前主题与终端背景色的兼容性。检测逻辑如下：

```
终端背景色 → getLuminance() → luminance > 128 ?
                                  ├── yes → "light" 终端
                                  └── no  → "dark"  终端

主题背景色 → getLuminance() → luminance > 128 ?
                                  ├── yes → "light" 主题
                                  └── no  → "dark"  主题

兼容性 = (终端类型 === 主题类型) || 主题类型 === "ansi"
```

> ⚠️ **ANSI 主题特殊处理**：`type: 'ansi'` 的主题（如 ANSI Dark、ANSI Light）始终与任何终端背景兼容，因为它们使用终端原生颜色名而非固定的 hex 值。`NO_COLOR` 环境变量存在时，系统会强制切换到 `NoColorTheme`。

---

## 10. Extension 目录结构

一个完整的 extension 目录结构：

```
my-extension/
├── gemini-extension.json      # 主配置文件（必须）
├── install-metadata.json      # 安装元数据（系统生成）
├── hooks/
│   └── hooks.json             # Hook 定义
├── skills/
│   └── my-skill.md            # Skill 定义（Markdown + frontmatter）
├── agents/
│   └── my-agent.json          # Sub-agent 定义
├── policies/
│   └── policy.json            # Policy Engine 规则
├── scripts/
│   └── on-start.js            # Hook 脚本
└── GEMINI.md                  # 上下文文件（contextFileName 引用）
```

**Skill 定义格式**：

```markdown
---
name: my-skill
description: Skill 描述
disabled: false
---

Skill 的指令正文（body），作为 prompt 注入到 agent。
```

---

## 11. 与 Claude Code Hooks 的对比

### 11.1 Hook 事件对比

| 能力 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **事件数量** | 11 个 | 约 4-5 个（PreToolUse, PostToolUse, Notification, Stop） |
| **Session 生命周期** | SessionStart, SessionEnd | 无专门事件 |
| **Model 层 hook** | BeforeModel, AfterModel, BeforeToolSelection | 无 |
| **Agent loop hook** | BeforeAgent, AfterAgent | 无直接对应（Stop hook 部分覆盖） |
| **压缩事件** | PreCompress | 无 |
| **Tool 事件** | BeforeTool, AfterTool | PreToolUse, PostToolUse |
| **通知事件** | Notification | Notification |

### 11.2 Hook 类型对比

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **实现类型** | Command + Runtime（进程内函数） | 仅 Command（外部脚本） |
| **通信方式** | stdin(JSON) → stdout(JSON) | stdin(JSON) → stdout(JSON) |
| **超时机制** | 可配置，默认 60s | 可配置，有默认超时 |
| **Exit code 语义** | 0=allow, 1=warn, >=2=block | 0=allow, 2=block |
| **决策类型** | ask/block/deny/approve/allow | approve/block |
| **匹配模式** | 正则 matcher | tool name 精确匹配 |

### 11.3 扩展机制对比

| 维度 | Gemini CLI Extension | Claude Code |
|------|---------------------|-------------|
| **包管理** | 完整 install/enable/disable 生命周期 | 无 extension 系统（hooks 仅通过 settings 配置） |
| **分发渠道** | Extension Registry + GitHub | 无（手动配置） |
| **能力范围** | MCP + hooks + themes + skills + agents + policies | hooks 仅配置文件 |
| **主题系统** | 完整的 CustomTheme 系统 | 无 |
| **配置分层** | Runtime > Project > User > System > Extensions | Project > User |
| **信任模型** | Trusted folders + hook 信任 + consent 确认 | 无显式信任机制 |
| **热重载** | 支持 enable/disable/restart 不退出 | 配置变更需重启 |

### 11.4 Hook 配置格式对比

**Gemini CLI**（`settings.json` 或 `hooks/hooks.json`）：
```json
{
  "hooks": {
    "BeforeTool": [
      {
        "matcher": "run_shell_command",
        "sequential": true,
        "hooks": [
          { "type": "command", "command": "node validate.js", "timeout": 5000 }
        ]
      }
    ]
  }
}
```

**Claude Code**（`.claude/settings.json`）：
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": ["python3 /path/to/validate.py"]
      }
    ]
  }
}
```

> 📌 **核心区别**：Gemini CLI 的 hook 定义是结构化对象（包含 type/name/command/timeout/env），Claude Code 的 hook 仅是命令字符串数组。Gemini CLI 支持 `sequential` 控制执行策略和 matcher 正则匹配，Claude Code 使用简单的工具名匹配。

---

## 12. 安全模型

### 12.1 多层安全机制

Gemini CLI 的 hook 和 extension 系统实现了多层安全防护：

| 层级 | 机制 | 说明 |
|------|------|------|
| **文件夹信任** | `TrustedFolders` | 项目级 hook 仅在受信任文件夹中执行 |
| **Hook 信任** | `TrustedHooksManager` | 首次检测到新的项目级 command hook 时警告 |
| **Extension 白名单** | `security.allowedExtensions` | 正则表达式白名单过滤 extension 来源 |
| **远程源阻断** | `security.blockGitExtensions` | 禁止从 GitHub/git 安装 extension |
| **Admin 管控** | `admin.extensions.enabled` | 管理员可全局禁用 extension 系统 |
| **MCP 管控** | `admin.mcp.enabled` + `admin.mcp.config` | 管理员 allowlist 过滤 MCP servers |
| **Consent 确认** | `maybeRequestConsentOrFail` | 安装/更新时要求用户确认权限 |
| **运行时检查** | `HookRunner` | 执行时二次检查 project hook + untrusted folder |
| **环境隔离** | `sanitizeEnvironment` | 清理传递给 hook 子进程的环境变量 |
| **注入防护** | `getAdditionalContext` | HTML 转义 `<` / `>` 防止 tag 注入 |

### 12.2 环境变量安全

Command hook 执行时，环境变量经过 `sanitizeEnvironment` 过滤，然后注入：
- `GEMINI_PROJECT_DIR` — 当前工作目录
- `CLAUDE_PROJECT_DIR` — 兼容性别名
- Hook 配置中的 `env` 字段
- Extension settings 的 resolved values

---

## 13. Telemetry 与可观测性

Hook 执行全程被 telemetry 记录：

```typescript
class HookCallEvent {
  constructor(
    eventName: HookEventName,
    hookType: HookType,
    hookName: string,
    input: HookInput,
    duration: number,
    success: boolean,
    output?: HookOutput,
    exitCode?: number,
    stdout?: string,
    stderr?: string,
    errorMessage?: string,
  )
}
```

每次 hook 执行都会：
1. 通过 `coreEvents.emitHookStart` / `emitHookEnd` 发送 UI 事件
2. 通过 `logHookCall` 写入 telemetry
3. 失败时通过 `coreEvents.emitFeedback` 显示警告（使用 WeakMap 去重同一请求的重复失败）

Extension 操作同样有完整的 telemetry 事件：`ExtensionInstallEvent`、`ExtensionUpdateEvent`、`ExtensionUninstallEvent`、`ExtensionEnableEvent`、`ExtensionDisableEvent`。

---

## 14. Extension 安装流程与输出示例

### 14.1 安装命令格式

```bash
# 从 GitHub 仓库安装
gemini extension install https://github.com/user/my-extension

# 从 GitHub Release 安装（自动检测最新 release）
gemini extension install https://github.com/user/my-extension --auto-update

# 安装预发布版本
gemini extension install https://github.com/user/my-extension --pre-release

# 从本地路径安装（复制模式）
gemini extension install /path/to/local/extension

# 指定 git ref 安装
gemini extension install https://github.com/user/my-extension --ref v2.0.0

# 跳过确认提示（CI/CD 场景）
gemini extension install https://github.com/user/my-extension --consent
```

### 14.2 安装流程详解

```
gemini extension install <source>
         │
         ▼
  ┌─── inferInstallMetadata() ───────────────────────┐
  │  解析 source → 确定 type (git/github-release/    │
  │  local/link)                                      │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─── Security Checks ─────────────────────────────┐
  │  1. allowedExtensions 正则白名单检查              │
  │  2. blockGitExtensions 远程源阻断检查             │
  │  3. workspace trust 检查（本地路径需要信任）       │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─── Download/Clone ──────────────────────────────┐
  │  git clone / GitHub Release 下载 / 本地复制      │
  │  到临时目录 tempDir                               │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─── loadExtensionConfig() ───────────────────────┐
  │  读取 gemini-extension.json                      │
  │  校验名称冲突                                     │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─── Consent ─────────────────────────────────────┐
  │  maybeRequestConsentOrFail()                     │
  │  显示权限列表，等待用户确认 [y/N]                 │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─── Settings ────────────────────────────────────┐
  │  maybePromptForSettings()                        │
  │  逐个提示用户配置 required settings               │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─── Copy & Metadata ────────────────────────────┐
  │  复制到 ~/.gemini/extensions/<name>/             │
  │  写入 install-metadata.json                      │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─── Enable & Start ─────────────────────────────┐
  │  enableExtension(name, SettingScope.User)        │
  │  loadExtension → startExtension                  │
  │  → 启动 MCP servers                              │
  │  → 注册 themes 到 ThemeManager                   │
  │  → 注册 policies/checkers                        │
  │  → 刷新 hook system                              │
  └──────────────────────────────────────────────────┘
         │
         ▼
  输出: Extension "my-extension" installed
        successfully and enabled.
```

### 14.3 安装过程 Console 输出示例

**场景一：从本地路径安装需要信任确认**

```
$ gemini extension install ./my-local-extension

Do you trust the files in this folder?

The extension source at "/Users/dev/my-local-extension" is not trusted.

Trusting a folder allows Gemini CLI to load its local configurations,
including custom commands, hooks, MCP servers, agent skills, and
settings. These configurations could execute code on your behalf or
change the behavior of the CLI.

This folder contains:
  • MCP Servers (1):
    - code-analyzer
  • Hooks (2):
    - BeforeTool hook
    - SessionStart hook
  • Skills (1):
    - code-review

Do you want to trust this folder and continue with the installation? [y/N]: y
Extension "my-devtools-extension" installed successfully and enabled.
```

**场景二：安全策略阻止安装**

```
$ gemini extension install https://github.com/untrusted/extension
Error: Installing extensions from remote sources is disallowed by
your current settings.
```

**场景三：Extension 已存在**

```
$ gemini extension install https://github.com/user/my-extension
Error: Extension "my-extension" is already installed. Please
uninstall it first.
```

### 14.4 `install-metadata.json` 示例

安装完成后，系统自动生成 `install-metadata.json` 记录安装来源信息：

```json
{
  "source": "https://github.com/user/my-devtools-extension",
  "type": "github-release",
  "releaseTag": "v2.1.0",
  "autoUpdate": true,
  "allowPreRelease": false
}
```

| 字段 | 说明 |
|------|------|
| `source` | 安装来源 URL 或本地路径 |
| `type` | 安装类型：`git` / `github-release` / `local` / `link` |
| `releaseTag` | GitHub Release tag（仅 `github-release` 类型） |
| `ref` | Git ref（仅 `git` 类型指定 ref 时） |
| `autoUpdate` | 是否启用自动更新 |
| `allowPreRelease` | 是否允许预发布版本 |

---

## 15. Hook 调试指南

调试 hook 是开发 extension 和排查问题的核心技能。Gemini CLI 提供了多层可观测性工具。

### 15.1 启用 Debug 日志

Gemini CLI 使用 `debugLogger` 记录所有 hook 相关的详细日志。通过 F12 打开 debug drawer 可以查看实时日志输出。

关键的 debug 日志点：

| 日志来源 | 日志内容 | 级别 |
|---------|---------|------|
| `HookRunner.expandCommand` | `Expanding hook command: <cmd> (cwd: <path>)` | debug |
| `HookRunner.executeHook` | `Hook execution error (non-fatal): <details>` | warn |
| `HookEventHandler.logHookExecution` | `Hook execution for <event>: N succeeded, M failed (<names>)` | warn/debug |
| `HookEventHandler.processCommonHookOutputFields` | `Hook system message: <msg>` | warn |
| `HookEventHandler.processCommonHookOutputFields` | `Hook requested to stop execution: <reason>` | log |

### 15.2 捕获 Hook 的 stderr 输出

Command hook 的 stderr 输出会被完整收集并记录到 telemetry。可以利用 stderr 输出调试信息而不影响 stdout 的 JSON 返回。

**调试用 hook 脚本示例**（Python）：

```python
#!/usr/bin/env python3
"""BeforeTool hook: validate shell commands with debug logging."""
import json
import sys

# 从 stdin 读取 hook input
raw_input = sys.stdin.read()
hook_input = json.loads(raw_input)

# stderr 用于调试输出，不会影响 hook 的 JSON 返回
print(f"[DEBUG] Event: {hook_input['hook_event_name']}", file=sys.stderr)
print(f"[DEBUG] Tool: {hook_input.get('tool_name', 'N/A')}", file=sys.stderr)
print(f"[DEBUG] CWD: {hook_input['cwd']}", file=sys.stderr)
print(f"[DEBUG] Full input: {json.dumps(hook_input, indent=2)}", file=sys.stderr)

# 检查 tool_input
tool_name = hook_input.get("tool_name", "")
tool_input = hook_input.get("tool_input", {})

if tool_name == "run_shell_command":
    command = tool_input.get("command", "")
    print(f"[DEBUG] Validating command: {command}", file=sys.stderr)

    # 危险命令检查
    dangerous_patterns = ["rm -rf /", ":(){ :|:& };:", "mkfs", "dd if="]
    for pattern in dangerous_patterns:
        if pattern in command:
            print(f"[DEBUG] BLOCKED: dangerous pattern '{pattern}'", file=sys.stderr)
            # stdout 返回 JSON → deny decision
            json.dump({
                "decision": "deny",
                "reason": f"Blocked: command contains dangerous pattern '{pattern}'"
            }, sys.stdout)
            sys.exit(2)

    print("[DEBUG] Command approved", file=sys.stderr)

# stdout 返回 JSON → allow decision
json.dump({"decision": "allow"}, sys.stdout)
sys.exit(0)
```

**对应的 hook 配置**：

```json
{
  "hooks": {
    "BeforeTool": [
      {
        "matcher": "run_shell_command",
        "hooks": [
          {
            "type": "command",
            "name": "shell-validator",
            "command": "python3 /path/to/validate_shell.py",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

### 15.3 Telemetry 日志中的 Hook 记录

每次 hook 执行都会通过 `HookCallEvent` 写入 telemetry。可以通过检查 telemetry 数据来回溯历史执行情况。

**`HookCallEvent` 完整字段**：

```typescript
class HookCallEvent {
  eventName: HookEventName;     // 触发的事件名
  hookType: HookType;           // 'command' | 'runtime'
  hookName: string;             // hook 标识名
  input: HookInput;             // 完整的 input 数据（包含 session_id, cwd 等）
  duration: number;             // 执行耗时(ms)
  success: boolean;             // 是否成功
  output?: HookOutput;          // hook 返回的 output
  exitCode?: number;            // command hook 的 exit code
  stdout?: string;              // command hook 的 stdout 完整输出
  stderr?: string;              // command hook 的 stderr 完整输出
  errorMessage?: string;        // 错误消息（如果失败）
}
```

### 15.4 常见调试场景与排查步骤

**问题一：Hook 不触发**

```
排查步骤：
1. 确认 hook 配置位置正确
   - Project hook → .gemini/settings.json
   - User hook → ~/.gemini/settings.json
   - Extension hook → <extension>/hooks/hooks.json

2. 检查 hooksConfig.enabled 是否为 true
   {
     "hooksConfig": { "enabled": true }
   }

3. 检查 hook 是否在 disabled 列表中
   {
     "hooksConfig": { "disabled": ["my-hook-name"] }
   }

4. 检查 matcher 是否匹配目标工具名/事件触发器
   - BeforeTool/AfterTool: matcher 匹配 tool_name
   - SessionStart: matcher 匹配 source (startup/resume/clear)
   - 空 matcher 或 "*" 匹配所有

5. Project hook 需要当前文件夹是 trusted folder
```

**问题二：Hook 返回被忽略**

```
排查步骤：
1. 检查 stdout 输出是否是合法 JSON
   → 使用 echo '{}' | python3 hook.py | jq . 验证

2. 确认 JSON 中使用了正确的字段名
   → decision (不是 status)
   → hookSpecificOutput (不是 output)
   → tool_input (不是 toolInput)

3. 如果返回纯文本，检查 exit code 对应的语义
   → exit 0 → allow + systemMessage
   → exit 1 → allow + warning
   → exit ≥2 → deny

4. 检查 stderr 是否被误当作 output
   → HookRunner 优先解析 stdout.trim()
   → 仅当 stdout 为空时才尝试解析 stderr.trim()
```

**问题三：Hook 超时**

```
排查步骤：
1. 检查默认超时时间：60000ms (60秒)

2. 如果 hook 脚本需要更多时间，增加 timeout 配置
   {
     "type": "command",
     "command": "python3 slow_hook.py",
     "timeout": 120000
   }

3. 超时后的信号序列：
   macOS/Linux: SIGTERM → 等待 5s → SIGKILL
   Windows:     taskkill /pid <PID> /f /t

4. 检查 hook 脚本是否有阻塞式 I/O 操作
   → 网络请求建议设置自己的超时
   → 文件操作建议使用异步 I/O
```

### 15.5 Hook 执行结果在 UI 中的表现

`HookEventHandler` 在执行前后会通过 `coreEvents` 发射 UI 事件：

```
Hook 执行开始:
  coreEvents.emitHookStart({
    hookName: "shell-validator",
    eventName: "BeforeTool",
    hookIndex: 1,           // 当前是第几个 hook
    totalHooks: 3           // 本次事件共有几个 hook
  })

Hook 执行结束:
  coreEvents.emitHookEnd({
    hookName: "shell-validator",
    eventName: "BeforeTool",
    success: true
  })

Hook 执行失败（去重后显示）:
  coreEvents.emitFeedback(
    'warning',
    'Hook(s) [shell-validator] failed for event BeforeTool.
     Press F12 to see the debug drawer for more details.'
  )
```

> 📌 **重复失败去重机制**：`HookEventHandler` 使用 `WeakMap<object, Set<string>>` 以原始请求对象为 key 跟踪已报告的失败。同一个 model request 触发的相同 hook 失败只会显示一次 warning，避免 streaming 场景下的重复警告噪音。

### 15.6 手动测试 Hook 脚本

开发阶段可以脱离 Gemini CLI 直接测试 hook 脚本的 stdin/stdout 行为：

```bash
# 构造测试 input JSON
cat <<'EOF' | python3 /path/to/my_hook.py
{
  "session_id": "test-session-001",
  "transcript_path": "",
  "cwd": "/tmp/test-project",
  "hook_event_name": "BeforeTool",
  "timestamp": "2026-03-15T10:00:00.000Z",
  "tool_name": "run_shell_command",
  "tool_input": {
    "command": "ls -la /home"
  }
}
EOF

# 验证输出是合法 JSON
cat <<'EOF' | python3 /path/to/my_hook.py 2>/dev/null | jq .
{
  "session_id": "test-session-001",
  "transcript_path": "",
  "cwd": "/tmp/test-project",
  "hook_event_name": "BeforeTool",
  "timestamp": "2026-03-15T10:00:00.000Z",
  "tool_name": "run_shell_command",
  "tool_input": { "command": "echo hello" }
}
EOF

# 同时查看 stderr 调试输出
cat <<'EOF' | python3 /path/to/my_hook.py 2>&1
{
  "session_id": "test-session-001",
  "transcript_path": "",
  "cwd": "/tmp/test-project",
  "hook_event_name": "BeforeTool",
  "timestamp": "2026-03-15T10:00:00.000Z",
  "tool_name": "run_shell_command",
  "tool_input": { "command": "rm -rf /" }
}
EOF

# 检查 exit code
echo $?
# 预期: 0=allow, 1=warn, >=2=deny
```

> 💡 **EPIPE 处理**：如果 hook 脚本在读取完 stdin 之前就退出（例如只检查事件名就决定跳过），`HookRunner` 会优雅地忽略 EPIPE 错误。因此 hook 脚本不必读取完整个 stdin 也不会导致系统错误。

---

## References

| 来源 | 路径 |
|------|------|
| Hook 类型定义 | `packages/core/src/hooks/types.ts` |
| Hook 系统主入口 | `packages/core/src/hooks/hookSystem.ts` |
| Hook 注册中心 | `packages/core/src/hooks/hookRegistry.ts` |
| Hook 执行器 | `packages/core/src/hooks/hookRunner.ts` |
| Hook 计划器 | `packages/core/src/hooks/hookPlanner.ts` |
| Hook 聚合器 | `packages/core/src/hooks/hookAggregator.ts` |
| Hook 事件处理器 | `packages/core/src/hooks/hookEventHandler.ts` |
| Hook 类型转换器 | `packages/core/src/hooks/hookTranslator.ts` |
| 信任 Hook 管理 | `packages/core/src/hooks/trustedHooks.ts` |
| Extension 接口 | `packages/core/src/config/config.ts` → `GeminiCLIExtension` |
| Extension 加载器 | `packages/core/src/utils/extensionLoader.ts` |
| Extension Manager | `packages/cli/src/config/extension-manager.ts` |
| Extension 配置 | `packages/cli/src/config/extension.ts` |
| Extension 启用管理 | `packages/cli/src/config/extensions/extensionEnablement.ts` |
| Extension Registry | `packages/cli/src/config/extensionRegistryClient.ts` |
| Theme Manager | `packages/cli/src/ui/themes/theme-manager.ts` |
| Theme 类型 | `packages/cli/src/ui/themes/theme.ts` |
| Settings Schema | `packages/cli/src/config/settingsSchema.ts` → `hooksConfig` / `hooks` |
| Hook 示例 Extension | `packages/cli/src/commands/extensions/examples/hooks/` |
| Theme 示例 Extension | `packages/cli/src/commands/extensions/examples/themes-example/` |
| MCP 示例 Extension | `packages/cli/src/commands/extensions/examples/mcp-server/` |

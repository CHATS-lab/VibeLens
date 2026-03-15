# Gemini CLI 配置系统深度解析

| 条目 | 内容 |
|------|------|
| **主题** | Gemini CLI 多层配置系统架构与实现 |
| **版本** | 基于 gemini-cli 源码 (2025-2026) |
| **核心文件** | `settingsSchema.ts`, `settings.ts`, `config.ts`, `storage.ts` |
| **主要特性** | 七层优先级合并、Schema 驱动配置、Trusted Folders 安全模型 |
| **适用范围** | VibeLens 项目对 Gemini CLI 配置体系的参考分析 |
| **上次更新** | 2026-03-15 |

---

## 1. 配置优先级架构总览

Gemini CLI 配置系统采用多层优先级架构，通过 `mergeSettings()` 函数将来自不同源头的配置进行深度合并。在 `settings.ts` 中明确定义了合并顺序：

```
Schema Defaults → System Defaults → User Settings → Workspace Settings → System Overrides
```

再加上在合并之前和之后生效的 Environment Variables 与 CLI Arguments，完整的七层优先级为：

| 优先级 | 配置层 | 来源路径 | 说明 |
|--------|--------|----------|------|
| 1 (最低) | **Schema Defaults** | `settingsSchema.ts` 内的 `default` 字段 | 硬编码在代码中的内置默认值 |
| 2 | **System Defaults** | `/etc/gemini-cli/system-defaults.json` | 企业管理员预设的组织级默认值 |
| 3 | **User Settings** | `~/.gemini/settings.json` | 用户个人配置 |
| 4 | **Workspace Settings** | `<project>/.gemini/settings.json` | 项目级配置（需 trusted folder） |
| 5 (最高) | **System Overrides** | `/etc/gemini-cli/settings.json` | 企业管理员的强制覆盖配置 |
| 特殊 | **Environment Variables** | `.env` 文件及系统环境变量 | 在合并前加载，用于值中的 `$VAR` 解析 |
| 特殊 | **CLI Arguments** | `--model`, `--sandbox`, `--yolo` 等 | 最终覆盖，通过 yargs 解析 |

> 📌 **关键设计**：System Defaults（第 2 层）作为组织级默认值，优先级低于 User Settings；而 System Overrides（第 5 层）作为强制覆盖，优先级高于所有文件配置。这让企业管理员既能设定合理默认值，又能强制执行安全策略。

合并逻辑在 `settings.ts` 的 `mergeSettings()` 函数中实现：

```typescript
export function mergeSettings(
  system: Settings,        // System Overrides (最高优先级)
  systemDefaults: Settings,// System Defaults
  user: Settings,          // User Settings
  workspace: Settings,     // Workspace Settings
  isTrusted: boolean,
): MergedSettings {
  const safeWorkspace = isTrusted ? workspace : ({} as Settings);
  const schemaDefaults = getDefaultsFromSchema();

  return customDeepMerge(
    getMergeStrategyForPath,
    schemaDefaults,    // 第 1 层
    systemDefaults,    // 第 2 层
    user,              // 第 3 层
    safeWorkspace,     // 第 4 层（仅受信任时）
    system,            // 第 5 层
  ) as MergedSettings;
}
```

### 1.1 配置加载全链路 ASCII 图

以下 ASCII 图展示了从文件发现到运行时可用的完整配置加载流水线，对应 `loadSettings()` 函数的内部实现：

```
                         ┌──────────────────────────────┐
                         │     1. Discover Config Files  │
                         └──────────────┬───────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              ▼                         ▼                         ▼
  ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
  │ /etc/gemini-cli/  │   │ ~/.gemini/        │   │ <project>/.gemini/│
  │ settings.json     │   │ settings.json     │   │ settings.json     │
  │ system-defaults   │   │                   │   │                   │
  │          .json    │   │                   │   │                   │
  └────────┬──────────┘   └────────┬──────────┘   └────────┬──────────┘
           │                       │                       │
           ▼                       ▼                       ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │            2. Parse JSONC (strip-json-comments)                 │
  └──────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │            3. Zod Validate (settingsZodSchema.safeParse)        │
  │               - 类型不匹配 → SettingsError (warning)            │
  │               - JSON 格式错误 → SettingsError (error/fatal)     │
  └──────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │            4. resolveEnvVarsInObject()                          │
  │               $VAR_NAME / ${VAR_NAME} → process.env 实际值      │
  └──────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │            5. Trust Check (initialTrustCheckSettings)           │
  │               schema + systemDefaults + user → isWorkspaceTrusted│
  └──────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │            6. customDeepMerge (5 层合并)                        │
  │               schemaDefaults → sysDefaults → user →             │
  │               workspace(if trusted) → sysOverrides              │
  └──────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │            7. loadEnvironment(.env)                             │
  │               findEnvFile() → dotenv.parse → process.env        │
  └──────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │            8. Fatal Error Check                                 │
  │               severity === 'error' → throw FatalConfigError     │
  └──────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │            9. migrateDeprecatedSettings()                       │
  │               检测废弃键 → 自动迁移 → 回写可写文件              │
  └──────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │   LoadedSettings    │
                  │   (运行时可用)      │
                  └─────────────────────┘
```

> 💡 **缓存优化**：`loadSettings()` 使用 10 秒 TTL 内存缓存（`createCache<string, LoadedSettings>`），以 `normalizedWorkspaceDir` 为缓存键。在同一会话内短时间重复调用时直接返回缓存结果，避免冗余磁盘 I/O。

---

## 2. Settings Schema 定义体系

`settingsSchema.ts` 是整个配置系统的核心 schema 定义文件。它通过 `SETTINGS_SCHEMA` 常量定义了所有配置项的结构，使用 `as const satisfies SettingsSchema` 确保 TypeScript 类型推导的精确性。

### 2.1 SettingDefinition 接口

每个配置项由 `SettingDefinition` 接口描述：

```typescript
export interface SettingDefinition {
  type: SettingsType;              // 'boolean' | 'string' | 'number' | 'array' | 'object' | 'enum'
  label: string;                   // UI 显示标签
  category: string;                // 分类（General, UI, Model, Tools, Security 等）
  requiresRestart: boolean;        // 修改后是否需要重启
  default: SettingsValue;          // Schema 层默认值
  description?: string;            // 描述文本
  properties?: SettingsSchema;     // 嵌套子配置
  showInDialog?: boolean;          // 是否在 settings dialog 中显示
  ignoreInDocs?: boolean;          // 是否在生成文档中隐藏
  mergeStrategy?: MergeStrategy;   // 合并策略
  options?: SettingEnumOption[];   // enum 类型的可选值列表
  items?: SettingCollectionDefinition;       // 数组元素类型描述
  additionalProperties?: SettingCollectionDefinition; // map 类型值描述
  unit?: string;                   // 单位后缀（如 '%'）
  ref?: string;                    // JSON Schema $ref 引用标识符
}
```

### 2.2 配置分类与顶层键

`SETTINGS_SCHEMA` 定义了以下顶层配置键：

| 顶层键 | Category | 说明 |
|--------|----------|------|
| `mcpServers` | Advanced | MCP server 配置映射 |
| `policyPaths` | Advanced | 额外 policy 文件路径 |
| `adminPolicyPaths` | Advanced | 管理员 policy 文件路径 |
| `general` | General | 通用设置（editor、approval mode、checkpointing 等） |
| `output` | General | CLI 输出格式（text/json） |
| `ui` | UI | 界面设置（theme、footer、accessibility 等） |
| `ide` | IDE | IDE 集成设置 |
| `privacy` | Privacy | 隐私统计设置 |
| `telemetry` | Advanced | 遥测配置 |
| `billing` | Advanced | 计费策略（quota overage 处理） |
| `model` | Model | 模型选择与会话控制 |
| `modelConfigs` | Model | 模型配置别名与覆盖规则 |
| `agents` | Advanced | 子代理设置（含 browser agent） |
| `context` | Context | 上下文管理（file filtering、memory 等） |
| `tools` | Tools | 工具配置（sandbox、shell、ripgrep 等） |
| `mcp` | MCP | MCP server 命令与准入控制 |
| `useWriteTodos` | Advanced | WriteTodos 工具开关 |
| `security` | Security | 安全设置（YOLO mode、folder trust、env redaction 等） |
| `advanced` | Advanced | 高级选项（DNS、排除变量等） |
| `experimental` | Experimental | 实验性功能开关 |
| `extensions` | Extensions | 扩展管理设置 |
| `skills` | Advanced | Agent skills 设置 |
| `hooksConfig` | Advanced | Hooks 系统全局配置 |
| `hooks` | Advanced | Hook 事件定义（BeforeTool、AfterTool 等） |
| `admin` | Admin | 远程企业管理员设置 |

> 💡 **Schema 驱动生成**：修改 `settingsSchema.ts` 后执行 `npm run docs:settings` 可自动重新生成配置文档。这体现了 "single source of truth" 的设计理念。

### 2.3 完整 settings.json 示例与字段说明

以下是一个覆盖主要配置域的真实 `~/.gemini/settings.json` 示例（JSONC 格式，支持注释）：

```jsonc
// ~/.gemini/settings.json — 用户级配置
{
  // ─── MCP Servers（SHALLOW_MERGE 策略）───
  "mcpServers": {
    "github-mcp": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "$GITHUB_TOKEN" },
      "timeout": 30000,
      "trust": true
    },
    "custom-sse-server": {
      "url": "https://mcp.internal.company.com/sse",
      "type": "sse",
      "headers": { "X-API-Key": "${INTERNAL_MCP_KEY}" }
    }
  },

  // ─── General Settings ───
  "general": {
    "preferredEditor": "code",
    "vimMode": false,
    "defaultApprovalMode": "auto_edit",
    "enableAutoUpdate": true,
    "enableNotifications": true,
    "maxAttempts": 10,
    "checkpointing": { "enabled": true },
    "sessionRetention": {
      "enabled": true,
      "maxAge": "30d",
      "maxCount": 500,
      "minRetention": "1d"
    }
  },

  // ─── Model Settings ───
  "model": {
    "name": "gemini-2.5-pro",
    "maxSessionTurns": 50,
    "compressionThreshold": 0.5,
    "disableLoopDetection": false,
    "summarizeToolOutput": {
      "run_shell_command": { "tokenBudget": 2000 }
    }
  },

  // ─── UI Settings ───
  "ui": {
    "theme": "DefaultDark",
    "autoThemeSwitching": true,
    "showLineNumbers": true,
    "loadingPhrases": "tips",
    "footer": {
      "hideCWD": false,
      "hideModelInfo": false,
      "hideContextPercentage": false
    }
  },

  // ─── Tools Settings ───
  "tools": {
    "useRipgrep": true,
    "truncateToolOutputThreshold": 40000,
    "disableLLMCorrection": true,
    "shell": {
      "enableInteractiveShell": true,
      "inactivityTimeout": 300,
      "showColor": false
    },
    "exclude": ["dangerous_custom_tool"]
  },

  // ─── Context Settings ───
  "context": {
    "includeDirectoryTree": true,
    "discoveryMaxDirs": 200,
    "includeDirectories": ["/shared/libs"],
    "fileFiltering": {
      "respectGitIgnore": true,
      "respectGeminiIgnore": true,
      "enableFuzzySearch": true,
      "customIgnoreFilePaths": [".myignore"]
    }
  },

  // ─── Security Settings ───
  "security": {
    "disableYoloMode": false,
    "disableAlwaysAllow": false,
    "folderTrust": { "enabled": true },
    "environmentVariableRedaction": {
      "enabled": true,
      "blocked": ["AWS_SECRET_ACCESS_KEY", "DATABASE_URL"],
      "allowed": ["NODE_ENV", "HOME"]
    }
  },

  // ─── Hooks（CONCAT 策略）───
  "hooks": {
    "BeforeTool": [
      {
        "command": "echo 'Tool ${toolName} is about to run'",
        "blocking": false
      }
    ],
    "SessionEnd": [
      {
        "command": "python3 ~/scripts/log-session.py",
        "blocking": true
      }
    ]
  },

  // ─── Advanced ───
  "advanced": {
    "excludedEnvVars": ["DEBUG", "DEBUG_MODE", "VERBOSE"]
  },

  // ─── Experimental ───
  "experimental": {
    "enableAgents": false,
    "plan": true,
    "toolOutputMasking": {
      "enabled": true,
      "toolProtectionThreshold": 50000
    }
  }
}
```

**核心字段速查表：**

| 配置路径 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `model.name` | `string` | `undefined` | 主模型名称，如 `"gemini-2.5-pro"` |
| `model.compressionThreshold` | `number` | `0.5` | context 使用率触发压缩的阈值 |
| `model.maxSessionTurns` | `number` | `-1` | 会话最大轮次，`-1` 表示无限 |
| `general.defaultApprovalMode` | `enum` | `"default"` | `default` / `auto_edit` / `plan` |
| `general.maxAttempts` | `number` | `10` | 主模型请求最大重试次数（上限 10） |
| `general.sessionRetention.maxAge` | `string` | `"30d"` | 自动清理超过此时间的会话 |
| `ui.theme` | `string` | `undefined` | 颜色主题名称 |
| `ui.loadingPhrases` | `enum` | `"tips"` | `tips` / `witty` / `all` / `off` |
| `tools.useRipgrep` | `boolean` | `true` | 使用 ripgrep 加速文件搜索 |
| `tools.truncateToolOutputThreshold` | `number` | `40000` | 工具输出截断字符阈值 |
| `tools.shell.inactivityTimeout` | `number` | `300` | shell 无输出超时（秒） |
| `context.discoveryMaxDirs` | `number` | `200` | memory 发现最大目录数 |
| `security.folderTrust.enabled` | `boolean` | `true` | 启用文件夹信任机制 |
| `security.disableYoloMode` | `boolean` | `false` | 在 system overrides 中设为 `true` 可强制禁用 YOLO |
| `advanced.excludedEnvVars` | `string[]` | `["DEBUG","DEBUG_MODE"]` | 从项目 `.env` 排除的变量名（UNION 合并） |
| `hooks.BeforeTool` | `array` | `[]` | 工具执行前的 hook 定义（CONCAT 合并） |

> 📌 **JSONC 支持**：Gemini CLI 使用 `strip-json-comments` 库在解析前移除注释，因此配置文件中可以自由使用 `//` 和 `/* */` 注释。保存时通过 `updateSettingsFilePreservingFormat()` 保留原始注释和格式。

---

## 3. Merge Strategies 合并策略

配置合并并非简单的对象覆盖，Gemini CLI 实现了四种粒度化的合并策略，通过 `MergeStrategy` 枚举定义：

```typescript
export enum MergeStrategy {
  REPLACE = 'replace',        // 完全替换旧值（默认行为）
  CONCAT = 'concat',          // 数组拼接
  UNION = 'union',            // 数组合并去重
  SHALLOW_MERGE = 'shallow_merge', // 对象浅合并
}
```

### 3.1 策略行为详解

| 策略 | 行为 | 适用场景 | 示例配置键 |
|------|------|----------|------------|
| **REPLACE** | 后层值完全替换前层值 | 标量值、需整体替换的配置 | `admin.*` (所有 admin 子键) |
| **CONCAT** | 新数组追加到旧数组末尾 | 需累积的有序列表 | `hooks.BeforeTool`, `hooks.AfterTool`, `context.includeDirectories` |
| **UNION** | 数组合并后去重（`Set` 语义） | 路径列表、排除列表 | `policyPaths`, `tools.exclude`, `context.fileFiltering.customIgnoreFilePaths`, `extensions.disabled`, `skills.disabled`, `hooksConfig.disabled`, `advanced.excludedEnvVars` |
| **SHALLOW_MERGE** | 对象级浅合并（`{...old, ...new}`） | 键值映射（保留旧条目、追加/覆盖新条目） | `mcpServers` |

### 3.2 合并实现

`deepMerge.ts` 中的 `customDeepMerge()` 函数递归合并对象，在每个路径节点查询 schema 中定义的 `mergeStrategy`：

```typescript
function mergeRecursively(target, source, getMergeStrategyForPath, path = []) {
  for (const key of Object.keys(source)) {
    // 防止 prototype pollution
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') continue;

    const newPath = [...path, key];
    const mergeStrategy = getMergeStrategyForPath(newPath);

    if (mergeStrategy === MergeStrategy.SHALLOW_MERGE) {
      target[key] = { ...objValue, ...srcValue };
    } else if (Array.isArray(objValue)) {
      if (mergeStrategy === MergeStrategy.CONCAT) {
        target[key] = objValue.concat(srcArray);
      } else if (mergeStrategy === MergeStrategy.UNION) {
        target[key] = [...new Set(objValue.concat(srcArray))];
      }
    } else if (isPlainObject(objValue) && isPlainObject(srcValue)) {
      mergeRecursively(objValue, srcValue, getMergeStrategyForPath, newPath);
    } else {
      target[key] = srcValue; // 默认 REPLACE
    }
  }
}
```

> ⚠️ **Prototype Pollution 防护**：合并逻辑显式跳过 `__proto__`、`constructor`、`prototype` 键，防止通过恶意配置文件进行原型链污染攻击。

### 3.3 Config Conflict Resolution 实战场景

当多个配置层为同一个键定义了不同值时，合并策略决定了最终结果。以下通过三个真实场景展示冲突解决过程。

#### 场景 A：`mcpServers` 冲突（SHALLOW_MERGE 策略）

```jsonc
// System Defaults (/etc/gemini-cli/system-defaults.json)
{ "mcpServers": { "corp-audit": { "command": "audit-mcp", "trust": true } } }

// User Settings (~/.gemini/settings.json)
{ "mcpServers": { "github": { "command": "npx", "args": ["-y", "@mcp/github"] } } }

// Workspace Settings (<project>/.gemini/settings.json)
{ "mcpServers": { "github": { "command": "gh-mcp", "args": ["--org", "myteam"] } } }
```

```
合并结果（SHALLOW_MERGE = {...old, ...new}）：
{
  "mcpServers": {
    "corp-audit": { "command": "audit-mcp", "trust": true },   // 来自 System Defaults（保留）
    "github": { "command": "gh-mcp", "args": ["--org", "myteam"] }  // Workspace 覆盖 User
  }
}
```

> 📌 **SHALLOW_MERGE 语义**：对于 `mcpServers`，浅合并按 server name 级别操作。如果同名 server 出现在多层，高优先级层**整体替换**该 server 的配置对象，而不是递归合并其内部字段。低优先级层中不同名的 server 会被保留。

#### 场景 B：`hooks.BeforeTool` 冲突（CONCAT 策略）

```jsonc
// User Settings
{
  "hooks": {
    "BeforeTool": [{ "command": "echo 'user hook'", "blocking": false }]
  }
}

// Workspace Settings
{
  "hooks": {
    "BeforeTool": [{ "command": "python3 validate.py", "blocking": true }]
  }
}
```

```
合并结果（CONCAT = oldArray.concat(newArray)）：
{
  "hooks": {
    "BeforeTool": [
      { "command": "echo 'user hook'", "blocking": false },      // 来自 User
      { "command": "python3 validate.py", "blocking": true }     // 来自 Workspace（追加）
    ]
  }
}
```

> 💡 **CONCAT vs UNION**：CONCAT 保留顺序和重复项（适合 hooks，同一 hook 可能需要在不同层重复配置）。UNION 会去重（适合路径列表如 `tools.exclude`、`policyPaths`）。

#### 场景 C：`tools.exclude` 冲突（UNION 策略）

```jsonc
// System Defaults
{ "tools": { "exclude": ["dangerous_tool_a"] } }

// User Settings
{ "tools": { "exclude": ["dangerous_tool_a", "my_private_tool"] } }

// Workspace Settings
{ "tools": { "exclude": ["workspace_debug_tool"] } }
```

```
合并结果（UNION = [...new Set(old.concat(new))]）：
{
  "tools": {
    "exclude": ["dangerous_tool_a", "my_private_tool", "workspace_debug_tool"]
  }
}
```

注意 `"dangerous_tool_a"` 出现在两层中但在 UNION 合并后只保留一个。

#### 场景 D：System Overrides 强制覆盖

```jsonc
// User Settings — 用户尝试开启 YOLO 模式
{ "security": { "disableYoloMode": false } }

// System Overrides (/etc/gemini-cli/settings.json) — 管理员强制禁用
{ "security": { "disableYoloMode": true } }
```

```
合并结果（REPLACE 默认策略，System Overrides 优先级最高）：
{
  "security": { "disableYoloMode": true }     // 管理员策略胜出
}
```

> ⚠️ **System Overrides 是最终仲裁者**：即使用户在 `~/.gemini/settings.json` 和项目 `.gemini/settings.json` 中都设置了某个值，System Overrides（第 5 层）仍会覆盖它们。这是企业级安全策略的核心保障机制。

---

## 4. Config Class 全面解析

`Config` 类（位于 `packages/core/src/config/config.ts`）是 Gemini CLI 运行时的核心配置容器，实现了 `McpContext` 和 `AgentLoopContext` 接口。它通过 `ConfigParameters` 接收合并后的配置值，初始化所有运行时服务。

### 4.1 ConfigParameters 参数分类

`ConfigParameters` 接口定义了 80+ 个配置参数，按功能域分组如下：

#### 会话与身份

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sessionId` | `string` | (必填) | 会话唯一标识 |
| `clientName` | `string?` | `undefined` | 客户端名称 |
| `clientVersion` | `string?` | `'unknown'` | 客户端版本 |
| `interactive` | `boolean?` | `false` | 是否交互模式 |
| `ideMode` | `boolean?` | `false` | IDE 集成模式 |

#### 模型配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | `string` | (必填) | 主模型名称 |
| `embeddingModel` | `string?` | `DEFAULT_GEMINI_EMBEDDING_MODEL` | 嵌入模型 |
| `maxSessionTurns` | `number?` | `-1` (无限) | 会话最大轮次 |
| `compressionThreshold` | `number?` | `undefined` | 上下文压缩阈值 |
| `disableLoopDetection` | `boolean?` | `false` | 禁用循环检测 |
| `modelConfigServiceConfig` | `ModelConfigServiceConfig?` | `DEFAULT_MODEL_CONFIGS` | 模型配置服务 |

#### 工具系统

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `coreTools` | `string[]?` | `undefined` | 核心工具白名单 |
| `allowedTools` | `string[]?` | `undefined` | 工具免确认列表（已废弃，迁移至 Policy Engine） |
| `excludeTools` | `string[]?` | `undefined` | 排除工具列表（已废弃） |
| `toolDiscoveryCommand` | `string?` | `undefined` | 工具发现命令 |
| `toolCallCommand` | `string?` | `undefined` | 工具调用命令 |
| `useRipgrep` | `boolean?` | `true` | 使用 ripgrep 搜索 |
| `truncateToolOutputThreshold` | `number?` | `40000` | 工具输出截断阈值 |
| `disableLLMCorrection` | `boolean?` | `true` | 禁用 LLM 纠错 |
| `useWriteTodos` | `boolean?` | `true` | 启用 WriteTodos 工具 |

#### MCP 与扩展

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mcpServers` | `Record<string, MCPServerConfig>?` | `undefined` | MCP server 配置 |
| `mcpEnabled` | `boolean?` | `true` | MCP 总开关 |
| `extensionsEnabled` | `boolean?` | `true` | 扩展总开关 |
| `mcpServerCommand` | `string?` | `undefined` | MCP 启动命令 |
| `allowedMcpServers` | `string[]?` | `[]` | MCP server 白名单 |
| `blockedMcpServers` | `string[]?` | `[]` | MCP server 黑名单 |

#### 安全与策略

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sandbox` | `SandboxConfig?` | `undefined` | 沙盒配置 |
| `toolSandboxing` | `boolean?` | `false` | 工具级沙盒 |
| `approvalMode` | `ApprovalMode?` | `undefined` | 审批模式 |
| `folderTrust` | `boolean?` | `false` | 文件夹信任功能 |
| `disableYoloMode` | `boolean?` | `false` | 禁用 YOLO 模式 |
| `disableAlwaysAllow` | `boolean?` | `false` | 禁用"始终允许" |
| `policyEngineConfig` | `PolicyEngineConfig?` | `undefined` | 策略引擎配置 |
| `enableConseca` | `boolean?` | `false` | 启用 Context-Aware Security Checker |

#### 上下文与文件

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `userMemory` | `string \| HierarchicalMemory?` | `''` | 用户 memory |
| `contextFileName` | `string \| string[]?` | `undefined` | 上下文文件名 |
| `fileFiltering` | `object?` | `DEFAULT_FILE_FILTERING_OPTIONS` | 文件过滤设置 |
| `includeDirectories` | `string[]?` | `[]` | 额外包含目录 |
| `includeDirectoryTree` | `boolean?` | `true` | 包含目录树 |

#### Hooks 与 Agents

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enableHooks` | `boolean?` | `true` | 启用 hooks 系统 |
| `hooks` | `Record<HookEventName, HookDefinition[]>?` | `undefined` | 用户级 hooks |
| `projectHooks` | `Record<HookEventName, HookDefinition[]>?` | `undefined` | 项目级 hooks |
| `enableAgents` | `boolean?` | `false` | 启用子代理 |
| `agents` | `AgentSettings?` | `{}` | 子代理设置 |
| `skillsSupport` | `boolean?` | `true` | 启用 skills |

### 4.2 Config 内部服务

`Config` 构造函数初始化了大量运行时服务：

- **ToolRegistry** — 工具注册与发现
- **PromptRegistry / ResourceRegistry** — Prompt 与资源管理
- **AgentRegistry** — 子代理注册
- **SkillManager** — 技能管理器
- **PolicyEngine** — 策略引擎（取代旧的 allowedTools/excludeTools）
- **GeminiClient / BaseLlmClient** — LLM 客户端
- **SandboxManager** — 沙盒管理
- **ModelRouterService** — 模型路由
- **ModelConfigService** — 模型配置别名/覆盖
- **McpClientManager** — MCP 客户端管理
- **HookSystem** — Hook 执行系统
- **CheckerRunner / CheckerRegistry** — 安全检查基础设施
- **Storage** — 路径解析与持久化
- **WorkspaceContext** — 工作区上下文
- **FileExclusions** — 文件排除规则
- **MessageBus** — 确认请求消息总线
- **UserHintService** — 用户提示服务
- **ContextManager** — 上下文管理器

---

## 5. Storage Class 路径解析

`Storage` 类（位于 `packages/core/src/config/storage.ts`）负责解析所有配置与数据的文件系统路径，是 Gemini CLI 存储层的核心。

### 5.1 全局路径（静态方法）

所有全局路径均基于 `~/.gemini/` 目录（可通过 `GEMINI_CLI_HOME` 环境变量自定义）：

```
~/.gemini/                          # getGlobalGeminiDir()
├── settings.json                   # getGlobalSettingsPath() — 用户配置
├── memory.md                       # getGlobalMemoryFilePath()
├── installation_id                 # getInstallationIdPath()
├── google_accounts.json            # getGoogleAccountsPath()
├── oauth_creds.json                # getOAuthCredsPath()
├── trustedFolders.json             # (trustedFolders.ts)
├── keybindings.json                # getUserKeybindingsPath()
├── projects.json                   # ProjectRegistry
├── mcp-oauth-tokens.json           # getMcpOAuthTokensPath()
├── a2a-oauth-tokens.json           # getA2AOAuthTokensPath()
├── policy_integrity.json           # getPolicyIntegrityStoragePath()
├── commands/                       # getUserCommandsDir()
├── skills/                         # getUserSkillsDir()
├── agents/                         # getUserAgentsDir()
├── policies/                       # getUserPoliciesDir()
│   └── auto-saved.toml
├── acknowledgments/
│   └── agents.json                 # getAcknowledgedAgentsPath()
├── history/
│   └── <project-id>/               # getHistoryDir()
└── tmp/                            # getGlobalTempDir()
    ├── bin/                         # getGlobalBinDir()
    └── <project-id>/               # getProjectTempDir()
        ├── shell_history
        ├── checkpoints/
        ├── logs/
        ├── plans/
        ├── tracker/
        ├── tasks/
        └── chats/
```

### 5.2 系统级路径

系统配置路径因操作系统而异：

| 操作系统 | 配置目录 | Settings Path | Defaults Path |
|----------|----------|---------------|---------------|
| **macOS** | `/Library/Application Support/GeminiCli/` | `settings.json` | `system-defaults.json` |
| **Windows** | `C:\ProgramData\gemini-cli\` | `settings.json` | `system-defaults.json` |
| **Linux** | `/etc/gemini-cli/` | `settings.json` | `system-defaults.json` |

> 💡 **路径覆盖**：可通过 `GEMINI_CLI_SYSTEM_SETTINGS_PATH` 环境变量自定义系统配置路径，System Defaults 路径自动推导为同目录下的 `system-defaults.json`。还可通过 `GEMINI_CLI_SYSTEM_DEFAULTS_PATH` 单独覆盖。

### 5.3 工作区级路径（实例方法）

```
<project-root>/
├── .gemini/                        # getGeminiDir()
│   ├── settings.json               # getWorkspaceSettingsPath()
│   ├── commands/                   # getProjectCommandsDir()
│   ├── skills/                     # getProjectSkillsDir()
│   ├── agents/                     # getProjectAgentsDir()
│   ├── policies/                   # getWorkspacePoliciesDir()
│   │   └── auto-saved.toml
│   └── extensions/                 # getExtensionsDir()
│       └── gemini-extension.json
└── .agents/                        # getAgentsDir()
    └── skills/                     # getProjectAgentSkillsDir()
```

### 5.4 项目标识与迁移

`Storage` 使用 `ProjectRegistry` 为每个项目生成短标识符（slug），并自动迁移旧版基于 SHA-256 hash 的目录结构到新格式：

```typescript
async initialize(): Promise<void> {
  const registry = new ProjectRegistry(registryPath, [tempDir, historyDir]);
  await registry.initialize();
  this.projectIdentifier = await registry.getShortId(this.getProjectRoot());
  await this.performMigration();
}
```

---

## 6. Trusted Folders 安全机制

Trusted Folders 是 Gemini CLI 的重要安全特性，控制 workspace settings 是否生效。其设计目标是防止恶意仓库通过 `.gemini/settings.json` 注入危险配置。

### 6.1 信任等级

```typescript
export enum TrustLevel {
  TRUST_FOLDER = 'TRUST_FOLDER',    // 信任此文件夹本身
  TRUST_PARENT = 'TRUST_PARENT',    // 信任此文件夹的父目录
  DO_NOT_TRUST = 'DO_NOT_TRUST',    // 显式不信任
}
```

### 6.2 信任判定流程

`isWorkspaceTrusted()` 函数按以下优先级判定工作区信任状态：

```
1. Headless 模式 → 自动信任
2. Folder trust 功能被禁用 → 自动信任
3. IDE 信任状态（从 ideContextStore 获取） → 使用 IDE 判定
4. 本地 trustedFolders.json 配置 → 基于路径匹配
5. 以上均无匹配 → undefined（未确定）
```

路径匹配使用最长前缀匹配策略，支持嵌套规则的精确控制：

```typescript
isPathTrusted(location: string): boolean | undefined {
  let longestMatchLen = -1;
  let longestMatchTrust: TrustLevel | undefined;

  for (const [rulePath, trustLevel] of Object.entries(config)) {
    const effectivePath = trustLevel === TrustLevel.TRUST_PARENT
      ? path.dirname(rulePath) : rulePath;

    if (isWithinRoot(realLocation, realEffectivePath)) {
      if (rulePath.length > longestMatchLen) {
        longestMatchLen = rulePath.length;
        longestMatchTrust = trustLevel;
      }
    }
  }
  // DO_NOT_TRUST → false, TRUST_FOLDER/TRUST_PARENT → true, 无匹配 → undefined
}
```

### 6.3 信任对配置加载的影响

当 workspace 不受信任时，`mergeSettings()` 将 workspace settings 替换为空对象：

```typescript
const safeWorkspace = isTrusted ? workspace : ({} as Settings);
```

此外，`.env` 文件在不受信任的非沙盒环境中被完全忽略；在不受信任但启用沙盒时，仅允许白名单变量（`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`），且值经过清理：

```typescript
export function sanitizeEnvVar(value: string): string {
  return value.replace(/[^a-zA-Z0-9\-_./]/g, '');
}
```

> ⚠️ **安全要点**：`trustedFolders.json` 以 `0o600` 权限写入，使用 `proper-lockfile` 处理并发更新，并通过 temp-then-rename 模式确保原子写入。

### 6.4 配置文件示例

```json
// ~/.gemini/trustedFolders.json
{
  "/home/user/projects/my-project": "TRUST_FOLDER",
  "/home/user/projects": "TRUST_PARENT",
  "/tmp/untrusted-repo": "DO_NOT_TRUST"
}
```

---

## 7. 环境变量与 .env 文件支持

### 7.1 .env 文件查找策略

`findEnvFile()` 从工作目录向上递归搜索 `.env` 文件，优先使用 Gemini 专属的 `.gemini/.env`：

```
搜索顺序（每层目录）：
1. <dir>/.gemini/.env    （Gemini 专属）
2. <dir>/.env            （通用）
...向上递归...
fallback:
3. ~/.gemini/.env
4. ~/.env
```

### 7.2 环境变量解析

`envVarResolver.ts` 支持在配置值中引用环境变量，使用 `$VAR_NAME` 或 `${VAR_NAME}` 语法。该解析在配置文件加载后立即执行：

```typescript
// 所有配置层都经过 env var 解析
systemSettings = resolveEnvVarsInObject(systemResult.settings);
systemDefaultSettings = resolveEnvVarsInObject(systemDefaultsResult.settings);
userSettings = resolveEnvVarsInObject(userResult.settings);
workspaceSettings = resolveEnvVarsInObject(workspaceResult.settings);
```

支持的语法：
- `$API_KEY` — 简单变量引用
- `${BASE_URL}/api` — 花括号包裹（支持路径拼接）
- 未定义的变量保留原始占位符

### 7.3 关键环境变量

| 环境变量 | 用途 |
|----------|------|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | API 认证密钥 |
| `GOOGLE_CLOUD_PROJECT` | Google Cloud 项目 ID |
| `GOOGLE_CLOUD_LOCATION` | Google Cloud 区域 |
| `GEMINI_CLI_HOME` | 覆盖 `~` 目录（全局配置根目录） |
| `GEMINI_CLI_SYSTEM_SETTINGS_PATH` | 覆盖系统配置路径 |
| `GEMINI_CLI_SYSTEM_DEFAULTS_PATH` | 覆盖系统默认配置路径 |
| `GEMINI_CLI_TRUSTED_FOLDERS_PATH` | 覆盖受信任文件夹配置路径 |
| `GEMINI_CLI_NO_RELAUNCH` | 禁止自动重启 |
| `GEMINI_CLI_SURFACE` / `SURFACE` | 标识运行表面 |
| `GEMINI_CLI_USE_COMPUTE_ADC` | 使用 Compute ADC 认证 |
| `GEMINI_CLI_ACTIVITY_LOG_TARGET` | 活动日志目标 |
| `GEMINI_CLI_INTEGRATION_TEST` | 集成测试标志 |
| `GEMINI_SYSTEM_MD` | 覆盖系统提示 |
| `GEMINI_DEBUG_LOG_FILE` | 调试日志输出文件 |
| `GEMINI_PTY_INFO` | PTY 信息 |
| `GEMINI_PROMPT_<KEY>` | 覆盖特定 prompt |
| `CLOUD_SHELL` | Cloud Shell 环境检测 |

### 7.4 环境变量覆盖实战示例

以下展示环境变量在配置系统中的实际使用方式。

#### 示例 1：在 settings.json 中引用环境变量

```jsonc
// ~/.gemini/settings.json
{
  "mcpServers": {
    "private-api": {
      "url": "${INTERNAL_API_BASE}/mcp",
      "headers": { "Authorization": "Bearer $API_TOKEN" }
    }
  }
}
```

当系统环境变量为 `INTERNAL_API_BASE=https://mcp.corp.example.com`、`API_TOKEN=sk-abc123` 时，`resolveEnvVarsInObject()` 解析后实际值为：

```json
{
  "mcpServers": {
    "private-api": {
      "url": "https://mcp.corp.example.com/mcp",
      "headers": { "Authorization": "Bearer sk-abc123" }
    }
  }
}
```

> 💡 **未定义变量保留原样**：如果 `$API_TOKEN` 在 `process.env` 中不存在，解析结果会保留 `"Bearer $API_TOKEN"` 原始字符串，而不是替换为空字符串。这避免了意外的配置损坏。

#### 示例 2：通过 `.env` 文件注入项目级变量

```bash
# <project>/.gemini/.env  — Gemini 专属（优先级高于 <project>/.env）
GEMINI_API_KEY=AIzaSyD-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_CLOUD_PROJECT=my-genai-project
GOOGLE_CLOUD_LOCATION=us-central1
CUSTOM_TOOL_PATH=/opt/tools/bin
```

#### 示例 3：覆盖系统级路径

```bash
# 企业环境：将所有配置重定向到受管目录
export GEMINI_CLI_HOME=/corp/managed/gemini
# 等效于 ~/.gemini/ → /corp/managed/gemini/.gemini/

# 自定义系统配置路径
export GEMINI_CLI_SYSTEM_SETTINGS_PATH=/corp/policy/gemini/overrides.json
export GEMINI_CLI_SYSTEM_DEFAULTS_PATH=/corp/policy/gemini/defaults.json
```

#### 示例 4：不受信任 workspace 的 `.env` 安全处理

当 workspace 未受信任但启用了沙盒时，`.env` 文件中只有白名单变量被加载，且值经过 `sanitizeEnvVar()` 清洗：

```bash
# 项目 .env 文件内容
GEMINI_API_KEY=AIzaSyD-xxxxx     # ✅ 白名单，正常加载
GOOGLE_API_KEY=sk-12345          # ✅ 白名单，正常加载
DATABASE_URL=postgres://user:p@ss@host/db  # ❌ 非白名单，跳过
HOME=/home/malicious;rm -rf /    # ❌ 非白名单，跳过
```

白名单变量经 sanitize 后只保留 `[a-zA-Z0-9\-_./]` 字符：

```
原始值: "AIzaSyD-xxxxx"  →  清洗后: "AIzaSyD-xxxxx"  （无变化）
原始值: "sk-12345"       →  清洗后: "sk-12345"        （无变化）
```

### 7.5 排除变量

项目 `.env` 文件中的某些变量默认被排除，通过 `advanced.excludedEnvVars` 配置控制：

```typescript
export const DEFAULT_EXCLUDED_ENV_VARS = ['DEBUG', 'DEBUG_MODE'];
```

该配置使用 `MergeStrategy.UNION` 合并，因此用户可以在不同配置层中追加排除变量而不会覆盖已有列表。例如，用户在 `~/.gemini/settings.json` 中添加 `"VERBOSE"`，workspace 中添加 `"TRACE"`，最终排除列表为 `["DEBUG", "DEBUG_MODE", "VERBOSE", "TRACE"]`。

---

## 8. CLI Arguments 命令行参数

CLI Arguments 是配置优先级链的最终环节，通过 yargs 解析。在 `packages/cli/src/config/config.ts` 中定义：

| 参数 | 短选项 | 类型 | 说明 |
|------|--------|------|------|
| `--model` | `-m` | `string` | 指定模型 |
| `--prompt` | `-p` | `string` | 非交互模式 prompt |
| `--prompt-interactive` | | `string` | 交互模式初始 prompt |
| `--sandbox` | `-s` | `boolean\|string` | 启用沙盒 |
| `--yolo` | `-y` | `boolean` | YOLO 模式（自动批准所有操作） |
| `--approval-mode` | | `string` | 审批模式（`default`/`auto_edit`/`plan`/`yolo`） |
| `--policy` | | `string[]` | 额外 policy 路径 |
| `--admin-policy` | | `string[]` | 管理员 policy 路径 |
| `--debug` | `-d` | `boolean` | 调试模式 |
| `--allowed-mcp-server-names` | | `string[]` | MCP server 白名单 |
| `--allowed-tools` | | `string[]` | 工具白名单 |
| `--extensions` | `-e` | `string[]` | 启用扩展 |
| `--list-extensions` | | `boolean` | 列出扩展 |
| `--resume` | `-r` | `string` | 恢复会话 |
| `--list-sessions` | | `boolean` | 列出会话 |
| `--delete-session` | | `string` | 删除会话 |
| `--include-directories` | | `string[]` | 包含额外目录 |
| `--screen-reader` | | `boolean` | 屏幕阅读器模式 |
| `--output-format` | | `string` | 输出格式 |
| `--raw-output` | | `boolean` | 原始输出模式 |

> ⚠️ **互斥检查**：`--yolo` 和 `--approval-mode` 不能同时使用，需使用 `--approval-mode=yolo` 替代。

---

## 9. Admin Settings 远程管理

`admin` 配置区域专用于企业管理员远程控制。与其他配置层不同，Admin Settings 通过远程 API 获取，完全忽略文件级 admin 配置：

```typescript
private computeMergedSettings(): MergedSettings {
  // Remote admin settings always take precedence
  // and file-based admin settings are ignored.
  merged.admin = customDeepMerge(
    (path) => getMergeStrategyForPath(['admin', ...path]),
    adminDefaults,
    this._remoteAdminSettings?.admin ?? {},
  ) as MergedSettings['admin'];
  return merged;
}
```

Admin 可控制：

| 设置 | 说明 |
|------|------|
| `admin.secureModeEnabled` | 禁用 YOLO 模式和"始终允许" |
| `admin.mcp.enabled` | MCP 总开关 |
| `admin.mcp.config` | 管理员配置的 MCP servers |
| `admin.extensions.enabled` | 扩展总开关 |
| `admin.skills.enabled` | Skills 总开关 |

整个 `admin` 区域使用 `MergeStrategy.REPLACE`，确保企业策略无法被用户配置部分覆盖。

---

## 10. 配置加载完整流程

`loadSettings()` 函数的完整执行流程：

```
1. 规范化 workspaceDir 路径
2. 检查缓存（10 秒 TTL）
3. 解析系统配置路径（跨平台）
4. 依次加载 4 个配置文件（支持 JSONC 注释）：
   - system settings.json
   - system-defaults.json
   - ~/.gemini/settings.json
   - <project>/.gemini/settings.json
5. 对每个配置运行 Zod 验证，收集 warnings/errors
6. 保留 originalSettings 克隆（用于后续保存时保留格式）
7. 对所有配置执行 resolveEnvVarsInObject()
8. 处理遗留主题名称迁移（VS → DefaultLight, VS2015 → DefaultDark）
9. 使用 schema defaults + system defaults + user settings 做初始信任检查
10. 判定 workspace 信任状态
11. 执行完整 5 层 mergeSettings()
12. 用临时合并结果调用 loadEnvironment() 加载 .env
13. 检查致命错误，存在则抛出 FatalConfigError
14. 创建 LoadedSettings 实例
15. 执行 migrateDeprecatedSettings() 自动迁移废弃配置
16. 返回 LoadedSettings
```

> 📌 **循环依赖处理**：`loadEnvironment()` 依赖 settings（用于判断 excluded env vars 和信任状态），而 settings 中的 `$VAR` 引用又依赖已加载的环境变量。解决方案是先用 `resolveEnvVarsInObject()` 解析 settings 文件中的 env var 引用，再用临时合并结果执行 `loadEnvironment()`。

### 10.1 Zod 验证机制详解

配置加载过程中，每个配置文件在 parse 后立即通过 `settings-validation.ts` 中构建的 Zod schema 进行结构验证。验证系统从 `SETTINGS_SCHEMA` 自动生成对应的 Zod schema：

```typescript
// settings-validation.ts — 核心验证逻辑
export const settingsZodSchema = buildSettingsZodSchema();

export function validateSettings(data: unknown): {
  success: boolean;
  data?: unknown;
  error?: z.ZodError;
} {
  const result = settingsZodSchema.safeParse(data);
  return result;
}
```

验证结果的处理策略分两级：

| 验证结果 | severity | 行为 |
|----------|----------|------|
| Zod 验证失败 | `warning` | 收集错误信息，配置继续加载（宽容模式） |
| JSON 解析失败或根类型非对象 | `error` | 标记为致命错误，最终抛出 `FatalConfigError` |

> 💡 **宽容验证策略**：Zod 验证失败仅产生 warning 而非致命错误。这意味着包含少量类型错误的配置文件仍可部分加载，不会阻止 CLI 启动。schema 使用 `.passthrough()` 允许未知顶层键通过验证，确保向前兼容。

### 10.2 Zod 验证错误输出示例

以下是实际验证错误场景及其对应的终端输出格式，基于 `formatValidationError()` 函数的实现。

#### 错误 1：类型不匹配 — `model.name` 传入 object 而非 string

```jsonc
// 错误的 settings.json
{
  "model": {
    "name": { "skipNextSpeakerCheck": true }
  }
}
```

终端输出：

```
Invalid configuration in ~/.gemini/settings.json:

Error in: model.name
    Expected type string, received object
Expected: string, but received: object

Please fix the configuration.
See: https://geminicli.com/docs/reference/configuration/
```

#### 错误 2：数组元素类型错误 — `tools.allowed` 包含非字符串元素

```jsonc
// 错误的 settings.json
{
  "tools": {
    "allowed": ["git", 123, "npm test"]
  }
}
```

终端输出：

```
Invalid configuration in ~/.gemini/settings.json:

Error in: tools.allowed[1]
    Expected string, received number
Expected: string, but received: number

Please fix the configuration.
See: https://geminicli.com/docs/reference/configuration/
```

#### 错误 3：enum 值不合法 — `mcpServers` 的 `type` 字段使用了无效值

```jsonc
// 错误的 settings.json
{
  "mcpServers": {
    "bad-server": {
      "url": "https://example.com/mcp",
      "type": "websocket"
    }
  }
}
```

终端输出：

```
Invalid configuration in ~/.gemini/settings.json:

Error in: mcpServers.bad-server.type
    Invalid enum value. Expected 'stdio' | 'sse' | 'http', received 'websocket'

Please fix the configuration.
See: https://geminicli.com/docs/reference/configuration/
```

#### 错误 4：多重错误限制显示（最多 5 条）

```jsonc
// 多处错误的 settings.json
{
  "tools": {
    "allowed": [1, 2, 3, 4, 5, 6]
  }
}
```

终端输出：

```
Invalid configuration in ~/.gemini/settings.json:

Error in: tools.allowed[0]
    Expected string, received number
Expected: string, but received: number

Error in: tools.allowed[1]
    Expected string, received number
Expected: string, but received: number

Error in: tools.allowed[2]
    Expected string, received number
Expected: string, but received: number

Error in: tools.allowed[3]
    Expected string, received number
Expected: string, but received: number

Error in: tools.allowed[4]
    Expected string, received number
Expected: string, but received: number

...and 1 more errors.

Please fix the configuration.
See: https://geminicli.com/docs/reference/configuration/
```

#### 错误 5：JSON 根类型非对象 — 致命错误

```jsonc
// 致命错误：settings.json 为数组而非对象
[{"model": "gemini-2.5-pro"}]
```

此情况不经过 Zod 验证，而是在 parse 阶段被检测：

```typescript
if (typeof rawSettings !== 'object' || rawSettings === null || Array.isArray(rawSettings)) {
  settingsErrors.push({
    message: 'Settings file is not a valid JSON object.',
    path: filePath,
    severity: 'error',   // 致命错误！
  });
}
```

最终抛出 `FatalConfigError`，CLI 无法启动：

```
Error in ~/.gemini/settings.json: Settings file is not a valid JSON object.
Please fix the configuration file(s) and try again.
```

> ⚠️ **致命 vs 警告**：JSON parse 失败或根类型错误是 `severity: 'error'`（致命），会阻止 CLI 启动。Zod 字段级验证失败是 `severity: 'warning'`（警告），CLI 仍可启动但会在日志中记录问题。这种分级策略平衡了安全性和可用性。

---

## 11. 废弃配置自动迁移

`migrateDeprecatedSettings()` 在每次加载时自动检测并迁移废弃配置项：

| 废弃路径 | 新路径 | 迁移逻辑 |
|----------|--------|----------|
| `general.disableAutoUpdate` | `general.enableAutoUpdate` | 布尔取反 |
| `general.disableUpdateNag` | `general.enableAutoUpdateNotification` | 布尔取反 |
| `ui.accessibility.disableLoadingPhrases` | `ui.accessibility.enableLoadingPhrases` | 布尔取反 |
| `ui.accessibility.enableLoadingPhrases` (false) | `ui.loadingPhrases` ('off') | 语义迁移 |
| `context.fileFiltering.disableFuzzySearch` | `context.fileFiltering.enableFuzzySearch` | 布尔取反 |
| `tools.approvalMode` | `general.defaultApprovalMode` | 键移动 |
| `experimental.codebaseInvestigatorSettings` | `agents.overrides.codebase_investigator` | 结构重组 |
| `experimental.cliHelpAgentSettings` | `agents.overrides.cli_help` | 结构重组 |

对于可写文件（user/workspace），迁移结果会自动回写；对于只读文件（system），会发出 warning 提示管理员手动更新。

---

## 12. 与 Claude Code 配置对比

| 维度 | Gemini CLI | Claude Code |
|------|-----------|-------------|
| **配置层数** | 5 层文件配置 + env + CLI args | 3 层（user/project/命令行） |
| **Schema 定义** | TypeScript `as const` 对象 + 自定义 SettingDefinition | JSON Schema 或内联默认值 |
| **合并策略** | 4 种策略（REPLACE/CONCAT/UNION/SHALLOW_MERGE） | 简单深度合并 |
| **Enterprise 管理** | 双层系统配置（defaults + overrides）+ 远程 Admin API | 无系统级管理 |
| **Workspace 信任** | TrustLevel 枚举 + 最长前缀匹配 | 无显式信任模型 |
| **配置格式** | JSONC（支持注释，strip-json-comments） | JSON / YAML |
| **环境变量** | `.env` 文件分层搜索 + `$VAR` 解析 + 白名单/清理机制 | 直接 `process.env` 访问 |
| **配置验证** | Zod schema 验证 + 结构化错误报告 | 简单类型检查 |
| **配置响应性** | useSyncExternalStore 集成 + 事件驱动 | 启动时加载 |
| **路径管理** | Storage 类统一管理 + ProjectRegistry slug | `~/.claude/` 固定路径 |
| **废弃迁移** | 自动检测 + 回写 | 手动迁移 |
| **配置缓存** | 10 秒 TTL 内存缓存 | 无显式缓存 |
| **格式保留** | 保存时保留注释和格式 | 标准 JSON 序列化 |
| **Context 文件** | `GEMINI.md`（可自定义文件名） | `CLAUDE.md` |
| **本地数据目录** | `~/.gemini/` | `~/.claude/` |

> 💡 **设计哲学差异**：Gemini CLI 的配置系统明显面向企业级使用场景，提供了 System Defaults/Overrides 双层企业管理、Trusted Folders 安全模型和远程 Admin Controls。Claude Code 的配置则更偏向开发者个人使用，结构简洁直接。

---

## 13. 关键实现细节

### 13.1 LoadedSettings 响应性

`LoadedSettings` 通过 `useSyncExternalStore` 模式集成 React 响应性更新：

```typescript
subscribe(listener: () => void): () => void {
  coreEvents.on(CoreEvent.SettingsChanged, listener);
  return () => coreEvents.off(CoreEvent.SettingsChanged, listener);
}

getSnapshot(): LoadedSettingsSnapshot {
  return this._snapshot;  // 返回不可变快照
}
```

每次 `setValue()` 调用都会触发重新计算合并值、生成新快照、并发出 `SettingsChanged` 事件。

### 13.2 配置保存格式保留

`saveSettings()` 使用 `updateSettingsFilePreservingFormat()` 确保用户手动添加的注释和格式化不会丢失：

```typescript
export function saveSettings(settingsFile: SettingsFile): void {
  settingsCache.clear(); // 清除全部缓存
  updateSettingsFilePreservingFormat(
    settingsFile.path,
    settingsFile.originalSettings,
  );
}
```

### 13.3 Workspace 为 Home 目录的特殊处理

当工作区就是用户 home 目录时，workspace settings 被标记为只读且跳过加载，避免全局配置被当作项目配置处理：

```typescript
isWorkspaceHomeDir(): boolean {
  return normalizePath(resolveToRealPath(this.targetDir)) ===
    normalizePath(resolveToRealPath(homedir()));
}
```

---

## 14. 场景化配置示例

以下提供三种典型使用场景的完整配置模板，从最小化到企业级递进。

### 14.1 Minimal Config — 个人开发者快速上手

最精简的配置，只需指定模型和基本偏好：

```jsonc
// ~/.gemini/settings.json — 最小配置
{
  "model": {
    "name": "gemini-2.5-flash"
  },
  "general": {
    "defaultApprovalMode": "default"
  },
  "ui": {
    "loadingPhrases": "tips"
  }
}
```

此配置仅设置 3 个键，其余所有值均来自 Schema Defaults。适合初次使用 Gemini CLI 的个人开发者。

### 14.2 Development Config — 全栈开发团队项目配置

项目级配置（`<project>/.gemini/settings.json`），包含 MCP servers、工具自定义和 hooks 集成：

```jsonc
// <project>/.gemini/settings.json — 开发团队配置
{
  // MCP servers 供团队共享（SHALLOW_MERGE：不会覆盖用户个人的 MCP servers）
  "mcpServers": {
    "project-docs": {
      "command": "npx",
      "args": ["-y", "@mcp/docs-server", "--root", "./docs"],
      "trust": true
    },
    "db-schema": {
      "url": "http://localhost:3100/mcp",
      "type": "http"
    }
  },

  // 自动批准编辑类工具，加速开发迭代
  "general": {
    "defaultApprovalMode": "auto_edit",
    "checkpointing": { "enabled": true }
  },

  // 使用 Pro 模型获得更好的代码质量
  "model": {
    "name": "gemini-2.5-pro",
    "compressionThreshold": 0.3,
    "summarizeToolOutput": {
      "run_shell_command": { "tokenBudget": 3000 }
    }
  },

  // 项目级上下文配置
  "context": {
    "includeDirectories": ["../shared-libs", "../protos"],
    "fileFiltering": {
      "respectGitIgnore": true,
      "customIgnoreFilePaths": [".geminiignore"]
    }
  },

  // 工具排除（UNION 合并，追加到用户级排除列表）
  "tools": {
    "exclude": ["web_search"],
    "shell": {
      "inactivityTimeout": 600
    }
  },

  // CI/CD 集成 hooks（CONCAT 合并，追加到用户级 hooks）
  "hooks": {
    "BeforeTool": [
      {
        "command": "node scripts/validate-tool-call.js",
        "blocking": true
      }
    ],
    "SessionEnd": [
      {
        "command": "python3 scripts/post-session-report.py",
        "blocking": false
      }
    ]
  },

  // 额外 policy 路径（UNION 合并）
  "policyPaths": ["./policies/project-policy.toml"]
}
```

> 📌 **Workspace 配置生效前提**：此配置文件位于项目 `.gemini/` 目录中，只有当该项目被标记为受信任（`trustedFolders.json` 中有对应条目）时才会参与合并。否则在 `mergeSettings()` 中被替换为空对象。

### 14.3 Enterprise/Managed Config — 企业级安全管控

企业管理员通过 System Defaults 和 System Overrides 双层配置实现组织级管控：

```jsonc
// /etc/gemini-cli/system-defaults.json — 组织级合理默认值（可被用户覆盖）
{
  "model": {
    "name": "gemini-2.5-pro"
  },
  "general": {
    "defaultApprovalMode": "default",
    "enableAutoUpdate": true,
    "sessionRetention": {
      "enabled": true,
      "maxAge": "90d"
    }
  },
  "ui": {
    "loadingPhrases": "tips",
    "showUserIdentity": true
  },
  "tools": {
    "useRipgrep": true,
    "truncateToolOutputThreshold": 40000
  },
  "context": {
    "fileFiltering": {
      "respectGitIgnore": true,
      "respectGeminiIgnore": true
    }
  },
  // 企业 MCP servers（SHALLOW_MERGE：用户可追加自己的 servers）
  "mcpServers": {
    "corp-code-review": {
      "command": "/usr/local/bin/corp-review-mcp",
      "trust": true
    }
  },
  // 企业级遥测
  "telemetry": {
    "enabled": true,
    "target": "cloud_logging",
    "useCliAuth": true
  }
}
```

```jsonc
// /etc/gemini-cli/settings.json — 强制覆盖（用户无法更改）
{
  // 强制禁用 YOLO 模式和"始终允许"
  "security": {
    "disableYoloMode": true,
    "disableAlwaysAllow": true,
    "folderTrust": { "enabled": true },
    "environmentVariableRedaction": {
      "enabled": true,
      "blocked": ["AWS_SECRET_ACCESS_KEY", "VAULT_TOKEN", "DATABASE_URL"]
    }
  },

  // 强制排除高风险工具
  "tools": {
    "exclude": ["web_fetch"]
  },

  // 管理员 policy
  "adminPolicyPaths": ["/etc/gemini-cli/policies/corp-security.toml"],

  // 排除敏感环境变量
  "advanced": {
    "excludedEnvVars": ["AWS_SECRET_ACCESS_KEY", "VAULT_TOKEN", "CORP_SSO_TOKEN"]
  }
}
```

**三层合并效果**：

```
System Defaults (优先级 2)        → 设定组织"推荐值"
用户可在 ~/.gemini/settings.json  → 覆盖推荐值（如换用 flash 模型）
System Overrides (优先级 5)       → 强制安全策略，用户无法绕过
```

具体合并结果示例 — 当用户设置 `"security": { "disableYoloMode": false }` 时：

| 配置键 | System Defaults | User | System Overrides | **最终值** |
|--------|----------------|------|------------------|------------|
| `security.disableYoloMode` | (未设) | `false` | `true` | **`true`** (overrides 胜出) |
| `model.name` | `"gemini-2.5-pro"` | `"gemini-2.5-flash"` | (未设) | **`"gemini-2.5-flash"`** (user 覆盖 defaults) |
| `tools.exclude` | (未设) | `["my_tool"]` | `["web_fetch"]` | **`["my_tool", "web_fetch"]`** (UNION 合并) |

> ⚠️ **Admin 远程控制**：除了文件级 System Overrides，企业管理员还可通过远程 Admin API 下发 `admin.*` 配置（如 `admin.secureModeEnabled: true`）。远程 Admin 设置完全独立于文件配置，由 `setRemoteAdminSettings()` 写入并在 `computeMergedSettings()` 中强制应用。

---

## References

| 文件路径 | 用途 |
|----------|------|
| `packages/cli/src/config/settingsSchema.ts` | Settings Schema 定义（2700+ 行） |
| `packages/cli/src/config/settings.ts` | 配置加载、合并、保存、迁移逻辑 |
| `packages/core/src/config/config.ts` | Config 类和 ConfigParameters |
| `packages/core/src/config/storage.ts` | Storage 路径解析 |
| `packages/cli/src/config/trustedFolders.ts` | Trusted Folders 机制 |
| `packages/cli/src/utils/deepMerge.ts` | 自定义深度合并算法 |
| `packages/cli/src/utils/envVarResolver.ts` | 环境变量解析器 |
| `packages/cli/src/config/settings-validation.ts` | Zod 验证 schema 构建与错误格式化 |
| `packages/cli/src/config/config.ts` | CLI 参数解析（yargs） |
| `packages/core/src/utils/paths.ts` | 基础路径工具（homedir、GEMINI_DIR） |

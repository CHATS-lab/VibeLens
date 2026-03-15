# Codex CLI 配置系统深度解析

| 条目 | 内容 |
|------|------|
| **主题** | OpenAI Codex CLI 的多层配置加载、合并算法与约束系统 |
| **核心源码** | `codex-rs/config/src/`、`codex-rs/protocol/src/config_types.rs`、`codex-rs/core/src/features.rs` |
| **配置格式** | TOML（`config.toml`） |

---

## 1 背景与设计目标

一个成熟的 CLI 工具需要灵活且可预测的配置系统。用户需要在不同粒度上定制行为：全局偏好（默认模型、审批策略）、项目级约定（信任级别、沙箱模式）、以及临时的命令行覆盖。同时，企业环境还需要组织级策略的强制执行——管理员应能限制某些配置的取值范围，防止用户绕过安全策略。

Codex CLI 的配置系统通过三个核心机制满足这些需求：**多层配置栈**（按优先级逐层合并）、**递归 TOML 合并算法**（深度合并嵌套表）、以及 **约束系统**（`Constrained<T>`，对配置值施加验证和限制）。本文将逐层解析这些机制的实现细节。

---

## 2 配置层级

### 2.1 层级栈

Codex 的配置从多个来源加载，按优先级从低到高排列：

| 优先级 | 来源 | 文件路径 | 说明 |
|--------|------|----------|------|
| 1（最低） | 内置默认值 | — | 硬编码在代码中的默认配置 |
| 2 | 系统配置 | `/etc/codex/config.toml` | 系统管理员设定 |
| 3 | 用户配置 | `~/.codex/config.toml` | 用户个人偏好 |
| 4 | 项目配置 | `.codex/config.toml` | 项目级定制（仅受信项目生效） |
| 5 | Profile 配置 | 用户配置中的 `[profiles.<name>]` | 通过 `--profile <name>` 选择 |
| 6 | 托管配置（MDM） | 设备管理策略推送 | 组织级强制策略 |
| 7（最高） | CLI 覆盖 | 命令行参数和 `--config` | 临时覆盖 |

以下 ASCII 图示展示了七层配置栈的优先级关系——越靠上的层优先级越高，在合并过程中会覆盖下方层的同名配置值：

```
  ┌─────────────────────────────────────────────────────┐
  │  Layer 7: CLI / SessionFlags   (precedence = 30)    │  ◄── 最高优先级
  │  命令行 --config model=gpt-5.4 等临时覆盖            │
  ├─────────────────────────────────────────────────────┤
  │  Layer 6: LegacyManagedConfig (MDM)  (prec = 40/50) │
  │  企业 MDM 推送的 managed_config.toml                 │
  ├─────────────────────────────────────────────────────┤
  │  Layer 5: Profile (内嵌于 user config)               │
  │  [profiles.fast] → 通过 --profile fast 激活          │
  ├─────────────────────────────────────────────────────┤
  │  Layer 4: Project  (precedence = 25)                │
  │  .codex/config.toml（仅 trusted 项目生效）           │
  ├─────────────────────────────────────────────────────┤
  │  Layer 3: User  (precedence = 20)                   │
  │  ~/.codex/config.toml                               │
  ├─────────────────────────────────────────────────────┤
  │  Layer 2: System  (precedence = 10)                 │
  │  /etc/codex/config.toml                             │
  ├─────────────────────────────────────────────────────┤
  │  Layer 1: MDM Managed Preferences  (precedence = 0) │  ◄── 最低优先级
  │  macOS MDM domain/key 推送的配置                     │
  └─────────────────────────────────────────────────────┘
        ▲ 合并方向：从底部开始，逐层向上合并覆盖
```

> 💡 **最佳实践**：`precedence()` 返回的数值间留有间隔（0、10、20、25、30...），这是一种典型的"预留空间"设计——未来新增层级时无需重编号现有层。

源码中 `ConfigLayerSource` 定义了每一层的类型和 precedence 排序值：

```rust
// codex-rs/app-server-protocol/src/protocol/v2.rs

pub enum ConfigLayerSource {
    Mdm { domain: String, key: String },                // precedence = 0
    System { file: AbsolutePathBuf },                   // precedence = 10
    User { file: AbsolutePathBuf },                     // precedence = 20
    Project { dot_codex_folder: AbsolutePathBuf },      // precedence = 25
    SessionFlags,                                       // precedence = 30
    LegacyManagedConfigTomlFromFile { file: AbsolutePathBuf }, // precedence = 40
    LegacyManagedConfigTomlFromMdm,                     // precedence = 50
}

impl ConfigLayerSource {
    pub fn precedence(&self) -> i16 {
        match self {
            ConfigLayerSource::Mdm { .. } => 0,
            ConfigLayerSource::System { .. } => 10,
            ConfigLayerSource::User { .. } => 20,
            ConfigLayerSource::Project { .. } => 25,
            ConfigLayerSource::SessionFlags => 30,
            ConfigLayerSource::LegacyManagedConfigTomlFromFile { .. } => 40,
            ConfigLayerSource::LegacyManagedConfigTomlFromMdm => 50,
        }
    }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `Mdm` | `{ domain, key }` | macOS MDM managed preferences，通过 domain 和 key 标识 |
| `System` | `{ file }` | 系统级 config.toml 的绝对路径（Unix: `/etc/codex/config.toml`） |
| `User` | `{ file }` | 用户级 config.toml 的绝对路径（`$CODEX_HOME/config.toml`） |
| `Project` | `{ dot_codex_folder }` | 项目中 `.codex/` 文件夹的绝对路径，支持嵌套项目（从 root 到 cwd） |
| `SessionFlags` | — | 运行时 CLI override（`--config` 参数或 UI 中的实时修改） |

**数据结构**：

```rust
// codex-rs/config/src/state.rs

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ConfigLayerStack {
    /// Layers are listed from lowest precedence (base) to highest (top),
    /// so later entries in the Vec override earlier ones.
    layers: Vec<ConfigLayerEntry>,

    /// Index into [layers] of the user config layer, if any.
    user_layer_index: Option<usize>,

    /// Constraints that must be enforced when deriving a [Config] from the layers.
    requirements: ConfigRequirements,

    /// Raw requirements data as loaded from requirements.toml/MDM/legacy sources.
    requirements_toml: ConfigRequirementsToml,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ConfigLayerEntry {
    pub name: ConfigLayerSource,         // Layer identifier (determines precedence)
    pub config: TomlValue,               // Parsed TOML value tree
    pub raw_toml: Option<String>,        // Original TOML text (for diagnostics)
    pub version: String,                 // Content fingerprint for optimistic locking
    pub disabled_reason: Option<String>, // Why this layer was skipped (e.g., untrusted)
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `ConfigLayerSource` | 标识层的来源类型，决定排序 precedence |
| `config` | `TomlValue` | 已解析的 TOML 值树，参与 merge 运算 |
| `raw_toml` | `Option<String>` | 原始 TOML 文本，用于错误诊断中精确定位行号 |
| `version` | `String` | 内容指纹哈希，用于 ConfigService write 时的 optimistic locking |
| `disabled_reason` | `Option<String>` | 若该层被跳过（如 untrusted project），记录原因 |

> 📌 **重点**：项目级配置（`.codex/config.toml`）仅在项目被标记为 `trusted` 时生效。未受信项目的 `.codex/` 配置会被跳过，防止恶意仓库通过配置注入修改 Codex 行为。信任级别通过用户配置中的 `[projects."<path>"]` 段设置。

### 2.2 项目信任机制

```toml
# In ~/.codex/config.toml
[projects."/Users/username/my-project"]
trust_level = "trusted"
```

只有 `trust_level = "trusted"` 的项目，其 `.codex/config.toml` 才会被加载到配置栈中。这是一个重要的安全措施——防止克隆恶意仓库时配置被自动应用。

### 2.3 配置加载流程

`load_config_layers_state()` 是整个配置系统的入口函数，负责从文件系统加载各层配置并组装为 `ConfigLayerStack`。以下 ASCII 流程图展示了完整的加载序列：

```
  ┌──────────────────────────────────────────────────────────────┐
  │                  load_config_layers_state()                  │
  │           codex-rs/core/src/config_loader/mod.rs             │
  └──────────────────────┬───────────────────────────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │  1. 加载 Requirements 约束   │
          │  (Cloud → MDM → System)     │
          └──────────────┬──────────────┘
                         │
     ┌───────────────────▼───────────────────┐
     │  cloud_requirements.get()             │  从云端获取组织约束
     │  ↓                                    │
     │  macos::load_managed_admin_req()      │  读取 macOS MDM preferences
     │  ↓                                    │
     │  load_requirements_toml()             │  读取 /etc/codex/requirements.toml
     │  ↓                                    │
     │  merge_unset_fields() 逐层合并约束     │  先到先得：高优先级约束不可被低优先级覆盖
     └───────────────────┬───────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │  2. 加载 Config 层           │
          └──────────────┬──────────────┘
                         │
     ┌───────────────────▼───────────────────┐
     │  load_config_toml_for_required_layer  │
     │  ├─ /etc/codex/config.toml → System   │  读取系统配置（若文件不存在则用空 Table）
     │  ├─ ~/.codex/config.toml   → User     │  读取用户配置
     │  └─ 解析 TOML + resolve 相对路径       │
     └───────────────────┬───────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │  3. 加载 Project 层          │
          │  (仅当 cwd 存在时)           │
          └──────────────┬──────────────┘
                         │
     ┌───────────────────▼───────────────────┐
     │  合并已有层 → 提取 trust 信息          │
     │  ↓                                    │
     │  project_trust_context()              │  判断项目信任级别
     │  ↓                                    │
     │  load_project_layers()                │  从 root → cwd 沿路径逐级加载
     │  ├─ /repo/.codex/config.toml          │  .codex/config.toml（trusted 才启用）
     │  └─ /repo/sub/.codex/config.toml      │  嵌套项目配置
     └───────────────────┬───────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │  4. 追加 SessionFlags 层     │
          │  (CLI --config overrides)   │
          └──────────────┬──────────────┘
                         │
     ┌───────────────────▼───────────────────┐
     │  build_cli_overrides_layer()          │  将 --config key=val 转为 TOML 层
     │  ↓                                    │
     │  追加 Legacy managed_config.toml      │  向后兼容旧版 MDM 格式
     └───────────────────┬───────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │  5. 构造 ConfigLayerStack   │
          │  verify_layer_ordering()    │  验证层排序正确性 + 唯一 User 层
          └──────────────┬──────────────┘
                         │
          ┌──────────────▼──────────────┐
          │  ConfigLayerStack::new()    │
          │  返回完整的配置栈 ✓          │
          └─────────────────────────────┘
```

关键源码摘录——`effective_config()` 方法将所有层逐层合并为最终有效配置：

```rust
// codex-rs/config/src/state.rs

impl ConfigLayerStack {
    pub fn effective_config(&self) -> TomlValue {
        let mut merged = TomlValue::Table(toml::map::Map::new());
        for layer in self.get_layers(
            ConfigLayerStackOrdering::LowestPrecedenceFirst,
            false,  // exclude disabled layers
        ) {
            merge_toml_values(&mut merged, &layer.config);
        }
        merged
    }
}
```

> ⚠️ **注意**：`verify_layer_ordering()` 在构造 `ConfigLayerStack` 时执行严格验证——检查层的 precedence 是否单调递增、User 层是否唯一、Project 层是否按路径从 root 到 cwd 排序。任何违反都会返回 `InvalidData` 错误。

---

## 3 合并算法

### 3.1 merge_toml_values

当多层配置需要合并时，Codex 使用递归的 TOML 值合并算法（`config/src/merge.rs`）。该函数仅 18 行，但驱动了整个配置系统的核心逻辑：

```rust
// codex-rs/config/src/merge.rs — 完整实现

use toml::Value as TomlValue;

/// Merge config `overlay` into `base`, giving `overlay` precedence.
pub fn merge_toml_values(base: &mut TomlValue, overlay: &TomlValue) {
    if let TomlValue::Table(overlay_table) = overlay
        && let TomlValue::Table(base_table) = base
    {
        // 两边都是 Table：递归合并每个 key
        for (key, value) in overlay_table {
            if let Some(existing) = base_table.get_mut(key) {
                merge_toml_values(existing, value);  // 递归
            } else {
                base_table.insert(key.clone(), value.clone());  // 新增
            }
        }
    } else {
        // 非 Table-Table 场景：overlay 整体替换 base
        *base = overlay.clone();
    }
}
```

**合并规则**：
- **标量值**（字符串、数字、布尔）：高优先级层直接覆盖低优先级层
- **表（Table）**：递归合并——两层都有的键递归处理，仅一层有的键保留
- **数组**：高优先级层的数组直接替换低优先级层的数组（不是追加）

以下 ASCII 图示展示了三种合并场景的行为差异：

```
 场景 A: 标量替换 (Scalar Replace)
 ─────────────────────────────────────────────────────
  Base (User)                Overlay (Project)
  ┌──────────────────┐       ┌──────────────────┐
  │ model = "gpt-5.3"│       │ model = "gpt-5.4"│
  └──────────────────┘       └──────────────────┘
                  ↓ merge ↓
          ┌──────────────────┐
          │ model = "gpt-5.4"│  ◄── overlay 直接替换
          └──────────────────┘

 场景 B: 表的递归合并 (Table Deep Merge)
 ─────────────────────────────────────────────────────
  Base (User)                Overlay (Project)
  ┌──────────────────┐       ┌──────────────────┐
  │ [tui]            │       │ [tui]            │
  │ status_line=[..]│        │ theme = "dark"   │
  │ animations=true  │       └──────────────────┘
  └──────────────────┘
                  ↓ merge ↓
          ┌──────────────────┐
          │ [tui]            │
          │ status_line=[..] │  ◄── 保留 (base only)
          │ animations=true  │  ◄── 保留 (base only)
          │ theme = "dark"   │  ◄── 新增 (overlay only)
          └──────────────────┘

 场景 C: 数组整体替换 (Array Replace, NOT Append)
 ─────────────────────────────────────────────────────
  Base (User)                        Overlay (Project)
  ┌─────────────────────────┐        ┌──────────────────────┐
  │ status_line = [          │        │ status_line = [       │
  │   "model",              │        │   "context-remaining" │
  │   "context-remaining"   │        │ ]                     │
  │ ]                       │        └──────────────────────┘
  └─────────────────────────┘
                  ↓ merge ↓
          ┌──────────────────────┐
          │ status_line = [       │
          │   "context-remaining" │  ◄── overlay 数组整体替换，非追加！
          │ ]                     │
          └──────────────────────┘
```

> ⚠️ **注意**：数组的合并行为是"替换"而非"追加"。如果 overlay 中定义了 `status_line`，base 中的整个数组会被丢弃。这是一个容易踩坑的设计——如果你想保留 base 数组中的某些元素，必须在 overlay 中完整列出。

**完整合并示例**：

```toml
# Base (user config, priority 3)
model = "gpt-5.3-codex"
[tui]
status_line = ["model", "context-remaining"]

# Overlay (project config, priority 4)
model = "gpt-5.4"
[tui]
theme = "dark"

# Result
model = "gpt-5.4"                                    # Overridden
[tui]
status_line = ["model", "context-remaining"]          # Inherited
theme = "dark"                                        # Added
```

### 3.2 CLI Override 构建

命令行中通过 `--config key=value` 传入的覆盖项，会被 `build_cli_overrides_layer()` 转换为一个 TOML Table 层。该函数支持 dotted-path 语法，自动创建嵌套结构：

```rust
// codex-rs/config/src/overrides.rs

pub fn build_cli_overrides_layer(cli_overrides: &[(String, TomlValue)]) -> TomlValue {
    let mut root = default_empty_table();
    for (path, value) in cli_overrides {
        apply_toml_override(&mut root, path, value.clone());
    }
    root
}

/// Apply a single dotted-path override onto a TOML value.
fn apply_toml_override(root: &mut TomlValue, path: &str, value: TomlValue) {
    use toml::value::Table;

    let mut current = root;
    let mut segments_iter = path.split('.').peekable();

    while let Some(segment) = segments_iter.next() {
        let is_last = segments_iter.peek().is_none();
        if is_last {
            // 最后一段：插入值
            match current {
                TomlValue::Table(table) => {
                    table.insert(segment.to_string(), value);
                }
                _ => {
                    let mut table = Table::new();
                    table.insert(segment.to_string(), value);
                    *current = TomlValue::Table(table);
                }
            }
            return;
        }
        // 中间段：确保路径上每一级都是 Table
        match current {
            TomlValue::Table(table) => {
                current = table
                    .entry(segment.to_string())
                    .or_insert_with(|| TomlValue::Table(Table::new()));
            }
            _ => { /* ... convert to table ... */ }
        }
    }
}
```

**使用示例**：

```bash
# CLI 命令
codex --config tui.theme=dark --config model=gpt-5.4

# 等价于生成以下 TOML 层
# [tui]
# theme = "dark"
# model = "gpt-5.4"
```

### 3.3 Profile 机制

Profile 提供命名的配置方案，通过 `--profile <name>` 在命令行切换。`ConfigProfile` 是 profile 的数据结构，涵盖了几乎所有可配置的运行参数：

```rust
// codex-rs/core/src/config/profile.rs

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, JsonSchema)]
#[schemars(deny_unknown_fields)]
pub struct ConfigProfile {
    pub model: Option<String>,
    pub service_tier: Option<ServiceTier>,
    pub model_provider: Option<String>,
    pub approval_policy: Option<AskForApproval>,
    pub approvals_reviewer: Option<ApprovalsReviewer>,
    pub sandbox_mode: Option<SandboxMode>,
    pub model_reasoning_effort: Option<ReasoningEffort>,
    pub plan_mode_reasoning_effort: Option<ReasoningEffort>,
    pub model_reasoning_summary: Option<ReasoningSummary>,
    pub model_verbosity: Option<Verbosity>,
    pub personality: Option<Personality>,
    pub web_search: Option<WebSearchMode>,
    pub tools: Option<ToolsToml>,
    pub features: Option<FeaturesToml>,
    // ... 其他可选字段
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `model` | `Option<String>` | 覆盖默认模型 |
| `service_tier` | `Option<ServiceTier>` | API service tier（`fast` / `flex`） |
| `model_provider` | `Option<String>` | 指定 model_providers 表中的 provider |
| `approval_policy` | `Option<AskForApproval>` | 覆盖审批策略 |
| `sandbox_mode` | `Option<SandboxMode>` | 覆盖沙箱模式 |
| `model_reasoning_effort` | `Option<ReasoningEffort>` | 推理强度（`low`/`medium`/`high`） |
| `personality` | `Option<Personality>` | 人格风格 |
| `features` | `Option<FeaturesToml>` | Profile-scoped 功能开关 |

**TOML 配置示例**：

```toml
# Base config
model = "gpt-5.4"

[profiles.fast]
model = "gpt-5.1-codex-mini"
model_reasoning_effort = "low"

[profiles.careful]
model = "gpt-5.4"
model_reasoning_effort = "high"
approval_policy = "unless-trusted"
```

**Profile 激活场景**——以下展示 `--profile fast` 激活前后的配置状态变化：

```
 ┌────────────────────────────────────┐
 │  激活前 (无 --profile)             │
 │  ─────────────────────             │
 │  model           = "gpt-5.4"      │
 │  reasoning_effort = (default)      │
 │  approval_policy = "on-request"    │
 │  sandbox_mode    = "workspace-write│"
 └────────────────┬───────────────────┘
                  │ codex --profile fast
                  ▼
 ┌────────────────────────────────────┐
 │  激活后 (--profile fast)           │
 │  ─────────────────────             │
 │  model           = "gpt-5.1-      │
 │                    codex-mini"     │  ◄── 被 profile 覆盖
 │  reasoning_effort = "low"          │  ◄── 被 profile 覆盖
 │  approval_policy = "on-request"    │  ◄── 未被 profile 覆盖，保持原值
 │  sandbox_mode    = "workspace-write│"  ◄── 未被 profile 覆盖，保持原值
 └────────────────────────────────────┘
```

Profile 的内容作为独立的配置层参与合并，优先级介于项目配置和托管配置之间。所有 `Option` 字段中为 `None` 的不参与覆盖——只有 profile 中显式设置的值才会覆盖 base config。

> 💡 **最佳实践**：为不同工作场景创建专用 profile 是最优实践。例如 `fast` 用于快速迭代（低推理强度 + 小模型），`careful` 用于关键代码审查（高推理强度 + 强审批），通过 `--profile` 一键切换而无需修改 config.toml。

---

## 4 约束系统

配置的灵活性带来了一个问题：如何在允许用户定制的同时，确保关键配置不被设为不安全的值？Codex 通过 `Constrained<T>` 泛型解决这个问题。

### 4.1 Constrained\<T\>

`Constrained<T>` 的完整实现位于 `codex-rs/config/src/constraint.rs`，核心是三个组件的组合：值、验证器、归一化器。

```rust
// codex-rs/config/src/constraint.rs

type ConstraintValidator<T> = dyn Fn(&T) -> ConstraintResult<()> + Send + Sync;
/// A ConstraintNormalizer is a function which transforms a value into
/// another of the same type. `Constrained` uses normalizers to transform
/// values to satisfy constraints or enforce values.
type ConstraintNormalizer<T> = dyn Fn(T) -> T + Send + Sync;

#[derive(Clone)]
pub struct Constrained<T> {
    value: T,
    validator: Arc<ConstraintValidator<T>>,
    normalizer: Option<Arc<ConstraintNormalizer<T>>>,
}
```

以下 ASCII 图展示了 `set()` 方法的完整执行流程——值在到达存储之前必须通过 normalizer 和 validator 两道关卡：

```
                         ┌─────────┐
                         │ set(val)│
                         └────┬────┘
                              │
                    ┌─────────▼─────────┐
                    │ normalizer 存在？   │
                    └────┬──────────┬────┘
                    Yes  │          │  No
              ┌──────────▼──┐      │
              │ val =        │      │
              │ normalizer(  │      │
              │   val)       │      │
              └──────────┬──┘      │
                         │         │
                    ┌────▼─────────▼────┐
                    │ validator(&val)    │
                    └────┬──────────┬───┘
                    Ok   │          │  Err
              ┌──────────▼──┐  ┌───▼───────────────┐
              │ self.value   │  │ ConstraintError    │
              │   = val      │  │ 返回错误，原值不变  │
              │ return Ok(())│  │ return Err(...)     │
              └─────────────┘  └───────────────────┘
```

**四种构造模式**：

| 模式 | 方法 | 行为 |
|------|------|------|
| 验证约束 | `new(value, validator)` | 初始值和每次 `set()` 都运行验证函数 |
| 归一化约束 | `normalized(value, normalizer)` | 值先经过 normalizer 变换，再验证 |
| 无约束 | `allow_any(value)` | 允许任何值，validator 固定返回 `Ok(())` |
| 锁定约束 | `allow_only(value)` | 只允许当前值，任何不同值都被拒绝 |

完整的创建和使用方法：

```rust
impl<T: Send + Sync> Constrained<T> {
    /// 创建带自定义验证器的约束值（初始值也必须通过验证）
    pub fn new(
        initial_value: T,
        validator: impl Fn(&T) -> ConstraintResult<()> + Send + Sync + 'static,
    ) -> ConstraintResult<Self>;

    /// 创建带归一化器的约束值（validator 允许任何值）
    pub fn normalized(
        initial_value: T,
        normalizer: impl Fn(T) -> T + Send + Sync + 'static,
    ) -> ConstraintResult<Self>;

    /// 无约束：任何值都被接受
    pub fn allow_any(initial_value: T) -> Self;

    /// 锁定：只有与初始值相等的值才被接受
    pub fn allow_only(only_value: T) -> Self where T: Clone + Debug + PartialEq + 'static;

    /// 获取当前值的引用
    pub fn get(&self) -> &T;

    /// 试探性检查某个值是否满足约束（不修改当前值）
    pub fn can_set(&self, candidate: &T) -> ConstraintResult<()>;

    /// 设置新值（经过 normalizer + validator 管道）
    pub fn set(&mut self, value: T) -> ConstraintResult<()>;
}
```

**用例**：

- **模型约束**：组织策略可以限制只允许使用特定模型（`allow_only("gpt-5.4")`）
- **沙箱约束**：MDM 可以锁定沙箱模式为 `workspace-write`（禁止 `danger-full-access`）
- **审批约束**：强制执行 `unless-trusted` 审批策略

### 4.2 ConstraintError 与验证错误示例

约束验证失败时，系统会返回结构化的 `ConstraintError`，包含字段名、候选值、允许集合和约束来源等信息：

```rust
// codex-rs/config/src/constraint.rs

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ConstraintError {
    #[error(
        "invalid value for `{field_name}`: `{candidate}` is not in the \
         allowed set {allowed} (set by {requirement_source})"
    )]
    InvalidValue {
        field_name: &'static str,
        candidate: String,
        allowed: String,
        requirement_source: RequirementSource,
    },

    #[error("field `{field_name}` cannot be empty")]
    EmptyField { field_name: String },

    #[error("invalid rules in requirements (set by {requirement_source}): {reason}")]
    ExecPolicyParse {
        requirement_source: RequirementSource,
        reason: String,
    },
}
```

| 错误类型 | 触发场景 | 错误消息示例 |
|----------|----------|-------------|
| `InvalidValue` | 值不在允许集合中 | `invalid value for 'sandbox_mode': 'danger-full-access' is not in the allowed set ["read-only", "workspace-write"] (set by MDM com.openai.codex:sandbox)` |
| `EmptyField` | 必填字段为空 | `field 'model' cannot be empty` |
| `ExecPolicyParse` | requirements.toml 中的执行策略语法错误 | `invalid rules in requirements (set by /etc/codex/requirements.toml): unexpected token` |

**场景 1：锁定值被覆盖（allow_only）**

```rust
// 管理员通过 MDM 锁定 sandbox_mode 为 "read-only"
let mut sandbox = Constrained::allow_only(SandboxMode::ReadOnly);

// 用户尝试在 config.toml 中设置 sandbox_mode = "danger-full-access"
let result = sandbox.set(SandboxMode::DangerFullAccess);
// => Err(ConstraintError::InvalidValue {
//        field_name: "<unknown>",
//        candidate: "DangerFullAccess",
//        allowed: "[ReadOnly]",
//        requirement_source: RequirementSource::Unknown,
//    })

// 原值保持不变
assert_eq!(*sandbox.get(), SandboxMode::ReadOnly);
```

**场景 2：自定义验证器（new）**

```rust
// 只允许正数的约束
let mut constrained = Constrained::new(1, |value| {
    if *value > 0 {
        Ok(())
    } else {
        Err(ConstraintError::InvalidValue {
            field_name: "<unknown>",
            candidate: value.to_string(),
            allowed: "positive values".to_string(),
            requirement_source: RequirementSource::Unknown,
        })
    }
}).expect("initial value should be accepted");

// 试探性检查（不修改值）
constrained.can_set(&2).expect("2 is positive, should pass");
constrained.can_set(&-1).expect_err("-1 is negative, should fail");

// 实际设置
constrained.set(-5).expect_err("negative values rejected");
assert_eq!(constrained.value(), 1);  // 原值不变
```

**场景 3：归一化器（normalized）**

```rust
// 创建一个自动将负数归一化为 0 的约束
let mut constrained = Constrained::normalized(-1, |value| value.max(0)).unwrap();
assert_eq!(constrained.value(), 0);   // -1 被归一化为 0

constrained.set(-5).unwrap();
assert_eq!(constrained.value(), 0);   // -5 被归一化为 0

constrained.set(10).unwrap();
assert_eq!(constrained.value(), 10);  // 10 >= 0，保持不变
```

### 4.3 ConfigRequirements 与约束来源追踪

约束不是凭空出现的——每个约束都有明确的来源（`RequirementSource`），以便在错误消息中告知用户"谁"设定了这个限制：

```rust
// codex-rs/config/src/config_requirements.rs

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RequirementSource {
    Unknown,
    MdmManagedPreferences { domain: String, key: String },
    CloudRequirements,
    SystemRequirementsToml { file: AbsolutePathBuf },
    LegacyManagedConfigTomlFromFile { file: AbsolutePathBuf },
    LegacyManagedConfigTomlFromMdm,
}

/// 约束值与其来源的组合
pub struct ConstrainedWithSource<T> {
    pub value: Constrained<T>,
    pub source: Option<RequirementSource>,
}

/// 所有全局约束的集合
pub struct ConfigRequirements {
    pub approval_policy: ConstrainedWithSource<AskForApproval>,
    pub sandbox_policy: ConstrainedWithSource<SandboxPolicy>,
    pub web_search_mode: ConstrainedWithSource<WebSearchMode>,
    pub feature_requirements: Option<Sourced<FeatureRequirementsToml>>,
    pub mcp_servers: Option<Sourced<BTreeMap<String, McpServerRequirement>>>,
    pub exec_policy: Option<Sourced<RequirementsExecPolicy>>,
    pub enforce_residency: ConstrainedWithSource<Option<ResidencyRequirement>>,
    pub network: Option<Sourced<NetworkConstraints>>,
}
```

| `RequirementSource` 变体 | 含义 | 错误消息中的显示 |
|--------------------------|------|-----------------|
| `MdmManagedPreferences` | macOS MDM 推送的 managed preferences | `MDM com.openai.codex:sandbox` |
| `CloudRequirements` | 云端组织策略 | `cloud requirements` |
| `SystemRequirementsToml` | 系统级 requirements.toml | `/etc/codex/requirements.toml` |
| `LegacyManagedConfigTomlFromFile` | 旧版 managed_config.toml 文件 | 文件路径 |
| `LegacyManagedConfigTomlFromMdm` | 旧版 MDM managed_config.toml | `MDM managed_config.toml (legacy)` |

`ConfigRequirementsToml` 是从 `requirements.toml` 文件反序列化得到的原始结构：

```toml
# /etc/codex/requirements.toml — 系统管理员设定的约束
allowed_approval_policies = ["on-request", "unless-trusted"]
allowed_sandbox_modes = ["read-only", "workspace-write"]
allowed_web_search_modes = ["disabled", "cached"]

[features]
multi_agent = true
js_repl = false    # 禁止使用 JS REPL

[rules]
# 执行策略规则...
```

> 📌 **重点**：约束来源的优先级遵循"先到先得"原则——`ConfigRequirementsWithSources::merge_unset_fields()` 方法只填充尚未设定的字段。这意味着 Cloud Requirements 优先于 MDM，MDM 优先于 System requirements.toml。一旦某个约束被高优先级来源设定，低优先级来源无法覆盖。

---

## 5 配置键与类型

### 5.1 顶层配置键

以下从源码 `ConfigToml` 结构体（`codex-rs/core/src/config/mod.rs`）提取的配置键覆盖了 Codex 的所有可配置方面：

```rust
// codex-rs/core/src/config/mod.rs（部分摘录）

#[derive(Serialize, Deserialize, Debug, Clone, Default, PartialEq, JsonSchema)]
#[schemars(deny_unknown_fields)]    // 未知字段会触发反序列化错误
pub struct ConfigToml {
    pub model: Option<String>,
    pub review_model: Option<String>,
    pub model_provider: Option<String>,
    pub model_context_window: Option<i64>,
    pub model_auto_compact_token_limit: Option<i64>,
    pub approval_policy: Option<AskForApproval>,
    pub approvals_reviewer: Option<ApprovalsReviewer>,
    pub shell_environment_policy: ShellEnvironmentPolicyToml,
    pub allow_login_shell: Option<bool>,
    pub sandbox_mode: Option<SandboxMode>,
    pub sandbox_workspace_write: Option<SandboxWorkspaceWrite>,
    pub default_permissions: Option<String>,
    pub permissions: Option<PermissionsToml>,
    pub notify: Option<Vec<String>>,
    pub instructions: Option<String>,
    pub developer_instructions: Option<String>,
    pub model_instructions_file: Option<AbsolutePathBuf>,
    pub compact_prompt: Option<String>,
    pub commit_attribution: Option<String>,
    pub model_reasoning_effort: Option<ReasoningEffort>,
    pub plan_mode_reasoning_effort: Option<ReasoningEffort>,
    pub model_reasoning_summary: Option<ReasoningSummary>,
    pub model_verbosity: Option<Verbosity>,
    pub personality: Option<Personality>,
    pub service_tier: Option<ServiceTier>,
    pub web_search: Option<WebSearchMode>,
    pub project_doc_max_bytes: Option<usize>,
    pub project_doc_fallback_filenames: Option<Vec<String>>,
    pub profile: Option<String>,
    pub profiles: HashMap<String, ConfigProfile>,
    pub history: Option<History>,
    pub log_dir: Option<AbsolutePathBuf>,
    pub tui: Option<Tui>,
    pub mcp_servers: HashMap<String, McpServerConfig>,
    pub model_providers: HashMap<String, ModelProviderInfo>,
    pub features: Option<FeaturesToml>,
    pub otel: Option<OtelConfigToml>,
    // ... 以及更多字段
}
```

> 💡 **最佳实践**：`#[schemars(deny_unknown_fields)]` 注解使得 config.toml 中的拼写错误会被立即捕获。例如写成 `modl = "gpt-5.4"` 会触发反序列化错误并精确定位到文件中的行号和列号。

| 配置键 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `model` | String | `"gpt-5.4"` | 默认模型 |
| `review_model` | String | — | `/review` 功能使用的模型 |
| `model_provider` | String | `"openai"` | model_providers 表中的 provider key |
| `model_context_window` | i64 | — | 模型上下文窗口大小（token 数） |
| `approval_policy` | Enum | `"on-request"` | 命令审批策略 |
| `sandbox_mode` | Enum | `"read-only"` | 沙箱模式 |
| `model_reasoning_effort` | Enum | — | 推理强度（`"low"` / `"medium"` / `"high"`） |
| `model_verbosity` | Enum | — | GPT-5 models 的输出详细程度 |
| `personality` | Enum | — | 沟通风格 |
| `web_search` | Enum | `"cached"` | 网络搜索行为 |
| `log_dir` | AbsolutePathBuf | — | 自定义日志目录 |
| `project_doc_max_bytes` | usize | 32,768 | AGENTS.md 总大小限制 |
| `project_doc_fallback_filenames` | Array | — | 备用指令文件名列表 |
| `approvals_reviewer` | Enum | `"user"` | 审批审查者（`user` / `guardian_subagent`） |
| `commit_attribution` | String | — | commit message 中的 co-author 署名（空字符串禁用） |
| `notify` | Array | — | 外部通知命令 argv（如 `["notify-send", "Codex"]`） |
| `profile` | String | — | 默认激活的 profile 名称 |
| `allow_login_shell` | bool | `true` | 是否允许模型请求 login shell |

### 5.2 配置段（Sections）

**[model_providers.\*]** — 自定义模型端点：

```toml
[model_providers.local-llama]
name = "local-llama"
base_url = "http://localhost:11434/v1"
```

**[shell_environment_policy]** — 子进程环境变量控制：

```toml
[shell_environment_policy]
# Control which environment variables are passed to child processes
include_only = ["PATH", "HOME", "USER"]
# Or alternatively:
exclude = ["SECRET_KEY", "API_TOKEN"]
```

**[otel]** — OpenTelemetry 遥测配置：

```toml
[otel]
endpoint = "https://telemetry.example.com"
service_name = "codex-cli"
```

**[tui]** — 终端 UI 选项：

```toml
[tui]
status_line = ["model-with-reasoning", "context-remaining", "current-dir"]
theme = "dark"
```

**[history]** — 历史持久化控制：

```toml
[history]
max_bytes = 10485760  # 10 MB
```

**[features]** — 功能开关：

```toml
[features]
shell_snapshot = true
multi_agent = true
js_repl = true
```

**[projects."\<path\>"]** — 按项目路径设置信任和覆盖：

```toml
[projects."/Users/username/my-project"]
trust_level = "trusted"
sandbox_mode = "workspace-write"
```

**[mcp_servers.\*]** — MCP 服务器定义（用于外部工具调用）：

```toml
[mcp_servers.filesystem]
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem"]
enabled = true
required = false
startup_timeout_sec = 30
tool_timeout_sec = 60

[mcp_servers.remote-api]
url = "https://mcp.example.com/v1"
bearer_token_env_var = "MCP_API_TOKEN"
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `command` / `url` | String | Stdio 模式的命令 或 StreamableHttp 模式的 URL |
| `args` | Array | 命令行参数（Stdio 模式） |
| `enabled` | bool | 是否启用（默认 `true`） |
| `required` | bool | 启动失败时是否阻止 Codex 运行 |
| `startup_timeout_sec` | u64 | 启动超时（秒） |
| `tool_timeout_sec` | u64 | 工具调用超时（秒） |
| `enabled_tools` | Array | 白名单工具列表（未设则全部启用） |
| `disabled_tools` | Array | 黑名单工具列表 |

**[permissions.\*]** — 命名权限 profile：

```toml
[permissions.web-dev]
[permissions.web-dev.filesystem]
# 允许读写 src/ 和 public/ 目录
allow = [
  { path = "src/", mode = "read-write" },
  { path = "public/", mode = "read-write" },
]
# 禁止访问 .env 文件
deny = [{ path = ".env", mode = "read" }]

[permissions.web-dev.network]
allowed_domains = ["registry.npmjs.org", "cdn.jsdelivr.net"]
```

**[notice.model_migrations]** — 模型迁移通知：

```toml
[notice.model_migrations]
"gpt-5.3-codex" = "gpt-5.4"
```

**[memories]** — 记忆子系统配置：

```toml
[memories]
generate_memories = true          # 是否从对话中提取记忆
use_memories = true               # 是否在新对话中使用历史记忆
max_raw_memories_for_consolidation = 512
max_unused_days = 21              # 未使用记忆的过期天数
extract_model = "gpt-5-mini"     # 用于提取记忆的模型
consolidation_model = "gpt-5"    # 用于合并记忆的模型
```

### 5.3 JSON Schema 生成

Codex 基于 `ConfigToml` 结构体的 `#[derive(JsonSchema)]` 自动生成 JSON Schema（Draft-07），用于 IDE 中的配置文件自动补全和验证：

```rust
// codex-rs/core/src/config/schema.rs

pub fn config_schema() -> RootSchema {
    SchemaSettings::draft07()
        .with(|settings| {
            settings.option_add_null_type = false;
        })
        .into_generator()
        .into_root_schema_for::<ConfigToml>()
}

pub fn config_schema_json() -> anyhow::Result<Vec<u8>> {
    let schema = config_schema();
    let value = serde_json::to_value(schema)?;
    let value = canonicalize(&value);  // 排序 keys 确保确定性输出
    let json = serde_json::to_vec_pretty(&value)?;
    Ok(json)
}
```

> 💡 **最佳实践**：运行 `codex config schema` 可以导出完整的 JSON Schema。将其配置到 VS Code 或其他编辑器中，可以获得 `config.toml` 的实时验证和字段自动补全。

---

## 6 协作模式

`CollaborationMode`（定义于 `protocol/src/config_types.rs`）控制代理的工作方式：

```rust
pub struct CollaborationMode {
    pub mode: ModeKind,       // "default" or "plan"
    pub settings: Settings,
}

pub struct Settings {
    pub model: String,
    pub reasoning_effort: Option<ReasoningEffort>,
    pub developer_instructions: Option<String>,
}
```

| 模式 | 行为 |
|------|------|
| `default` | 标准模式，模型自主决定执行步骤 |
| `plan` | 计划模式，模型先制定计划等待用户审批，然后执行 |

每种模式可以配置独立的模型、推理强度和开发者指令。

---

## 7 人格系统

`Personality` 枚举控制模型的沟通风格：

```rust
pub enum Personality {
    None,        // 无人格修饰
    Friendly,    // 友好、亲切
    Pragmatic,   // 务实、直接
}
```

人格通过配置文件或命令行设置，会被注入到模型的 system prompt 中。`.personality_migration` 文件记录人格系统的迁移版本，确保版本升级时的一次性配置迁移。

---

## 8 特性标志系统

特性标志（Feature Flag）允许功能的分阶段发布和 A/B 测试。

### 8.1 Feature 枚举

```rust
pub enum Feature {
    // Stable features
    GhostCommit,
    ShellTool,

    // Experimental features
    JsRepl,
    CodeMode,
    CodeModeOnly,
    UnifiedExec,
    ShellZshFork,
    ExecPermissionApprovals,
    CodexHooks,
    RequestPermissionsTool,
    WebSearchRequest,
    WebSearchCached,

    // Sandbox features
    UseLegacyLandlock,
    WindowsSandbox,
    WindowsSandboxElevated,
    UseLinuxSandboxBwrap,

    // Other
    RuntimeMetrics,
    Sqlite,
    MemoryTool,
    Collab,
    SpawnCsv,
    Apps,
}
```

### 8.2 生命周期阶段

```rust
pub enum Stage {
    UnderDevelopment,      // 内部开发中
    Experimental {         // 实验性（用户可选启用）
        name: String,
        menu_description: String,
        announcement: String,
    },
    Stable,                // 稳定（默认启用）
    Deprecated,            // 已弃用
    Removed,               // 已移除
}
```

用户可通过 `codex features` CLI 命令查看和管理特性标志，通过 `[features]` 配置段或命令行参数启用/禁用实验性功能。

---

## 9 配置错误诊断系统

Codex 的配置系统在加载和写入过程中可能遇到各类错误。为了帮助用户精确定位问题，系统提供了丰富的诊断信息，包括文件路径、行号、列号和上下文代码片段。

### 9.1 错误定位机制

`ConfigError` 记录了错误发生的精确位置（文件 + 行/列范围），`format_config_error()` 将其渲染为类似编译器的错误输出：

```rust
// codex-rs/config/src/diagnostics.rs

pub struct ConfigError {
    pub path: PathBuf,       // 出错的配置文件路径
    pub range: TextRange,    // 出错的行/列范围
    pub message: String,     // 错误描述
}

pub struct TextRange {
    pub start: TextPosition,  // 起始位置 (1-based)
    pub end: TextPosition,    // 结束位置 (1-based)
}

pub struct TextPosition {
    pub line: usize,
    pub column: usize,
}
```

**错误输出示例**——当 config.toml 中包含未知字段时：

```
~/.codex/config.toml:5:1: unknown field `modl`, expected one of `model`, `approval_policy`, ...
  |
5 | modl = "gpt-5.4"
  | ^^^^
```

### 9.2 ConfigService 写入验证

通过 API 或 TUI 修改配置时，`ConfigService` 执行多重验证，确保修改不会破坏配置的有效性：

```
  ┌──────────────────────────────────────┐
  │  ConfigService::write_value()        │
  └──────────────┬───────────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │ 1. 检查文件路径是否为 user config │  只允许写入 ~/.codex/config.toml
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │ 2. 乐观锁检查 expected_version   │  版本冲突 → ConfigVersionConflict
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │ 3. 应用编辑到 user config 副本   │  parse key_path + merge strategy
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │ 4. validate_config() — Schema   │  反序列化为 ConfigToml 验证结构
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │ 5. validate feature settings    │  检查 feature flags 与 requirements 一致
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │ 6. 重新合并整个配置栈 → validate │  检查合并后的 effective config 是否合法
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │ 7. 检测是否被高优先级层覆盖      │  被覆盖时返回 WriteStatus::OkOverridden
  └──────────────┬──────────────────┘
                 │
  ┌──────────────▼──────────────────┐
  │ 8. 持久化到磁盘（atomic write）  │  使用 write_atomically() 防止写入中断
  └──────────────┬──────────────────┘
                 │
          ┌──────▼──────┐
          │ 返回结果 ✓   │
          └─────────────┘
```

当用户写入的值被更高优先级层覆盖时，系统会返回 `WriteStatus::OkOverridden` 并附带说明：

```json
{
  "status": "OkOverridden",
  "overridden_metadata": {
    "message": "Overridden by managed policy (MDM): com.openai.codex",
    "effective_value": "read-only"
  }
}
```

> ⚠️ **注意**：`ConfigService` 只允许写入 user config 层（`~/.codex/config.toml`）。尝试写入 system config 或 project config 会返回 `ConfigLayerReadonly` 错误。这是一项安全设计——防止通过 API 绕过文件权限修改系统级配置。

---

## 10 完整配置示例

```toml
# ~/.codex/config.toml — User-level configuration

# Default model for all sessions
model = "gpt-5.4"

# Approval and sandbox policies
approval_policy = "on-request"
sandbox_mode = "workspace-write"

# Communication style
personality = "pragmatic"

# Web search behavior
web_search = "cached"

# Reasoning effort
model_reasoning_effort = "high"

# AGENTS.md size limit (32 KiB)
project_doc_max_bytes = 32768

# Custom model provider (e.g., local Ollama)
[model_providers.local]
name = "local-ollama"
base_url = "http://localhost:11434/v1"

# Named profiles for different work styles
[profiles.fast]
model = "gpt-5.1-codex-mini"
model_reasoning_effort = "low"

[profiles.careful]
model = "gpt-5.4"
model_reasoning_effort = "high"
approval_policy = "unless-trusted"

# TUI customization
[tui]
status_line = ["model-with-reasoning", "context-remaining", "current-dir"]

# Feature flags
[features]
multi_agent = true
js_repl = true

# Shell environment policy
[shell_environment_policy]
exclude = ["AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY"]

# Per-project trust and overrides
[projects."/Users/username/trusted-project"]
trust_level = "trusted"

[projects."/Users/username/sensitive-project"]
trust_level = "trusted"
sandbox_mode = "read-only"
approval_policy = "unless-trusted"

# Model migration notices
[notice.model_migrations]
"gpt-5.3-codex" = "gpt-5.4"

# History persistence
[history]
max_bytes = 10485760

# OpenTelemetry (optional)
[otel]
endpoint = "https://otel-collector.example.com:4317"
```

> ⚠️ **注意**：`[shell_environment_policy]` 中的 `exclude` 列表应包含所有敏感环境变量，防止它们被传递给沙箱内的子进程。即使在 `workspace-write` 模式下，环境变量也是一个常被忽视的信息泄露渠道。

---

## 11 与 Claude Code 配置的对比

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **格式** | TOML（`config.toml`） | JSON（`settings.json`） |
| **层级数** | 7 层（系统→用户→项目→profile→MDM→CLI） | 3 层（全局→项目→工作区） |
| **合并算法** | 递归 TOML 深度合并 | 简单覆盖 |
| **约束系统** | `Constrained<T>`（验证器、归一化器、锁定） | 无 |
| **项目信任** | 显式 `trust_level` 控制项目配置加载 | 无信任机制 |
| **Profile** | `[profiles.<name>]` + `--profile` 切换 | 无 |
| **企业管理** | MDM 托管配置（最高优先级） | 无 |
| **特性标志** | `Feature` 枚举 + `Stage` 生命周期 | 无正式特性标志系统 |
| **环境变量** | `[shell_environment_policy]` 精细控制 | 无独立控制 |
| **遥测** | `[otel]` OpenTelemetry 集成 | 内置遥测 |
| **人格** | `Personality` 枚举（none/friendly/pragmatic） | 无 |
| **协作模式** | `CollaborationMode`（default/plan） | 类似（plan mode） |

> 💡 **最佳实践**：Codex 的配置系统显著更复杂，但也更适合企业部署场景。`Constrained<T>` 约束系统和 MDM 托管配置使得组织可以强制执行安全策略（如禁止 `danger-full-access` 模式），而不依赖于用户的自律。Claude Code 的配置更简洁，适合个人开发者快速上手。

---

## Reference

- [Codex 配置基础](https://developers.openai.com/codex/config-basic/)
- [Codex 高级配置](https://developers.openai.com/codex/config-advanced/)
- [TOML 规范](https://toml.io/)
- [Codex CLI 命令行参考](https://developers.openai.com/codex/cli/reference)

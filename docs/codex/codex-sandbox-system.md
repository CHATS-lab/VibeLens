# Codex CLI 沙箱与安全系统

| 条目 | 内容 |
|------|------|
| **主题** | OpenAI Codex CLI 的跨平台沙箱隔离与命令审批机制 |
| **核心源码** | `codex-rs/core/src/sandboxing/`、`codex-rs/linux-sandbox/`、`codex-rs/process-hardening/`、`codex-rs/windows-sandbox-rs/` |
| **支持平台** | macOS（Seatbelt）、Linux（Bubblewrap + Landlock + seccomp）、Windows（Restricted Token + Firewall） |

---

## 1 背景与安全模型

AI 编程代理的核心安全挑战在于：模型需要执行任意 shell 命令和修改文件来完成编程任务，但同时必须防止恶意或错误的操作对用户系统造成不可逆的损害。这是一个典型的"能力与安全的张力"问题。

Codex CLI 采用纵深防御（Defense in Depth）策略，在多个层面实施安全控制：沙箱策略（SandboxPolicy）定义了文件系统和网络的访问边界；审批策略（AskForApproval）控制哪些操作需要用户确认；执行策略（ExecPolicy）通过 Starlark 规则引擎自动评估命令的安全性；Guardian 子代理提供基于 AI 的风险评估。这些机制共同构成了 Codex 的安全防线。

### 1.1 纵深防御层次图

以下 ASCII 图示展示了 Codex CLI 从外到内的四层安全防线，每一层都是独立的安全屏障：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Layer 1: 平台沙箱 (OS-Level)                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  macOS: Seatbelt (sandbox-exec + .sbpl profile)              │  │
│  │  Linux: Bubblewrap (user namespace) + Landlock LSM + seccomp │  │
│  │  Windows: Restricted Token + ACL + Firewall                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Layer 2: SandboxPolicy 策略引擎                    │  │
│  │  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────┐ │  │
│  │  │  ReadOnly     │  │ WorkspaceWrite  │  │ DangerFullAccess│ │  │
│  │  │  (只读全盘)    │  │ (读全盘+写cwd)   │  │ (无限制)         │ │  │
│  │  └──────────────┘  └─────────────────┘  └─────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │         Layer 3: AskForApproval + ExecPolicy 审批层             │  │
│  │  Starlark 规则引擎 → 前缀匹配 → Allow / Prompt / Forbidden   │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │            Layer 4: Guardian AI 风险评估 (可选)                  │  │
│  │  risk_score < 80 → 自动批准 │ risk_score >= 80 → 拒绝/上报    │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

> 📌 **重点**：这四层防线彼此独立——即使某一层被绕过，其余层仍然能够提供保护。例如，即使 ExecPolicy 规则放行了一条命令，平台沙箱仍然会限制其文件系统和网络访问。

---

## 2 沙箱策略

### 2.1 SandboxPolicy 枚举

`SandboxPolicy` 定义于 `codex-rs/protocol/src/protocol.rs`，是所有平台沙箱实现的统一抽象：

```rust
pub enum SandboxPolicy {
    // No restrictions whatsoever
    DangerFullAccess,

    // Read-only access
    ReadOnly {
        access: ReadOnlyAccess,        // Restricted or FullAccess
        network_access: bool,          // Default: false
    },

    // External sandbox (process already sandboxed)
    ExternalSandbox {
        network_access: NetworkAccess, // Enabled or Restricted
    },

    // Read everywhere + write to workspace
    WorkspaceWrite {
        writable_roots: Vec<AbsolutePathBuf>,  // Additional writable dirs
        read_only_access: ReadOnlyAccess,
        network_access: bool,
        exclude_tmpdir_env_var: bool,
        exclude_slash_tmp: bool,
    },
}
```

三种用户可见的沙箱模式对应 `SandboxMode` 枚举：

| 模式 | 配置值 | 文件系统 | 网络 |
|------|--------|----------|------|
| **只读** | `read-only` | 只读全盘（或受限路径） | 默认禁止 |
| **工作区写入** | `workspace-write` | 读全盘 + 写 cwd 和 `writable_roots` | 默认禁止 |
| **完全访问** | `danger-full-access` | 无限制 | 无限制 |

> ⚠️ **注意**：`danger-full-access` 模式完全绕过所有沙箱保护，仅在用户明确知晓风险后使用。在 `workspace-write` 模式下，`~/.codex/memories/` 通常被加入 `writable_roots`，允许记忆系统持久化数据。

### 2.2 ReadOnlyAccess

控制只读模式下的文件访问范围：

```rust
pub enum ReadOnlyAccess {
    // Restrict to explicit paths + platform defaults
    Restricted {
        include_platform_defaults: bool,
        readable_roots: Vec<AbsolutePathBuf>,
    },
    // Allow all file reads (default)
    FullAccess,
}
```

`Restricted` 变体将文件读取限制在显式列出的路径和平台默认路径（如系统库目录）内，提供更严格的隔离。

---

## 3 平台沙箱实现

在理解了统一的沙箱策略抽象之后，下面深入每个平台的具体实现。`SandboxManager` 根据运行平台自动选择对应的隔离机制，将 `SandboxPolicy` 转换为平台特定的安全配置。

### 3.0 平台沙箱选择流程

`get_platform_sandbox()` 函数（`core/src/safety.rs`）根据编译目标平台自动选择沙箱实现。`SandboxManager::select_initial()` 在此基础上结合 `SandboxablePreference` 和策略条件做最终决策：

```
                    ┌──────────────────────┐
                    │   select_initial()   │
                    │ SandboxablePreference│
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        ┌──────────┐   ┌────────────┐   ┌────────────┐
        │  Forbid   │   │  Require   │   │    Auto    │
        └────┬─────┘   └─────┬──────┘   └─────┬──────┘
             │               │                 │
             ▼               ▼                 ▼
     SandboxType::None   get_platform_    should_require_
                         sandbox()        platform_sandbox()?
                             │                 │
                             │          ┌──────┴──────┐
                             ▼          │ Yes         │ No
                    ┌────────────────┐   │             ▼
                    │ cfg!(target_os)│   │    SandboxType::None
                    └───────┬───────┘   │
                            │           ▼
            ┌───────────────┼──── get_platform_sandbox()
            ▼               ▼               ▼
     ┌──────────────┐ ┌────────────┐ ┌─────────────────────┐
     │    macOS      │ │   Linux    │ │      Windows         │
     │MacosSeatbelt  │ │LinuxSeccomp│ │WindowsRestrictedToken│
     │(sandbox-exec) │ │(bwrap+     │ │(if enabled)          │
     │               │ │ seccomp)   │ │                      │
     └──────────────┘ └────────────┘ └─────────────────────┘
```

对应的平台选择源码（`core/src/safety.rs`）：

```rust
pub fn get_platform_sandbox(windows_sandbox_enabled: bool) -> Option<SandboxType> {
    if cfg!(target_os = "macos") {
        Some(SandboxType::MacosSeatbelt)
    } else if cfg!(target_os = "linux") {
        Some(SandboxType::LinuxSeccomp)
    } else if cfg!(target_os = "windows") {
        if windows_sandbox_enabled {
            Some(SandboxType::WindowsRestrictedToken)
        } else {
            None
        }
    } else {
        None
    }
}
```

| 平台 | SandboxType | 隔离机制 | 启用条件 |
|------|-------------|----------|----------|
| macOS | `MacosSeatbelt` | `sandbox-exec` + SBPL profile | 始终可用 |
| Linux | `LinuxSeccomp` | Bubblewrap + Landlock + seccomp BPF | 始终可用 |
| Windows | `WindowsRestrictedToken` | Restricted Token + ACL + Firewall | 需 `WindowsSandbox` 特性标志 |
| 其他 | `None` | 无沙箱 | -- |

> ⚠️ **注意**：在 Windows 上，如果 `WindowsSandbox` 特性标志未启用，`get_platform_sandbox()` 返回 `None`，此时沙箱退化为应用层保护。这是因为 Windows 沙箱仍处于 `Experimental` 阶段。

### 3.1 SandboxManager 调度

`SandboxManager`（定义于 `core/src/sandboxing/mod.rs`）是沙箱的统一调度入口：

```rust
pub struct SandboxTransformRequest<'a> {
    pub spec: CommandSpec,
    pub policy: &'a SandboxPolicy,
    pub file_system_policy: &'a FileSystemSandboxPolicy,
    pub network_policy: NetworkSandboxPolicy,
    pub sandbox: SandboxType,
    pub enforce_managed_network: bool,
    pub network: Option<&'a NetworkProxy>,
    pub sandbox_policy_cwd: &'a Path,
    pub macos_seatbelt_profile_extensions: Option<&'a MacOsSeatbeltProfileExtensions>,
    pub codex_linux_sandbox_exe: Option<&'a PathBuf>,
    pub use_legacy_landlock: bool,
    pub windows_sandbox_level: WindowsSandboxLevel,
    pub windows_sandbox_private_desktop: bool,
}
```

`SandboxType` 枚举选择具体的沙箱实现：

```rust
pub enum SandboxType {
    None,                      // No sandbox
    MacosSeatbelt,            // macOS: sandbox-exec
    LinuxSeccomp,             // Linux: Bubblewrap + Landlock
    WindowsRestrictedToken,   // Windows: Restricted Token
}
```

`SandboxManager` 的 `select_initial()` 方法根据文件系统策略、网络策略和平台偏好选择初始沙箱类型；`transform()` 方法将 `SandboxTransformRequest` 转换为可执行的 `ExecRequest`。

#### transform() 转换流程

`transform()` 方法是沙箱执行的核心管道，它根据 `SandboxType` 分发到不同的平台实现。以下是其内部逻辑流程：

```
  SandboxTransformRequest { spec, policy, sandbox, ... }
                    │
                    ▼
  ┌─────────────────────────────────────────────┐
  │ 1. 计算 EffectiveSandboxPermissions          │
  │    合并 base policy + additional_permissions │
  └──────────────────┬──────────────────────────┘
                     │
                     ▼
  ┌─────────────────────────────────────────────┐
  │ 2. 注入环境变量                               │
  │    CODEX_SANDBOX_NETWORK_DISABLED=1 (若禁网) │
  └──────────────────┬──────────────────────────┘
                     │
                     ▼
  ┌──────────────────┴──────────────────────────┐
  │                match sandbox                 │
  ├──────────┬──────────────┬───────────────────┤
  │  macOS   │    Linux     │     Windows       │
  ▼          ▼              ▼                   │
  sandbox-   codex-linux-   (in-process         │
  exec -p    sandbox        restricted          │
  <policy>   --sandbox-     token)              │
  -D...      policy <json>                      │
  -- cmd     -- cmd                             │
  ├──────────┴──────────────┴───────────────────┤
  │                                              │
  │ env += { CODEX_SANDBOX="seatbelt" }  (macOS) │
  │ arg0 = "codex-linux-sandbox"         (Linux) │
  └──────────────────┬───────────────────────────┘
                     │
                     ▼
              ExecRequest { command, cwd, env, sandbox, ... }
```

### 3.2 macOS Seatbelt 沙箱

macOS 平台使用 Apple 的 Seatbelt 机制，通过 `.sbpl`（Sandbox Profile Language）文件定义权限。

**实现要点**（`core/src/seatbelt.rs`）：

- 使用 `/usr/bin/sandbox-exec` 启动受限进程（硬编码路径，防止 PATH 注入攻击）
- 基础策略 `seatbelt_base_policy.sbpl` 采用 `(deny default)` 默认拒绝
- 允许进程执行和 fork（`same-sandbox` 限制）
- 文件访问通过参数化路径控制（`-D<PARAM>=<PATH>`）
- sysctl 白名单仅允许硬件信息查询

**命令结构**：

```bash
/usr/bin/sandbox-exec -p "policy-content" \
    -DWORKDIR=/path/to/project \
    -DWRITABLE_ROOT_1=/path/to/memories \
    -- /bin/bash -c "user-command"
```

**网络策略**（`seatbelt_network_policy.sbpl`）：
- 默认禁止所有网络访问
- 当配置了网络代理时，动态生成允许回环端口和 Unix 域套接字的策略
- 代理端口通过白名单机制放行

**扩展机制**：

```rust
pub struct MacOsSeatbeltProfileExtensions {
    policy: String,              // Additional SBPL rules
    dir_params: Vec<(String, PathBuf)>,  // Additional -D parameters
}
```

#### Seatbelt 基础策略文件详解

`seatbelt_base_policy.sbpl` 是所有 macOS 沙箱配置的起点，采用"默认拒绝"（deny default）策略，仅白名单放行必要权限。以下是该文件的核心内容（源自 `core/src/seatbelt_base_policy.sbpl`）：

```scheme
(version 1)

; 参考 Chrome 浏览器的 sandbox policy 设计
; start with closed-by-default
(deny default)

; 子进程继承父进程的沙箱策略
(allow process-exec)
(allow process-fork)
(allow signal (target same-sandbox))

; 进程信息查询（仅限同沙箱内的进程）
(allow process-info* (target same-sandbox))

; 允许写 /dev/null（字符设备）
(allow file-write-data
  (require-all
    (path "/dev/null")
    (vnode-type CHARACTER-DEVICE)))

; sysctl 白名单：仅允许硬件信息查询
(allow sysctl-read
  (sysctl-name "hw.activecpu")
  (sysctl-name "hw.memsize")
  (sysctl-name "hw.ncpu")
  (sysctl-name "hw.physicalcpu")
  (sysctl-name "hw.logicalcpu")
  (sysctl-name "kern.osversion")
  (sysctl-name "kern.hostname")
  ;; ... 更多 hw.* 和 kern.* 白名单条目
)

; 允许 PTY 操作（交互式 shell 所需）
(allow pseudo-tty)
(allow file-read* file-write* file-ioctl (literal "/dev/ptmx"))
(allow file-read* file-write*
  (require-all
    (regex #"^/dev/ttys[0-9]+")
    (extension "com.apple.sandbox.pty")))
```

**策略文件字段说明**：

| 指令 | 说明 |
|------|------|
| `(deny default)` | 默认拒绝所有操作，这是安全基线 |
| `(allow process-exec)` | 允许执行新进程（子命令需要） |
| `(allow process-fork)` | 允许 fork 子进程 |
| `(target same-sandbox)` | 限制信号/进程查询仅在同一沙箱内 |
| `(sysctl-name "hw.*")` | 白名单硬件信息查询，防止 fingerprinting |
| `(allow pseudo-tty)` | 允许 PTY 分配，使交互式 shell 可用 |

#### 实际 sandbox-exec 命令示例

当 Codex 在 `workspace-write` 模式下执行 `git status` 命令时，`SandboxManager::transform()` 会生成如下的沙箱命令：

```bash
# 实际生成的 sandbox-exec 命令
/usr/bin/sandbox-exec \
    -p "(version 1)
(deny default)
(allow process-exec)
(allow process-fork)
(allow signal (target same-sandbox))
(allow process-info* (target same-sandbox))
... [seatbelt_base_policy.sbpl 内容]
; allow read-only file operations
(allow file-read*
(subpath (param \"READABLE_ROOT_0\")))
(allow file-write*
(subpath (param \"WRITABLE_ROOT_0\")) (subpath (param \"WRITABLE_ROOT_1\")))
" \
    -DREADABLE_ROOT_0=/ \
    -DWRITABLE_ROOT_0=/Users/dev/my-project \
    -DWRITABLE_ROOT_1=/Users/dev/.codex/memories \
    -DDARWIN_USER_CACHE_DIR=/var/folders/xx/xxxxxx/C \
    -- git status
```

**命令结构分析**：

| 参数 | 说明 |
|------|------|
| `/usr/bin/sandbox-exec` | 硬编码路径，防止 PATH 注入 |
| `-p "..."` | 内联的完整 SBPL 策略 |
| `-DREADABLE_ROOT_0=/` | 参数化可读路径（全盘只读） |
| `-DWRITABLE_ROOT_0=...` | 参数化可写路径（项目目录） |
| `-DWRITABLE_ROOT_1=...` | 额外可写路径（memories 目录） |
| `-DDARWIN_USER_CACHE_DIR=...` | macOS 用户缓存目录（通过 `confstr` 获取） |
| `-- git status` | 分隔符后为实际命令 |

#### 网络策略动态生成

当配置了网络代理时，`dynamic_network_policy_for_network()` 函数（`core/src/seatbelt.rs`）动态生成额外的 Seatbelt 规则：

```scheme
; 配置了代理时动态生成 —— 仅允许到代理端口的回环连接
(allow network-outbound (remote ip "localhost:8080"))

; 允许 Unix domain socket（如果配置了 allow_unix_sockets）
(allow system-socket (socket-domain AF_UNIX))
(allow network-bind (local unix-socket (subpath (param "UNIX_SOCKET_PATH_0"))))
(allow network-outbound (remote unix-socket (subpath (param "UNIX_SOCKET_PATH_0"))))

; 无代理配置 + 网络完全启用时
(allow network-outbound)
(allow network-inbound)
; 加上 seatbelt_network_policy.sbpl 的 TLS/DNS 服务访问
```

> 💡 **最佳实践**：Seatbelt 的网络策略设计遵循最小权限原则——即使网络策略设为 `Enabled`，当存在代理配置时也仅允许连接代理端口而非全部网络。这确保所有外部流量都经过代理的审查。

### 3.3 Linux Bubblewrap + Landlock + seccomp

Linux 平台采用多层沙箱组合，提供最严格的隔离：

**主要模式**（`linux-sandbox` crate）：
- **Bubblewrap 模式**：使用用户命名空间进行文件系统隔离，结合 Landlock LSM 的访问控制
- **传统 Landlock-only 模式**：通过 `use_legacy_landlock` 特性标志启用，作为 Bubblewrap 不可用时的降级方案

**关键组件**：
- `bwrap.rs` — Bubblewrap 封装器（约 43KB），处理挂载点配置、命名空间设置
- `landlock.rs` — Landlock LSM 策略生成，内核级文件访问控制
- `proxy_routing.rs` — 网络代理路由配置
- `seccompiler` — seccomp 系统调用过滤

**策略传递方式**：沙箱策略序列化为 JSON，通过 CLI 参数传递给 `codex-linux-sandbox` 可执行文件。

#### codex-linux-sandbox CLI 参数结构

`LandlockCommand`（`linux-sandbox/src/linux_run_main.rs`）定义了完整的 CLI 接口：

```rust
pub struct LandlockCommand {
    #[arg(long = "sandbox-policy-cwd")]
    pub sandbox_policy_cwd: PathBuf,

    #[arg(long = "sandbox-policy")]
    pub sandbox_policy: Option<SandboxPolicy>,       // 旧版兼容

    #[arg(long = "file-system-sandbox-policy")]
    pub file_system_sandbox_policy: Option<FileSystemSandboxPolicy>,

    #[arg(long = "network-sandbox-policy")]
    pub network_sandbox_policy: Option<NetworkSandboxPolicy>,

    #[arg(long = "use-legacy-landlock", default_value_t = false)]
    pub use_legacy_landlock: bool,

    #[arg(long = "apply-seccomp-then-exec", default_value_t = false)]
    pub apply_seccomp_then_exec: bool,               // 内部阶段 2 标志

    #[arg(long = "allow-network-for-proxy", default_value_t = false)]
    pub allow_network_for_proxy: bool,

    #[arg(long = "proxy-route-spec")]
    pub proxy_route_spec: Option<String>,             // 代理路由规格

    #[arg(long = "no-proc", default_value_t = false)]
    pub no_proc: bool,                                // 跳过 /proc 挂载

    #[arg(trailing_var_arg = true)]
    pub command: Vec<String>,
}
```

**实际命令示例**（`workspace-write` 模式，禁止网络）：

```bash
codex-linux-sandbox \
    --sandbox-policy-cwd /home/dev/my-project \
    --sandbox-policy '{"WorkspaceWrite":{"writable_roots":["/home/dev/my-project","/home/dev/.codex/memories"],"read_only_access":"FullAccess","network_access":false,"exclude_tmpdir_env_var":false,"exclude_slash_tmp":false}}' \
    --file-system-sandbox-policy '{"kind":"Restricted","entries":[{"path":{"Path":{"path":"/home/dev/my-project"}},"access":"Write"},{"path":{"Path":{"path":"/"}},"access":"Read"}]}' \
    --network-sandbox-policy '"Restricted"' \
    -- /bin/bash -c "git status"
```

**内层 seccomp 阶段命令**（由外层 bwrap 调用）：

```bash
# bwrap 调用内层二进制，附加 --apply-seccomp-then-exec
bwrap --new-session --die-with-parent \
    --ro-bind / / --dev /dev \
    --bind /home/dev/my-project /home/dev/my-project \
    --ro-bind /home/dev/my-project/.git /home/dev/my-project/.git \
    --unshare-user --unshare-pid --unshare-net \
    --proc /proc \
    --argv0 codex-linux-sandbox \
    -- /path/to/codex-linux-sandbox \
        --sandbox-policy-cwd /home/dev/my-project \
        --sandbox-policy '{"WorkspaceWrite":{...}}' \
        --file-system-sandbox-policy '{...}' \
        --network-sandbox-policy '"Restricted"' \
        --apply-seccomp-then-exec \
        -- /bin/bash -c "git status"
```

> 📌 **重点**：JSON 传递策略的设计允许沙箱策略的增量演进，新增字段不会破坏旧版本的沙箱可执行文件。这对于 CLI 工具的向前兼容性至关重要。

#### Linux 沙箱两阶段执行流程

Linux 沙箱采用两阶段架构：外层 Bubblewrap 建立文件系统视图，内层 seccomp 收紧系统调用。以下是 `run_main()`（`linux-sandbox/src/linux_run_main.rs`）的完整执行流程：

```
                   ┌──────────────────────────┐
                   │   codex-linux-sandbox     │
                   │       run_main()          │
                   └────────────┬─────────────┘
                                │
                    ┌───────────▼───────────┐
                    │ resolve_sandbox_      │
                    │ policies()            │
                    │ (JSON → 结构体)        │
                    └───────────┬───────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼                               ▼
    ┌─────────────────────┐         ┌─────────────────────┐
    │ use_legacy_landlock  │         │ Bubblewrap 模式      │
    │ = true (降级方案)     │         │ (默认)                │
    └──────────┬──────────┘         └──────────┬──────────┘
               │                                │
               ▼                                ▼
    ┌─────────────────────┐         ┌─────────────────────┐
    │ apply_sandbox_policy│         │ 阶段 1: 外层 bwrap   │
    │ _to_current_thread()│         │ ┌─────────────────┐ │
    │ ├ set_no_new_privs  │         │ │ --new-session   │ │
    │ ├ Landlock ruleset  │         │ │ --die-with-parent│ │
    │ └ seccomp filter    │         │ │ --ro-bind / /   │ │
    └──────────┬──────────┘         │ │ --dev /dev      │ │
               │                    │ │ --bind <writable>│ │
               ▼                    │ │ --unshare-user  │ │
    ┌─────────────────────┐         │ │ --unshare-pid   │ │
    │   execvp(command)   │         │ │ --unshare-net   │ │
    └─────────────────────┘         │ │ --proc /proc    │ │
                                    │ └─────────────────┘ │
                                    └──────────┬──────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │ 阶段 2: 内层 seccomp │
                                    │ --apply-seccomp-    │
                                    │   then-exec          │
                                    │ ├ set_no_new_privs   │
                                    │ ├ seccomp BPF filter │
                                    │ └ (可选) proxy routes │
                                    └──────────┬──────────┘
                                               │
                                               ▼
                                    ┌─────────────────────┐
                                    │   execvp(command)    │
                                    └─────────────────────┘
```

> 💡 **最佳实践**：两阶段设计的原因是 Bubblewrap 可能依赖 setuid 权限来创建命名空间，而 seccomp 的 `PR_SET_NO_NEW_PRIVS` 会阻止 setuid 提权。因此必须先完成 bwrap 的挂载设置，再收紧 seccomp 限制。

#### Landlock 文件系统规则结构

`install_filesystem_landlock_rules_on_current_thread()`（`linux-sandbox/src/landlock.rs`）在内核层面限制文件访问。以下是其策略结构：

```rust
// Landlock LSM 策略安装 (linux-sandbox/src/landlock.rs)
fn install_filesystem_landlock_rules_on_current_thread(
    writable_roots: Vec<AbsolutePathBuf>,
) -> Result<()> {
    let abi = ABI::V5;
    let access_rw = AccessFs::from_all(abi);     // 全部读写权限
    let access_ro = AccessFs::from_read(abi);     // 只读权限

    let mut ruleset = Ruleset::default()
        .set_compatibility(CompatLevel::BestEffort)
        .handle_access(access_rw)?
        .create()?
        // 全盘只读
        .add_rules(landlock::path_beneath_rules(&["/"], access_ro))?
        // /dev/null 读写（命令输出重定向所需）
        .add_rules(landlock::path_beneath_rules(&["/dev/null"], access_rw))?
        .set_no_new_privs(true);

    // 仅对指定的 writable_roots 授予读写权限
    if !writable_roots.is_empty() {
        ruleset = ruleset.add_rules(
            landlock::path_beneath_rules(&writable_roots, access_rw)
        )?;
    }

    let status = ruleset.restrict_self()?;
    if status.ruleset == landlock::RulesetStatus::NotEnforced {
        return Err(CodexErr::Sandbox(SandboxErr::LandlockRestrict));
    }
    Ok(())
}
```

等效的 Landlock 策略可视化表示：

```
┌─────────────────────────────────────────────────────┐
│              Landlock Ruleset (ABI V5)               │
├─────────────────────────────────────────────────────┤
│  Rule 1:  /              → AccessFs::from_read()    │
│           (全盘只读访问)                               │
├─────────────────────────────────────────────────────┤
│  Rule 2:  /dev/null      → AccessFs::from_all()     │
│           (读写，命令输出重定向所需)                      │
├─────────────────────────────────────────────────────┤
│  Rule 3:  /home/dev/proj → AccessFs::from_all()     │
│           (项目目录读写)                                │
├─────────────────────────────────────────────────────┤
│  Rule 4:  ~/.codex/mem   → AccessFs::from_all()     │
│           (memories 持久化)                            │
├─────────────────────────────────────────────────────┤
│  set_no_new_privs: true                              │
│  compatibility: BestEffort                           │
└─────────────────────────────────────────────────────┘
```

#### seccomp 网络过滤规则

网络沙箱通过 seccomp BPF 过滤器在系统调用层面阻止网络操作（`linux-sandbox/src/landlock.rs`）。根据 `NetworkSeccompMode`，过滤策略有两种模式：

```
┌──────────────────────────────────────────────────────────────────┐
│                 seccomp BPF 网络过滤策略                           │
├────────────────────────────┬─────────────────────────────────────┤
│   Restricted 模式           │   ProxyRouted 模式                  │
│   (完全禁止网络)              │   (仅允许代理连接)                    │
├────────────────────────────┼─────────────────────────────────────┤
│ 禁止:                       │ 禁止:                               │
│  SYS_connect               │  socket(非 AF_INET/AF_INET6)       │
│  SYS_accept / accept4      │  socketpair(AF_UNIX)               │
│  SYS_bind                  │                                     │
│  SYS_listen                │ 允许:                                │
│  SYS_sendto / sendmmsg     │  socket(AF_INET) — 连接代理桥接      │
│  SYS_recvmmsg              │  socket(AF_INET6) — IPv6 代理       │
│  SYS_getsockopt/setsockopt │                                     │
│  SYS_getpeername           │                                     │
│  SYS_getsockname           │                                     │
│  SYS_shutdown              │                                     │
│  socket(非 AF_UNIX)         │                                     │
│  socketpair(非 AF_UNIX)     │                                     │
├────────────────────────────┴─────────────────────────────────────┤
│ 两种模式共同禁止:                                                  │
│  SYS_ptrace — 防止调试器注入                                       │
│  SYS_io_uring_setup / enter / register — 防止绕过 seccomp         │
├──────────────────────────────────────────────────────────────────┤
│ Default action: Allow (允许所有未匹配的系统调用)                     │
│ Match action:   Errno(EPERM) (匹配的调用返回 EPERM 错误)           │
└──────────────────────────────────────────────────────────────────┘
```

> ⚠️ **注意**：`io_uring` 系列系统调用在两种模式下都被禁止。这是因为 `io_uring` 可以执行异步 I/O 操作（包括网络 I/O），绕过传统的 seccomp 系统调用过滤。

#### Linux 平台默认可读路径

当 `ReadOnlyAccess::Restricted` 设置 `include_platform_defaults = true` 时，Bubblewrap 会自动挂载以下系统路径为只读（`linux-sandbox/src/bwrap.rs`）：

```rust
const LINUX_PLATFORM_DEFAULT_READ_ROOTS: &[&str] = &[
    "/bin",
    "/sbin",
    "/usr",
    "/etc",
    "/lib",
    "/lib64",
    "/nix/store",              // Nix 包管理器支持
    "/run/current-system/sw",  // NixOS 系统路径
];
```

### 3.4 Windows 沙箱

Windows 平台实现了两层沙箱架构（`windows-sandbox-rs` crate）：

**受限令牌模式**（`WindowsSandboxLevel::RestrictedToken`）：
- `command_runner_win.rs` — 使用受限安全令牌执行命令
- `acl.rs` — 文件系统 ACL（访问控制列表）管理
- `workspace_acl.rs` — 工作区目录权限配置
- `token.rs` — 令牌操作（权限降级/提升）

**提升模式**（`WindowsSandboxLevel::Elevated`）：
- 两阶段协调：`setup_main_win.rs`（setup 阶段）→ `elevated_impl.rs`（执行阶段）
- `sandbox_users.rs` — 创建隔离用户账户
- `hide_users.rs` — 防止用户枚举
- `firewall.rs` — 通过 Windows 防火墙实施网络策略
- `audit.rs` — 安全审计日志

**依赖**：`windows` crate（Win32 API）和 `windows-sys`，提供对 Windows 安全子系统的完整访问。

### 3.5 网络代理（Network Proxy）

`network-proxy` crate（基于 `rama` 框架）提供网络流量代理和管控：

- HTTP/HTTPS/SOCKS5 协议支持
- `globset` 模式匹配实现域名/路径级别的访问控制
- 与各平台沙箱深度集成：
  - macOS：Seatbelt 动态策略允许代理端口
  - Linux：策略 JSON 包含代理网络设置
  - Windows：防火墙规则放行代理流量

---

## 4 审批系统

沙箱控制了"能做什么"，审批系统控制了"是否需要用户确认"。两者共同构成 Codex 的安全访问控制。

### 4.1 AskForApproval 策略

`AskForApproval` 枚举定义了命令审批的行为模式：

| 变体 | 行为 |
|------|------|
| `UnlessTrusted` | 仅自动放行已知安全的只读命令，其余需用户确认 |
| `OnRequest` | 模型自主决定是否请求用户审批（**默认值**） |
| `Granular(GranularApprovalConfig)` | 细粒度控制：按类别分别设置审批行为 |
| `Never` | 从不向用户请求审批（所有需要审批的操作直接拒绝） |
| `OnFailure`（已弃用） | 沙箱失败时自动提升权限 |

**GranularApprovalConfig** 提供更精细的控制：

```rust
pub struct GranularApprovalConfig {
    pub sandbox_approval: bool,        // Shell 命令审批
    pub rules: bool,                   // ExecPolicy 提示规则
    pub skill_approval: bool,          // 技能脚本执行审批
    pub request_permissions: bool,     // request_permissions 工具审批
    pub mcp_elicitations: bool,        // MCP 工具审批
}
```

### 4.2 SandboxPermissions

工具调用时可以请求不同级别的沙箱权限：

```rust
pub enum SandboxPermissions {
    UseDefault,                // 使用当前轮次的默认沙箱策略
    RequireEscalated,          // 请求完全脱离沙箱
    WithAdditionalPermissions, // 保持沙箱但请求扩展权限
}
```

当工具请求 `WithAdditionalPermissions` 时，系统通过 `PermissionProfile` 计算交集（requested ∩ granted），确保只授予必要的最小权限。

### 4.3 权限配置

```rust
pub struct PermissionProfile {
    pub network: Option<NetworkPermissions>,
    pub file_system: Option<FileSystemPermissions>,
    pub macos: Option<MacOsSeatbeltProfileExtensions>,
}

pub struct FileSystemPermissions {
    pub read: Option<Vec<AbsolutePathBuf>>,
    pub write: Option<Vec<AbsolutePathBuf>>,
}
```

权限操作支持合并（`merge_permission_profiles`）和交集（`intersect_permission_profiles`），以及路径规范化（`normalize_additional_permissions`）。

#### 权限计算流程

当工具请求 `WithAdditionalPermissions` 时，系统通过以下流程计算最终生效的权限：

```
 ┌──────────────────┐     ┌──────────────────┐
 │ requested         │     │ granted           │
 │ PermissionProfile │     │ PermissionProfile │
 │ ┌──────────────┐ │     │ ┌──────────────┐ │
 │ │ read:        │ │     │ │ read:        │ │
 │ │  /home/dev   │ │     │ │  /home/dev   │ │
 │ │  /var/log    │ │     │ │  /tmp        │ │
 │ │ write:       │ │     │ │ write:       │ │
 │ │  /home/dev   │ │     │ │  /home/dev   │ │
 │ │  /etc/nginx  │ │     │ │              │ │
 │ │ network: true│ │     │ │ network: true│ │
 │ └──────────────┘ │     │ └──────────────┘ │
 └────────┬─────────┘     └────────┬─────────┘
          │                        │
          └───────────┬────────────┘
                      ▼
         intersect_permission_profiles()
                      │
                      ▼
         ┌──────────────────────┐
         │ effective             │
         │ PermissionProfile     │
         │ ┌──────────────────┐ │
         │ │ read:  /home/dev │ │  ← 交集：/var/log 未被 grant
         │ │ write: /home/dev │ │  ← 交集：/etc/nginx 未被 grant
         │ │ network: true    │ │  ← 双方都允许
         │ └──────────────────┘ │
         └──────────────────────┘
```

> 📌 **重点**：权限交集机制确保了最小权限原则——工具只能获得"它请求的"且"用户已授予的"权限的交集。即使工具请求了 `/etc/nginx` 的写权限，如果用户未授予该路径，最终生效的权限中不会包含它。

---

## 5 ExecPolicy：Starlark 规则引擎

除了沙箱和审批策略之外，Codex 还提供了 ExecPolicy 系统——一个基于 Starlark 脚本语言的命令审批规则引擎（`execpolicy` crate）。

### 5.1 Decision 枚举

每条规则评估后产生一个决策：

```rust
pub enum Decision {
    Allow,     // 自动放行
    Prompt,    // 请求用户确认
    Forbidden, // 直接禁止
}
```

### 5.2 规则体系

```rust
pub struct Policy {
    rules_by_program: MultiMap<String, RuleRef>,  // Per-program rules
    network_rules: Vec<NetworkRule>,                // Network rules
    host_executables_by_name: HashMap<String, Arc<[AbsolutePathBuf]>>,
}
```

规则按程序名分组存储，支持前缀匹配。核心的 `PrefixRule` 将命令前缀映射到 `Decision`：

```rust
pub struct PrefixRule {
    pub pattern: PrefixPattern,
    pub decision: Decision,
}
```

例如，可以配置 `["git", "status"]` → `Allow`，`["rm", "-rf"]` → `Forbidden`。

规则支持运行时追加（`blocking_append_allow_prefix_rule`、`blocking_append_network_rule`），使得审批策略可以在会话过程中动态调整。

---

## 6 Guardian：AI 风险评估

Guardian 是 Codex 独有的安全创新——使用另一个 AI 代理来评估命令执行的风险级别。

### 6.1 启用条件

```rust
pub fn routes_approval_to_guardian(turn: &TurnContext) -> bool {
    turn.approval_policy.value() == AskForApproval::OnRequest
        && turn.config.approvals_reviewer == ApprovalsReviewer::GuardianSubagent
}
```

当审批策略为 `OnRequest` 且审批审查者设为 `GuardianSubagent` 时，命令审批交由 Guardian 子代理处理。

### 6.2 风险评估

Guardian 对每个需要审批的命令产生 `GuardianAssessment`：

```rust
pub struct GuardianAssessment {
    risk_level: GuardianRiskLevel,   // Low | Medium | High
    risk_score: u8,                   // 0-255
    rationale: String,
    evidence: Vec<GuardianEvidence>,
}
```

**审批阈值**：`risk_score < 80` → 自动批准，`risk_score >= 80` → 拒绝/上报。

**关键常量**：

| 常量 | 值 | 说明 |
|------|----|------|
| `GUARDIAN_PREFERRED_MODEL` | `gpt-5.4` | Guardian 使用的模型 |
| `GUARDIAN_REVIEW_TIMEOUT` | 90 秒 | 评估超时 |
| `GUARDIAN_MAX_MESSAGE_TRANSCRIPT_TOKENS` | 10,000 | 消息上下文截断 |
| `GUARDIAN_MAX_TOOL_TRANSCRIPT_TOKENS` | 10,000 | 工具上下文截断 |
| `GUARDIAN_APPROVAL_RISK_THRESHOLD` | 80 | 风险阈值 |

**安全保证**：Guardian 采用"失败即关闭"（fail-closed）策略——超时、错误或格式错误的输出都被视为拒绝。

### 6.3 审批请求类型

```rust
pub enum GuardianApprovalRequest {
    Shell { id, command, cwd, sandbox_permissions, justification },
    ExecCommand { id, command, cwd, sandbox_permissions, tty },
    #[cfg(unix)]
    Execve { id, tool_name, program, ... },
}
```

Guardian 继承父会话的托管网络代理，确保风险评估过程本身也在安全边界内运行。

#### Guardian 审批请求完整类型

除了基本的 Shell 和 ExecCommand 外，Guardian 支持多种审批请求类型（`core/src/guardian.rs`）：

```rust
pub(crate) enum GuardianApprovalRequest {
    Shell {
        id: String,
        command: Vec<String>,
        cwd: PathBuf,
        sandbox_permissions: SandboxPermissions,
        additional_permissions: Option<PermissionProfile>,
        justification: Option<String>,
    },
    ExecCommand {
        id: String,
        command: Vec<String>,
        cwd: PathBuf,
        sandbox_permissions: SandboxPermissions,
        additional_permissions: Option<PermissionProfile>,
        justification: Option<String>,
        tty: bool,
    },
    #[cfg(unix)]
    Execve {
        id: String,
        tool_name: String,
        program: String,
        argv: Vec<String>,
        cwd: PathBuf,
        additional_permissions: Option<PermissionProfile>,
    },
    ApplyPatch {
        id: String,
        cwd: PathBuf,
        files: Vec<AbsolutePathBuf>,
        change_count: usize,
        patch: String,
    },
    NetworkAccess {
        id: String,
        turn_id: String,
        target: String,
        host: String,
        protocol: NetworkApprovalProtocol,
        port: u16,
    },
    McpToolCall {
        id: String,
        server: String,
        tool_name: String,
        arguments: Option<Value>,
        connector_id: Option<String>,
        connector_name: Option<String>,
        connector_description: Option<String>,
        tool_title: Option<String>,
        tool_description: Option<String>,
        annotations: Option<GuardianMcpAnnotations>,
    },
}
```

| 请求类型 | 触发场景 | 关键字段 |
|----------|----------|----------|
| `Shell` | 模型请求执行 shell 命令 | `command`, `justification` |
| `ExecCommand` | 执行带 TTY 的命令 | `command`, `tty` |
| `Execve` | Unix 系统调用级执行 | `program`, `argv` |
| `ApplyPatch` | 应用代码补丁 | `files`, `change_count`, `patch` |
| `NetworkAccess` | 访问外部网络 | `host`, `protocol`, `port` |
| `McpToolCall` | 调用 MCP 工具 | `server`, `tool_name`, `annotations` |

### 6.4 Guardian 审批流程图

```
  ┌────────────────────┐
  │ 模型请求执行命令      │
  │ (e.g., git push)    │
  └─────────┬──────────┘
            │
            ▼
  ┌────────────────────────────┐
  │ routes_approval_to_       │
  │ guardian(turn)?            │
  │ (approval == OnRequest     │
  │  && reviewer == Guardian)  │
  └──────────┬─────────────────┘
       ┌─────┴─────┐
       │ No        │ Yes
       ▼           ▼
  ┌─────────┐  ┌────────────────────────────────────┐
  │ 用户审批 │  │ run_guardian_review()               │
  └─────────┘  │  1. 发送 InProgress 事件              │
               │  2. build_guardian_prompt_items()    │
               │     ├ 压缩对话历史 (≤10K tokens)     │
               │     ├ 压缩工具证据 (≤10K tokens)     │
               │     └ 构造 Planned action JSON      │
               │  3. 启动 Guardian 子代理              │
               └──────────┬─────────────────────────┘
                          │
                ┌─────────▼──────────┐
                │  tokio::select!    │
                │  ┌───────────────┐ │
                │  │ 子代理完成     │ │ ← 90s 超时
                │  │ 超时           │ │
                │  │ 外部取消       │ │
                │  └───────┬───────┘ │
                └──────────┼─────────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
     ┌──────────┐   ┌──────────┐   ┌──────────┐
     │ 正常返回  │   │ 超时      │   │ 取消      │
     │ 解析 JSON │   │ risk=100 │   │ Aborted  │
     └────┬─────┘   │ High     │   └──────────┘
          │         └────┬─────┘
          ▼              ▼
    risk_score < 80?
    ┌────┴────┐
    │ Yes     │ No
    ▼         ▼
  Approved  Denied
```

### 6.5 Guardian 风险评估 JSON 示例

**场景：低风险操作 —— `git push` 到公开仓库**

Guardian 接收的 Planned action JSON：

```json
{
  "command": [
    "git",
    "push",
    "origin",
    "guardian-approval-mvp"
  ],
  "cwd": "/repo/codex-rs/core",
  "justification": "Need to push the reviewed docs fix to the repo remote.",
  "sandbox_permissions": "use_default",
  "tool": "shell"
}
```

Guardian 返回的风险评估（`GuardianAssessment`）：

```json
{
  "risk_level": "low",
  "risk_score": 25,
  "rationale": "The user explicitly requested pushing the docs fix. The target branch is a feature branch on a public repo. No sensitive data is being exfiltrated.",
  "evidence": [
    {
      "message": "User message in transcript: 'Please check the repo visibility and push the docs fix if needed.'",
      "why": "Explicit user authorization for the push action."
    },
    {
      "message": "Tool result: repo visibility: public",
      "why": "The repo is public, so pushing to it does not expose private data."
    }
  ]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `risk_level` | `"low" \| "medium" \| "high"` | 风险等级分类 |
| `risk_score` | `0-100` | 量化风险分数，< 80 自动批准 |
| `rationale` | `string` | 风险判断的理由说明 |
| `evidence` | `[{message, why}]` | 支撑判断的证据列表 |

**场景：高风险操作 —— 删除系统文件**

```json
{
  "risk_level": "high",
  "risk_score": 95,
  "rationale": "The command 'rm -rf /etc/nginx' would delete critical system configuration files. No explicit user authorization found in the transcript for this destructive action.",
  "evidence": [
    {
      "message": "Command target: /etc/nginx (system configuration directory)",
      "why": "Deleting system configuration files causes service disruption and is costly to reverse."
    },
    {
      "message": "No matching user request found in transcript",
      "why": "The user asked to 'fix the nginx config', not to delete the entire directory."
    }
  ]
}
```

**fail-closed 示例 —— 超时或错误**：

```json
{
  "risk_level": "high",
  "risk_score": 100,
  "rationale": "Automatic approval review timed out while evaluating the requested approval.",
  "evidence": []
}
```

Guardian 被拒绝后，系统会向模型发送固定的拒绝消息（`GUARDIAN_REJECTION_MESSAGE`）：

```
This action was rejected due to unacceptable risk.
The agent must not attempt to achieve the same outcome via workaround,
indirect execution, or policy circumvention.
Proceed only with a materially safer alternative,
or if the user explicitly approves the action after being informed of the risk.
Otherwise, stop and request user input.
```

> 💡 **最佳实践**：Guardian 模式适合企业环境下的自动化工作流——它减少了人工审批的负担，同时保持了对高风险操作的控制。对于个人使用，`OnRequest` + 用户审批通常已足够。

---

## 7 特性标志

沙箱相关的能力由特性标志（Feature Flag）控制，支持分阶段发布：

| 特性 | 阶段 | 说明 |
|------|------|------|
| `UseLegacyLandlock` | Stable | 使用传统 Landlock-only 模式 |
| `UseLinuxSandboxBwrap` | Stable | 使用 Bubblewrap 沙箱 |
| `WindowsSandbox` | Experimental | Windows 受限令牌沙箱 |
| `WindowsSandboxElevated` | Experimental | Windows 提升沙箱 |
| `ExecPermissionApprovals` | Experimental | 执行权限审批 |
| `RequestPermissionsTool` | Experimental | request_permissions 工具 |

特性标志的生命周期：`UnderDevelopment` → `Experimental` → `Stable` → `Deprecated` → `Removed`。

---

## 7.1 沙箱拒绝检测与调试

当沙箱阻止了某个操作时，Codex 需要检测并区分"命令自身失败"和"沙箱拒绝"。`SandboxManager::denied()` 方法调用 `is_likely_sandbox_denied()` 来判断：

```rust
pub fn denied(&self, sandbox: SandboxType, out: &ExecToolCallOutput) -> bool {
    crate::exec::is_likely_sandbox_denied(sandbox, out)
}
```

#### macOS Seatbelt 拒绝日志

在 macOS 上，Seatbelt 拒绝会记录到系统日志中。Codex 的 `DenialLogger`（`cli/src/debug_sandbox/seatbelt.rs`）通过 `log stream` 命令实时捕获这些日志：

```bash
# Codex 内部使用的日志监控命令
log stream --style ndjson --predicate \
  '(((processID == 0) AND (senderImagePath CONTAINS "/Sandbox")) \
    OR (subsystem == "com.apple.sandbox.reporting"))'
```

捕获到的拒绝日志格式（NDJSON）：

```json
{
  "eventMessage": "Sandbox: git(12345) deny(1) file-write-create /etc/nginx/conf.d/new.conf",
  "timestamp": "2025-05-15T10:30:45.123Z",
  "subsystem": "com.apple.sandbox.reporting"
}
```

`parse_message()` 函数使用正则 `^Sandbox:\s*(.+?)\((\d+)\)\s+deny\(.*?\)\s*(.+)$` 提取进程名、PID 和被拒绝的能力：

| 提取字段 | 示例值 | 说明 |
|----------|--------|------|
| `name` | `git` | 被拒绝的进程名 |
| `pid` | `12345` | 进程 ID |
| `capability` | `file-write-create /etc/nginx/conf.d/new.conf` | 被拒绝的操作 |

> 💡 **最佳实践**：开发者调试沙箱问题时，可以查看 macOS Console.app 中 `com.apple.sandbox.reporting` 子系统的日志，快速定位哪些操作被 Seatbelt 拒绝。

---

## 8 与 Claude Code 安全模型的对比

| 维度 | Codex CLI | Claude Code |
|------|-----------|-------------|
| **沙箱层级** | 操作系统原生（Seatbelt/Landlock/seccomp/Win32） | 进程级隔离 |
| **沙箱策略** | 三级：read-only → workspace-write → danger-full-access | 无明确沙箱策略枚举 |
| **命令审批** | `AskForApproval` 枚举（5 种模式，含细粒度 Granular） | 权限模式（tool-level allow/deny） |
| **规则引擎** | Starlark ExecPolicy（前缀匹配、可编程） | 无 |
| **AI 审批** | Guardian 子代理（AI 风险评估） | 无 |
| **权限提升** | `SandboxPermissions::RequireEscalated` / `WithAdditionalPermissions` | 无对应机制 |
| **网络控制** | 平台沙箱 + 网络代理 | 无独立网络控制 |
| **Windows 支持** | 受限令牌 + 防火墙 + 隔离用户 | 无原生 Windows 沙箱 |
| **策略传递** | JSON 序列化（向前兼容） | N/A |
| **企业管理** | 支持 MDM 托管策略 | 无 |

> 📌 **重点**：Codex 的安全模型显著更深入——它在操作系统层面实施隔离（Seatbelt sandbox profiles、Landlock LSM、seccomp BPF），而 Claude Code 主要依赖应用层面的权限检查。这反映了两个工具不同的安全理念：Codex 假设模型可能产生恶意输出并在系统层面进行防护，Claude Code 更多依赖模型自身的安全对齐和用户的运行时确认。

---

## Reference

- [Apple Seatbelt（sandbox-exec）文档](https://developer.apple.com/documentation/security/app_sandbox)
- [Linux Landlock LSM](https://landlock.io/)
- [seccomp 系统调用过滤](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html)
- [Bubblewrap 容器沙箱](https://github.com/containers/bubblewrap)
- [Starlark 语言规范](https://github.com/bazelbuild/starlark)
- [Codex CLI 安全文档](https://developers.openai.com/codex/cli/features/)

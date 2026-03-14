# Claude Code Session Manager — Product Specification

| Field | Value |
|-------|-------|
| **Document owner** | Product & Engineering |
| **Status** | Draft |
| **Version** | v0.1 |
| **Created** | 2026-03-11 |
| **Last updated** | 2026-03-11 |
| **Target release** | v1.0 |

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v0.1 | 2026-03-11 | AI-assisted | Initial draft |

---

## 1 Executive Summary

Claude Code Session Manager（以下简称 CCSM）是一个 Web 应用，用于浏览、管理和持久化 Claude Code 的对话历史。应用采用经典的左右分栏布局——左侧为会话列表（支持勾选），右侧为对话 trajectory 展示（只读）。核心差异化功能是**将选中的会话批量发送到远程 MongoDB 服务器**，实现跨机器的对话归档与检索。

> 📌 DECISION: 以 [claude-run](https://github.com/kamranahmedse/claude-run) 为骨架进行扩展（~2,700 行，React 19 + Hono + Vite + Tailwind CSS 4），而非从零构建或基于更重的 Claudex/Claud-ometer。原因：claude-run 的 UI 布局完全符合需求，代码量最小，SSE 实时架构已就绪，改造路径最短。

---

## 2 Problem Statement

### 2.1 Background

Claude Code 将所有对话以 JSONL 格式存储在本地 `~/.claude/projects/` 目录。社区已有 50+ 工具围绕这些日志构建（详见 [调研报告](./claude-code-monitor-telemetry-survey.md)），但存在以下空白：

- 所有现有查看器（claude-run, history-viewer, Claudex, Claud-ometer）都是**纯本地工具**
- **没有任何工具支持 MongoDB 远程持久化**（最接近的是 better-ccflare 的 PostgreSQL 支持）
- 当用户在多台机器上使用 Claude Code 时，无法集中查看和归档对话历史

### 2.2 Problem Definition

> **Claude Code 重度用户**需要一种方式来**集中浏览和归档多台机器上的对话历史**，因为**本地 JSONL 文件分散在各台机器上，无法统一检索和长期保存**，但目前**所有开源工具都只支持本地查看，缺少远程持久化能力**。

### 2.3 Evidence

| Evidence type | Source | Key finding |
|---------------|--------|-------------|
| 生态调研 | awesome-claude-code + GitHub 搜索 | 50+ 工具中 0 个支持 MongoDB 远程持久化 |
| 竞品分析 | claude-run, Claudex, Claud-ometer, history-viewer | 全部基于本地 JSONL/SQLite，无远程写入 |
| 用户场景 | 多机器开发者 | 在办公电脑、家用电脑、CI 机器分别产生对话，无法统一归档 |

---

## 3 Goals & Success Metrics

### 3.1 Product Goals

| # | Goal | Alignment |
|---|------|-----------|
| G1 | 提供清晰的会话列表 + 对话 trajectory 浏览体验 | 核心功能：对话查看器 |
| G2 | 支持勾选会话并批量发送到远程 MongoDB | 核心差异化：远程持久化 |
| G3 | 从远程 MongoDB 浏览已归档会话 | 远程数据消费闭环 |

### 3.2 Success Metrics

| Metric | Baseline | Target | Measurement method |
|--------|----------|--------|--------------------|
| 本地会话加载时间 | — | < 2s（100 个会话） | 浏览器 Performance API |
| 消息 trajectory 渲染 | — | < 1s（1000 条消息） | 首次渲染完成时间 |
| 会话上传成功率 | — | > 99% | API 成功/失败计数 |
| 远程会话检索延迟 | — | < 500ms（p95） | MongoDB 查询耗时 |

> 📊 METRIC: 上线后连续监控 2 周，确认性能指标稳定达标。

### 3.3 Non-Goals (Out of Scope)

- 🚫 OUT OF SCOPE: 与 Claude Code Agent 的实时交互（本工具为只读查看器）
- 🚫 OUT OF SCOPE: Token 成本分析仪表板（可在 v2 从 Claud-ometer 借鉴 Recharts 图表）
- 🚫 OUT OF SCOPE: 全文搜索（v1 仅前端内存过滤，v2 可引入 MongoDB Atlas Search）
- 🚫 OUT OF SCOPE: 多用户认证/权限管理（v1 为单用户工具）
- 🚫 OUT OF SCOPE: 移动端适配

---

## 4 Target Users & Personas

### 4.1 Primary Persona

| Attribute | Detail |
|-----------|--------|
| **Name** | "Alex, Claude Code 高频开发者" |
| **Role** | 全栈开发工程师 |
| **Goal** | 集中浏览和归档多台机器上的 Claude Code 对话 |
| **Pain point** | 对话散落在多台机器的本地 JSONL 中，无法统一检索 |
| **Technical skill** | High |
| **Usage frequency** | Daily |
| **Key quote** | "我每天在 3 台机器上用 Claude Code，想回顾上周的一段对话，完全找不到在哪台机器上" |

### 4.2 Secondary Persona

| Attribute | Detail |
|-----------|--------|
| **Name** | "Team Lead, 团队管理者" |
| **Role** | 技术团队负责人 |
| **Goal** | 了解团队成员使用 Claude Code 的模式和效率 |
| **Pain point** | 无法查看团队成员的 AI 协作记录 |
| **Technical skill** | Medium-High |
| **Usage frequency** | Weekly |

### 4.3 Anti-Personas (Who This Is NOT For)

- 不使用 Claude Code CLI 的 Claude.ai Web 用户
- 需要实时与 Claude 交互的用户（本工具只读）
- 需要企业级审计合规的大型组织（v1 无权限管理）

---

## 5 User Stories & Requirements

### 5.1 User Stories

| ID | Priority | As a... | I want to... | So that... |
|----|----------|---------|-------------|-----------|
| US-1 | P0 | 开发者 | 在左侧 sidebar 看到所有本地会话列表 | 我能快速找到某个对话 |
| US-2 | P0 | 开发者 | 点击一个会话后在右侧查看完整的对话 trajectory | 我能回顾 AI 协作的完整过程 |
| US-3 | P0 | 开发者 | 在 trajectory 中看到工具调用的详情（Bash、Read、Edit 等） | 我能了解 Claude 执行了哪些操作 |
| US-4 | P0 | 开发者 | 勾选一个或多个会话，点击"上传"发送到远程 MongoDB | 我能持久化保存重要对话 |
| US-5 | P0 | 开发者 | 切换到"远程"模式浏览已上传的会话 | 我能在任何机器上查看归档对话 |
| US-6 | P1 | 开发者 | 按项目名称筛选会话列表 | 我能快速聚焦到某个项目的对话 |
| US-7 | P1 | 开发者 | 在会话列表中搜索关键词 | 我能按内容查找对话 |
| US-8 | P1 | 开发者 | 看到每个会话的摘要预览（首条用户消息 + 消息数 + 时间） | 我能在不打开的情况下识别对话 |
| US-9 | P1 | 开发者 | 实时看到正在进行的会话更新 | 我能在另一个窗口监控 Claude Code 工作 |
| US-10 | P2 | 开发者 | 配置远程 MongoDB 连接信息 | 我能指定自己的 MongoDB 实例 |
| US-11 | P2 | 开发者 | 全选/反选所有会话 | 我能一键上传所有对话 |

### 5.2 Acceptance Criteria

**US-1: 会话列表**

```
AC-1.1: Given 本地 ~/.claude/projects/ 下有 50 个会话 JSONL 文件,
        When 用户打开应用,
        Then 左侧 sidebar 显示 50 个会话条目,
        And 按最后修改时间降序排列.

AC-1.2: Given 本地没有任何 JSONL 文件,
        When 用户打开应用,
        Then sidebar 显示空状态提示 "No sessions found".

AC-1.3: Given 会话列表有 500+ 条,
        When 用户滚动列表,
        Then 使用虚拟滚动, 滚动流畅无卡顿 (60fps).
```

**US-2: 对话 Trajectory 展示**

```
AC-2.1: Given 用户选中了一个包含 100 条消息的会话,
        When 右侧面板加载完成,
        Then 显示所有 user 和 assistant 消息,
        And 每条消息显示角色标签、时间戳.

AC-2.2: Given 一条 assistant 消息包含 Markdown 格式的代码块,
        When 渲染该消息,
        Then 代码块有语法高亮.

AC-2.3: Given 消息列表已加载,
        When 新消息实时追加（SSE 推送）,
        Then 如果用户已滚动到底部, 自动滚动显示新消息;
        And 如果用户在中间位置, 不自动滚动, 显示 "Scroll to bottom" 按钮.
```

**US-3: 工具调用展示**

```
AC-3.1: Given 一条 assistant 消息包含 tool_use content block（如 Bash 命令）,
        When 渲染该消息,
        Then 显示可折叠的工具调用面板,
        And 面板标题显示工具名称和摘要.

AC-3.2: Given 一个 Bash 工具调用有对应的 tool_result,
        When 用户展开该面板,
        Then 同时显示命令输入和执行输出,
        And 输出保留 ANSI 颜色.
```

**US-4: 勾选并上传到 MongoDB**

```
AC-4.1: Given sidebar 显示会话列表,
        When 用户勾选 3 个会话并点击 "Upload" 按钮,
        Then 向后端 POST /api/sessions/upload 发送请求,
        And 3 个会话的完整数据（含所有消息）写入 MongoDB,
        And UI 显示成功提示 "3 sessions uploaded".

AC-4.2: Given 用户未勾选任何会话,
        When 用户点击 "Upload" 按钮,
        Then 按钮为禁用状态（不可点击）.

AC-4.3: Given 上传过程中网络断开,
        When 请求失败,
        Then UI 显示错误提示 "Upload failed: {error message}",
        And 已成功的部分不回滚（幂等设计, 按 sessionId 去重）.
```

**US-5: 远程会话浏览**

```
AC-5.1: Given 用户切换到 "Remote" 数据源,
        When 远程 MongoDB 中有 20 个已归档会话,
        Then sidebar 显示 20 个远程会话,
        And 会话条目带有 "remote" 标记以区分本地.

AC-5.2: Given 用户在 Remote 模式下点击一个会话,
        When 右侧面板加载,
        Then 从 MongoDB 获取并渲染完整对话 trajectory,
        And 渲染效果与本地模式一致.
```

### 5.3 Functional Requirements

#### 5.3.1 本地数据读取

| ID | Requirement | Priority | Notes |
|----|------------|----------|-------|
| FR-1 | 系统应扫描 `~/.claude/projects/` 和 `~/.claude/history.jsonl` 发现所有会话 | P0 | 参考 claude-run storage.ts |
| FR-2 | 系统应逐行解析 JSONL 文件，提取 user/assistant/tool_use/tool_result 消息 | P0 | 跳过格式错误的行 |
| FR-3 | 系统应监听 JSONL 文件变化，通过 SSE 推送增量更新 | P1 | Chokidar, 20ms 防抖 |
| FR-4 | 系统应支持按字节偏移量增量加载，避免重复读取已解析内容 | P1 | 大文件性能优化 |

#### 5.3.2 对话展示

| ID | Requirement | Priority | Notes |
|----|------------|----------|-------|
| FR-5 | 系统应渲染 Markdown 内容（GFM 规范） | P0 | react-markdown + remark-gfm |
| FR-6 | 系统应渲染代码块并提供语法高亮 | P0 | Prism |
| FR-7 | 系统应渲染 8 种工具调用：Bash, Read, Edit, Write, Grep, Glob, Todo, Task | P0 | 可折叠面板 |
| FR-8 | 系统应渲染 thinking 内容块（可折叠） | P1 | Extended Thinking |
| FR-9 | 系统应为会话显示摘要预览（首条用户消息截断 + 消息数） | P1 | |

#### 5.3.3 远程持久化

| ID | Requirement | Priority | Notes |
|----|------------|----------|-------|
| FR-10 | 系统应提供 checkbox UI 允许用户勾选会话 | P0 | 支持多选 + 全选 |
| FR-11 | 系统应批量上传勾选的会话到 MongoDB | P0 | POST /api/sessions/upload |
| FR-12 | 上传应为幂等操作，按 sessionId 去重（upsert） | P0 | 防止重复上传 |
| FR-13 | 系统应支持切换数据源（Local / Remote） | P0 | 类似 Claud-ometer 的 Live/Imported 切换 |
| FR-14 | 系统应从 MongoDB 读取已归档会话列表 | P0 | GET /api/remote/sessions |
| FR-15 | 系统应从 MongoDB 读取单个会话的完整消息 | P0 | GET /api/remote/sessions/:id |
| FR-16 | 系统应支持配置 MongoDB 连接字符串 | P2 | 环境变量或设置页面 |

### 5.4 Non-Functional Requirements

| ID | Category | Requirement | Threshold | Measurement |
|----|----------|-------------|-----------|-------------|
| NFR-1 | Performance | 本地会话列表加载 | < 2s (100 sessions) | Performance API |
| NFR-2 | Performance | 对话 trajectory 首次渲染 | < 1s (1000 messages) | Performance API |
| NFR-3 | Performance | 虚拟滚动帧率 | 60fps | Chrome DevTools |
| NFR-4 | Performance | MongoDB 上传 10 个会话 | < 5s | API 响应时间 |
| NFR-5 | Performance | MongoDB 会话列表查询 | < 500ms (p95) | MongoDB profiler |
| NFR-6 | Scalability | 本地会话数量 | 1000+ | 虚拟滚动支撑 |
| NFR-7 | Scalability | 单个会话消息数 | 10,000+ | 增量加载 + 虚拟滚动 |
| NFR-8 | Scalability | MongoDB 存储会话数 | 100,000+ | 索引优化 |
| NFR-9 | Compatibility | 浏览器支持 | Chrome/Firefox/Safari/Edge 最近 2 个版本 | 手动测试 |
| NFR-10 | Security | MongoDB 连接 | TLS 加密传输 | 连接字符串配置 |

---

## 6 User Flow

### 6.1 Primary User Flow — 浏览本地会话

```
┌─────────────┐
│  启动应用    │
│  (npm start) │
└──────┬──────┘
       │
       ▼
┌──────────────┐     扫描 ~/.claude/
│  加载会话列表  │◀──── history.jsonl + projects/
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Sidebar 渲染 │
│  会话列表     │
└──────┬───────┘
       │ 点击一个会话
       ▼
┌──────────────┐     SSE: /api/conversation/:id/stream
│  右侧渲染     │◀──── 增量推送消息
│  Trajectory   │
└──────────────┘
```

### 6.2 Primary User Flow — 上传到 MongoDB

```
┌──────────────┐
│  Sidebar 中   │
│  勾选 N 个会话│
└──────┬───────┘
       │ 点击 "Upload" 按钮
       ▼
┌──────────────┐
│  前端收集     │
│  选中 IDs     │
└──────┬───────┘
       │ POST /api/sessions/upload { sessionIds: [...] }
       ▼
┌──────────────┐     读取每个 JSONL
│  后端解析     │◀──── 提取完整消息
│  选中会话     │
└──────┬───────┘
       │ MongoDB bulkWrite (upsert by sessionId)
       ▼
  ┌──────────┐     Fail    ┌────────────┐
  │ 写入成功? │────────────▶│ 返回错误   │
  └────┬─────┘             │ 已成功部分  │
       │ Yes               │ 不回滚     │
       ▼                   └────────────┘
┌──────────────┐
│  返回 200    │
│  成功数/总数  │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  UI toast:   │
│  "N sessions │
│   uploaded"  │
└──────────────┘
```

### 6.3 Primary User Flow — 浏览远程会话

```
┌──────────────┐
│  切换数据源   │
│  Local→Remote│
└──────┬───────┘
       │ GET /api/remote/sessions
       ▼
┌──────────────┐
│  Sidebar 渲染 │
│  远程会话列表  │
└──────┬───────┘
       │ 点击一个会话
       ▼
┌──────────────┐
│  GET /api/   │
│  remote/     │
│  sessions/:id│
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  右侧渲染     │
│  Trajectory   │
│  (与本地一致) │
└──────────────┘
```

### 6.4 Error / Edge Case Flows

| Scenario | Expected behavior |
|----------|------------------|
| JSONL 文件包含格式错误的行 | 跳过该行，继续解析后续行 |
| MongoDB 连接失败 | Toast 错误提示；Local 模式正常使用，Remote 模式显示连接错误 |
| 上传过程中部分成功 | 返回成功数/失败数；幂等设计允许重试 |
| 上传已存在的会话 | Upsert 覆盖更新，不报错 |
| 本地 JSONL 文件在浏览中被删除 | SSE 断开后显示 "Session file not found" |
| 超大会话（10,000+ 消息） | 增量加载 + 虚拟滚动保证性能 |

---

## 7 Technical Specification

### 7.1 Tech Stack

| Layer | Technology | Version | Justification |
|-------|-----------|---------|---------------|
| **Frontend** | React + TypeScript | 19 / 5.7 | claude-run 骨架，团队熟悉 |
| **Build (FE)** | Vite | 6.x | 快速 HMR，claude-run 已用 |
| **Styling** | Tailwind CSS | 4.x | claude-run 已用，原子化 CSS |
| **Icons** | Lucide React | 0.56x | claude-run 已用 |
| **Virtual Scroll** | @tanstack/react-virtual | 3.x | claude-run 已用，大列表必需 |
| **Markdown** | react-markdown + remark-gfm | 10.x / 4.x | claude-run 已用 |
| **Backend** | Hono (Node.js) | 4.x | claude-run 已用，轻量高性能 |
| **Build (BE)** | TSUP | 8.x | claude-run 已用 |
| **File Watch** | Chokidar | 4.x | claude-run 已用，SSE 增量推送 |
| **Diff** | diff (npm) | 8.x | Edit 工具渲染用 |
| **Database** | MongoDB | 7.x+ | 远程持久化目标 |
| **MongoDB Driver** | mongodb (npm) | 6.x | 官方 Node.js 驱动 |

> 📌 DECISION: 继承 claude-run 的 Hono + Vite + React 19 全栈，在此基础上添加 MongoDB 驱动。不引入 Next.js 或 Fastify，避免重写服务端。

### 7.2 System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser (React SPA)                       │
│                                                                  │
│  ┌─────────────┐  ┌──────────────────┐  ┌─────────────────────┐ │
│  │  Sidebar     │  │  Trajectory View │  │  Upload Toolbar     │ │
│  │  - sessions  │  │  - messages      │  │  - checkbox state   │ │
│  │  - checkboxes│  │  - tool blocks   │  │  - upload button    │ │
│  │  - search    │  │  - markdown      │  │  - data source      │ │
│  │  - filter    │  │  - code highlight│  │    toggle           │ │
│  └──────┬──────┘  └────────┬─────────┘  └──────────┬──────────┘ │
│         │                  │                        │            │
└─────────┼──────────────────┼────────────────────────┼────────────┘
          │ HTTP/SSE         │ HTTP/SSE               │ HTTP POST
          ▼                  ▼                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Hono Server (:12001)                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Routes                                                    │  │
│  │  GET  /api/sessions              → list local sessions     │  │
│  │  GET  /api/sessions/stream       → SSE session updates     │  │
│  │  GET  /api/conversation/:id      → full conversation       │  │
│  │  GET  /api/conversation/:id/stream → SSE message updates   │  │
│  │  POST /api/sessions/upload       → upload to MongoDB       │  │
│  │  GET  /api/remote/sessions       → list remote sessions    │  │
│  │  GET  /api/remote/sessions/:id   → get remote conversation │  │
│  │  GET  /api/projects              → list projects           │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  storage.ts   │  │  watcher.ts  │  │  mongo.ts              │ │
│  │  (JSONL parse)│  │  (Chokidar)  │  │  (MongoDB driver)      │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────────┘ │
│         │                 │                      │               │
└─────────┼─────────────────┼──────────────────────┼───────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
   ┌─────────────┐  ┌─────────────┐       ┌─────────────┐
   │ ~/.claude/   │  │ ~/.claude/  │       │  MongoDB    │
   │ projects/    │  │ (fswatch)   │       │  Server     │
   │ *.jsonl      │  │             │       │  (remote)   │
   └─────────────┘  └─────────────┘       └─────────────┘
```

> 🔒 SECURITY: MongoDB 连接必须使用 TLS。连接字符串通过环境变量 `MONGODB_URI` 传入，不在前端暴露。

### 7.3 Data Model

#### Entity-Relationship Diagram (MongoDB Collections)

```
┌──────────────────────────┐       ┌──────────────────────────────┐
│      sessions            │       │      messages                │
├──────────────────────────┤       ├──────────────────────────────┤
│ _id        ObjectId  PK  │──┐    │ _id        ObjectId  PK     │
│ sessionId  String    UQ  │  │    │ sessionId  String    FK,IDX │
│ projectId  String    IDX │  └──1▶│ uuid       String    UQ     │
│ projectName String       │       │ parentUuid String           │
│ timestamp  Date      IDX │       │ role       String    IDX    │
│ duration   Number        │       │            ("user"|"assistant"|"system")
│ messageCount Number      │       │ type       String           │
│ toolCallCount Number     │       │            ("user"|"assistant"|"tool_use"
│ models     [String]      │       │             |"tool_result"|"summary")
│ version    String        │       │ content    Mixed            │
│ gitBranch  String        │       │            (String | ContentBlock[])
│ cwd        String        │       │ model      String           │
│ firstMessage String      │       │ timestamp  Date      IDX    │
│ totalInputTokens  Number │       │ isSidechain Boolean         │
│ totalOutputTokens Number │       │ usage      Object           │
│ totalCacheRead    Number │       │   .input_tokens      Number │
│ totalCacheWrite   Number │       │   .output_tokens     Number │
│ uploadedAt Date          │       │   .cache_creation    Number │
│ sourceHost String        │       │   .cache_read        Number │
└──────────────────────────┘       │ toolCalls  [Object]         │
                                   │   .id       String          │
                                   │   .name     String          │
                                   │   .input    Mixed           │
                                   │ toolResult Object           │
                                   │   .tool_use_id String       │
                                   │   .content     Mixed        │
                                   │   .is_error    Boolean      │
                                   └──────────────────────────────┘
```

#### Field Details

**sessions**

| Field | Type | Constraints | Description |
|-------|------|------------|-------------|
| `sessionId` | `String` | UNIQUE index | Claude Code 原始会话 UUID |
| `projectId` | `String` | Index | URL-encoded 项目路径 |
| `projectName` | `String` | — | 可读的项目名称 |
| `timestamp` | `Date` | Index, DESC | 最后活动时间 |
| `duration` | `Number` | — | 会话时长（秒） |
| `messageCount` | `Number` | — | 消息总数 |
| `toolCallCount` | `Number` | — | 工具调用次数 |
| `models` | `[String]` | — | 使用的模型列表 |
| `firstMessage` | `String` | — | 首条用户消息预览（截断 100 字符） |
| `totalInputTokens` | `Number` | — | 累计输入 Token |
| `totalOutputTokens` | `Number` | — | 累计输出 Token |
| `uploadedAt` | `Date` | — | 上传时间 |
| `sourceHost` | `String` | — | 上传来源主机名（用于标识多机器） |

**messages**

| Field | Type | Constraints | Description |
|-------|------|------------|-------------|
| `sessionId` | `String` | Index | 关联的会话 ID |
| `uuid` | `String` | UNIQUE index | 消息唯一 ID |
| `parentUuid` | `String` | — | 父消息 ID（层级关系） |
| `role` | `String` | — | "user" / "assistant" / "system" |
| `type` | `String` | — | JSONL 原始 type 字段 |
| `content` | `Mixed` | — | 字符串或 ContentBlock 数组 |
| `model` | `String` | — | 使用的模型 ID |
| `timestamp` | `Date` | Index | 消息时间 |
| `isSidechain` | `Boolean` | — | 是否为子 Agent 对话 |
| `usage` | `Object` | — | Token 用量 |
| `toolCalls` | `[Object]` | — | 从 content 中提取的 tool_use blocks |
| `toolResult` | `Object` | — | 从 content 中提取的 tool_result |

#### MongoDB Indexes

```javascript
// sessions collection
db.sessions.createIndex({ sessionId: 1 }, { unique: true })
db.sessions.createIndex({ projectId: 1, timestamp: -1 })
db.sessions.createIndex({ timestamp: -1 })

// messages collection
db.messages.createIndex({ uuid: 1 }, { unique: true })
db.messages.createIndex({ sessionId: 1, timestamp: 1 })
```

> 📌 DECISION: 使用两个 collection（sessions + messages）而非单个嵌套文档，原因：
> 单个会话可能有 10,000+ 条消息，超出 MongoDB 16MB 文档大小限制。
> 分开存储支持按消息级别检索和分页。

### 7.4 API Specification

#### Endpoints

| Method | Path | Source | Description | Request | Response |
|--------|------|--------|-------------|---------|----------|
| `GET` | `/api/sessions` | Local | 列出本地会话 | Query: `?projectId=` | `200`: `SessionInfo[]` |
| `GET` | `/api/sessions/stream` | Local | SSE 实时会话更新 | — | SSE: `SessionInfo[]` events |
| `GET` | `/api/conversation/:id` | Local | 获取完整对话 | — | `200`: `Message[]` |
| `GET` | `/api/conversation/:id/stream` | Local | SSE 实时消息增量 | Query: `?offset=` | SSE: `Message[]` events |
| `GET` | `/api/projects` | Local | 列出所有项目 | — | `200`: `Project[]` |
| `POST` | `/api/sessions/upload` | → MongoDB | 上传选中会话 | Body: `UploadRequest` | `200`: `UploadResult` |
| `GET` | `/api/remote/sessions` | MongoDB | 列出远程会话 | Query: `?projectId=&limit=&offset=` | `200`: `SessionInfo[]` |
| `GET` | `/api/remote/sessions/:id` | MongoDB | 获取远程对话 | — | `200`: `SessionDetail` |

#### Request/Response Schemas

**POST /api/sessions/upload**

Request:
```json
{
  "sessionIds": ["uuid-1", "uuid-2", "uuid-3"]
}
```

Response (200):
```json
{
  "total": 3,
  "uploaded": 3,
  "skipped": 0,
  "errors": []
}
```

Response (partial failure):
```json
{
  "total": 3,
  "uploaded": 2,
  "skipped": 0,
  "errors": [
    { "sessionId": "uuid-3", "error": "Session file not found" }
  ]
}
```

**GET /api/remote/sessions**

Response (200):
```json
[
  {
    "sessionId": "uuid-1",
    "projectName": "my-project",
    "timestamp": "2026-03-10T14:30:00Z",
    "messageCount": 42,
    "toolCallCount": 15,
    "firstMessage": "Help me refactor the auth module...",
    "models": ["claude-sonnet-4-6"],
    "sourceHost": "macbook-pro.local",
    "uploadedAt": "2026-03-11T09:00:00Z"
  }
]
```

**GET /api/remote/sessions/:id**

Response (200):
```json
{
  "session": { /* SessionInfo fields */ },
  "messages": [
    {
      "uuid": "msg-uuid-1",
      "role": "user",
      "content": "Help me refactor...",
      "timestamp": "2026-03-10T14:30:00Z"
    },
    {
      "uuid": "msg-uuid-2",
      "role": "assistant",
      "content": [
        { "type": "text", "text": "I'll help you refactor..." },
        { "type": "tool_use", "id": "tu-1", "name": "Read", "input": { "file_path": "/src/auth.ts" } }
      ],
      "model": "claude-sonnet-4-6",
      "timestamp": "2026-03-10T14:30:05Z",
      "usage": { "input_tokens": 1200, "output_tokens": 350 }
    }
  ]
}
```

#### Error Responses

| Status | Code | Description |
|--------|------|-------------|
| `400` | `INVALID_REQUEST` | sessionIds 为空或格式错误 |
| `404` | `SESSION_NOT_FOUND` | 本地 JSONL 文件不存在 |
| `500` | `MONGODB_ERROR` | MongoDB 连接或写入失败 |
| `503` | `MONGODB_UNAVAILABLE` | MongoDB 未配置或不可达 |

Error body format:
```json
{
  "error": {
    "code": "MONGODB_UNAVAILABLE",
    "message": "MongoDB connection not configured. Set MONGODB_URI environment variable."
  }
}
```

### 7.5 Sequence Diagram — Upload Sessions to MongoDB

```
Browser              Hono Server            Storage             MongoDB
  │                      │                     │                    │
  │  POST /api/sessions/upload                 │                    │
  │  { sessionIds: [A, B] }                    │                    │
  │─────────────────────▶│                     │                    │
  │                      │                     │                    │
  │                      │  readSession(A)     │                    │
  │                      │────────────────────▶│                    │
  │                      │◀────────────────────│                    │
  │                      │  [entries A]        │                    │
  │                      │                     │                    │
  │                      │  readSession(B)     │                    │
  │                      │────────────────────▶│                    │
  │                      │◀────────────────────│                    │
  │                      │  [entries B]        │                    │
  │                      │                     │                    │
  │                      │  buildSessionDoc(A) │                    │
  │                      │  buildSessionDoc(B) │                    │
  │                      │                     │                    │
  │                      │  bulkWrite sessions (upsert)             │
  │                      │─────────────────────────────────────────▶│
  │                      │◀─────────────────────────────────────────│
  │                      │                     │                    │
  │                      │  bulkWrite messages (upsert by uuid)     │
  │                      │─────────────────────────────────────────▶│
  │                      │◀─────────────────────────────────────────│
  │                      │                     │                    │
  │  200 { uploaded: 2 } │                     │                    │
  │◀─────────────────────│                     │                    │
```

---

## 8 Design & UX

### 8.1 Wireframe — Main Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ☰ CCSM                    [Local ▼ | Remote]           ⚙️  Settings   │
├──────────────────────┬───────────────────────────────────────────────────┤
│                      │                                                   │
│  🔍 Search sessions  │  Session: "Refactor auth module"                 │
│                      │  Project: my-project | 2h ago | 42 msgs          │
│  Filter: [All ▼]     │                                                   │
│                      │  ┌─────────────────────────────────────────────┐  │
│  ┌──────────────────┐│  │ 👤 User  14:30                             │  │
│  │ ☐ Refactor auth  ││  │ Help me refactor the auth module to use    │  │
│  │   my-project     ││  │ JWT instead of sessions.                   │  │
│  │   42 msgs · 2h   ││  └─────────────────────────────────────────────┘  │
│  ├──────────────────┤│                                                   │
│  │ ☐ Fix login bug  ││  ┌─────────────────────────────────────────────┐  │
│  │   web-app        ││  │ 🤖 Claude (sonnet-4-6)  14:30              │  │
│  │   18 msgs · 30m  ││  │ I'll help you refactor the auth module.    │  │
│  ├──────────────────┤│  │ Let me first read the current code.        │  │
│  │ ☐ Add dark mode  ││  │                                             │  │
│  │   ui-lib         ││  │ ┌─ 📖 Read ──────────────────────────────┐ │  │
│  │   65 msgs · 4h   ││  │ │ /src/auth.ts                          │ │  │
│  ├──────────────────┤│  │ │ ▶ Click to expand                     │ │  │
│  │ ☐ Debug API      ││  │ └────────────────────────────────────────┘ │  │
│  │   backend        ││  │                                             │  │
│  │   27 msgs · 1h   ││  │ ┌─ 🔧 Edit ─────────────────────────────┐ │  │
│  └──────────────────┘│  │ │ /src/auth.ts                          │ │  │
│                      │  │ │ ▶ Click to expand (diff view)         │ │  │
│                      │  │ └────────────────────────────────────────┘ │  │
│  ┌──────────────────┐│  └─────────────────────────────────────────────┘  │
│  │ [Upload Selected]││                                                   │
│  │  0 selected      ││         ··· more messages ···                    │
│  └──────────────────┘│                                                   │
│                      │                                    [↓ Scroll ↓]  │
├──────────────────────┴───────────────────────────────────────────────────┤
│  Status: Connected · 4 projects · 156 sessions                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Wireframe — Upload Confirmation

```
┌──────────────────────────────────────────┐
│  Upload Sessions to MongoDB              │
│                                          │
│  You are about to upload 3 sessions:     │
│                                          │
│  • Refactor auth module (42 msgs)        │
│  • Fix login bug (18 msgs)              │
│  • Add dark mode (65 msgs)              │
│                                          │
│  Total: 125 messages                     │
│  Destination: mongodb://...masked...     │
│                                          │
│       [Cancel]        [Upload Now]       │
└──────────────────────────────────────────┘
```

### 8.3 Design Principles

- **只读查看器** — 永远不修改本地 JSONL 文件，只读取
- **渐进式披露** — 工具调用默认折叠，点击展开详情
- **本地优先** — MongoDB 不可用时，本地浏览功能完全正常
- **视觉区分** — 本地 vs 远程会话用标签/颜色明确区分
- **保持 claude-run 的暗色主题** — 开发者工具应该是暗色的

---

## 9 Security & Privacy

| Concern | Requirement | Implementation |
|---------|-------------|---------------|
| MongoDB 凭据 | 不在前端暴露连接字符串 | 环境变量 `MONGODB_URI`，服务端读取 |
| 数据传输 | MongoDB 连接加密 | TLS/SSL（mongodb+srv:// 或 ssl=true） |
| 本地文件访问 | 只读 `~/.claude/` 目录 | 路径规范化，拒绝符号链接跳出 |
| 输入校验 | 防止注入 | sessionId 格式校验（UUID 正则），不拼接用户输入到查询 |
| CORS | 仅允许同源访问 | Hono 默认不设置 CORS headers |

> 🔒 SECURITY: 路径遍历防护——所有文件路径都必须 `resolve()` + `startsWith(claudeDir)` 检查。参考 claude-run 已有的安全实现。

---

## 10 Dependencies & Integrations

| Dependency | Type | Status | Risk |
|-----------|------|--------|------|
| Claude Code 本地 JSONL 格式 | External (Anthropic) | Stable | 格式变更可能破坏解析器 |
| MongoDB Server | External | User-provided | 用户需自行部署或使用 Atlas |
| mongodb npm driver | Library | Stable (v6) | — |
| claude-run codebase | Fork baseline | Available (MIT) | 上游更新需手动合并 |
| Node.js 20+ | Runtime | Stable | — |

> ⚠️ RISK: Claude Code JSONL 格式未公开文档化，Anthropic 可能在新版本中变更格式。Mitigation: 参考 Claudex 的 templateDetector 做版本检测，解析器对未知字段做 graceful fallback。

---

## 11 Rollout & Launch Plan

### 11.1 Rollout Strategy

| Phase | Scope | Success gate |
|-------|-------|-------------|
| Alpha | 开发者本地使用 | 本地浏览功能完全正常，上传到本地 MongoDB 成功 |
| Beta | 连接远程 MongoDB Atlas | 跨机器上传和查看成功 |
| v1.0 | 公开发布（npm / GitHub） | README 完整，`npx` 可用 |

### 11.2 Monitoring

| Signal | Method | Alert threshold |
|--------|--------|----------------|
| 上传失败率 | 后端日志 | 任何 500 错误 |
| MongoDB 查询延迟 | MongoDB profiler | > 1s |
| 前端渲染性能 | 浏览器 Performance API | LCP > 3s |

---

## 12 Timeline & Milestones

| Milestone | Description | Dependencies |
|-----------|-------------|-------------|
| M1: Fork & Setup | Fork claude-run，搭建开发环境，添加 MongoDB 驱动 | — |
| M2: Checkbox UI | Sidebar 添加 checkbox + 全选/反选 + Upload 按钮 | M1 |
| M3: Upload API | POST /api/sessions/upload 实现 + MongoDB 写入 | M1 |
| M4: Remote Browse | Remote 模式 + GET /api/remote/* 实现 | M3 |
| M5: Polish | 错误处理、loading 状态、空状态、确认弹窗 | M2 + M4 |
| M6: Release | README、npm 发布、测试 | M5 |

---

## 13 Assumptions & Risks

### 13.1 Assumptions

| # | Assumption | Impact if wrong |
|---|-----------|----------------|
| A1 | Claude Code JSONL 格式在 v2.x/v3.x 之间变化较小 | 需要多版本解析器（参考 Claudex templateDetector） |
| A2 | 用户能自行部署 MongoDB（Atlas 免费层或自托管） | 需要提供 Docker Compose 快速部署方案 |
| A3 | 单个会话最大 10,000 条消息 | 超出时可能需要分页加载 |
| A4 | 用户在可信网络环境中使用 | 否则需要添加认证层 |

### 13.2 Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|-----------|
| R1 | Claude Code 格式变更破坏解析器 | Medium | High | 版本检测 + graceful fallback |
| R2 | 大型会话上传超时 | Low | Medium | 分批上传 + 进度回调 |
| R3 | MongoDB Atlas 免费层空间不足 | Medium | Low | 文档说明存储预估 + 清理策略 |
| R4 | claude-run 上游重大重构 | Low | Medium | Fork 后独立演进 |

---

## 14 Open Questions

| # | Question | Status | Decision |
|---|----------|--------|----------|
| Q1 | 是否需要支持删除已上传的远程会话？ | Open | — |
| Q2 | 上传时是否需要压缩（gzip）以节省带宽？ | Open | — |
| Q3 | 是否需要显示上传进度条？ | Open | — |
| Q4 | 远程模式是否需要分页（当远程会话 > 1000 时）？ | Open | — |
| Q5 | 是否需要标记哪些本地会话已上传过？ | Open | — |

---

## 15 Future Considerations

- 💡 FUTURE v2: Token 成本分析仪表板（从 Claud-ometer 借鉴 Recharts 图表组件）
- 💡 FUTURE v2: 全文搜索（MongoDB Atlas Search 或 Mongoose text index）
- 💡 FUTURE v2: 会话标签/收藏/自定义标题（参考 Claudex session_metadata）
- 💡 FUTURE v2: 多用户认证（JWT）
- 💡 FUTURE v3: 活动热力图 + 峰值小时图（参考 Claud-ometer）
- 💡 FUTURE v3: Session Board 像素视图（参考 history-viewer）
- 💡 FUTURE v3: 自动上传模式（文件监听 → 自动同步到 MongoDB）

---

## Appendix

### A. Glossary

| Term | Definition |
|------|-----------|
| JSONL | JSON Lines，每行一个 JSON 对象的文本格式 |
| Trajectory | 完整的对话轨迹，包含所有 user/assistant/tool 消息 |
| Sidechain | Claude Code 子 Agent 产生的对话分支 |
| Content Block | Claude API 返回的结构化内容块（text/tool_use/tool_result/thinking） |
| SSE | Server-Sent Events，服务端单向推送协议 |
| Upsert | Update or Insert，存在则更新，不存在则插入 |
| Compaction | Claude Code 的上下文压缩机制，丢弃早期消息以释放 Token 窗口 |

### B. Related Documents

| Document | Link |
|----------|------|
| 生态调研报告 | [docs/claude-code-monitor-telemetry-survey.md](./claude-code-monitor-telemetry-survey.md) |
| Claudex 分析 | [docs/claudex.md](./claudex.md) |
| claude-code-history-viewer 分析 | [docs/claude-code-history-viewer.md](./claude-code-history-viewer.md) |
| Claud-ometer 分析 | [docs/claud-ometer.md](./claud-ometer.md) |
| cclogviewer 分析 | [docs/cclogviewer.md](./cclogviewer.md) |
| claude-conversation-extractor 分析 | [docs/claude-conversation-extractor.md](./claude-conversation-extractor.md) |
| claude-run 源码 | [claude-code-monitors/claude-run/](../claude-code-monitors/claude-run/) |

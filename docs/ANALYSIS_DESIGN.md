# VibeLens Analysis Feature Design Document

| Field | Value |
|-------|-------|
| **Document owner** | Engineering |
| **Status** | Draft |
| **Version** | v0.1 |
| **Created** | 2026-03-13 |
| **Last updated** | 2026-03-13 |
| **Target release** | v1.0 |

## Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v0.1 | 2026-03-13 | AI-assisted | Initial draft |

---

## 1 Executive Summary

VibeLens 当前已实现会话浏览（Local/HuggingFace 数据源）和 MongoDB 推送能力，但**分析模块全部为 stub**：`analysis/user_preference.py` 和 `analysis/agent_behavior.py` 均抛出 `NotImplementedError`，`api/analysis.py` 返回 `{"status": "not_implemented"}`。

分析功能是 VibeLens 的**核心差异化能力**。Claude Code 官方的 `/insights` 命令已提供基础分析，但存在四个关键空白（无主观数据、无开源数据集、无跨用户比较、无纵向时序分析）。VibeLens 的目标是：

1. **复现 Insights 基线能力**（session stats, facet extraction, narrative insights）
2. **填补四项空白**（主观数据接入、开源数据集导出、跨用户匿名对比、纵向趋势追踪）
3. **引入新型分析**（thinking-action 一致性、Agent 效率评分、交互模式聚类）

本文档定义分析系统的完整架构——从数据摄取、计算管线、数据模型到 API 端点和前端可视化。

---

## 2 Related Work — Claude Insights `/insights`

### 2.1 工作原理

Claude Code 的 `/insights` 命令实现了一个 6 阶段 pipeline：

| Stage | 名称 | 说明 |
|-------|------|------|
| 1 | Session Discovery | 扫描 `~/.claude/projects/` 发现所有 `.jsonl` 会话文件 |
| 2 | Metadata Extraction | 提取每个会话的基础统计（消息数、工具调用数、时长、模型） |
| 3 | Facet Extraction (LLM) | 使用 Claude 对每个会话进行分类：13 种 goal categories、12 种 friction categories、outcome/satisfaction 评分、session_type |
| 4 | Caching | 将 facet 结果缓存到 `~/.claude/usage-data/facets/*.json`，避免重复 LLM 调用 |
| 5 | Aggregated Insights (LLM) | 将所有 facets 聚合后调用 Claude 生成叙述性洞察（项目领域、交互风格、friction 分析、建议） |
| 6 | HTML Report Rendering | 渲染交互式 HTML 报告（统计卡片、图表、叙述段落），写入临时文件并在浏览器打开 |

**Facet 分类体系：**

- **Goal categories (13)**：feature_development, bug_fixing, refactoring, testing, documentation, devops, learning, code_review, data_processing, design, debugging, configuration, other
- **Friction categories (12)**：context_confusion, tool_errors, unclear_instructions, scope_creep, performance_issues, dependency_issues, test_failures, environment_issues, communication_gaps, knowledge_gaps, permission_issues, none
- **Outcome**：success / partial_success / failure / abandoned
- **Satisfaction**：1–5 scale
- **Session type**：coding / debugging / learning / planning / review / other

### 2.2 Insights 的优势

- 自动化分类，用户零配置
- Facet 缓存避免重复 LLM 开销
- 叙述性洞察可读性强
- HTML 报告美观直观

### 2.3 Insights 的四项空白

| # | Gap | 说明 | VibeLens 对策 |
|---|-----|------|---------------|
| G1 | 无 pre/post 主观数据 | 缺少用户对 session 的自评（满意度、任务完成度），只有 LLM 推断 | 支持导入含主观标注的数据集（如 dataclaw） |
| G2 | 无开源数据集 | 分析结果锁定在本机，无法用于学术研究 | 提供 HuggingFace 兼容的去标识化导出 |
| G3 | 无跨用户比较 | 单用户视角，无法回答"我的效率在群体中处于什么水平" | 匿名化 benchmarking 框架 |
| G4 | 无纵向/时序分析 | 只有当前快照，无法追踪"我的工具使用模式如何随时间演变" | 时间序列趋势分析 + 学习曲线检测 |

---

## 3 Analysis Pipeline Architecture

### 3.1 三层架构

分析系统采用三层架构，按计算复杂度和依赖递增排列：

```
┌─────────────────────────────────────────────────────────────────┐
│                         Tier 3: LLM-Powered                      │
│  Facet extraction · Aggregated insights · Thinking-action check  │
│  ─────────── 需要 Claude API，异步后台执行 ───────────            │
├─────────────────────────────────────────────────────────────────┤
│                       Tier 2: Pattern Mining                     │
│  Tool sequences · Session clustering · Longitudinal trends       │
│  Efficiency scoring · Phase detection                            │
│  ─────────── 纯计算，但需要跨 session 聚合 ───────────           │
├─────────────────────────────────────────────────────────────────┤
│                       Tier 1: Pure Computation                   │
│  Session stats · Tool usage · Time patterns · Token economics    │
│  ─────────── 纯计算，单 session 粒度，毫秒级 ───────────         │
└─────────────────────────────────────────────────────────────────┘
```

| Tier | 特征 | 延迟 | LLM 依赖 | 示例 |
|------|------|------|----------|------|
| Tier 1 | 单 session 粒度统计 | < 100ms | 无 | 消息数、工具分布、Token 用量、session 时长 |
| Tier 2 | 跨 session 聚合 + 算法 | < 5s | 无 | 工具序列挖掘、k-means 聚类、纵向趋势、效率评分 |
| Tier 3 | LLM 推理 | 10s–60s | 是 | Facet extraction、叙述性洞察、thinking-action 一致性 |

### 3.2 Pipeline 编排流程

```
┌──────────────┐
│  Trigger     │
│  (API call / │
│   scheduled) │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌────────────────┐
│  Data Loader │────▶│  Session Data  │
│  (DB query)  │     │  (messages +   │
└──────────────┘     │   metadata)    │
                     └───────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌────────────┐ ┌────────────┐ ┌────────────┐
       │  Tier 1    │ │  Tier 2    │ │  Tier 3    │
       │  Compute   │ │  Mining    │ │  LLM Jobs  │
       │  (sync)    │ │  (sync)    │ │  (async)   │
       └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
             │              │              │
             ▼              ▼              ▼
       ┌────────────────────────────────────────┐
       │           analysis_cache table          │
       │  (keyed by analysis_type + params hash) │
       └────────────────────────────────────────┘
             │
             ▼
       ┌────────────┐
       │  API 返回   │
       │  or 前端轮询 │
       └────────────┘
```

**关键设计决策：**

- Tier 1 和 Tier 2 **同步执行**，结果直接返回
- Tier 3 通过 **analysis_jobs 表** 异步执行，前端轮询 job 状态
- 所有结果缓存在 **analysis_cache 表**，支持 TTL 过期

---

## 4 Data Sources

### 4.1 已接入的数据源

VibeLens 已支持通过 `ingest/claude_code.py` 解析 `~/.claude/projects/` 下的 session JSONL 文件，以及通过 `ingest/dataclaw.py` 解析 HuggingFace dataclaw 数据集。

### 4.2 `/insights` 生成的结构化数据（`~/.claude/usage-data/`）

Claude Code 的 `/insights` 命令会在 `~/.claude/usage-data/` 下生成两类结构化数据文件和一份 HTML 报告，这些是 VibeLens 分析的高价值输入：

#### 4.2.1 `usage-data/session-meta/{session-id}.json`

每个 session 一个文件，包含 Insights 提取的结构化元数据：

```json
{
  "session_id": "007a2b80-...",
  "project_path": "/Users/.../StudyNote",
  "start_time": "2026-03-11T18:45:37.879Z",
  "duration_minutes": 64,
  "user_message_count": 5,
  "assistant_message_count": 2,
  "tool_counts": {},
  "languages": {},
  "git_commits": 0,
  "git_pushes": 0,
  "input_tokens": 0,
  "output_tokens": 0,
  "first_prompt": "how are you?",
  "user_interruptions": 0,
  "user_response_times": [44.395, 44.394, 44.394],
  "tool_errors": 0,
  "tool_error_categories": {},
  "uses_task_agent": false,
  "uses_mcp": false,
  "uses_web_search": false,
  "uses_web_fetch": false,
  "lines_added": 0,
  "lines_removed": 0,
  "files_modified": 0,
  "message_hours": [14, 15, 15, 15, 15],
  "user_message_timestamps": ["2026-03-11T18:45:42.831Z", "..."]
}
```

**分析价值**：
- `user_response_times` — 用户反应时间分布，可用于 engagement 分析
- `message_hours` — 精确到小时的活动时间分布，Tier 1 直接可用
- `tool_counts` / `tool_errors` / `tool_error_categories` — 工具使用和错误分类
- `lines_added` / `lines_removed` / `files_modified` — 代码影响量化
- `uses_task_agent` / `uses_mcp` / `uses_web_search` — 功能采用追踪
- `user_interruptions` — 用户中断频率，friction 指标之一

#### 4.2.2 `usage-data/facets/{session-id}.json`

每个 session 一个文件，包含 LLM 提取的分类 facets（Insights 的 Tier 3 缓存）：

```json
{
  "underlying_goal": "User greeted Claude casually...",
  "goal_categories": {"warmup_minimal": 1},
  "outcome": "not_achieved",
  "user_satisfaction_counts": {"frustrated": 1},
  "claude_helpfulness": "unhelpful",
  "session_type": "quick_question",
  "friction_counts": {"api_key_error": 2},
  "friction_detail": "Claude repeatedly returned 'Invalid API key' errors...",
  "primary_success": "none",
  "brief_summary": "User attempted a casual greeting but was blocked...",
  "session_id": "007a2b80-..."
}
```

**分析价值**：
- `goal_categories` — 带权重的目标分类（不仅仅是标签，还有出现次数）
- `user_satisfaction_counts` — 用户满意度分布（frustrated / satisfied / neutral 等）
- `claude_helpfulness` — Agent 有用性评估
- `friction_counts` + `friction_detail` — friction 事件类型及详细描述
- `brief_summary` — LLM 生成的 session 摘要
- **关键发现**：Insights 的 facets schema 与原始计划中假设的不同——使用 `_counts` 字典而非简单列表，且包含 `claude_helpfulness` 和 `primary_success` 字段

#### 4.2.3 `usage-data/report.html`

Insights 生成的交互式 HTML 报告，可作为导出报告的参考模板。

### 4.3 其他 `~/.claude/` 数据源

| 数据源 | 路径 | 数据内容 | 分析用途 |
|--------|------|----------|----------|
| Stats cache | `~/.claude/stats-cache.json` | 每日活动聚合（messageCount, sessionCount, toolCallCount）、工具使用统计、模型使用统计、项目分解、周趋势 | Tier 1 dashboard 快速渲染；纵向趋势基线 |
| Todos | `~/.claude/todos/{session}-agent-{id}.json` | 任务列表（subject, status, blockedBy, owner） | 任务完成率分析；任务 DAG 复杂度评估 |
| Tasks | `~/.claude/tasks/{task-id}/*.json` | 多步骤任务队列 | 任务分解策略分析；步骤完成追踪 |
| File history | `~/.claude/file-history/{session-id}/*.history` | 文件编辑快照历史 | 代码影响分析；文件热点图；代码 churn 相关性 |
| Plans | `~/.claude/plans/*.md` | 已保存的实现计划 | 计划-执行一致性分析 |

### 4.4 Ingest 扩展计划

需要新增以下 ingest 模块：

```python
# 新增 ingest 模块
ingest/
├── claude_code.py          # 已有：session JSONL 解析
├── dataclaw.py             # 已有：HuggingFace dataclaw 解析
├── usage_data.py           # 新增：usage-data/session-meta + facets 解析（最高优先级）
├── stats_cache.py          # 新增：stats-cache.json 解析
├── todos.py                # 新增：todos/ 目录解析
├── tasks.py                # 新增：tasks/ 目录解析
└── file_history.py         # 新增：file-history/ 目录解析
```

> 📌 **优先级**：`usage_data.py` 优先级最高——它直接提供 Insights 已经计算好的 session-meta 和 facets 数据，VibeLens 可以**直接复用**而无需重复 LLM 调用。这意味着 Tier 3 (facet extraction) 可以先走"导入已有 facets"路径，仅对没有 facets 的 session 触发新的 LLM 调用。

---

## 5 Feature Inventory

### Category A — Baseline（复现 Insights 能力）

| ID | Feature | Tier | 说明 |
|----|---------|------|------|
| A1 | Session filtering & metadata extraction | 1 | 按项目/时间/模型筛选 session，提取基础统计（消息数、工具数、时长、Token 用量） |
| A2 | Facet extraction | 3 | LLM 驱动的 session 分类：goal_categories, outcome, friction, satisfaction, session_type |
| A3 | Aggregated narrative insights | 3 | 基于所有 facets 生成叙述性洞察：项目领域分布、交互风格、friction 分析、改进建议 |
| A4 | Statistics dashboard | 1 | 每日活动图表、工具分布、语言分解、模型使用分布 |
| A5 | Executive summary generation | 3 | LLM 生成一段式使用总结（类似 Insights 报告首段） |

### Category B — Novel Features（超越 Insights）

| ID | Feature | Tier | 说明 | 对应 Gap |
|----|---------|------|------|----------|
| B1 | Within-session temporal analysis | 2 | Session 内阶段检测（探索→实现→调试→验证），动量变化（停滞/加速）识别 | — |
| B2 | Longitudinal evolution tracking | 2 | 跨时间维度追踪：工具采用趋势、效率学习曲线、项目活跃度变化 | G4 |
| B3 | Cross-user comparison framework | 2 | 匿名化 benchmarking：将个人指标与群体分布对比（百分位排名） | G3 |
| B4 | Agent efficiency scoring | 2 | 每 session 综合效率分数（Token 效率 × 工具效率 × 错误率倒数 × 任务完成度），支持跨模型比较 | — |
| B5 | Thinking-action consistency analysis | 3 | 比较 thinking block 中的计划与实际 tool_use 行为的一致性（需要 extended thinking 数据） | — |
| B6 | Task completion graph | 1 | 解析 todos/tasks 目录，构建任务 DAG，计算完成率、阻塞链长度、任务分解深度 | — |
| B7 | Code impact analysis | 2 | 基于 file-history 计算文件热点图、编辑频次、代码 churn 与 session 结果的相关性 | — |
| B8 | Interaction pattern clustering | 2 | 对 session 特征向量（工具分布、时长、Token、消息数）做 k-means 聚类，发现典型交互模式 | — |
| B9 | Research dataset export | 1 | 去标识化导出（移除文件路径、用户名、代码内容），HuggingFace datasets 格式，支持自定义 anonymization 规则 | G1, G2 |

---

## 6 Data Models

### 6.1 已有模型（`src/vibelens/models/analysis.py`）

```python
# 已有，无需修改
ToolUsageStat         # 工具使用统计
TimePattern           # 时间模式统计
UserPreferenceResult  # 用户偏好分析结果
AgentBehaviorResult   # Agent 行为模式分析结果
```

### 6.2 新增模型

```python
class SessionFacet(BaseModel):
    """LLM 提取的 session 分类 facets (Tier 3).

    字段设计对齐 ~/.claude/usage-data/facets/*.json 的实际 schema。
    """
    session_id: str
    underlying_goal: str                        # LLM 推断的底层目标描述
    goal_categories: dict[str, int]             # 带权重的目标分类 {category: count}
    outcome: str                                # not_achieved / partial / achieved / abandoned
    user_satisfaction_counts: dict[str, int]     # {frustrated: 1, satisfied: 2, ...}
    claude_helpfulness: str                     # unhelpful / somewhat_helpful / helpful / very_helpful
    session_type: str                           # quick_question / coding / debugging / learning / ...
    friction_counts: dict[str, int]             # {api_key_error: 2, context_confusion: 1, ...}
    friction_detail: str                        # LLM 生成的 friction 详细描述
    primary_success: str                        # none / partial / full
    brief_summary: str                          # LLM 生成的 session 摘要
    extracted_at: datetime


class SessionPhase(BaseModel):
    """Session 内阶段划分 (B1)."""
    phase_name: str                     # exploration / implementation / debugging / verification
    start_index: int                    # 起始消息索引
    end_index: int                      # 结束消息索引
    tool_distribution: dict[str, int]   # 该阶段工具使用分布
    duration_seconds: int
    message_count: int


class EfficiencyScore(BaseModel):
    """Session 效率评分 (B4)."""
    session_id: str
    overall_score: float                # 0.0–1.0 综合评分
    token_efficiency: float             # output_tokens / input_tokens ratio
    tool_efficiency: float              # successful_tool_calls / total_tool_calls
    error_rate: float                   # tool_errors / total_tool_calls
    messages_per_minute: float          # 对话节奏
    model: str


class LongitudinalTrend(BaseModel):
    """纵向趋势数据点 (B2)."""
    date: str                           # ISO date
    metric_name: str                    # e.g. "avg_efficiency_score"
    metric_value: float
    sample_count: int                   # 该日期的 session 数量


class ClusterResult(BaseModel):
    """聚类分析结果 (B8)."""
    cluster_id: int
    cluster_label: str                  # 自动命名或 LLM 命名
    session_count: int
    centroid: dict[str, float]          # 特征向量质心
    session_ids: list[str]


class DashboardResult(BaseModel):
    """Dashboard 聚合数据 (A4)."""
    daily_activity: list[dict]          # [{date, messageCount, sessionCount, toolCallCount}]
    tool_distribution: list[ToolUsageStat]
    model_distribution: dict[str, int]
    project_distribution: dict[str, int]
    total_sessions: int
    total_messages: int
    total_tool_calls: int
    date_range: dict[str, str]          # {start, end}


class AnalysisJob(BaseModel):
    """异步分析任务 (Tier 3)."""
    job_id: str
    job_type: str                       # generate_facets / generate_insights
    status: str                         # pending / running / completed / failed
    progress: float                     # 0.0–1.0
    created_at: datetime
    completed_at: datetime | None = None
    result: dict | None = None
    error: str | None = None


class ExportConfig(BaseModel):
    """研究数据集导出配置 (B9)."""
    format: str = "jsonl"               # jsonl / parquet / csv
    anonymize: bool = True
    remove_code_content: bool = True    # 移除代码块内容
    remove_file_paths: bool = True      # 移除文件路径
    include_facets: bool = True
    include_efficiency: bool = True
    date_range: dict[str, str] | None = None
```

### 6.3 对已有模型的扩展

```python
# UserPreferenceResult 新增字段
class UserPreferenceResult(BaseModel):
    # ... 已有字段保持不变 ...
    efficiency_summary: EfficiencyScore | None = None       # 整体效率概览
    longitudinal_trends: list[LongitudinalTrend] = []       # 纵向趋势
    cluster_membership: ClusterResult | None = None         # 所属聚类


# AgentBehaviorResult 新增字段
class AgentBehaviorResult(BaseModel):
    # ... 已有字段保持不变 ...
    phase_distribution: dict[str, float] = {}               # 各阶段时间占比
    cross_model_ranking: dict[str, float] | None = None     # 跨模型效率排名
```

---

## 7 API Endpoints

### 7.1 Dashboard（Tier 1，同步）

| Method | Path | 说明 | Response |
|--------|------|------|----------|
| `GET` | `/api/analysis/dashboard` | 获取全局 dashboard 数据 | `DashboardResult` |
| `GET` | `/api/analysis/dashboard?source_type=local&project=MyApp` | 按数据源/项目筛选 | `DashboardResult` |

### 7.2 Per-session 分析

| Method | Path | Tier | 说明 | Response |
|--------|------|------|------|----------|
| `GET` | `/api/analysis/sessions/{id}/meta` | 1 | Session 元数据统计 | `SessionMetadata` |
| `GET` | `/api/analysis/sessions/{id}/facets` | 3 (cached) | Session facets（命中缓存直接返回，否则触发 job） | `SessionFacet \| {job_id}` |
| `GET` | `/api/analysis/sessions/{id}/phases` | 2 | Session 内阶段划分 | `list[SessionPhase]` |
| `GET` | `/api/analysis/sessions/{id}/efficiency` | 2 | Session 效率评分 | `EfficiencyScore` |

### 7.3 聚合分析

| Method | Path | Tier | 说明 | Response |
|--------|------|------|------|----------|
| `GET` | `/api/analysis/tool-usage` | 1 | 工具使用统计 | `list[ToolUsageStat]` |
| `GET` | `/api/analysis/time-patterns` | 1 | 时间模式统计 | `TimePattern` |
| `GET` | `/api/analysis/longitudinal?metric=avg_efficiency_score&days=90` | 2 | 纵向趋势 | `list[LongitudinalTrend]` |
| `GET` | `/api/analysis/clusters?k=5` | 2 | 聚类分析 | `list[ClusterResult]` |
| `GET` | `/api/analysis/user-preference` | 1+2 | 用户偏好分析（已有 stub） | `UserPreferenceResult` |
| `GET` | `/api/analysis/agent-behavior?model=claude-sonnet-4-6` | 1+2 | Agent 行为分析（已有 stub） | `AgentBehaviorResult` |

### 7.4 LLM-Powered（Tier 3，异步 Job）

| Method | Path | 说明 | Response |
|--------|------|------|----------|
| `POST` | `/api/analysis/generate-facets` | 对指定 sessions 批量提取 facets | `{job_id}` |
| `POST` | `/api/analysis/generate-insights` | 基于所有 facets 生成叙述性洞察 | `{job_id}` |
| `GET` | `/api/analysis/jobs/{id}` | 查询 job 状态和结果 | `AnalysisJob` |

**POST /api/analysis/generate-facets Request：**

```json
{
  "session_ids": ["uuid-1", "uuid-2"],
  "force_refresh": false
}
```

**POST /api/analysis/generate-insights Request：**

```json
{
  "source_type": "local",
  "project": "MyApp",
  "date_range": {
    "start": "2026-01-01",
    "end": "2026-03-13"
  }
}
```

**GET /api/analysis/jobs/{id} Response：**

```json
{
  "job_id": "job-uuid-1",
  "job_type": "generate_facets",
  "status": "running",
  "progress": 0.6,
  "created_at": "2026-03-13T10:00:00Z",
  "completed_at": null,
  "result": null,
  "error": null
}
```

### 7.5 Export

| Method | Path | 说明 | Response |
|--------|------|------|----------|
| `POST` | `/api/export/research-dataset` | 导出去标识化研究数据集 | `{job_id}`（大数据量异步）|
| `POST` | `/api/export/report` | 导出 HTML/PDF 分析报告 | `{download_url}` |

**POST /api/export/research-dataset Request：**

```json
{
  "format": "jsonl",
  "anonymize": true,
  "remove_code_content": true,
  "remove_file_paths": true,
  "include_facets": true,
  "include_efficiency": true,
  "date_range": {
    "start": "2026-01-01",
    "end": "2026-03-13"
  }
}
```

---

## 8 Database Schema

### 8.1 新增表

在现有 `sessions` + `messages` 表基础上，新增以下表：

```sql
-- Session 元数据扩展（从 stats-cache / 计算得出）
CREATE TABLE IF NOT EXISTS session_meta (
    session_id       TEXT PRIMARY KEY,
    total_input_tokens   INTEGER NOT NULL DEFAULT 0,
    total_output_tokens  INTEGER NOT NULL DEFAULT 0,
    total_cache_read     INTEGER NOT NULL DEFAULT 0,
    total_cache_write    INTEGER NOT NULL DEFAULT 0,
    tool_distribution    TEXT NOT NULL DEFAULT '{}',   -- JSON: {tool_name: count}
    language_distribution TEXT NOT NULL DEFAULT '{}',   -- JSON: {language: count}
    git_commits          INTEGER NOT NULL DEFAULT 0,
    avg_response_time    REAL NOT NULL DEFAULT 0.0,    -- 秒
    lines_added          INTEGER NOT NULL DEFAULT 0,
    lines_removed        INTEGER NOT NULL DEFAULT 0,
    computed_at          TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- LLM 提取的 Facets（Tier 3 结果缓存，对齐 usage-data/facets/ schema）
CREATE TABLE IF NOT EXISTS session_facets (
    session_id               TEXT PRIMARY KEY,
    underlying_goal          TEXT NOT NULL DEFAULT '',
    goal_categories          TEXT NOT NULL DEFAULT '{}',   -- JSON: {category: count}
    outcome                  TEXT NOT NULL DEFAULT '',
    user_satisfaction_counts TEXT NOT NULL DEFAULT '{}',    -- JSON: {label: count}
    claude_helpfulness       TEXT NOT NULL DEFAULT '',
    session_type             TEXT NOT NULL DEFAULT '',
    friction_counts          TEXT NOT NULL DEFAULT '{}',    -- JSON: {friction_type: count}
    friction_detail          TEXT NOT NULL DEFAULT '',
    primary_success          TEXT NOT NULL DEFAULT '',
    brief_summary            TEXT NOT NULL DEFAULT '',
    extracted_at             TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- 通用分析结果缓存
CREATE TABLE IF NOT EXISTS analysis_cache (
    cache_key        TEXT PRIMARY KEY,                  -- analysis_type + params_hash
    analysis_type    TEXT NOT NULL,                     -- dashboard / clusters / longitudinal / ...
    params_hash      TEXT NOT NULL,                     -- SHA256 of query params
    result           TEXT NOT NULL,                     -- JSON serialized result
    computed_at      TEXT NOT NULL,
    expires_at       TEXT                               -- TTL expiration
);

CREATE INDEX IF NOT EXISTS idx_cache_type ON analysis_cache(analysis_type);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON analysis_cache(expires_at);

-- 异步分析任务
CREATE TABLE IF NOT EXISTS analysis_jobs (
    job_id           TEXT PRIMARY KEY,
    job_type         TEXT NOT NULL,                     -- generate_facets / generate_insights / export
    status           TEXT NOT NULL DEFAULT 'pending',   -- pending / running / completed / failed
    progress         REAL NOT NULL DEFAULT 0.0,
    params           TEXT NOT NULL DEFAULT '{}',        -- JSON: job parameters
    result           TEXT,                              -- JSON: job result
    error            TEXT,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    completed_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);
```

### 8.2 现有 Schema 不变

现有 `sessions` 和 `messages` 表（`src/vibelens/db.py`）保持不变。新增表通过 `session_id` 外键关联。

---

## 9 Frontend Design

### 9.1 新增页面

| 页面 | 路径 | 说明 |
|------|------|------|
| Analysis Dashboard | `/analyze` | 全局分析仪表盘，Tier 1 统计 + 图表 |
| Session Deep-Dive | `/analyze/session/{id}` | 单 session 深度分析（phases, efficiency, facets） |
| Export | `/export` | 研究数据集导出配置 |

### 9.2 Dashboard Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  ☰ VibeLens              [Browse] [Analyze] [Export]       ⚙️       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Total       │ │ Total       │ │ Total Tool  │ │ Avg         │   │
│  │ Sessions    │ │ Messages    │ │ Calls       │ │ Efficiency  │   │
│  │    156      │ │   12,543    │ │   3,821     │ │   0.72      │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
│                                                                      │
│  ┌──────────────────────────────┐ ┌──────────────────────────────┐  │
│  │  Daily Activity              │ │  Tool Distribution           │  │
│  │  ┌────────────────────────┐  │ │  ┌────────────────────────┐  │  │
│  │  │  ▁▂▃▅▇█▇▅▃▂▁▂▃▅▇█▇▅  │  │ │  │  Read   ████████ 42%  │  │  │
│  │  │  ────────────────────  │  │ │  │  Edit   █████   28%    │  │  │
│  │  │  Feb    Mar    Apr     │  │ │  │  Bash   ████    20%    │  │  │
│  │  └────────────────────────┘  │ │  │  Grep   ██      10%   │  │  │
│  └──────────────────────────────┘ │  └────────────────────────┘  │  │
│                                    └──────────────────────────────┘  │
│  ┌──────────────────────────────┐ ┌──────────────────────────────┐  │
│  │  Activity Heatmap            │ │  Longitudinal Trend          │  │
│  │  ┌────────────────────────┐  │ │  ┌────────────────────────┐  │  │
│  │  │  Mon ░░▓▓░░░░▓▓▓░░░   │  │ │  │  efficiency ──────╱──  │  │  │
│  │  │  Tue ░░░▓▓▓░░░▓░░░░   │  │ │  │  tool_calls ─────╱──  │  │  │
│  │  │  Wed ░░▓▓▓▓░░░░▓▓░░   │  │ │  │  ────────────────────  │  │  │
│  │  │  ... 00  06  12  18    │  │ │  │  Jan    Feb    Mar     │  │  │
│  │  └────────────────────────┘  │ │  └────────────────────────┘  │  │
│  └──────────────────────────────┘ └──────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Session Clusters (k=4)                                      │   │
│  │  ┌────────────────────────────────────────────────────────┐  │   │
│  │  │    ○○○                                                  │  │   │
│  │  │   ○○○○   Quick Fixes (32 sessions)                     │  │   │
│  │  │  ○○○○○     ●●●                                         │  │   │
│  │  │              ●●●●  Deep Development (28 sessions)       │  │   │
│  │  │               ●●●●●                                     │  │   │
│  │  │    ◆◆◆            ▲▲▲                                   │  │   │
│  │  │   ◆◆◆◆  Debug     ▲▲▲▲  Learning (15 sessions)        │  │   │
│  │  │  ◆◆◆◆◆  (25 sessions)                                  │  │   │
│  │  └────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 9.3 Chart 组件

| 组件 | 类型 | 数据 |
|------|------|------|
| ActivityChart | 柱状图 (SVG) | 每日 messageCount / sessionCount |
| ToolDistribution | 水平柱状图 (SVG) | 工具调用次数占比 |
| HeatmapChart | 热力图 (SVG) | 7×24 小时活动矩阵 |
| LongitudinalChart | 折线图 (SVG) | 指标随时间变化趋势 |
| ClusterScatter | 散点图 (SVG) | PCA 降维后的聚类可视化 |
| PhaseTimeline | 时间线 (SVG) | Session 内阶段划分条形图 |

### 9.4 图表技术方案

**推荐方案：Recharts**

- 项目已在 PRODUCT_SPEC.md 中提到未来会从 Claud-ometer 借鉴 Recharts 图表
- Recharts 基于 React + D3，轻量且声明式
- 支持 responsive container、暗色主题、动画
- 备选：自定义 SVG 组件（更轻量，但开发成本更高）

---

## 10 Implementation Phases

### Phase 1: Foundation — Tier 1 Analytics + Dashboard

**目标**：实现同步统计分析 + dashboard 基础页面

| 任务 | 文件 | 说明 |
|------|------|------|
| 实现 `analyze_user_preferences()` | `analysis/user_preference.py` | 替换 stub，从 DB 查询并计算 ToolUsageStat, TimePattern |
| 实现 `analyze_agent_behavior()` | `analysis/agent_behavior.py` | 替换 stub，计算工具模式、Token 统计 |
| 新增 dashboard 聚合 | `analysis/dashboard.py` | 计算 DashboardResult |
| 新增 stats-cache ingest | `ingest/stats_cache.py` | 解析 `~/.claude/stats-cache.json` |
| 新增 session_meta 表 | `db.py` | 扩展 schema |
| 实现 dashboard API | `api/analysis.py` | 替换 stub endpoints |
| 前端 Dashboard 页面 | `frontend/src/pages/analyze.tsx` | 统计卡片 + 图表 |
| 前端图表组件 | `frontend/src/components/analysis/` | ActivityChart, ToolDistribution |

### Phase 2: Pattern Mining — Tier 2

**目标**：跨 session 聚合分析 + 时序/效率功能

| 任务 | 文件 | 说明 |
|------|------|------|
| Session 阶段检测 (B1) | `analysis/phases.py` | 基于工具使用模式变化的阶段划分算法 |
| 纵向趋势 (B2) | `analysis/longitudinal.py` | 按天/周聚合，计算趋势 |
| 效率评分 (B4) | `analysis/efficiency.py` | 多维度效率评分 |
| 代码影响分析 (B7) | `analysis/code_impact.py` | file-history 热点图 |
| todos/tasks ingest (B6) | `ingest/todos.py`, `ingest/tasks.py` | 解析 todos/tasks 目录 |
| 新增 API endpoints | `api/analysis.py` | phases, longitudinal, efficiency, clusters |
| 前端 Session Deep-Dive | `frontend/src/pages/session-analysis.tsx` | 阶段时间线 + 效率评分 |
| 前端纵向图表 | `frontend/src/components/analysis/` | LongitudinalChart, HeatmapChart |

### Phase 3: LLM-Powered — Tier 3

**目标**：接入 Claude API，实现 facet extraction 和叙述性洞察

| 任务 | 文件 | 说明 |
|------|------|------|
| Facet extraction prompt | `analysis/facets.py` | 构建 prompt，调用 Claude API，解析结构化输出 |
| Aggregated insights | `analysis/insights.py` | 基于 facets 聚合，调用 Claude 生成叙述性洞察 |
| Thinking-action analysis (B5) | `analysis/thinking_action.py` | 比较 thinking block 与后续 tool_use |
| 异步 job 系统 | `analysis/jobs.py` | 基于 analysis_jobs 表的任务调度 |
| session_facets 表 | `db.py` | 新增表 + CRUD |
| analysis_jobs 表 | `db.py` | 新增表 + CRUD |
| Job API endpoints | `api/analysis.py` | generate-facets, generate-insights, jobs/{id} |
| Executive summary (A5) | `analysis/insights.py` | LLM 生成报告首段 |

### Phase 4: Research Features

**目标**：聚类分析、跨用户框架、数据集导出

| 任务 | 文件 | 说明 |
|------|------|------|
| Session 聚类 (B8) | `analysis/clustering.py` | scikit-learn k-means + PCA 降维 |
| Cross-user framework (B3) | `analysis/cross_user.py` | 匿名化指标聚合 + 百分位排名 |
| 研究数据集导出 (B9) | `export/research_dataset.py` | 去标识化 + JSONL/Parquet 输出 |
| HTML 报告导出 | `export/report.py` | Jinja2 模板渲染 |
| Export API | `api/export.py` | research-dataset, report |
| 前端 Export 页面 | `frontend/src/pages/export.tsx` | 导出配置表单 |
| 前端聚类可视化 | `frontend/src/components/analysis/` | ClusterScatter |

---

## 11 Gap Analysis Table

| # | Insights Gap | VibeLens Feature(s) | Phase | 说明 |
|---|-------------|---------------------|-------|------|
| G1 | 无 pre/post 主观数据 | B9 (Research dataset export) + dataclaw 数据源 | 4 | 支持导入含主观标注的 dataclaw 数据集；导出时可附加外部标注 |
| G2 | 无开源数据集 | B9 (Research dataset export) | 4 | HuggingFace datasets 格式导出，去标识化，可配置 anonymization |
| G3 | 无跨用户比较 | B3 (Cross-user comparison) | 4 | 匿名化 benchmarking：将个人效率/工具使用指标与群体分布对比 |
| G4 | 无纵向/时序分析 | B2 (Longitudinal tracking) + B1 (Temporal analysis) | 2 | 学习曲线检测、工具采用趋势、效率变化追踪 |

**覆盖度**：所有 4 项 Gap 均有对应功能覆盖。其中 G4 在 Phase 2 即可实现（Tier 2 纯计算），G1/G2/G3 依赖 Phase 4 的研究基础设施。

---

## 12 Research Questions

VibeLens 分析平台可以支撑以下 HCI 研究问题：

| # | Research Question | 所需 Feature | 分析方法 |
|---|-------------------|-------------|----------|
| RQ1 | AI 编码 Agent 的工具选择策略是否随使用时间推移而演变？ | B2 (Longitudinal) | 工具分布的 Jensen-Shannon divergence 随时间变化 |
| RQ2 | 不同 LLM 模型（Opus vs Sonnet vs Haiku）在工具使用效率上是否存在显著差异？ | B4 (Efficiency) | 跨模型 efficiency score 的 ANOVA 检验 |
| RQ3 | Agent 的 thinking 内容与实际行为的一致性是否影响任务完成质量？ | B5 (Thinking-action) | thinking-action consistency 与 outcome 的相关分析 |
| RQ4 | 编程 session 中是否存在可识别的阶段转换模式（探索→实现→调试）？ | B1 (Temporal) | 隐马尔可夫模型 (HMM) 拟合阶段序列 |
| RQ5 | 用户的 AI 编码交互模式是否可以聚类为有意义的类型？ | B8 (Clustering) | k-means + 轮廓系数优化 |
| RQ6 | 代码修改频率（churn）是否与 session 中的 friction 事件相关？ | B7 (Code impact) + A2 (Facets) | file churn 与 friction_categories 的 chi-squared 检验 |
| RQ7 | 跨用户比较中，哪些行为模式与更高的任务完成率相关？ | B3 (Cross-user) + B4 (Efficiency) | 回归分析：行为特征 → outcome 预测 |
| RQ8 | 任务分解策略（DAG 深度/宽度）是否影响 Agent 协作效率？ | B6 (Task graph) + B4 (Efficiency) | DAG 结构特征与 efficiency score 的相关性 |
| RQ9 | 一天中不同时段的 AI 编码效率是否存在显著差异？ | A4 (Dashboard) + B4 (Efficiency) | 按小时分组的 efficiency score 的 Kruskal-Wallis 检验 |
| RQ10 | 开源 Agent trajectory 数据集能否用于训练更好的 Agent 行为预测模型？ | B9 (Export) | 基于导出数据训练 sequence-to-sequence 模型 |

---

## 13 Privacy & Security

### 13.1 设计原则

| 原则 | 说明 |
|------|------|
| **Local-first** | 所有分析默认在本地执行，不将原始会话数据发送到外部服务（LLM 调用除外） |
| **最小权限** | 对 `~/.claude/` 目录只读访问，不修改任何文件 |
| **可配置匿名化** | 导出时支持多级去标识化配置 |

### 13.2 Anonymization 策略

| 级别 | 移除内容 | 保留内容 | 适用场景 |
|------|----------|----------|----------|
| Level 0 (无) | — | 全部 | 个人本地分析 |
| Level 1 (轻) | 用户名、主机名 | 文件路径、代码内容、项目名 | 团队内部分享 |
| Level 2 (中) | + 文件路径、项目名 | 代码内容（hash 替换路径） | 受信研究合作 |
| Level 3 (重) | + 代码内容、消息文本 | 工具名、Token 统计、时间戳、结构元数据 | 公开数据集发布 |

### 13.3 Export 安全检查

- 导出前强制预览：显示将包含的字段列表和样本数据
- 代码内容替换为 `[CODE_BLOCK_REMOVED]` 占位符（Level 2+）
- 文件路径替换为 `project_N/file_M.ext` 格式的匿名路径（Level 2+）
- 时间戳可选偏移（随机 ±7 天）以防时间关联攻击

### 13.4 LLM 调用隐私

- Tier 3 LLM 调用发送的数据：仅消息角色、工具名称、简短摘要（非完整代码）
- Facet extraction prompt 不包含完整消息内容，仅包含结构化特征
- 用户可在设置中禁用 Tier 3 分析

---

## Appendix

### A. Glossary

| Term | Definition |
|------|-----------|
| Facet | LLM 提取的会话分类维度（goal, outcome, friction, satisfaction） |
| Tier 1 | 纯计算分析层，无 LLM 依赖，毫秒级延迟 |
| Tier 2 | 模式挖掘分析层，跨 session 聚合，秒级延迟 |
| Tier 3 | LLM 驱动分析层，异步执行，10–60s 延迟 |
| Efficiency Score | 多维度综合效率评分（Token 效率 × 工具效率 × 错误率倒数） |
| Phase Detection | 识别 session 内的阶段转换（探索→实现→调试→验证） |
| Longitudinal Analysis | 跨时间维度的趋势追踪和变化检测 |
| Anonymization | 去标识化处理，移除可识别个人信息 |
| DAG | Directed Acyclic Graph，任务依赖的有向无环图 |

### B. Related Documents

| Document | Link |
|----------|------|
| Product Specification | [docs/PRODUCT_SPEC.md](./PRODUCT_SPEC.md) |
| Technical Design | [docs/TECHNICAL_DESIGN.md](./TECHNICAL_DESIGN.md) |
| Claude Code 本地数据结构 | [docs/CLAUDE_LOCAL_STRUCTURE.md](./CLAUDE_LOCAL_STRUCTURE.md) |
| 分析模型定义 | [src/vibelens/models/analysis.py](../src/vibelens/models/analysis.py) |
| Claude Code JSONL 解析器 | [src/vibelens/ingest/claude_code.py](../src/vibelens/ingest/claude_code.py) |
| 数据库 Schema | [src/vibelens/db.py](../src/vibelens/db.py) |

# CCSM Technical Design Document

| Field | Value |
|-------|-------|
| **Document owner** | Engineering |
| **Status** | Draft |
| **Version** | v0.2 |
| **Created** | 2026-03-11 |
| **Last updated** | 2026-03-11 |

---

## 1 项目概述

Claude Code Session Manager（CCSM）是一个 **Agent Trajectory 分析与可视化平台**。它从多种数据源（本地 Claude Code JSONL、HuggingFace dataclaw 数据集、MongoDB）拉取 AI 编码 Agent 的对话历史，提供交互式会话浏览、CooperBench 风格的时间线可视化、用户工作流分析和 Agent 行为模式分析，并支持将数据推送到多个目标（MongoDB、HuggingFace）。

技术栈：Python FastAPI 后端 + React TypeScript 前端 + SQLite 本地存储（可升级 PostgreSQL）。

---

## 2 系统架构

```
┌───────────────────────────────────────────────────────────────────────┐
│                       Browser (React SPA)                             │
│                                                                       │
│  ┌───────────────┐  ┌──────────────────┐  ┌──────────────────────────┐│
│  │  Sidebar      │  │  Trajectory View │  │  Analysis Dashboard      ││
│  │  - sessions   │  │  - timeline bar  │  │  - tool usage stats      ││
│  │  - checkboxes │  │  - messages      │  │  - time patterns         ││
│  │  - search     │  │  - tool blocks   │  │  - agent comparison      ││
│  │  - source tab │  │  - thinking      │  │  - intent distribution   ││
│  └──────┬────────┘  └────────┬─────────┘  └───────────┬──────────────┘│
│         │                    │                        │               │
└─────────┼────────────────────┼────────────────────────┼───────────────┘
          │ HTTP/SSE           │ HTTP/SSE               │ HTTP
          ▼                    ▼                        ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    FastAPI Server (:12001)                            │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  Routes                                                         │  │
│  │  GET  /api/sessions                → list sessions (any source) │  │
│  │  GET  /api/sessions/stream         → SSE session updates        │  │
│  │  GET  /api/sessions/{id}           → full conversation          │  │
│  │  GET  /api/sessions/{id}/stream    → SSE message updates        │  │
│  │  GET  /api/projects                → list projects              │  │
│  │  POST /api/push/mongodb            → push to MongoDB            │  │
│  │  POST /api/push/huggingface        → push to HuggingFace        │  │
│  │  POST /api/pull/huggingface        → pull from HF dataclaw      │  │
│  │  GET  /api/analysis/user/{id}      → user preference analysis   │  │
│  │  GET  /api/analysis/agent-patterns → agent behavior patterns    │  │
│  │  GET  /api/sources                 → list configured sources     │  │
│  │  GET  /api/targets                 → list configured targets     │  │
│  │  GET  /api/settings                → server status & config      │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────┐ ┌─────────────────┐   │
│  │ sources/     │ │ targets/     │ │ analysis/│ │ storage.py      │   │
│  │  local.py    │ │  mongodb.py  │ │ user.py  │ │ (SQLite/PG)     │   │
│  │  huggingface.│ │  huggingface.│ │ agent.py │ │                 │   │
│  │  mongodb.py  │ │  (extensible)│ │ viz.py   │ │                 │   │
│  └──────┬───────┘ └──────┬───────┘ └────┬─────┘ └────────┬────────┘   │
│         │                │              │                │            │
└─────────┼────────────────┼──────────────┼────────────────┼────────────┘
          │                │              │                │
          ▼                ▼              ▼                ▼
   ┌─────────────┐  ┌──────────┐  ┌──────────┐    ┌─────────────┐
   │ ~/.claude/  │  │ MongoDB  │  │ Claude   │    │ SQLite      │
   │ projects/   │  │ Server   │  │ API      │    │ (本地存储)   │
   │ *.jsonl     │  │ (remote) │  │ (分析)    │    │             │
   └─────────────┘  └──────────┘  └──────────┘    └─────────────┘
          ▲
          │
   ┌─────────────┐
   │ HuggingFace │
   │ dataclaw    │
   │ datasets    │
   └─────────────┘
```

---

## 3 完整文件树

```
ccsm/
├── pyproject.toml                    # Python 项目配置，依赖声明 (PEP 621)
├── .env.example                      # 环境变量示例
├── README.md
│
├── ccsm/                             # Python 后端包
│   ├── __init__.py
│   ├── main.py                       # FastAPI 应用入口 + CLI (typer)
│   ├── config.py                     # 配置管理 (pydantic-settings)
│   ├── models.py                     # 统一数据模型 (Pydantic)
│   ├── db.py                         # SQLite/PostgreSQL 连接管理
│   │
│   ├── routes/                       # FastAPI 路由
│   │   ├── __init__.py
│   │   ├── sessions.py               # 会话列表 + 详情 + SSE 流
│   │   ├── push.py                   # 数据推送端点 (MongoDB, HF)
│   │   ├── pull.py                   # 数据拉取端点 (HF dataclaw)
│   │   ├── analysis.py               # 分析端点
│   │   └── settings.py               # 配置状态端点
│   │
│   ├── sources/                      # 数据源适配器 (Pull)
│   │   ├── __init__.py               # DataSource 协议定义
│   │   ├── local.py                  # 本地 Claude Code JSONL 读取
│   │   ├── huggingface.py            # HuggingFace dataclaw 拉取
│   │   └── mongodb.py                # MongoDB 远程查询
│   │
│   ├── targets/                      # 数据目标适配器 (Push)
│   │   ├── __init__.py               # DataTarget 协议定义
│   │   ├── mongodb.py                # MongoDB 写入
│   │   └── huggingface.py            # HuggingFace 发布
│   │
│   ├── analysis/                     # 分析引擎
│   │   ├── __init__.py
│   │   ├── user_preference.py        # 用户偏好分析
│   │   ├── agent_behavior.py         # Agent 行为模式分析
│   │   └── intent.py                 # LLM 驱动的意图分类
│   │
│   ├── ingest/                       # 数据格式转换
│   │   ├── __init__.py
│   │   ├── normalizer.py             # 多格式 → 统一模型转换
│   │   ├── claude_code.py            # Claude Code JSONL 解析
│   │   └── dataclaw.py               # dataclaw JSONL 解析
│   │
│   └── watcher.py                    # 本地文件监听 (watchfiles)
│
├── web/                              # React 前端
│   ├── index.html
│   ├── index.css                     # Tailwind + dark theme
│   ├── main.tsx                      # React DOM 入口
│   ├── app.tsx                       # 根组件：状态管理 + 布局
│   ├── types.ts                      # TypeScript 类型定义（对齐后端 models.py）
│   ├── utils.ts                      # formatTime, sanitizeText
│   ├── tsconfig.json
│   ├── vite.config.ts                # Vite + proxy + Tailwind
│   │
│   ├── hooks/
│   │   ├── use-event-source.ts       # SSE 连接 hook (指数退避重连)
│   │   └── use-api.ts                # REST API 请求 hook
│   │
│   ├── components/
│   │   ├── session-list.tsx          # 虚拟滚动列表 + checkbox + 搜索
│   │   ├── session-view.tsx          # 对话 trajectory 视图
│   │   ├── timeline-bar.tsx          # CooperBench 风格时间线条
│   │   ├── message-block.tsx         # 消息渲染（tool blocks + thinking）
│   │   ├── markdown-renderer.tsx     # Markdown + 语法高亮
│   │   ├── scroll-to-bottom.tsx      # 浮动滚动按钮
│   │   ├── data-source-panel.tsx     # 数据源切换面板 (Local/HF/MongoDB)
│   │   ├── push-toolbar.tsx          # 推送工具栏（目标选择 + 上传）
│   │   ├── push-dialog.tsx           # 推送确认弹窗
│   │   ├── analysis-dashboard.tsx    # 分析仪表盘容器
│   │   ├── toast.tsx                 # Toast 通知
│   │   │
│   │   ├── analysis/                 # 分析可视化组件
│   │   │   ├── tool-usage-chart.tsx  # 工具使用分布图
│   │   │   ├── time-pattern.tsx      # 时间模式热力图
│   │   │   ├── intent-dist.tsx       # 意图分类分布
│   │   │   └── token-efficiency.tsx  # Token 效率对比
│   │   │
│   │   └── tool-renderers/           # 工具调用渲染器
│   │       ├── index.ts
│   │       ├── bash-renderer.tsx
│   │       ├── edit-renderer.tsx
│   │       ├── read-renderer.tsx
│   │       ├── search-renderer.tsx
│   │       ├── todo-renderer.tsx
│   │       ├── task-renderer.tsx
│   │       ├── ask-question-renderer.tsx
│   │       └── copy-button.tsx
│   │
│   └── pages/                        # 页面级组件
│       ├── browse.tsx                # 默认：会话浏览页
│       └── analyze.tsx               # 分析仪表盘页
│
├── tests/                            # 测试
│   ├── test_sources.py
│   ├── test_targets.py
│   ├── test_normalizer.py
│   └── test_analysis.py
│
└── docker-compose.yml                # Phase 2: 多服务部署
```

---

## 4 统一数据模型

CCSM 的核心是一个统一数据模型，能够表示来自不同源（Claude Code JSONL、dataclaw、MongoDB）的 Agent 对话数据。

### 4.1 Pydantic 模型定义（`ccsm/models.py`）

```python
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class DataSourceType(str, Enum):
    LOCAL = "local"
    HUGGINGFACE = "huggingface"
    MONGODB = "mongodb"


class DataTargetType(str, Enum):
    MONGODB = "mongodb"
    HUGGINGFACE = "huggingface"


class ToolCall(BaseModel):
    """单次工具调用记录。"""
    id: str = ""
    name: str
    input: dict | str | None = None
    output: str | None = None
    is_error: bool = False


class TokenUsage(BaseModel):
    """Token 用量统计。"""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class ContentBlock(BaseModel):
    """Claude API 内容块。"""
    type: str                                   # "text" | "thinking" | "tool_use" | "tool_result"
    text: str | None = None
    thinking: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict | str | None = None
    tool_use_id: str | None = None
    content: str | list | None = None
    is_error: bool | None = None


class Message(BaseModel):
    """统一消息模型，兼容所有数据源。"""
    uuid: str
    session_id: str
    parent_uuid: str = ""
    role: str                                   # "user" | "assistant" | "system"
    type: str                                   # "user" | "assistant" | "summary" | "tool_result"
    content: str | list[ContentBlock] = ""
    thinking: str | None = None                 # dataclaw 格式的 thinking 字段
    model: str = ""
    timestamp: datetime | None = None
    is_sidechain: bool = False
    usage: TokenUsage | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class SessionSummary(BaseModel):
    """会话摘要，用于列表展示。"""
    session_id: str
    project_id: str = ""
    project_name: str = ""
    timestamp: datetime | None = None
    duration: int = 0                           # 秒
    message_count: int = 0
    tool_call_count: int = 0
    models: list[str] = Field(default_factory=list)
    first_message: str = ""
    source_type: DataSourceType = DataSourceType.LOCAL
    source_name: str = ""                       # e.g. "peteromallet/dataclaw-data"
    source_host: str = ""                       # 上传来源主机名


class SessionDetail(BaseModel):
    """会话完整数据，包含所有消息。"""
    summary: SessionSummary
    messages: list[Message]


class SessionMetadata(BaseModel):
    """从消息列表中提取的聚合元数据。"""
    message_count: int = 0
    tool_call_count: int = 0
    models: list[str] = Field(default_factory=list)
    first_message: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    duration: int = 0


# ─── Push/Pull request/response types ───
class PushRequest(BaseModel):
    """推送请求。"""
    session_ids: list[str]
    target: DataTargetType


class PushResult(BaseModel):
    """推送结果。"""
    total: int
    uploaded: int
    skipped: int
    errors: list[dict] = Field(default_factory=list)


class PullRequest(BaseModel):
    """HuggingFace 数据拉取请求。"""
    repo_id: str                                # e.g. "peteromallet/my-personal-codex-data"
    force_refresh: bool = False


class PullResult(BaseModel):
    """拉取结果。"""
    repo_id: str
    sessions_imported: int
    messages_imported: int
    skipped: int


class RemoteSessionsQuery(BaseModel):
    """远程会话查询参数。"""
    project_id: str | None = None
    source_type: DataSourceType | None = None
    limit: int = 100
    offset: int = 0


# ─── Analysis result types ───
class ToolUsageStat(BaseModel):
    """工具使用统计。"""
    tool_name: str
    call_count: int
    avg_per_session: float
    error_rate: float


class TimePattern(BaseModel):
    """时间模式统计。"""
    hour_distribution: dict[int, int]           # hour -> session_count
    weekday_distribution: dict[int, int]        # 0=Mon -> session_count
    avg_session_duration: float                 # 秒
    avg_messages_per_session: float


class UserPreferenceResult(BaseModel):
    """用户偏好分析结果。"""
    source_name: str
    session_count: int
    tool_usage: list[ToolUsageStat]
    time_pattern: TimePattern
    model_distribution: dict[str, int]
    project_distribution: dict[str, int]
    top_tool_sequences: list[list[str]]         # 常见工具调用序列


class AgentBehaviorResult(BaseModel):
    """Agent 行为模式分析结果。"""
    model: str
    session_count: int
    avg_tool_calls_per_session: float
    avg_tokens_per_session: float
    tool_selection_variability: float           # 0-1, 越高越不稳定
    common_tool_patterns: list[dict]
    thinking_action_consistency: float | None   # 0-1, None if no thinking data
```

### 4.2 TypeScript 类型定义（`web/types.ts`）

```typescript
// 与后端 models.py 对齐
export type DataSourceType = "local" | "huggingface" | "mongodb";
export type DataTargetType = "mongodb" | "huggingface";

export interface ToolCall {
  id: string;
  name: string;
  input: unknown;
  output?: string;
  is_error: boolean;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
}

export interface ContentBlock {
  type: "text" | "thinking" | "tool_use" | "tool_result";
  text?: string;
  thinking?: string;
  id?: string;
  name?: string;
  input?: unknown;
  tool_use_id?: string;
  content?: string | ContentBlock[];
  is_error?: boolean;
}

export interface Message {
  uuid: string;
  session_id: string;
  parent_uuid: string;
  role: "user" | "assistant" | "system";
  type: string;
  content: string | ContentBlock[];
  thinking?: string;
  model: string;
  timestamp: string;
  is_sidechain: boolean;
  usage?: TokenUsage;
  tool_calls: ToolCall[];
}

export interface SessionSummary {
  session_id: string;
  project_id: string;
  project_name: string;
  timestamp: string;
  duration: number;
  message_count: number;
  tool_call_count: number;
  models: string[];
  first_message: string;
  source_type: DataSourceType;
  source_name: string;
  source_host: string;
}

export interface SessionDetail {
  summary: SessionSummary;
  messages: Message[];
}

export interface PushRequest {
  session_ids: string[];
  target: DataTargetType;
}

export interface PushResult {
  total: number;
  uploaded: number;
  skipped: number;
  errors: Array<{ session_id: string; error: string }>;
}

export interface PullRequest {
  repo_id: string;
  force_refresh: boolean;
}

export interface PullResult {
  repo_id: string;
  sessions_imported: number;
  messages_imported: number;
  skipped: number;
}

// Analysis types
export interface ToolUsageStat {
  tool_name: string;
  call_count: number;
  avg_per_session: number;
  error_rate: number;
}

export interface TimePattern {
  hour_distribution: Record<number, number>;
  weekday_distribution: Record<number, number>;
  avg_session_duration: number;
  avg_messages_per_session: number;
}

export interface UserPreferenceResult {
  source_name: string;
  session_count: number;
  tool_usage: ToolUsageStat[];
  time_pattern: TimePattern;
  model_distribution: Record<string, number>;
  project_distribution: Record<string, number>;
  top_tool_sequences: string[][];
}

// Timeline visualization types
export interface TimelineStep {
  index: number;
  timestamp: number;
  tool_type: ToolType;
  tool_name: string;
  agent_id: string;
  duration_ms: number;
}

export type ToolType =
  | "bash"
  | "edit"
  | "read"
  | "search"
  | "communication"
  | "task"
  | "think"
  | "other";

export const TOOL_TYPE_COLORS: Record<ToolType, string> = {
  bash: "bg-yellow-400",
  edit: "bg-green-500",
  read: "bg-blue-600",
  search: "bg-sky-300",
  communication: "bg-orange-400",
  task: "bg-purple-400",
  think: "bg-gray-400",
  other: "bg-gray-300",
};
```

---

## 5 模块设计

### 5.1 数据源协议（`ccsm/sources/__init__.py`）

```python
from typing import Protocol, AsyncIterator
from ccsm.models import SessionSummary, SessionDetail, Message, RemoteSessionsQuery


class DataSource(Protocol):
    """数据源适配器协议。所有数据源必须实现此接口。"""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        ...

    @property
    def display_name(self) -> str:
        """用于 UI 展示的数据源名称。"""
        ...

    async def list_sessions(self, query: RemoteSessionsQuery) -> list[SessionSummary]:
        """返回会话摘要列表，支持过滤和分页。"""
        ...

    async def get_session(self, session_id: str) -> SessionDetail | None:
        """返回单个会话的完整数据（含所有消息）。"""
        ...

    async def list_projects(self) -> list[str]:
        """返回所有项目名称列表。"""
        ...

    def supports_streaming(self) -> bool:
        """是否支持 SSE 实时流式推送。"""
        ...

    async def stream_messages(
        self, session_id: str, offset: int = 0
    ) -> AsyncIterator[list[Message]]:
        """SSE 流式推送消息增量。仅 local 源支持。"""
        ...
```

### 5.2 本地数据源（`ccsm/sources/local.py`）

```python
import json
from pathlib import Path
from datetime import datetime
from ccsm.models import (
    SessionSummary, SessionDetail, Message, ContentBlock,
    TokenUsage, ToolCall, SessionMetadata, DataSourceType,
    RemoteSessionsQuery,
)

HISTORY_FILE = "history.jsonl"
PROJECTS_DIR = "projects"


class LocalClaudeCodeSource:
    """从本地 ~/.claude/ 读取 Claude Code 会话数据。"""

    def __init__(self, claude_dir: Path):
        self._claude_dir = claude_dir
        self._history_cache: list[dict] | None = None
        self._file_index: dict[str, Path] = {}

    @property
    def source_type(self) -> str:
        return DataSourceType.LOCAL

    @property
    def display_name(self) -> str:
        return f"Local ({self._claude_dir})"

    def supports_streaming(self) -> bool:
        return True

    async def list_sessions(self, query: RemoteSessionsQuery) -> list[SessionSummary]:
        """扫描 history.jsonl + projects/ 目录，合并去重。"""
        self._build_file_index()
        history = self._load_history_cache()
        sessions: dict[str, SessionSummary] = {}

        for entry in history:
            sid = entry.get("sessionId", "")
            if not sid:
                continue
            if query.project_id and entry.get("project", "") != query.project_id:
                continue
            sessions[sid] = SessionSummary(
                session_id=sid,
                project_id=entry.get("project", ""),
                project_name=self._extract_project_name(entry.get("project", "")),
                timestamp=datetime.fromtimestamp(entry.get("timestamp", 0)),
                first_message=entry.get("display", ""),
                source_type=DataSourceType.LOCAL,
            )

        sorted_sessions = sorted(
            sessions.values(), key=lambda s: s.timestamp or datetime.min, reverse=True
        )
        return sorted_sessions[query.offset : query.offset + query.limit]

    async def get_session(self, session_id: str) -> SessionDetail | None:
        """读取完整的 JSONL 文件并解析所有消息。"""
        file_path = self._find_session_file(session_id)
        if not file_path or not file_path.exists():
            return None

        entries = self._parse_jsonl(file_path)
        messages = self._entries_to_messages(entries, session_id)
        metadata = self._extract_metadata(messages)

        summary = SessionSummary(
            session_id=session_id,
            message_count=metadata.message_count,
            tool_call_count=metadata.tool_call_count,
            models=metadata.models,
            first_message=metadata.first_message,
            duration=metadata.duration,
            source_type=DataSourceType.LOCAL,
        )
        return SessionDetail(summary=summary, messages=messages)

    def _build_file_index(self) -> None:
        """扫描 projects/ 目录构建 sessionId → 文件路径映射。"""
        projects_dir = self._claude_dir / PROJECTS_DIR
        if not projects_dir.exists():
            return
        for jsonl_file in projects_dir.rglob("*.jsonl"):
            session_id = jsonl_file.stem
            self._file_index[session_id] = jsonl_file

    def _find_session_file(self, session_id: str) -> Path | None:
        if not self._file_index:
            self._build_file_index()
        return self._file_index.get(session_id)

    def _load_history_cache(self) -> list[dict]:
        if self._history_cache is not None:
            return self._history_cache
        history_path = self._claude_dir / HISTORY_FILE
        if not history_path.exists():
            self._history_cache = []
            return self._history_cache
        entries = []
        for line in history_path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._history_cache = entries
        return self._history_cache

    def invalidate_cache(self) -> None:
        self._history_cache = None

    @staticmethod
    def _parse_jsonl(file_path: Path) -> list[dict]:
        entries = []
        for line in file_path.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    @staticmethod
    def _entries_to_messages(entries: list[dict], session_id: str) -> list[Message]:
        """将 Claude Code JSONL entries 转换为统一 Message 模型。"""
        messages: list[Message] = []
        for idx, entry in enumerate(entries):
            entry_type = entry.get("type", "")
            if entry_type not in ("user", "assistant", "summary"):
                continue

            msg_data = entry.get("message", {})
            content_raw = msg_data.get("content", entry.get("summary", ""))
            tool_calls: list[ToolCall] = []

            if isinstance(content_raw, list):
                for block in content_raw:
                    if block.get("type") == "tool_use":
                        tool_calls.append(ToolCall(
                            id=block.get("id", ""),
                            name=block.get("name", ""),
                            input=block.get("input"),
                        ))

            usage_raw = msg_data.get("usage")
            usage = None
            if usage_raw:
                usage = TokenUsage(
                    input_tokens=usage_raw.get("input_tokens", 0),
                    output_tokens=usage_raw.get("output_tokens", 0),
                    cache_creation_tokens=usage_raw.get("cache_creation_input_tokens", 0),
                    cache_read_tokens=usage_raw.get("cache_read_input_tokens", 0),
                )

            messages.append(Message(
                uuid=entry.get("uuid", f"{session_id}-{idx}"),
                session_id=session_id,
                parent_uuid=entry.get("parentUuid", ""),
                role=msg_data.get("role", entry_type),
                type=entry_type,
                content=content_raw,
                model=msg_data.get("model", ""),
                timestamp=entry.get("timestamp"),
                usage=usage,
                tool_calls=tool_calls,
            ))
        return messages

    @staticmethod
    def _extract_metadata(messages: list[Message]) -> SessionMetadata:
        """从消息列表中提取聚合元数据。"""
        models: set[str] = set()
        first_message = ""
        total_input = total_output = total_cache_read = total_cache_write = 0
        tool_call_count = 0
        timestamps: list[float] = []

        for msg in messages:
            if msg.timestamp:
                ts = msg.timestamp.timestamp() if isinstance(msg.timestamp, datetime) else 0
                if ts > 0:
                    timestamps.append(ts)
            if msg.role == "user" and not first_message:
                if isinstance(msg.content, str):
                    first_message = msg.content[:100]
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if hasattr(block, "text") and block.text:
                            first_message = block.text[:100]
                            break
            if msg.model:
                models.add(msg.model)
            if msg.usage:
                total_input += msg.usage.input_tokens
                total_output += msg.usage.output_tokens
                total_cache_read += msg.usage.cache_read_tokens
                total_cache_write += msg.usage.cache_creation_tokens
            tool_call_count += len(msg.tool_calls)

        duration = int(max(timestamps) - min(timestamps)) if len(timestamps) >= 2 else 0

        return SessionMetadata(
            message_count=len(messages),
            tool_call_count=tool_call_count,
            models=sorted(models),
            first_message=first_message,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cache_read=total_cache_read,
            total_cache_write=total_cache_write,
            duration=duration,
        )

    @staticmethod
    def _extract_project_name(project_id: str) -> str:
        return project_id.rsplit("-", 1)[-1] if project_id else ""
```

### 5.3 HuggingFace 数据源（`ccsm/sources/huggingface.py`）

```python
from huggingface_hub import HfApi, hf_hub_download
from ccsm.models import (
    SessionSummary, SessionDetail, DataSourceType, RemoteSessionsQuery,
)
from ccsm.ingest.dataclaw import DataclawParser


class HuggingFaceSource:
    """从 HuggingFace dataclaw 数据集拉取会话数据。"""

    def __init__(self, db):
        self._api = HfApi()
        self._parser = DataclawParser()
        self._db = db

    @property
    def source_type(self) -> str:
        return DataSourceType.HUGGINGFACE

    @property
    def display_name(self) -> str:
        return "HuggingFace (dataclaw)"

    def supports_streaming(self) -> bool:
        return False

    async def discover_repos(self) -> list[str]:
        """发现所有带 dataclaw tag 的数据集。"""
        datasets = self._api.list_datasets(tags="dataclaw")
        return [ds.id for ds in datasets]

    async def pull_repo(self, repo_id: str, force_refresh: bool = False) -> dict:
        """下载并导入指定数据集到本地 DB。"""
        path = hf_hub_download(
            repo_id=repo_id,
            filename="conversations.jsonl",
            repo_type="dataset",
        )
        sessions = self._parser.parse_file(path)
        imported = skipped = 0

        for session in sessions:
            session.summary.source_type = DataSourceType.HUGGINGFACE
            session.summary.source_name = repo_id
            existed = await self._db.session_exists(session.summary.session_id)
            if existed and not force_refresh:
                skipped += 1
                continue
            await self._db.upsert_session(session)
            imported += 1

        return {"sessions_imported": imported, "skipped": skipped}

    async def list_sessions(self, query: RemoteSessionsQuery) -> list[SessionSummary]:
        """从本地 DB 中查询已导入的 HF 会话。"""
        return await self._db.list_sessions(
            source_type=DataSourceType.HUGGINGFACE, query=query
        )

    async def get_session(self, session_id: str) -> SessionDetail | None:
        return await self._db.get_session(session_id)
```

### 5.4 dataclaw 格式解析器（`ccsm/ingest/dataclaw.py`）

```python
import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from ccsm.models import (
    SessionDetail, SessionSummary, Message, ToolCall,
    TokenUsage, DataSourceType,
)

MAX_FIRST_MESSAGE_LENGTH = 100


class DataclawParser:
    """解析 dataclaw 的 conversations.jsonl 格式。

    dataclaw 格式每行一个完整 session:
    {
      "session_id": "...",
      "project": "...",
      "model": "...",
      "git_branch": "...",
      "start_time": "2026-01-15T10:30:00Z",
      "end_time": "2026-01-15T11:30:00Z",
      "messages": [
        {
          "role": "user" | "assistant",
          "content": "...",
          "thinking": "...",
          "tool_uses": [{"name": "Bash", "input": "..."}],
          "timestamp": "..."
        }
      ],
      "stats": { "user_messages": 5, "assistant_messages": 5, ... }
    }
    """

    def parse_file(self, file_path: str | Path) -> list[SessionDetail]:
        sessions: list[SessionDetail] = []
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    session = self._parse_session(raw)
                    if session:
                        sessions.append(session)
                except json.JSONDecodeError:
                    continue
        return sessions

    def _parse_session(self, raw: dict) -> SessionDetail | None:
        session_id = raw.get("session_id", "")
        if not session_id:
            return None

        raw_messages = raw.get("messages", [])
        messages: list[Message] = []
        tool_call_count = 0
        first_message = ""

        for idx, msg_raw in enumerate(raw_messages):
            tool_calls: list[ToolCall] = []
            for tu in msg_raw.get("tool_uses", []):
                tool_calls.append(ToolCall(
                    id=str(uuid4())[:8],
                    name=tu.get("name", ""),
                    input=tu.get("input", ""),
                ))
                tool_call_count += 1

            role = msg_raw.get("role", "user")
            content = msg_raw.get("content", "")

            if role == "user" and not first_message and content:
                first_message = content[:MAX_FIRST_MESSAGE_LENGTH]

            messages.append(Message(
                uuid=f"{session_id}-{idx}",
                session_id=session_id,
                role=role,
                type=role,
                content=content,
                thinking=msg_raw.get("thinking"),
                model=raw.get("model", ""),
                timestamp=msg_raw.get("timestamp"),
                tool_calls=tool_calls,
            ))

        stats = raw.get("stats", {})
        start_time = raw.get("start_time")
        end_time = raw.get("end_time")
        duration = 0
        if start_time and end_time:
            try:
                dt_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                dt_end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                duration = int((dt_end - dt_start).total_seconds())
            except (ValueError, TypeError):
                pass

        summary = SessionSummary(
            session_id=session_id,
            project_name=raw.get("project", ""),
            timestamp=start_time,
            duration=duration,
            message_count=stats.get("user_messages", 0) + stats.get("assistant_messages", 0),
            tool_call_count=tool_call_count,
            models=[raw["model"]] if raw.get("model") else [],
            first_message=first_message,
            source_type=DataSourceType.HUGGINGFACE,
        )

        return SessionDetail(summary=summary, messages=messages)
```

### 5.5 数据目标协议（`ccsm/targets/__init__.py`）

```python
from typing import Protocol
from ccsm.models import SessionDetail, PushResult


class DataTarget(Protocol):
    """数据推送目标适配器协议。"""

    @property
    def target_type(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    async def is_connected(self) -> bool: ...

    async def push_sessions(self, sessions: list[SessionDetail]) -> PushResult: ...
```

### 5.6 MongoDB 目标（`ccsm/targets/mongodb.py`）

```python
from motor.motor_asyncio import AsyncIOMotorClient
from ccsm.models import SessionDetail, PushResult, DataTargetType
import os

BATCH_SIZE = 500


class MongoDBTarget:
    """将会话数据推送到 MongoDB。"""

    def __init__(self, uri: str = "", db_name: str = "ccsm"):
        self._uri = uri or os.getenv("MONGODB_URI", "")
        self._db_name = db_name
        self._client: AsyncIOMotorClient | None = None

    @property
    def target_type(self) -> str:
        return DataTargetType.MONGODB

    @property
    def display_name(self) -> str:
        return f"MongoDB ({self._db_name})"

    async def connect(self) -> None:
        if not self._uri:
            return
        self._client = AsyncIOMotorClient(
            self._uri,
            maxPoolSize=10,
            serverSelectionTimeoutMS=5000,
        )
        db = self._client[self._db_name]
        self._sessions_col = db["sessions"]
        self._messages_col = db["messages"]
        await self._ensure_indexes()

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    async def is_connected(self) -> bool:
        if not self._client:
            return False
        try:
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False

    async def _ensure_indexes(self) -> None:
        await self._sessions_col.create_index("sessionId", unique=True)
        await self._sessions_col.create_index([("projectId", 1), ("timestamp", -1)])
        await self._sessions_col.create_index([("timestamp", -1)])
        await self._messages_col.create_index("uuid", unique=True)
        await self._messages_col.create_index([("sessionId", 1), ("timestamp", 1)])

    async def push_sessions(self, sessions: list[SessionDetail]) -> PushResult:
        """将会话批量 upsert 到 MongoDB。"""
        result = PushResult(total=len(sessions), uploaded=0, skipped=0)
        host = os.uname().nodename

        for detail in sessions:
            try:
                s = detail.summary
                session_doc = {
                    "sessionId": s.session_id,
                    "projectId": s.project_id,
                    "projectName": s.project_name,
                    "timestamp": s.timestamp,
                    "duration": s.duration,
                    "messageCount": s.message_count,
                    "toolCallCount": s.tool_call_count,
                    "models": s.models,
                    "firstMessage": s.first_message,
                    "sourceHost": host,
                    "sourceType": s.source_type,
                    "sourceName": s.source_name,
                }
                await self._sessions_col.update_one(
                    {"sessionId": s.session_id},
                    {"$set": session_doc},
                    upsert=True,
                )

                msg_ops = []
                for msg in detail.messages:
                    msg_doc = {
                        "uuid": msg.uuid,
                        "sessionId": msg.session_id,
                        "parentUuid": msg.parent_uuid,
                        "role": msg.role,
                        "type": msg.type,
                        "content": msg.content if isinstance(msg.content, str)
                            else [b.model_dump() for b in msg.content],
                        "model": msg.model,
                        "timestamp": msg.timestamp,
                        "toolCalls": [tc.model_dump() for tc in msg.tool_calls],
                        "usage": msg.usage.model_dump() if msg.usage else None,
                    }
                    msg_ops.append(
                        {"updateOne": {
                            "filter": {"uuid": msg.uuid},
                            "update": {"$set": msg_doc},
                            "upsert": True,
                        }}
                    )

                for i in range(0, len(msg_ops), BATCH_SIZE):
                    batch = msg_ops[i : i + BATCH_SIZE]
                    await self._messages_col.bulk_write(
                        [self._to_pymongo_op(op) for op in batch], ordered=False
                    )

                result.uploaded += 1
            except Exception as e:
                result.errors.append({
                    "session_id": detail.summary.session_id,
                    "error": str(e),
                })

        return result

    @staticmethod
    def _to_pymongo_op(op: dict):
        from pymongo import UpdateOne
        inner = op["updateOne"]
        return UpdateOne(inner["filter"], inner["update"], upsert=inner["upsert"])
```

### 5.7 HuggingFace 目标（`ccsm/targets/huggingface.py`）

```python
import json
import tempfile
from pathlib import Path
from huggingface_hub import HfApi
from ccsm.models import SessionDetail, PushResult, DataTargetType


class HuggingFaceTarget:
    """将会话数据以 dataclaw 格式推送到 HuggingFace。"""

    def __init__(self, token: str = "", repo_id: str = ""):
        self._api = HfApi(token=token) if token else HfApi()
        self._repo_id = repo_id

    @property
    def target_type(self) -> str:
        return DataTargetType.HUGGINGFACE

    @property
    def display_name(self) -> str:
        return f"HuggingFace ({self._repo_id})"

    async def is_connected(self) -> bool:
        try:
            self._api.whoami()
            return True
        except Exception:
            return False

    async def push_sessions(self, sessions: list[SessionDetail]) -> PushResult:
        """将会话转换为 dataclaw JSONL 格式并上传到 HuggingFace。"""
        result = PushResult(total=len(sessions), uploaded=0, skipped=0)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            for detail in sessions:
                try:
                    dataclaw_obj = self._to_dataclaw_format(detail)
                    f.write(json.dumps(dataclaw_obj) + "\n")
                    result.uploaded += 1
                except Exception as e:
                    result.errors.append({
                        "session_id": detail.summary.session_id,
                        "error": str(e),
                    })
            tmp_path = f.name

        if result.uploaded > 0:
            self._api.upload_file(
                path_or_fileobj=tmp_path,
                path_in_repo="conversations.jsonl",
                repo_id=self._repo_id,
                repo_type="dataset",
            )

        Path(tmp_path).unlink(missing_ok=True)
        return result

    @staticmethod
    def _to_dataclaw_format(detail: SessionDetail) -> dict:
        """将统一模型转换为 dataclaw 格式。"""
        s = detail.summary
        dataclaw_messages = []
        for msg in detail.messages:
            dm = {
                "role": msg.role,
                "content": msg.content if isinstance(msg.content, str) else "",
                "timestamp": str(msg.timestamp) if msg.timestamp else "",
            }
            if msg.thinking:
                dm["thinking"] = msg.thinking
            if msg.tool_calls:
                dm["tool_uses"] = [
                    {"name": tc.name, "input": str(tc.input) if tc.input else ""}
                    for tc in msg.tool_calls
                ]
            dataclaw_messages.append(dm)

        return {
            "session_id": s.session_id,
            "project": s.project_name,
            "model": s.models[0] if s.models else "",
            "start_time": str(s.timestamp) if s.timestamp else "",
            "messages": dataclaw_messages,
            "stats": {
                "user_messages": sum(1 for m in detail.messages if m.role == "user"),
                "assistant_messages": sum(1 for m in detail.messages if m.role == "assistant"),
            },
        }
```

### 5.8 文件监听器（`ccsm/watcher.py`）

```python
import asyncio
from pathlib import Path
from typing import Callable
from watchfiles import awatch, Change

DEBOUNCE_MS = 20


class FileWatcher:
    """监听本地 Claude Code 文件变化，触发回调。"""

    def __init__(self, claude_dir: Path):
        self._claude_dir = claude_dir
        self._history_callbacks: list[Callable] = []
        self._session_callbacks: list[Callable[[str, Path], None]] = []
        self._task: asyncio.Task | None = None

    def on_history_change(self, callback: Callable) -> None:
        self._history_callbacks.append(callback)

    def on_session_change(self, callback: Callable[[str, Path], None]) -> None:
        self._session_callbacks.append(callback)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._watch())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch(self) -> None:
        watch_paths = [
            str(self._claude_dir / "history.jsonl"),
            str(self._claude_dir / "projects"),
        ]
        async for changes in awatch(*watch_paths, debounce=DEBOUNCE_MS):
            for change_type, path_str in changes:
                if change_type not in (Change.modified, Change.added):
                    continue
                path = Path(path_str)
                if path.name == "history.jsonl":
                    for cb in self._history_callbacks:
                        cb()
                elif path.suffix == ".jsonl":
                    session_id = path.stem
                    for cb in self._session_callbacks:
                        cb(session_id, path)
```

### 5.9 FastAPI 应用入口（`ccsm/main.py`）

```python
import typer
import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from ccsm.config import Settings
from ccsm.sources.local import LocalClaudeCodeSource
from ccsm.sources.huggingface import HuggingFaceSource
from ccsm.targets.mongodb import MongoDBTarget
from ccsm.targets.huggingface import HuggingFaceTarget
from ccsm.watcher import FileWatcher
from ccsm.db import Database
from ccsm.routes import sessions, push, pull, analysis, settings as settings_route

cli = typer.Typer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的资源管理。"""
    cfg: Settings = app.state.settings

    # 初始化数据库
    db = Database(cfg.database_url)
    await db.connect()
    app.state.db = db

    # 初始化数据源
    local_source = LocalClaudeCodeSource(Path(cfg.claude_dir))
    hf_source = HuggingFaceSource(db)
    app.state.sources = {
        "local": local_source,
        "huggingface": hf_source,
    }

    # 初始化数据目标
    mongodb_target = MongoDBTarget(uri=cfg.mongodb_uri, db_name=cfg.db_name)
    if cfg.mongodb_uri:
        await mongodb_target.connect()
    hf_target = HuggingFaceTarget(
        token=cfg.hf_token, repo_id=cfg.hf_repo_id
    )
    app.state.targets = {
        "mongodb": mongodb_target,
        "huggingface": hf_target,
    }

    # 启动文件监听
    watcher = FileWatcher(Path(cfg.claude_dir))
    watcher.on_history_change(local_source.invalidate_cache)
    await watcher.start()
    app.state.watcher = watcher

    yield

    # 清理
    await watcher.stop()
    await mongodb_target.disconnect()
    await db.disconnect()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    app = FastAPI(title="CCSM", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings

    app.include_router(sessions.router, prefix="/api")
    app.include_router(push.router, prefix="/api")
    app.include_router(pull.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(settings_route.router, prefix="/api")

    # 静态文件（构建后的前端）
    web_dist = Path(__file__).parent.parent / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True))

    return app


@cli.command()
def serve(
    port: int = typer.Option(12001, "--port", "-p", help="Server port"),
    claude_dir: str = typer.Option("~/.claude", "--dir", "-d", help="Claude directory"),
    mongodb_uri: str = typer.Option("", "--mongodb-uri", envvar="MONGODB_URI"),
    db_name: str = typer.Option("ccsm", "--db-name", envvar="DB_NAME"),
    database_url: str = typer.Option(
        "sqlite+aiosqlite:///ccsm.db", "--database-url", envvar="DATABASE_URL"
    ),
    hf_token: str = typer.Option("", "--hf-token", envvar="HF_TOKEN"),
    hf_repo_id: str = typer.Option("", "--hf-repo-id", envvar="HF_REPO_ID"),
    dev: bool = typer.Option(False, "--dev", help="Enable CORS"),
):
    """启动 CCSM 服务器。"""
    settings = Settings(
        port=port,
        claude_dir=str(Path(claude_dir).expanduser()),
        mongodb_uri=mongodb_uri,
        db_name=db_name,
        database_url=database_url,
        hf_token=hf_token,
        hf_repo_id=hf_repo_id,
        dev=dev,
    )
    app = create_app(settings)

    if dev:
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    cli()
```

### 5.10 配置管理（`ccsm/config.py`）

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，支持环境变量和 CLI 参数。"""
    port: int = 12001
    claude_dir: str = "~/.claude"
    mongodb_uri: str = ""
    db_name: str = "ccsm"
    database_url: str = "sqlite+aiosqlite:///ccsm.db"
    hf_token: str = ""
    hf_repo_id: str = ""
    dev: bool = False

    model_config = {"env_prefix": "CCSM_"}
```

---

## 6 数据流

### 6.1 本地会话浏览（SSE 流式）

```
Browser                    FastAPI Server              LocalClaudeCodeSource      FileWatcher
  │                            │                            │                        │
  │  GET /                     │  serve SPA                 │                        │
  │───────────────────────────>│                            │                        │
  │  <html>                    │                            │                        │
  │<───────────────────────────│                            │                        │
  │                            │                            │                        │
  │  EventSource               │                            │                        │
  │  /api/sessions/stream      │                            │                        │
  │───────────────────────────>│                            │                        │
  │                            │  list_sessions()           │                        │
  │                            │───────────────────────────>│                        │
  │                            │  [SessionSummary[]]        │                        │
  │                            │<───────────────────────────│                        │
  │  SSE: event=sessions       │                            │                        │
  │<───────────────────────────│                            │                        │
  │                            │                            │                        │
  │  [user clicks session]     │                            │                        │
  │  EventSource               │                            │                        │
  │  /api/sessions/{id}/stream │                            │                        │
  │───────────────────────────>│                            │                        │
  │                            │  get_session(id)           │                        │
  │                            │───────────────────────────>│                        │
  │  SSE: event=messages       │                            │  parse JSONL           │
  │<───────────────────────────│<───────────────────────────│                        │
  │                            │                            │                        │
  │                          [file change detected]         │                        │
  │                            │                            │  on_session_change()   │
  │                            │<───────────────────────────────────────────────────│
  │                            │  re-read from offset       │                        │
  │  SSE: event=messages       │                            │                        │
  │<───────────────────────────│                            │                        │
```

### 6.2 HuggingFace 数据拉取

```
Browser                    FastAPI Server              HuggingFaceSource          HuggingFace API
  │                            │                            │                        │
  │  POST /api/pull/huggingface│                            │                        │
  │  { repo_id: "user/data" } │                            │                        │
  │───────────────────────────>│                            │                        │
  │                            │  pull_repo(repo_id)        │                        │
  │                            │───────────────────────────>│                        │
  │                            │                            │  hf_hub_download()     │
  │                            │                            │───────────────────────>│
  │                            │                            │  conversations.jsonl   │
  │                            │                            │<───────────────────────│
  │                            │                            │                        │
  │                            │                            │  DataclawParser.parse()│
  │                            │                            │  → SessionDetail[]     │
  │                            │                            │                        │
  │                            │                            │  db.upsert_session()   │
  │                            │                            │  (each session → SQLite)│
  │                            │                            │                        │
  │                            │  PullResult                │                        │
  │                            │<───────────────────────────│                        │
  │  200 { sessions_imported } │                            │                        │
  │<───────────────────────────│                            │                        │
```

### 6.3 推送到 MongoDB

```
Browser                    FastAPI Server              LocalSource / DB           MongoDBTarget
  │                            │                            │                        │
  │  POST /api/push/mongodb    │                            │                        │
  │  { session_ids: [A,B] }   │                            │                        │
  │───────────────────────────>│                            │                        │
  │                            │  validate request          │                        │
  │                            │  check target.is_connected │                        │
  │                            │                            │                        │
  │                            │  get_session(A)            │                        │
  │                            │───────────────────────────>│                        │
  │                            │  SessionDetail(A)          │                        │
  │                            │<───────────────────────────│                        │
  │                            │  get_session(B)            │                        │
  │                            │───────────────────────────>│                        │
  │                            │  SessionDetail(B)          │                        │
  │                            │<───────────────────────────│                        │
  │                            │                            │                        │
  │                            │  push_sessions([A, B])     │                        │
  │                            │───────────────────────────────────────────────────>│
  │                            │                            │  sessions.updateOne    │
  │                            │                            │  (upsert by sessionId) │
  │                            │                            │  messages.bulkWrite    │
  │                            │                            │  (upsert by uuid,      │
  │                            │                            │   batches of 500)      │
  │                            │  PushResult                │                        │
  │                            │<──────────────────────────────────────────────────│
  │  200 { uploaded: 2 }       │                            │                        │
  │<───────────────────────────│                            │                        │
```

### 6.4 推送到 HuggingFace

```
Browser                    FastAPI Server              HuggingFaceTarget          HuggingFace API
  │                            │                            │                        │
  │  POST /api/push/huggingface│                            │                        │
  │  { session_ids: [A,B] }   │                            │                        │
  │───────────────────────────>│                            │                        │
  │                            │  load SessionDetail[A,B]   │                        │
  │                            │  from local/db             │                        │
  │                            │                            │                        │
  │                            │  push_sessions([A,B])      │                        │
  │                            │───────────────────────────>│                        │
  │                            │                            │  _to_dataclaw_format() │
  │                            │                            │  write temp .jsonl     │
  │                            │                            │  upload_file()         │
  │                            │                            │───────────────────────>│
  │                            │                            │<───────────────────────│
  │                            │  PushResult                │                        │
  │                            │<───────────────────────────│                        │
  │  200 { uploaded: 2 }       │                            │                        │
  │<───────────────────────────│                            │                        │
```

---

## 7 API 合约

### 7.1 会话浏览

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions` | 列出会话（支持 source 过滤） |
| `GET` | `/api/sessions/stream` | SSE 实时会话更新（仅 local） |
| `GET` | `/api/sessions/{id}` | 获取完整对话 |
| `GET` | `/api/sessions/{id}/stream` | SSE 消息增量推送（仅 local） |
| `GET` | `/api/projects` | 列出所有项目 |

**GET /api/sessions**

Query:
- `source` — `local` | `huggingface` | `mongodb`（默认 `local`）
- `project_id` — 按项目过滤
- `limit` — 默认 100
- `offset` — 默认 0

Response `200`:
```json
[
  {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "project_name": "myapp",
    "timestamp": "2026-03-10T14:30:00Z",
    "duration": 3600,
    "message_count": 42,
    "tool_call_count": 15,
    "models": ["claude-sonnet-4-6"],
    "first_message": "Help me refactor the auth module...",
    "source_type": "local",
    "source_name": "",
    "source_host": ""
  }
]
```

**GET /api/sessions/{id}**

Query:
- `source` — 指定从哪个源加载（默认按 session_id 自动匹配）

Response `200`:
```json
{
  "summary": { "session_id": "...", "...": "..." },
  "messages": [
    {
      "uuid": "msg-001",
      "session_id": "550e8400-...",
      "role": "user",
      "type": "user",
      "content": "Help me refactor...",
      "timestamp": "2026-03-10T14:30:00Z",
      "tool_calls": [],
      "usage": null
    },
    {
      "uuid": "msg-002",
      "role": "assistant",
      "type": "assistant",
      "content": [
        { "type": "text", "text": "I'll help you..." },
        { "type": "tool_use", "id": "tu-1", "name": "Read", "input": { "file_path": "/src/auth.ts" } }
      ],
      "model": "claude-sonnet-4-6",
      "timestamp": "2026-03-10T14:30:05Z",
      "tool_calls": [{ "id": "tu-1", "name": "Read", "input": { "file_path": "/src/auth.ts" } }],
      "usage": { "input_tokens": 1200, "output_tokens": 350 }
    }
  ]
}
```

Response `404`:
```json
{ "error": { "code": "SESSION_NOT_FOUND", "message": "Session not found" } }
```

### 7.2 数据推送

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/push/mongodb` | 推送选中会话到 MongoDB |
| `POST` | `/api/push/huggingface` | 推送选中会话到 HuggingFace |

**POST /api/push/mongodb**

Request:
```json
{
  "session_ids": ["550e8400-e29b-41d4-a716-446655440000", "6ba7b810-..."]
}
```

Response `200`:
```json
{ "total": 2, "uploaded": 2, "skipped": 0, "errors": [] }
```

Response `200` (partial failure):
```json
{
  "total": 2, "uploaded": 1, "skipped": 0,
  "errors": [{ "session_id": "6ba7b810-...", "error": "Session file not found" }]
}
```

Response `400`:
```json
{ "error": { "code": "INVALID_REQUEST", "message": "session_ids array is required" } }
```

Response `503`:
```json
{ "error": { "code": "TARGET_UNAVAILABLE", "message": "MongoDB not configured. Set MONGODB_URI." } }
```

### 7.3 数据拉取

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/pull/huggingface` | 从 HF dataclaw 数据集拉取 |
| `GET` | `/api/pull/huggingface/repos` | 列出可用的 dataclaw 数据集 |

**POST /api/pull/huggingface**

Request:
```json
{ "repo_id": "peteromallet/my-personal-codex-data", "force_refresh": false }
```

Response `200`:
```json
{ "repo_id": "peteromallet/my-personal-codex-data", "sessions_imported": 82, "messages_imported": 1456, "skipped": 3 }
```

**GET /api/pull/huggingface/repos**

Response `200`:
```json
[
  { "repo_id": "peteromallet/my-personal-codex-data", "size_mb": 82.6, "last_modified": "2026-03-01" },
  { "repo_id": "user2/dataclaw-export", "size_mb": 12.3, "last_modified": "2026-02-15" }
]
```

### 7.4 分析

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/analysis/user-preference` | 用户偏好分析 |
| `GET` | `/api/analysis/agent-behavior` | Agent 行为模式分析 |
| `GET` | `/api/analysis/tool-sequences` | 工具调用序列分析 |

**GET /api/analysis/user-preference**

Query:
- `source_name` — 数据源名称（如 HF repo_id）
- `project_id` — 可选过滤

Response `200`:
```json
{
  "source_name": "peteromallet/my-personal-codex-data",
  "session_count": 82,
  "tool_usage": [
    { "tool_name": "Bash", "call_count": 456, "avg_per_session": 5.6, "error_rate": 0.03 },
    { "tool_name": "Read", "call_count": 312, "avg_per_session": 3.8, "error_rate": 0.0 },
    { "tool_name": "Edit", "call_count": 198, "avg_per_session": 2.4, "error_rate": 0.01 }
  ],
  "time_pattern": {
    "hour_distribution": { "9": 12, "10": 18, "14": 15, "15": 20, "16": 10 },
    "weekday_distribution": { "0": 15, "1": 18, "2": 20, "3": 16, "4": 13 },
    "avg_session_duration": 1800.5,
    "avg_messages_per_session": 24.3
  },
  "model_distribution": { "claude-sonnet-4-6": 45, "claude-opus-4-6": 37 },
  "project_distribution": { "myapp": 30, "backend-api": 25, "docs": 27 },
  "top_tool_sequences": [
    ["Read", "Edit", "Bash"],
    ["Bash", "Read", "Edit", "Bash"],
    ["Grep", "Read", "Edit"]
  ]
}
```

**GET /api/analysis/agent-behavior**

Query:
- `model` — 模型名过滤
- `source_type` — 数据源类型

Response `200`:
```json
{
  "model": "claude-sonnet-4-6",
  "session_count": 120,
  "avg_tool_calls_per_session": 8.3,
  "avg_tokens_per_session": 45000,
  "tool_selection_variability": 0.42,
  "common_tool_patterns": [
    { "pattern": ["Read", "Edit", "Bash"], "frequency": 0.35 },
    { "pattern": ["Grep", "Read", "Edit"], "frequency": 0.22 }
  ],
  "thinking_action_consistency": 0.87
}
```

### 7.5 配置与状态

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/settings` | 服务器状态和配置 |
| `GET` | `/api/sources` | 已配置的数据源 |
| `GET` | `/api/targets` | 已配置的数据目标 |

**GET /api/settings**

Response `200`:
```json
{
  "version": "1.0.0",
  "sources": {
    "local": { "type": "local", "connected": true, "path": "~/.claude" },
    "huggingface": { "type": "huggingface", "connected": true },
    "mongodb": { "type": "mongodb", "connected": false }
  },
  "targets": {
    "mongodb": { "type": "mongodb", "connected": false, "uri_masked": "" },
    "huggingface": { "type": "huggingface", "connected": true, "repo_id": "user/data" }
  }
}
```

### 7.6 错误码汇总

| HTTP Status | Code | Description |
|-------------|------|-------------|
| `400` | `INVALID_REQUEST` | 请求参数错误（session_ids 为空、格式错误） |
| `404` | `SESSION_NOT_FOUND` | 指定的会话不存在 |
| `404` | `REPO_NOT_FOUND` | HuggingFace 数据集不存在 |
| `500` | `INTERNAL_ERROR` | 服务器内部错误 |
| `503` | `TARGET_UNAVAILABLE` | 推送目标未配置或不可达 |
| `503` | `SOURCE_UNAVAILABLE` | 数据源不可达 |

错误响应格式统一：
```json
{ "error": { "code": "TARGET_UNAVAILABLE", "message": "Human-readable explanation." } }
```

---

## 8 数据库设计

### 8.1 SQLite Schema（本地模式）

```sql
CREATE TABLE sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT UNIQUE NOT NULL,
    project_id      TEXT DEFAULT '',
    project_name    TEXT DEFAULT '',
    timestamp       TEXT,                           -- ISO 8601
    duration        INTEGER DEFAULT 0,
    message_count   INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    models          TEXT DEFAULT '[]',              -- JSON array
    first_message   TEXT DEFAULT '',
    source_type     TEXT NOT NULL DEFAULT 'local',  -- local | huggingface | mongodb
    source_name     TEXT DEFAULT '',                -- e.g. HF repo_id
    source_host     TEXT DEFAULT '',
    total_input_tokens  INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    imported_at     TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_sessions_source ON sessions(source_type, timestamp DESC);
CREATE INDEX idx_sessions_project ON sessions(project_id, timestamp DESC);

CREATE TABLE messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid        TEXT UNIQUE NOT NULL,
    session_id  TEXT NOT NULL REFERENCES sessions(session_id),
    parent_uuid TEXT DEFAULT '',
    role        TEXT NOT NULL,
    type        TEXT NOT NULL,
    content     TEXT DEFAULT '',                    -- JSON (string or ContentBlock[])
    thinking    TEXT,
    model       TEXT DEFAULT '',
    timestamp   TEXT,
    is_sidechain BOOLEAN DEFAULT FALSE,
    usage       TEXT,                              -- JSON (TokenUsage)
    tool_calls  TEXT DEFAULT '[]'                  -- JSON (ToolCall[])
);
CREATE INDEX idx_messages_session ON messages(session_id, timestamp);

CREATE TABLE analysis_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key   TEXT UNIQUE NOT NULL,              -- e.g. "user_pref:repo_id:project"
    result      TEXT NOT NULL,                     -- JSON
    created_at  TEXT DEFAULT (datetime('now')),
    expires_at  TEXT
);
```

### 8.2 MongoDB Collections（推送目标）

与 PRODUCT_SPEC.md 中定义一致：

**sessions collection:**

```javascript
db.sessions.createIndex({ sessionId: 1 }, { unique: true });
db.sessions.createIndex({ projectId: 1, timestamp: -1 });
db.sessions.createIndex({ timestamp: -1 });
db.sessions.createIndex({ sourceType: 1, timestamp: -1 });
```

**messages collection:**

```javascript
db.messages.createIndex({ uuid: 1 }, { unique: true });
db.messages.createIndex({ sessionId: 1, timestamp: 1 });
```

### 8.3 Upsert 幂等逻辑

所有写入操作（无论目标是 SQLite 还是 MongoDB）都是幂等的：

1. **Session upsert**: 按 `session_id` 唯一约束。存在则覆盖全部字段。
2. **Message upsert**: 按 `uuid` 唯一约束。存在则覆盖。
3. **MongoDB bulkWrite**: `ordered: false`，单条失败不阻塞其余。
4. **批量大小**: 每 500 条 message 为一个 batch，避免内存溢出。
5. **重复导入**: HF 数据拉取时，若 `force_refresh=false` 且 session_id 已存在，跳过（skipped++）。

---

## 9 前端组件架构

### 9.1 组件树

```
<App>
  ├── <header>
  │   ├── Logo + Title
  │   ├── <DataSourcePanel                   // Local | HuggingFace | MongoDB 选项卡
  │   │     activeSource={dataSource}
  │   │     sources={availableSources}
  │   │     onChange={handleSourceChange}
  │   │   />
  │   └── <nav> Browse | Analyze             // 页面切换
  │
  ├── [Browse Page]
  │   ├── <aside> (collapsible sidebar)
  │   │   ├── <select> (project filter)
  │   │   ├── <SessionList
  │   │   │     sessions={filteredSessions}
  │   │   │     selectedSession={selectedSession}
  │   │   │     onSelectSession={...}
  │   │   │     selectable={true}
  │   │   │     selectedIds={selectedSessionIds}
  │   │   │     onToggleSelect={...}
  │   │   │   />
  │   │   └── <PushToolbar                   // 推送工具栏
  │   │         selectedCount={selectedSessionIds.size}
  │   │         targets={availableTargets}
  │   │         onPush={handlePush}
  │   │       />
  │   │
  │   └── <main>
  │       ├── <SessionHeader />              // 会话元数据
  │       ├── <TimelineBar                   // CooperBench 风格时间线
  │       │     steps={timelineSteps}
  │       │     filters={activeFilters}
  │       │     onClickStep={scrollToMessage}
  │       │   />
  │       ├── <SessionView
  │       │     sessionId={selectedSession}
  │       │     source={dataSource}
  │       │   />
  │       │   ├── <MessageBlock />
  │       │   │   ├── <MarkdownRenderer />
  │       │   │   ├── <ThinkingBlock />      // 折叠面板
  │       │   │   └── <ToolBlock />
  │       │   │       ├── <BashRenderer />
  │       │   │       ├── <EditRenderer />
  │       │   │       ├── <ReadRenderer />
  │       │   │       └── ...
  │       │   └── <ScrollToBottom />
  │       │
  │       └── <PushDialog />                 // 推送确认弹窗
  │
  ├── [Analyze Page]
  │   ├── <AnalysisDashboard>
  │   │   ├── <ToolUsageChart />             // 工具使用分布 (Recharts)
  │   │   ├── <TimePatternHeatmap />         // 时间模式热力图
  │   │   ├── <IntentDistribution />         // 意图分类分布
  │   │   ├── <TokenEfficiency />            // Token 效率对比
  │   │   └── <ToolSequenceViz />            // 常见工具调用序列
  │   │
  │   └── <AgentComparison />                // 跨模型行为对比
  │
  └── <ToastContainer />                     // 全局通知
```

### 9.2 TimelineBar 组件设计

参考 CooperBench 的实现方式：纯 CSS 绝对定位，不依赖图表库。

```typescript
// web/components/timeline-bar.tsx
interface TimelineBarProps {
  steps: TimelineStep[];
  filters: Set<ToolType>;
  onToggleFilter: (type: ToolType) => void;
  onClickStep: (index: number) => void;
}
```

渲染逻辑：
1. 计算时间范围：`timeRange = { start: min(timestamps), end: max(timestamps), duration }`
2. 每个 step 渲染为一个绝对定位的 `<div>`：
   - `left = ((step.timestamp - timeRange.start) / timeRange.duration) * 100 + '%'`
   - `width = ((nextStep.timestamp - step.timestamp) / timeRange.duration) * 100 + '%'`（最小 2px）
   - 背景色由 `TOOL_TYPE_COLORS[step.tool_type]` 决定
3. 底部显示时间刻度标记
4. 点击 step 块触发 `onClickStep`，滚动到对应消息

```
┌─ Timeline ──────────────────────────────────────────────────────────┐
│  ☑ Bash  ☑ Edit  ☑ Read  ☑ Search  ☑ Think  ☑ Other               │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │▓▓▓▓░░▓▓▓▓▓▓░░░▓▓░░▓▓▓▓▓▓▓▓░░▓▓░░░░▓▓▓▓▓▓▓▓▓▓░░▓▓▓▓▓▓▓▓▓▓│ │
│  └────────────────────────────────────────────────────────────────┘ │
│  10:30:00        10:35:00        10:40:00        10:45:00          │
└─────────────────────────────────────────────────────────────────────┘

颜色映射:
  ▓ 黄色 = Bash    ▓ 绿色 = Edit    ▓ 蓝色 = Read
  ▓ 青色 = Search  ▓ 灰色 = Think   ▓ 浅灰 = Other
```

### 9.3 状态管理

```typescript
// web/app.tsx — 根组件状态

// 数据源与导航
const [dataSource, setDataSource] = useState<DataSourceType>("local");
const [activePage, setActivePage] = useState<"browse" | "analyze">("browse");

// 会话列表
const [sessions, setSessions] = useState<SessionSummary[]>([]);
const [loading, setLoading] = useState(true);
const [selectedProject, setSelectedProject] = useState<string | null>(null);
const [selectedSession, setSelectedSession] = useState<string | null>(null);

// 多选与推送
const [selectedSessionIds, setSelectedSessionIds] = useState<Set<string>>(new Set());
const [pushTarget, setPushTarget] = useState<DataTargetType | null>(null);
const [pushStatus, setPushStatus] = useState<{ loading: boolean; result: PushResult | null }>({
  loading: false, result: null,
});
const [showPushDialog, setShowPushDialog] = useState(false);

// UI
const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
const [toasts, setToasts] = useState<Toast[]>([]);

// 可用源和目标（从 /api/settings 获取）
const [availableSources, setAvailableSources] = useState<Record<string, SourceInfo>>({});
const [availableTargets, setAvailableTargets] = useState<Record<string, TargetInfo>>({});
```

### 9.4 数据源切换逻辑

```typescript
const handleSourceChange = useCallback(async (source: DataSourceType) => {
  setDataSource(source);
  setSelectedSession(null);
  setSelectedSessionIds(new Set());
  setLoading(true);

  try {
    const params = new URLSearchParams({ source });
    if (selectedProject) params.set("project_id", selectedProject);
    const res = await fetch(`/api/sessions?${params}`);
    const data: SessionSummary[] = await res.json();
    setSessions(data);
  } catch {
    addToast("error", `Failed to load ${source} sessions`);
  } finally {
    setLoading(false);
  }
}, [selectedProject]);
```

### 9.5 推送处理逻辑

```typescript
const handlePush = useCallback(async (target: DataTargetType) => {
  if (selectedSessionIds.size === 0) return;
  setPushStatus({ loading: true, result: null });

  try {
    const res = await fetch(`/api/push/${target}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_ids: [...selectedSessionIds] }),
    });
    const result: PushResult = await res.json();
    setPushStatus({ loading: false, result });

    if (result.errors.length === 0) {
      addToast("success", `${result.uploaded} session(s) pushed to ${target}`);
      setSelectedSessionIds(new Set());
    } else {
      addToast("error", `${result.uploaded} pushed, ${result.errors.length} failed`);
    }
  } catch (err) {
    setPushStatus({ loading: false, result: null });
    addToast("error", `Push failed: ${err instanceof Error ? err.message : "Unknown"}`);
  }

  setShowPushDialog(false);
}, [selectedSessionIds]);
```

---

## 10 分析引擎设计

### 10.1 用户偏好分析（`ccsm/analysis/user_preference.py`）

```python
from collections import Counter, defaultdict
from datetime import datetime
from ccsm.models import (
    SessionDetail, UserPreferenceResult, ToolUsageStat, TimePattern,
)

SEQUENCE_WINDOW = 3


def analyze_user_preference(sessions: list[SessionDetail]) -> UserPreferenceResult:
    """分析用户在一组 session 中的编码偏好和工作模式。"""
    tool_counter: Counter = Counter()
    tool_errors: Counter = Counter()
    model_counter: Counter = Counter()
    project_counter: Counter = Counter()
    hour_counter: Counter = Counter()
    weekday_counter: Counter = Counter()
    durations: list[float] = []
    msg_counts: list[int] = []
    sequences: list[list[str]] = []

    for detail in sessions:
        s = detail.summary
        if s.project_name:
            project_counter[s.project_name] += 1
        if s.duration > 0:
            durations.append(s.duration)
        msg_counts.append(len(detail.messages))

        for model in s.models:
            model_counter[model] += 1

        if s.timestamp:
            ts = s.timestamp if isinstance(s.timestamp, datetime) else datetime.fromisoformat(str(s.timestamp))
            hour_counter[ts.hour] += 1
            weekday_counter[ts.weekday()] += 1

        session_tools: list[str] = []
        for msg in detail.messages:
            for tc in msg.tool_calls:
                tool_counter[tc.name] += 1
                if tc.is_error:
                    tool_errors[tc.name] += 1
                session_tools.append(tc.name)

        for i in range(len(session_tools) - SEQUENCE_WINDOW + 1):
            seq = session_tools[i : i + SEQUENCE_WINDOW]
            sequences.append(seq)

    session_count = len(sessions)
    tool_stats = []
    for name, count in tool_counter.most_common():
        tool_stats.append(ToolUsageStat(
            tool_name=name,
            call_count=count,
            avg_per_session=round(count / max(session_count, 1), 1),
            error_rate=round(tool_errors[name] / max(count, 1), 3),
        ))

    seq_counter = Counter(tuple(s) for s in sequences)
    top_sequences = [list(seq) for seq, _ in seq_counter.most_common(10)]

    return UserPreferenceResult(
        source_name="",
        session_count=session_count,
        tool_usage=tool_stats,
        time_pattern=TimePattern(
            hour_distribution=dict(hour_counter),
            weekday_distribution=dict(weekday_counter),
            avg_session_duration=sum(durations) / max(len(durations), 1),
            avg_messages_per_session=sum(msg_counts) / max(len(msg_counts), 1),
        ),
        model_distribution=dict(model_counter),
        project_distribution=dict(project_counter),
        top_tool_sequences=top_sequences,
    )
```

### 10.2 Agent 行为模式分析（`ccsm/analysis/agent_behavior.py`）

```python
from collections import Counter
from ccsm.models import SessionDetail, AgentBehaviorResult

SEQUENCE_WINDOW = 3


def analyze_agent_behavior(
    sessions: list[SessionDetail], model_filter: str = ""
) -> AgentBehaviorResult:
    """分析 Agent 在多个 session 中的行为模式。"""
    filtered = sessions
    if model_filter:
        filtered = [s for s in sessions if model_filter in str(s.summary.models)]

    total_tool_calls = 0
    total_tokens = 0
    tool_sequences: list[tuple[str, ...]] = []
    tool_sets_per_session: list[set[str]] = []

    for detail in filtered:
        session_tools: list[str] = []
        session_tool_set: set[str] = set()
        session_tokens = 0

        for msg in detail.messages:
            for tc in msg.tool_calls:
                session_tools.append(tc.name)
                session_tool_set.add(tc.name)
                total_tool_calls += 1
            if msg.usage:
                session_tokens += msg.usage.input_tokens + msg.usage.output_tokens

        total_tokens += session_tokens
        tool_sets_per_session.append(session_tool_set)

        for i in range(len(session_tools) - SEQUENCE_WINDOW + 1):
            seq = tuple(session_tools[i : i + SEQUENCE_WINDOW])
            tool_sequences.append(seq)

    n = max(len(filtered), 1)

    # 工具选择变异性: Jaccard 距离的平均值
    variability = _compute_tool_variability(tool_sets_per_session)

    seq_counter = Counter(tool_sequences)
    total_seqs = max(sum(seq_counter.values()), 1)
    common_patterns = [
        {"pattern": list(seq), "frequency": round(count / total_seqs, 3)}
        for seq, count in seq_counter.most_common(10)
    ]

    return AgentBehaviorResult(
        model=model_filter or "all",
        session_count=len(filtered),
        avg_tool_calls_per_session=round(total_tool_calls / n, 1),
        avg_tokens_per_session=round(total_tokens / n, 0),
        tool_selection_variability=round(variability, 3),
        common_tool_patterns=common_patterns,
        thinking_action_consistency=None,
    )


def _compute_tool_variability(tool_sets: list[set[str]]) -> float:
    """计算 session 间工具选择的变异性（平均 Jaccard 距离）。"""
    if len(tool_sets) < 2:
        return 0.0
    distances = []
    for i in range(len(tool_sets)):
        for j in range(i + 1, min(i + 20, len(tool_sets))):
            union = tool_sets[i] | tool_sets[j]
            if not union:
                continue
            intersection = tool_sets[i] & tool_sets[j]
            distances.append(1 - len(intersection) / len(union))
    return sum(distances) / max(len(distances), 1)
```

---

## 11 实现里程碑

### M1: 项目脚手架与统一模型（Day 1-2）

**构建内容：**
1. 初始化 Python 项目：`pyproject.toml`（FastAPI, uvicorn, pydantic, watchfiles, motor, huggingface_hub）
2. 初始化 React 前端：Vite + React 19 + TypeScript + Tailwind CSS
3. 创建 `ccsm/models.py`（全部 Pydantic 模型）
4. 创建 `web/types.ts`（对齐的 TypeScript 类型）
5. 创建 `ccsm/config.py`（pydantic-settings 配置）
6. 创建 `.env.example`

**验证：** `python -m ccsm.main serve` 启动，访问 `localhost:12001` 返回空白 SPA。

### M2: 本地数据源 + 会话浏览（Day 3-5）

**构建内容：**
1. `ccsm/sources/local.py` — 完整的本地 JSONL 解析
2. `ccsm/watcher.py` — watchfiles 文件监听
3. `ccsm/routes/sessions.py` — GET /api/sessions, GET /api/sessions/{id}, SSE 端点
4. `web/components/session-list.tsx` — 虚拟滚动列表 + 搜索
5. `web/components/session-view.tsx` — 消息渲染
6. `web/components/message-block.tsx` + 所有 tool-renderers
7. `web/hooks/use-event-source.ts` — SSE hook

**验证：** 启动应用，看到本地 Claude Code 会话列表，点击查看完整 trajectory，SSE 实时更新。

### M3: SQLite 存储层（Day 5-6）

**构建内容：**
1. `ccsm/db.py` — SQLite 连接 + CRUD 操作 (aiosqlite)
2. schema 初始化（sessions, messages, analysis_cache 表）
3. 通用 `upsert_session` / `list_sessions` / `get_session` 方法

**验证：** 数据导入后可以从 SQLite 中查询出来。

### M4: HuggingFace 数据拉取（Day 7-8）

**构建内容：**
1. `ccsm/ingest/dataclaw.py` — dataclaw JSONL 解析器
2. `ccsm/ingest/normalizer.py` — 多格式归一化接口
3. `ccsm/sources/huggingface.py` — HF 数据源适配器
4. `ccsm/routes/pull.py` — POST /api/pull/huggingface, GET /api/pull/huggingface/repos
5. 前端：数据源切换面板 + HF repo 选择器

**验证：** 输入 `peteromallet/my-personal-codex-data`，成功拉取 82 个 session 到本地 SQLite，在前端切换到 HuggingFace 源可以浏览。

### M5: 数据推送（MongoDB + HuggingFace）（Day 9-10）

**构建内容：**
1. `ccsm/targets/mongodb.py` — MongoDB 推送（motor async driver）
2. `ccsm/targets/huggingface.py` — HF 推送（dataclaw 格式转换）
3. `ccsm/routes/push.py` — POST /api/push/mongodb, POST /api/push/huggingface
4. 前端：checkbox 多选 + 推送工具栏 + 目标选择 + 确认弹窗 + Toast

**验证：** 选中 3 个本地会话 → 推送到 MongoDB → 成功。从 HF 拉取的会话 → 推送到 HF 新 repo → 成功。

### M6: CooperBench 风格时间线（Day 11-12）

**构建内容：**
1. `web/components/timeline-bar.tsx` — 纯 CSS 绝对定位时间线
2. 工具类型分类 + 颜色映射
3. 过滤 checkbox
4. 点击 step → 滚动到对应消息
5. 时间刻度标记

**验证：** 打开一个有 50+ tool calls 的 session，时间线渲染正确，颜色区分清晰，点击跳转准确。

### M7: 分析引擎 + 仪表盘（Day 13-15）

**构建内容：**
1. `ccsm/analysis/user_preference.py` — 用户偏好分析
2. `ccsm/analysis/agent_behavior.py` — Agent 行为模式分析
3. `ccsm/routes/analysis.py` — 分析 API 端点
4. 前端分析页面：
   - `tool-usage-chart.tsx` — Recharts 条形图
   - `time-pattern.tsx` — 热力图
   - `token-efficiency.tsx` — 对比图

**验证：** 导入 dataclaw 数据后，切换到 Analyze 页面，看到完整的用户偏好分析和 Agent 行为模式图表。

### M8: 打磨与边缘情况（Day 16-17）

**构建内容：**
1. Loading 骨架屏 + 空状态
2. 错误边界处理
3. 大型 session 性能优化（虚拟滚动、增量加载）
4. 部分推送失败处理
5. 断网恢复
6. dataclaw 格式版本兼容（不同 agent 来源的字段差异）
7. 端到端测试

**验证：** 完整 E2E 流程：本地浏览 → 拉取 HF 数据 → 分析 → 选中推送到 MongoDB → 切换源查看。

---

## 12 错误处理

### 12.1 后端错误处理

| Error | Location | Strategy |
|-------|----------|----------|
| 格式错误的 JSONL 行 | `local.py`, `dataclaw.py` | 跳过该行，继续解析 |
| Session 文件不存在 | `local.py` | 返回 `None`，调用方处理 |
| HF 数据集不存在 | `huggingface.py` | 捕获 404，返回 `REPO_NOT_FOUND` |
| HF 下载超时 | `huggingface.py` | 30s 超时，返回 `SOURCE_UNAVAILABLE` |
| MongoDB 连接失败 | `mongodb.py` | 日志记录，`is_connected()` 返回 `False` |
| MongoDB 单条写入失败 | `mongodb.py` | 捕获异常，记入 `errors[]`，继续下一条 |
| SQLite 写入冲突 | `db.py` | ON CONFLICT 处理（upsert） |
| 请求体校验失败 | FastAPI | Pydantic 自动返回 422 |
| 未知服务端错误 | 全局 | 500 + 错误日志 |

### 12.2 前端错误处理

| Error | Location | Strategy |
|-------|----------|----------|
| SSE 连接断开 | `use-event-source.ts` | 指数退避重连（1s→2s→4s→...→30s，最多 10 次） |
| 推送网络失败 | `app.tsx` | 错误 Toast，保留选择状态（用户可重试） |
| 推送部分失败 | `app.tsx` | 警告 Toast 显示成功/失败数 |
| 数据源切换失败 | `app.tsx` | 错误 Toast，保持当前源 |
| HF 拉取失败 | Pull dialog | 错误提示 + 重试按钮 |
| Session 加载失败 | `session-view.tsx` | 面板显示 "Failed to load session" |
| 分析计算超时 | `analyze.tsx` | 30s 超时提示，建议缩小分析范围 |

---

## 13 配置

### 13.1 环境变量

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CCSM_PORT` | No | `12001` | 服务端口 |
| `CCSM_CLAUDE_DIR` | No | `~/.claude` | Claude Code 数据目录 |
| `MONGODB_URI` | No | `""` | MongoDB 连接字符串（为空则禁用 MongoDB 功能） |
| `DB_NAME` | No | `ccsm` | MongoDB 数据库名 |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///ccsm.db` | 本地数据库 URL |
| `HF_TOKEN` | No | `""` | HuggingFace API token（推送用） |
| `HF_REPO_ID` | No | `""` | HuggingFace 推送目标 repo |

### 13.2 CLI 参数

```
Usage: python -m ccsm.main serve [OPTIONS]

Options:
  -p, --port INTEGER          Server port [default: 12001]
  -d, --dir TEXT              Claude directory path [default: ~/.claude]
  --mongodb-uri TEXT          MongoDB connection URI [env: MONGODB_URI]
  --db-name TEXT              MongoDB database name [default: ccsm]
  --database-url TEXT         Local database URL [default: sqlite+aiosqlite:///ccsm.db]
  --hf-token TEXT             HuggingFace API token [env: HF_TOKEN]
  --hf-repo-id TEXT           HuggingFace push target repo [env: HF_REPO_ID]
  --dev                       Enable CORS for development
```

CLI 参数优先于环境变量。

### 13.3 `.env.example`

```bash
# MongoDB (optional, enables MongoDB push/pull)
# MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net
# DB_NAME=ccsm

# HuggingFace (optional, enables HF push/pull)
# HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxx
# HF_REPO_ID=username/my-dataclaw-export

# Local database (default: SQLite)
# DATABASE_URL=sqlite+aiosqlite:///ccsm.db
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/ccsm  # for Phase 2

# Server
# CCSM_PORT=12001
# CCSM_CLAUDE_DIR=~/.claude
```

### 13.4 依赖列表

**Python 后端（pyproject.toml）：**

```toml
[project]
name = "ccsm"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.7.0",
    "typer>=0.15.0",
    "aiosqlite>=0.21.0",
    "watchfiles>=1.0.0",
    "motor>=3.7.0",              # async MongoDB driver
    "huggingface-hub>=0.28.0",
    "sse-starlette>=2.2.0",     # SSE support for FastAPI
]

[project.optional-dependencies]
postgres = ["asyncpg>=0.30.0"]
analysis = ["anthropic>=0.43.0"]  # LLM-driven intent classification
dev = ["ruff", "pytest", "pytest-asyncio", "httpx"]

[project.scripts]
ccsm = "ccsm.main:cli"
```

**React 前端（web/package.json）：**

```json
{
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-markdown": "^10.1.0",
    "remark-gfm": "^4.0.1",
    "@tanstack/react-virtual": "^3.13.0",
    "lucide-react": "^0.562.0",
    "recharts": "^2.15.0",
    "diff": "^8.0.0"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "vite": "^6.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/vite": "^4.0.0"
  }
}
```

### 13.5 Vite 配置

```typescript
// web/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 12000,
    proxy: {
      "/api": {
        target: "http://localhost:12001",
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            // Disable buffering for SSE endpoints
            if (proxyRes.headers["content-type"]?.includes("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
              proxyRes.headers["x-accel-buffering"] = "no";
            }
          });
        },
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
```

---

## 14 设计决策

### 14.1 Python FastAPI 而非 Hono (Node.js)

**决策：** 使用 Python FastAPI 作为后端。

**理由：** 项目从"会话查看器"演进为"分析平台"。HuggingFace 生态（`huggingface_hub`, `datasets`）是 Python 原生的。分析引擎需要的工具（pandas, scikit-learn, Counter/defaultdict 等数据处理原语）在 Python 中更自然。LLM 意图分类使用 Anthropic Python SDK。

**代价：** 放弃 claude-run 的 SSE + Chokidar 实现（~500 行），需用 `sse-starlette` + `watchfiles` 重写。前后端类型不共享（Pydantic ↔ TypeScript 需手动对齐）。

### 14.2 可扩展的 Source/Target 插件架构

**决策：** 使用 Python Protocol（结构化子类型）定义 `DataSource` 和 `DataTarget` 接口。

**理由：** dataclaw 已扩展到支持 Codex、Gemini CLI、OpenCode 等多种 Agent。未来可能需要接入 CooperBench 的多 Agent trajectory 数据、或推送到 S3/GCS 等存储。Protocol 模式无需继承，新增数据源只需实现接口方法。

**代价：** 初始实现需要写三个 source 适配器和两个 target 适配器，工作量大于硬编码单一路径。

### 14.3 SQLite 本地 → PostgreSQL 远程的升级路径

**决策：** 默认使用 SQLite（零配置），通过 `DATABASE_URL` 环境变量支持切换到 PostgreSQL。

**理由：** 本地工具模式下 SQLite 零部署成本。SQLite 对于单用户 + 数万 session 的规模完全够用。升级到 PostgreSQL 时，使用 SQLAlchemy 异步引擎（aiosqlite → asyncpg），SQL schema 保持一致。

**代价：** 不能使用 PostgreSQL 专有功能（如 JSONB 索引、全文搜索）。SQLite 不支持并发写入（单用户场景可接受）。

### 14.4 CooperBench 风格时间线使用纯 CSS 而非图表库

**决策：** TimelineBar 组件使用绝对定位的 `<div>` 元素，不依赖 Recharts 或 D3。

**理由：** CooperBench 验证了这种方案的可行性。时间线的核心是"将时间戳映射到百分比位置 + 颜色编码"，这是 CSS 的强项。引入图表库会增加 ~100KB 包体积，且 Gantt 图不是标准图表类型，定制反而更复杂。

**代价：** 缩放、拖拽、tooltip 等交互需要手动实现。如果未来需要多 Agent 并行时间线（CooperBench 的 Agent A/B 双轨），需要扩展布局逻辑。

### 14.5 REST 用于非实时数据，SSE 仅用于本地文件

**决策：** SSE 流式推送仅用于本地 JSONL 文件变更场景。HuggingFace 和 MongoDB 的数据加载使用普通 REST。

**理由：** HF 和 MongoDB 中的数据是静态的（上传后不会变）。SSE 对静态数据没有意义，反而增加连接开销。本地文件需要 SSE 是因为 Claude Code 可能正在写入 JSONL 文件。

### 14.6 dataclaw 格式作为数据交换标准

**决策：** 推送到 HuggingFace 时使用 dataclaw 的 `conversations.jsonl` 格式。

**理由：** dataclaw 是目前唯一一个公开的 AI 编码 Agent 对话数据发布标准。使用相同格式意味着我们导出的数据可以被 dataclaw 社区的其他工具消费，反之亦然。格式简单（每行一个完整 session），无需分割文件。

**代价：** dataclaw 格式的 `tool_uses` 只包含工具名和输入摘要，不包含输出。从 Claude Code JSONL 转换时会丢失 tool_result 内容。这是 dataclaw 的隐私设计决策——tool output 可能包含敏感代码。

---

## 附录 A: 数据格式对照表

| 字段 | Claude Code JSONL | dataclaw | CCSM 统一模型 |
|------|-------------------|----------|---------------|
| 会话 ID | 文件名 (UUID.jsonl) | `session_id` | `session_id` |
| 项目 | 目录名 (encoded path) | `project` | `project_name` |
| 模型 | `message.model` | `model` | `models[]` |
| 角色 | `message.role` | `role` | `role` |
| 内容 | `message.content` (string \| ContentBlock[]) | `content` (string) | `content` (string \| ContentBlock[]) |
| 思维链 | ContentBlock `type=thinking` | `thinking` | `thinking` |
| 工具调用 | ContentBlock `type=tool_use` | `tool_uses[]` | `tool_calls[]` |
| 工具结果 | ContentBlock `type=tool_result` | *(不包含)* | `tool_calls[].output` |
| Token 用量 | `message.usage` | `stats` (聚合) | `usage` (per-message) |
| 时间戳 | `timestamp` (per-entry) | `timestamp` (per-message) + `start_time`/`end_time` | `timestamp` |

## 附录 B: 参考项目

| 项目 | 关系 | 参考内容 |
|------|------|---------|
| [claude-run](https://github.com/kamranahmedse/claude-run) | 原始骨架 | UI 布局、JSONL 解析、SSE 架构、tool renderer 组件 |
| [dataclaw](https://github.com/peteromallet/dataclaw) | 数据生态 | conversations.jsonl 格式、HF 发布流程、隐私处理策略 |
| [CooperBench](https://github.com/cooperbench/website) | 可视化参考 | 时间线条形图、多 Agent 双轨布局、工具类型颜色编码、步骤过滤器 |
| [Claudex](https://github.com/getAsterisk/claudex) | 竞品 | 全文搜索、session_metadata、模板检测器 |
| [Claud-ometer](https://github.com/nicobailey/claud-ometer) | 竞品 | Token 成本分析、活动热力图、Live/Imported 切换 |

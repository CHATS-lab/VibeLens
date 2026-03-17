# VibeLens

Agent trajectory analysis and visualization platform. Parses, normalizes, and visualizes conversation histories from multiple coding agent CLIs (Claude Code, Codex, Gemini, Dataclaw), stores them in SQLite, and serves them through a FastAPI backend with a React frontend.

## Features

### Multi-Agent Ingestion
- **Claude Code**: Parse `~/.claude/` conversation history, including subagent sessions
- **Codex CLI**: Parse `~/.codex/` rollout JSONL files (OpenAI Responses API format)
- **Gemini CLI**: Parse `~/.gemini/` session JSON files with hash directory resolution
- **Dataclaw**: Import HuggingFace-exported JSONL datasets
- **Auto-detection**: `fingerprint_file()` probes files and returns ranked format matches with confidence scores; `parse_auto()` selects the right parser automatically

### Data Sources & Targets
- **Local source**: Discover and parse sessions from local agent data directories
- **HuggingFace source**: Pull dataclaw-exported datasets from HuggingFace repos
- **MongoDB**: Push/pull sessions to/from a remote MongoDB instance (two-collection design: sessions + messages)

### Parser Infrastructure
- **Pluggable parsers**: Abstract `BaseParser` ABC with 4 concrete implementations
- **Tool normalization**: Unified tool categorization (file_read, file_write, shell, search, web, agent) and input/output summarization across all agent formats
- **Parse diagnostics**: `DiagnosticsCollector` tracks skipped lines, orphaned tool calls/results, and computes a completeness score per session
- **Cross-agent correlation**: Match sessions across different agents by overlapping time windows and shared project directories
- **Idempotent IDs**: Deterministic SHA-256-based identifiers ensure parsing the same file twice produces identical results

### Session Analytics
- **Tool dependency graph**: Infers causal relationships between tool calls (read-before-write, search-then-read, error-retry) and produces a DAG of the agent's problem-solving strategy
- **Phase detection**: Classifies session segments into phases (exploration, implementation, debugging, verification, planning) using sliding-window analysis over tool call categories
- **Parallel parsing**: `ProcessPoolExecutor`-based multi-file parsing for CPU-bound JSONL processing

### Two-Mode System
- **Self-use mode** (default): Local sessions from `~/.claude/` + persistent SQLite uploads. Full access to MongoDB, HuggingFace, and local sources.
- **Demo mode**: Public-facing. Pre-loaded example sessions + ephemeral per-tab uploads. Storage is configurable (in-memory or SQLite). Uploads are scoped per browser tab via `X-Session-Token` header, lost on page refresh.

### Storage & API
- **SessionStore protocol**: Pluggable storage backend with `SqliteSessionStore` and `MemorySessionStore` implementations
- **SQLite storage**: Persistent session and message storage with async access
- **In-memory storage**: Per-token ephemeral storage with TTL cleanup for demo mode
- **MongoDB storage**: Optional remote storage with two-collection design (sessions + messages), batch insert, and duplicate detection
- **REST API**: FastAPI backend for session listing, filtering, pagination, detail views, push/pull operations, and system configuration
- **React frontend**: Session browser with rich message rendering, tool-call visualization, sub-agent display, and batch collection

### Frontend
- **Session browser**: Searchable, filterable session list with project dropdown and pagination
- **Message rendering**: Role-specific styling with tool-specific renderers (Bash commands, file diffs, grep patterns, etc.)
- **Extended thinking**: Expandable display for Claude's thinking tokens
- **Sub-agent display**: Collapsible nested panels for multi-agent cascade hierarchies
- **Prompt navigation**: Right sidebar showing numbered user turns with scroll-to navigation
- **Token statistics**: Input/output/cache metrics displayed per session
- **Batch collection**: Multi-select sessions and push to MongoDB with confirmation dialog
- **Session export**: Copy full session JSON to clipboard

## Quick Start

```bash
uv sync

# Self-use mode (default) — reads local ~/.claude/ sessions
cp config/self-use.yaml vibelens.yaml
uv run vibelens serve

# Demo mode — pre-loaded examples, ephemeral uploads
uv run vibelens serve --config config/demo-memory.yaml
```

## Configuration

VibeLens uses YAML-based configuration with environment variable overrides. Config templates live in `config/`.

Priority (highest to lowest):
1. **Environment variables** (`VIBELENS_*`)
2. **`.env` file**
3. **YAML config file** (`vibelens.yaml`)
4. **Built-in defaults**

### Config Templates

| Template | Mode | Storage | Use Case |
|----------|------|---------|----------|
| `config/self-use.yaml` | `self` | SQLite | Local development, personal use |
| `config/demo-memory.yaml` | `demo` | Memory | Public demo, uploads lost on restart |
| `config/demo-sqlite.yaml` | `demo` | SQLite | Public demo, uploads persist across restarts |
| `config/vibelens.example.yaml` | `self` | SQLite | Full reference with all options documented |

### YAML Config (recommended)

Copy a template and edit:

```bash
cp config/self-use.yaml vibelens.yaml
```

```yaml
app:
  mode: self                       # "self" or "demo"

server:
  host: 127.0.0.1
  port: 12001

database:
  path: ~/.vibelens/vibelens.db

sources:
  claude_dir: ~/.claude

# Demo mode settings (only used when app.mode is "demo")
demo:
  storage: memory                  # "memory" or "sqlite"
  example_sessions: "examples/claude-code-example.jsonl"
  session_ttl: 3600
  persist_uploads: false
```

### Starting the Server

```bash
# Auto-discovers vibelens.yaml in current directory
vibelens serve

# Explicit config file
vibelens serve --config config/demo-memory.yaml

# Override specific settings via CLI flags
vibelens serve --host 0.0.0.0 --port 8080

# Override via environment variables
VIBELENS_PORT=8080 VIBELENS_APP_MODE=demo vibelens serve
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBELENS_APP_MODE` | `self` | Operating mode: `self` or `demo` |
| `VIBELENS_HOST` | `127.0.0.1` | Server bind address |
| `VIBELENS_PORT` | `12001` | Server port |
| `VIBELENS_DB_PATH` | `~/.vibelens/vibelens.db` | SQLite database file |
| `VIBELENS_CLAUDE_DIR` | `~/.claude` | Claude Code history root |
| `VIBELENS_MONGODB_URI` | *(empty)* | MongoDB connection URI |
| `VIBELENS_MONGODB_DB` | `vibelens` | MongoDB database name |
| `VIBELENS_HF_TOKEN` | *(empty)* | HuggingFace API token |
| `VIBELENS_DEMO_STORAGE` | `memory` | Demo storage backend: `memory` or `sqlite` |
| `VIBELENS_DEMO_EXAMPLE_SESSIONS` | *(empty)* | Comma-separated example session paths |
| `VIBELENS_DEMO_SESSION_TTL` | `3600` | Seconds before orphaned demo uploads are evicted |
| `VIBELENS_DEMO_PERSIST_UPLOADS` | `false` | Save uploaded files to disk in demo mode |
| `VIBELENS_CONFIG` | *(empty)* | Path to YAML config file |

## Development

```bash
# Backend
uv run ruff check src/
uv run pytest tests/ -v

# Frontend
cd frontend
npm install
npm run dev
```

## Architecture

```
src/vibelens/
  config/              # Configuration package
    settings.py        # Pydantic Settings model (AppMode, demo fields)
    loader.py          # YAML config loading and auto-discovery
    validators.py      # Integration config validators
  stores/              # Session storage backends
    protocol.py        # SessionStore Protocol definition
    sqlite.py          # SqliteSessionStore — wraps db.py
    memory.py          # MemorySessionStore — per-token with TTL
  ingest/              # Format parsers and analysis
    parsers/           # Format-specific parser implementations
      base.py          # BaseParser ABC with shared helpers
      claude_code.py   # Claude Code JSONL parser
      codex.py         # Codex CLI rollout parser
      gemini.py        # Gemini CLI session parser
      dataclaw.py      # Dataclaw HuggingFace export parser
    correlator.py      # Cross-agent session correlation
    tool_normalizers.py # Tool categorization and summary extraction
    diagnostics.py     # Parse quality metrics collection
    fingerprint.py     # Format auto-detection with confidence scoring
    tool_graph.py      # Tool call dependency DAG construction
    phase_detector.py  # Session conversation phase classification
    parallel.py        # Multi-file parallel parsing
  models/              # Pydantic domain models
    enums.py           # AgentType, AppMode, DataSourceType, SessionPhase
    message.py         # Message, ToolCall, TokenUsage, ContentBlock
    session.py         # SessionSummary, SessionDetail, SubAgentSession
    requests.py        # API request/response models
    analysis.py        # Analytics result models
  sources/             # Data source connectors (local, HuggingFace, MongoDB)
  targets/             # Data target connectors (MongoDB, HuggingFace)
  analysis/            # Session analytics and pattern detection
  api/                 # FastAPI route handlers
  utils/               # Shared utilities (logging, timestamps, paths, JSON)
  db.py                # SQLite database layer
  app.py               # FastAPI application factory (mode-aware lifespan)
  cli.py               # Typer CLI entrypoint
config/                # Configuration templates
  self-use.yaml        # Default self-use mode
  demo-memory.yaml     # Demo mode with in-memory storage
  demo-sqlite.yaml     # Demo mode with SQLite persistence
  vibelens.example.yaml # Full reference config
examples/              # Example session files for demo mode
  claude-code-example.jsonl
  codex-example.jsonl
  gemini-example.json
frontend/              # React + Vite + Tailwind UI
  src/
    app.tsx                  # AppContext (sessionToken, fetchWithToken, appMode)
    components/
      session-list.tsx       # Filterable session list with multi-select
      session-view.tsx       # Full session viewer with metadata and messages
      message-block.tsx      # Rich message rendering with tool-specific views
      sub-agent-block.tsx    # Collapsible sub-agent hierarchy display
      prompt-nav-panel.tsx   # Right sidebar prompt navigation
      upload-dialog.tsx      # File upload wizard
      confirm-dialog.tsx     # Modal confirmation dialog
      collapsible-pill.tsx   # Reusable expandable panel
      markdown-renderer.tsx  # Markdown content rendering
      copy-button.tsx        # Clipboard copy with feedback
```

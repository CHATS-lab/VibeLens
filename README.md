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

### Storage & API
- **SQLite storage**: Persistent session and message storage with async access
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
cp vibelens.example.yaml vibelens.yaml   # edit with your settings
uv run vibelens serve
```

## Configuration

VibeLens uses YAML-based configuration with environment variable overrides.

Priority (highest to lowest):
1. **Environment variables** (`VIBELENS_*`)
2. **`.env` file**
3. **YAML config file** (`vibelens.yaml`)
4. **Built-in defaults**

### YAML Config (recommended)

Copy the template and edit:

```bash
cp vibelens.example.yaml vibelens.yaml
```

```yaml
server:
  host: 127.0.0.1
  port: 12001

database:
  path: ~/.vibelens/vibelens.db

mongodb:
  uri: mongodb+srv://user:pass@host/
  db_name: vibelens

sources:
  claude_dir: ~/.claude

integrations:
  hf_token: ""
```

### Starting the Server

```bash
# Auto-discovers vibelens.yaml in current directory
vibelens serve

# Explicit config file
vibelens serve --config path/to/config.yaml

# Override specific settings via CLI flags
vibelens serve --host 0.0.0.0 --port 8080

# Override via environment variables
VIBELENS_PORT=8080 VIBELENS_MONGODB_URI=mongodb://localhost vibelens serve
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VIBELENS_HOST` | `127.0.0.1` | Server bind address |
| `VIBELENS_PORT` | `12001` | Server port |
| `VIBELENS_DB_PATH` | `~/.vibelens/vibelens.db` | SQLite database file |
| `VIBELENS_CLAUDE_DIR` | `~/.claude` | Claude Code history root |
| `VIBELENS_MONGODB_URI` | *(empty)* | MongoDB connection URI |
| `VIBELENS_MONGODB_DB` | `vibelens` | MongoDB database name |
| `VIBELENS_HF_TOKEN` | *(empty)* | HuggingFace API token |
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
    settings.py        # Pydantic Settings model and load_settings()
    loader.py          # YAML config loading and auto-discovery
    validators.py      # Integration config validators
  ingest/              # Format parsers and analysis
    base.py            # BaseParser ABC with shared helpers
    claude_code.py     # Claude Code JSONL parser
    codex.py           # Codex CLI rollout parser
    gemini.py          # Gemini CLI session parser
    dataclaw.py        # Dataclaw HuggingFace export parser
    correlator.py      # Cross-agent session correlation
    tool_normalizers.py # Tool categorization and summary extraction
    diagnostics.py     # Parse quality metrics collection
    fingerprint.py     # Format auto-detection with confidence scoring
    tool_graph.py      # Tool call dependency DAG construction
    phase_detector.py  # Session conversation phase classification
    parallel.py        # Multi-file parallel parsing
  models/              # Pydantic domain models
    message.py         # Message, ToolCall, TokenUsage, ContentBlock, SubAgentSession
    session.py         # SessionSummary, SessionDetail, ParseDiagnostics
    requests.py        # API request/response models
    analysis.py        # Analytics result models
  sources/             # Data source connectors (local, HuggingFace, MongoDB)
  targets/             # Data target connectors (MongoDB, HuggingFace)
  analysis/            # Session analytics and pattern detection
  api/                 # FastAPI route handlers
  utils/               # Shared utilities (logging, timestamps, paths, JSON)
  db.py                # SQLite database layer
  app.py               # FastAPI application factory
  cli.py               # Typer CLI entrypoint
frontend/              # React + Vite + Tailwind UI
  src/
    components/
      session-list.tsx       # Filterable session list with multi-select
      session-view.tsx       # Full session viewer with metadata and messages
      message-block.tsx      # Rich message rendering with tool-specific views
      sub-agent-block.tsx    # Collapsible sub-agent hierarchy display
      prompt-nav-panel.tsx   # Right sidebar prompt navigation
      confirm-dialog.tsx     # Modal confirmation dialog
      collapsible-pill.tsx   # Reusable expandable panel
      markdown-renderer.tsx  # Markdown content rendering
      copy-button.tsx        # Clipboard copy with feedback
```

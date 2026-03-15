# VibeLens

Agent trajectory analysis and visualization platform. Parses, normalizes, and visualizes conversation histories from multiple coding agent CLIs (Claude Code, Codex, Gemini, Dataclaw), stores them in SQLite, and serves them through a FastAPI backend with a React frontend.

## Features

### Multi-Agent Ingestion
- **Claude Code**: Parse `~/.claude/` conversation history, including subagent sessions
- **Codex CLI**: Parse `~/.codex/` rollout JSONL files (OpenAI Responses API format)
- **Gemini CLI**: Parse `~/.gemini/` session JSON files with hash directory resolution
- **Dataclaw**: Import HuggingFace-exported JSONL datasets
- **Auto-detection**: `fingerprint_file()` probes files and returns ranked format matches with confidence scores; `parse_auto()` selects the right parser automatically

### Data Sources
- **Local source**: Discover and parse sessions from local agent data directories
- **HuggingFace source**: Pull dataclaw-exported datasets from HuggingFace repos

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
- **REST API**: FastAPI backend for session listing, filtering, pagination, and detail views
- **React frontend**: Session browser with message rendering and tool-call visualization

## Quick Start

```bash
uv sync
uv run vibelens serve
```

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
    message.py         # Message, ToolCall, TokenUsage, ContentBlock
    session.py         # SessionSummary, SessionDetail, ParseDiagnostics
    requests.py        # API request/response models
  sources/             # Data source connectors (local, HuggingFace)
  targets/             # Data target connectors (MongoDB, HuggingFace)
  analysis/            # Session analytics and pattern detection
  api/                 # FastAPI route handlers
  utils/               # Shared utilities (logging, timestamps, paths, JSON)
  db.py                # SQLite database layer
  app.py               # FastAPI application factory
  cli.py               # Typer CLI entrypoint
frontend/              # React + Vite + Tailwind UI
```

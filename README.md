# VibeLens

Agent trajectory analysis and visualization platform. Parses Claude Code conversation logs and dataclaw-exported datasets, stores them in SQLite, and serves them through a FastAPI backend with a React frontend.

## Features

- **Local source**: Parse `~/.claude/` conversation history, including subagent sessions
- **HuggingFace source**: Pull dataclaw-exported datasets from HuggingFace repos
- **Pluggable parsers**: Abstract `BaseParser` with `ClaudeCodeParser` and `DataclawParser` implementations
- **SQLite storage**: Persistent session and message storage with async access
- **REST API**: FastAPI backend for session listing, filtering, and detail views
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
uv run pytest

# Frontend
cd frontend
npm install
npm run dev
```

## Architecture

```
src/vibelens/
  ingest/          # Format parsers (BaseParser, ClaudeCodeParser, DataclawParser)
  sources/         # Data sources (LocalSource, HuggingFaceSource)
  models/          # Pydantic models (Message, Session, Analysis)
  api/             # FastAPI route handlers
  utils/           # Shared utilities (logging, timestamps, paths)
  db.py            # SQLite database layer
  app.py           # FastAPI application factory
  cli.py           # Typer CLI entrypoint
frontend/          # React + Vite + Tailwind UI
```

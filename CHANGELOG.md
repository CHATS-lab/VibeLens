# Changelog

## [0.1.0] - 2026-03-14

### Added
- Project skeleton with FastAPI backend, React frontend, and CLI entrypoint.
- `BaseParser` abstract base class for pluggable format parsers.
- `ClaudeCodeParser` for parsing `~/.claude/` JSONL conversation logs.
- Subagent parsing: `ClaudeCodeParser` discovers and parses `{session-id}/subagents/agent-*.jsonl` files.
- `DataclawParser` for parsing dataclaw-exported HuggingFace datasets.
- `LocalSource` for reading sessions from the local Claude Code directory.
- `HuggingFaceSource` for downloading and importing dataclaw datasets.
- SQLite database layer with async access via `aiosqlite`.
- Pydantic models for sessions, messages, tool calls, and token usage.
- Shared utilities for logging, timestamps, path encoding, and JSON helpers.
- REST API endpoints for session listing, filtering, pagination, and detail views.
- React frontend with session list, session detail, and message rendering components.
- Comprehensive test suite (139 passing tests across parsers, sources, models, and DB).
- Reference repos and documentation links in CLAUDE.md.

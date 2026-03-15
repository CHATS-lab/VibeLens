# Changelog

## [0.2.0] - 2026-03-15

### Added
- **Codex CLI parser** (`CodexParser`): Parse `~/.codex/sessions/` rollout JSONL files using the OpenAI Responses API format.
- **Gemini CLI parser** (`GeminiParser`): Parse `~/.gemini/tmp/{hash}/chats/session-*.json` files with 4-tier project path resolution (`.project_root`, `projects.json`, hash fallback, tool argument inference).
- **Cross-agent session correlator** (`correlate_sessions`): Match sessions across different agents by overlapping time windows and shared project directories.
- **Tool normalization** (`tool_normalizers.py`): Unified `categorize_tool()` mapping tool names to semantic categories (file_read, file_write, shell, search, web, agent), `summarize_tool_input()` for one-line input summaries, and `summarize_tool_output()` for output digests.
- **Parse diagnostics** (`DiagnosticsCollector`): Tracks skipped lines, orphaned tool calls/results, and computes a completeness score. Integrated into all 4 parsers.
- **Tool call dependency graph** (`tool_graph.py`): `build_tool_graph()` infers causal relationships (read-before-write, search-then-read, error-retry, sequential) and produces a DAG.
- **Session phase detection** (`phase_detector.py`): `detect_phases()` classifies session segments into phases (exploration, implementation, debugging, verification, planning) using sliding-window analysis.
- **Format auto-detection** (`fingerprint.py`): `fingerprint_file()` probes files and returns ranked format matches with confidence scores. `parse_auto()` selects the right parser automatically.
- **Parallel multi-file parsing** (`parallel.py`): `parse_files_parallel()` uses `ProcessPoolExecutor` for CPU-bound JSONL parsing across multiple files.
- **Streaming history index**: `parse_history_index()` now supports `since` and `limit` parameters for efficient filtering of large history files. Added `count_history_entries()` for O(1) memory line counting.
- **Timestamp validation**: `MIN_VALID_EPOCH` / `MAX_VALID_EPOCH` range guards reject timestamps before 2015 or after 2035. Added `safe_int()` for NaN/Inf/None-safe integer conversion.
- **Defensive type guards**: `coerce_to_string()`, `coerce_to_list()`, `extract_text_from_blocks()` handle polymorphic content fields across all agent formats.
- **Idempotent ID generation**: `deterministic_id()` produces SHA-256-based repeatable identifiers, replacing `uuid4()` in Dataclaw and Gemini parsers for cache/dedup compatibility.
- **Bounded tool result cache**: Claude Code and Codex parsers use `OrderedDict` bounded at 500 entries instead of unbounded dicts, reducing memory for large sessions.
- **`output_digest` field on `ToolCall`**: One-line digest of tool output signal (e.g., "42 lines", "ERROR: file not found", "applied").
- **Subagent session model**: `SubAgentSession` preserves cascade hierarchy without merging sub-agent messages into the main session.
- **API request models**: `PushRequest`, `PullRequest`, `PushResult`, `PullResult`, `RemoteSessionsQuery` in `models/requests.py`.
- Test suite expanded from 139 to 480 tests covering all new modules.

### Changed
- `BaseParser.enrich_tool_calls()` now also populates `output_digest` from tool output.
- `BaseParser.iter_jsonl_safe()` accepts optional `DiagnosticsCollector` for tracking parse quality metrics.
- All parsers refactored to use shared `coerce_to_string()` for content extraction instead of ad-hoc inline type checking.
- Gemini parser `resolve_project_path()` extended with 4th-tier resolution via tool call argument inspection.

### Fixed
- `parse_auto()` error message had incorrect ternary operator precedence, producing "no matches" instead of the intended message.
- Parsers no longer silently produce different IDs when parsing the same file twice (idempotent IDs).
- Timestamp parsing now rejects `float('inf')`, `float('nan')`, negative values, and out-of-range dates instead of producing garbage datetimes.

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

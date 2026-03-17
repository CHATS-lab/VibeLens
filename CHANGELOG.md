# Changelog

## [0.5.0] - 2026-03-17

### Added
- **Two-mode system**: Self-use (default) and demo mode with configurable storage backends.
  - `AppMode` enum (`self` / `demo`) controls application behavior.
  - `SessionStore` protocol with `SqliteSessionStore` and `MemorySessionStore` implementations in new `stores/` package.
  - Per-tab client isolation via `X-Session-Token` header and `crypto.randomUUID()` in React.
  - Background TTL cleanup evicts orphaned demo uploads after configurable timeout.
- **Demo mode**: Pre-loaded example sessions visible to all clients, ephemeral uploads scoped per browser tab, lost on page refresh.
  - In-memory storage (default) or SQLite persistence for demo uploads.
  - `SHARED_TOKEN` sentinel for shared example sessions.
  - Example session loading at startup via `parse_auto()`.
- **Config templates** (`config/`): `self-use.yaml`, `demo-memory.yaml`, `demo-sqlite.yaml`, `vibelens.example.yaml`.
- **Example sessions** (`examples/`): Bundled Claude Code, Codex, and Gemini example files for demo mode.
- **VibeLens Export v1** parser (`vibelens.py`): Parse re-imported VibeLens export JSON files.
- **Zip upload** (`POST /api/upload/zip`): Upload zip archives containing multiple session files.
- **Batch download** (`POST /api/sessions/download`): Export multiple sessions as a zip archive.
- **`sub_agent_count`** field on `SessionSummary` for displaying sub-agent counts in the session header.
- **Integration tests** (`test_examples.py`): 28 tests parsing real example data files to verify metadata, content, and token aggregation.
- Settings fields: `app_mode`, `demo_storage`, `demo_example_sessions`, `demo_session_ttl`, `demo_persist_uploads`.
- Environment variables: `VIBELENS_APP_MODE`, `VIBELENS_DEMO_STORAGE`, `VIBELENS_DEMO_EXAMPLE_SESSIONS`, `VIBELENS_DEMO_SESSION_TTL`, `VIBELENS_DEMO_PERSIST_UPLOADS`.

### Changed
- **Frontend**: `AppContext` provides `sessionToken`, `appMode`, `fetchWithToken` to all components. Collect/Resume buttons hidden in demo mode.
- **Session endpoints**: All endpoints accept `X-Session-Token` header and branch on `is_demo_mode()`.
- **Upload endpoints**: Mode-aware storage routing through `SessionStore` instead of direct SQLite.
- **System endpoints**: `GET /api/settings` returns `app_mode`; sources/targets filtered by mode.
- `vibelens.example.yaml` moved to `config/vibelens.example.yaml`.
- README updated with two-mode documentation, config templates table, and new environment variables.
- CLAUDE.md project structure updated with `stores/`, `config/`, `examples/` directories.

### Fixed
- **Claude Code parser**: `parse_file()` now populates `timestamp`, `duration`, `tool_call_count`, `models`, `project_name`, `project_id`, and all token counts from `compute_session_metadata()`.
- **Claude Code project name**: New `_extract_project_path()` reads `cwd` field from JSONL entries to derive project name.
- **Gemini empty content**: Messages with only `thoughts` (no content) now use thinking text as display content instead of rendering blank.
- **Gemini token totals**: Summary now aggregates `total_input_tokens`, `total_output_tokens`, `total_cache_read` from per-message token data.
- **Gemini project resolution**: New `_resolve_project()` chains three strategies — filesystem layout, `projectHash` SHA-256 reverse-lookup against `~/.gemini/projects.json`, and tool call argument inference. Handles both current (`{projects: {path: dirname}}`) and legacy projects.json formats.
- **Gemini JSON fingerprinting**: `_probe_json()` now reads the full file instead of truncating at 8KB, fixing detection failure for files larger than `MAX_PROBE_BYTES`.
- **Memory store sorting**: `list_sessions()` coerces timestamps to `str()` to avoid `TypeError` when mixing `str` and `datetime` objects.

## [0.4.0] - 2026-03-16

### Added
- **File upload** (`POST /api/upload`): Upload conversation files (JSONL/JSON) directly through the UI with auto-format detection and SQLite persistence.
- **Upload dialog** (`upload-dialog.tsx`): Drag-and-drop / file picker dialog for uploading conversation files with progress feedback.
- **Session export** (`GET /api/sessions/{id}/export`): Download individual sessions as JSON in MongoDB document format (`{session, messages}`).
- **View modes** (`session-list.tsx`): Toggle between "By Time" (flat chronological list) and "By Project" (collapsible grouped headers) views.
- **Resizable panels** (`resize-handle.tsx`): Drag-to-resize left sidebar (240–600px) and right prompt navigation panel (160–400px).
- **SQLite session merging** (`sessions.py`): Unified session listing across local files and SQLite (upload/huggingface sources), deduplicated and sorted by timestamp.

### Changed
- **Parsers refactored** into `ingest/parsers/` sub-package: `base.py`, `claude_code.py`, `codex.py`, `gemini.py`, `dataclaw.py` moved from flat `ingest/` module.
- **MongoDB serialization** functions `serialize_session()` and `flatten_messages()` made public (renamed from private `_serialize_*` / `_flatten_*`) for reuse in export endpoint.
- **Global scroll disabled**: `overflow: hidden` on `html/body/#root` prevents outer page scrolling; only inner containers scroll.
- **Download button** replaces clipboard copy in session header — triggers real file download instead of copying JSON to clipboard.
- **Project dropdown removed** from session list sidebar; project grouping is now handled by the "By Project" view mode.
- **Pagination moved** to sidebar footer bar; only visible in "By Time" mode.
- **Session count** displayed in sidebar footer alongside pagination controls.
- Tests updated for parser path changes, public MongoDB serialization functions, and new test directories (`tests/config/`, `tests/sources/`, `tests/targets/`, `tests/utils/`).
- Version bumped to 0.4.0.

## [0.3.0] - 2026-03-15

### Added
- **MongoDB target** (`MongoDBTarget`): Push parsed sessions to a remote MongoDB instance with two-collection design (sessions + messages), batch insert (500/batch), duplicate detection, and index creation.
- **MongoDB source** (`MongoDBSource`): Query sessions from MongoDB with filtering, pagination, and recursive sub-agent hierarchy reconstruction.
- **Config package** (`config/`): Refactored single `config.py` into `config/` package with `settings.py` (Pydantic Settings model), `loader.py` (YAML auto-discovery), and `validators.py` (integration config validators).
- **YAML configuration**: First-class YAML config file support with auto-discovery of `vibelens.yaml` in working directory, nested section structure, and env var overrides.
- **Push API** (`POST /api/push/mongodb`): Push selected sessions from SQLite to MongoDB with confirmation and result reporting.
- **System API**: `GET /api/settings`, `GET /api/sources`, `GET /api/targets` endpoints for runtime configuration introspection.
- **Frontend batch collection UI**: Multi-select checkboxes, select all/partial, confirmation dialog, push result display with error details.
- **Frontend session viewer**: Full session detail view with metadata pills (duration, turns, tools, models), token statistics grid, two-column layout with prompt navigation sidebar.
- **Frontend message rendering**: Role-specific message blocks with tool-specific renderers — `BashRenderer` (command + copy), `EditRenderer` (diff with +/- counts), `WriteRenderer` (file preview), `ReadRenderer` (path + language badge), `GrepRenderer`, `GlobRenderer`, and generic JSON fallback.
- **Frontend extended thinking**: Expandable amber panel for Claude's thinking tokens.
- **Frontend sub-agent display** (`sub-agent-block.tsx`): Collapsible nested panels for multi-agent cascade hierarchies with violet accent colors.
- **Frontend prompt navigation** (`prompt-nav-panel.tsx`): Right sidebar showing numbered user turns with scroll-to navigation via IntersectionObserver.
- **Frontend components**: `collapsible-pill.tsx`, `confirm-dialog.tsx`, `copy-button.tsx`, `markdown-renderer.tsx`.
- **App icon**: Custom VibeLens icon with transparent background, browser favicons (16px, 32px), and sidebar logo display.
- **File logging** (`utils/log.py`): Timestamped log files in `logs/` directory with configurable log level.
- **MongoDB specification document** (`docs/mongodb-target-spec.md`).
- Tests for MongoDB target and source (`test_targets_mongodb.py`, `test_sources_mongodb.py`), config package (`test_config.py`).

### Changed
- Config refactored from single `config.py` to `config/` package with YAML-first approach.
- `.env.example` removed in favor of `vibelens.example.yaml` with inline env var documentation.
- `deps.py` expanded with lazy-initialized MongoDB target/source singletons.
- `app.py` lifespan now initializes MongoDB connections and indexes on startup, cleans up on shutdown.
- `cli.py` enhanced with `--config` / `-c` flag and file logging setup.
- `db.py` updated with source tracking columns and token usage aggregation.
- Frontend sidebar enlarged with VibeLens icon (48px) and branding (text-2xl).
- Session list now supports project filtering, search, and pagination (100 sessions/page).
- Version bumped to 0.3.0.

### Fixed
- `vibelens.example.yaml` sanitized to remove hardcoded credentials.

## [0.2.0] - 2026-03-15

### Added
- **Codex CLI parser** (`CodexParser`): Parse `~/.codex/sessions/` rollout JSONL files using the OpenAI Responses API format.
- **Gemini CLI parser** (`GeminiParser`): Parse `~/.gemini/tmp/{hash}/chats/session-*.json` files with 4-tier project path resolution (`.project_root`, `projects.json`, hash fallback, tool argument inference).
- **Cross-agent session correlator** (`correlate_sessions`): Match sessions across different agents by overlapping time windows and shared project directories.
- **Tool normalization** (`tool_normalizers.py`): Unified `categorize_tool()` mapping tool names to semantic categories (file_read, file_write, shell, search, web, agent), `summarize_tool_input()` for one-line input summaries, and `summarize_tool_output()` for output digests.
- **Parse diagnostics** (`DiagnosticsCollector`): Tracks skipped lines, orphaned tool calls/results, and computes a completeness score. Integrated into all 4 parsers.
- **Tool call dependency graph** (`tool_graph.py`): `build_tool_graph()` infers causal relationships (read-before-write, search-then-read, error-retry) and produces a DAG.
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

# Ingest Pipeline

Parser framework that converts raw agent conversation files into normalized ATIF trajectories.

## Purpose

Each coding agent CLI stores session data in its own format. The ingest layer provides a parser per format, a format auto-detection system, and shared utilities for tool normalization, diagnostics, and metrics extraction. All parsers produce `list[Trajectory]` output that the rest of the platform consumes uniformly.

## Architecture

```
Raw Agent Files
      |
      v
+------------------+
| discovery.py     |  Format auto-detection (confidence scoring)
+--------+---------+
         |
         v
+------------------+     +------------------+
| Parser per format|---->| BaseParser ABC   |  Shared helpers: truncation,
|  claude_code.py  |     | (parsers/base.py)|  metadata, tool enrichment
|  codex.py        |     +------------------+
|  gemini.py       |
|  dataclaw.py     |
|  openclaw.py     |
|  claude_code_web |
|  parsed.py       |
+--------+---------+
         |
         v
+------------------+
| list[Trajectory] |  Normalized ATIF v1.6 output
+------------------+
```

## Key Files

| File | Role |
|------|------|
| `ingest/parsers/base.py` | `BaseParser` ABC with shared helpers |
| `ingest/parsers/claude_code.py` | Claude Code JSONL parser (sub-agent cascade, tool result pairing) |
| `ingest/parsers/claude_code_web.py` | Claude Code web export parser |
| `ingest/parsers/codex.py` | Codex CLI parser (OpenAI Responses API format) |
| `ingest/parsers/gemini.py` | Gemini CLI parser (parts-based content) |
| `ingest/parsers/dataclaw.py` | Dataclaw HuggingFace JSONL parser |
| `ingest/parsers/openclaw.py` | OpenClaw event-based JSONL parser |
| `ingest/parsers/parsed.py` | `ParsedTrajectoryParser` for pre-parsed JSON |
| `ingest/discovery.py` | Format fingerprinting and auto-detection |
| `ingest/diagnostics.py` | Parse quality tracking per session |
| `ingest/fast_metrics.py` | Line-by-line JSONL scanner for aggregate metrics |
| `ingest/index_builder.py` | Skeleton trajectory builder for LocalStore |
| `ingest/index_cache.py` | Persistent JSON cache for fast startup |

## BaseParser ABC

All parsers extend `BaseParser`, which provides:

- `parse_file(path)` -- Abstract method each parser implements
- `discover_session_files(data_dir)` -- Find parseable files in an agent data directory
- `parse_session_index(data_dir)` -- Fast index parsing (optional, for Claude Code and Codex)
- `get_session_files(session_file)` -- All files belonging to a session (base: single file; Claude Code: main + sub-agents)
- `truncate_first_message(text)` -- Cap at 200 chars
- `find_first_user_text(messages)` -- Extract first meaningful user prompt
- `iter_jsonl_safe(path, diagnostics)` -- Resilient JSONL parsing, skips malformed lines

## Parser Implementations

| Parser | Agent | Source Format | Key Features |
|--------|-------|---------------|--------------|
| `ClaudeCodeParser` | Claude Code | JSONL per session | History index parsing, sub-agent discovery, tool result pairing, content block extraction |
| `ClaudeCodeWebParser` | Claude Code (web) | JSON export | Web UI conversation export |
| `CodexParser` | Codex CLI | JSONL rollout files | OpenAI Responses API reconstruction, function call extraction |
| `GeminiParser` | Gemini CLI | JSON per session | Parts-based content, project resolution via `.project_root` |
| `DataclawParser` | Dataclaw | HuggingFace JSONL | Multi-session JSONL, format auto-detection |
| `OpenClawParser` | OpenClaw | Event-based JSONL | `type: "message"` wrapping, session index support |
| `ParsedTrajectoryParser` | Pre-parsed | JSON array | Loads already-parsed trajectory groups (DiskStore) |

## Agent Data Directories (macOS)

| Agent | Directory | Format |
|-------|-----------|--------|
| Claude Code | `~/.claude/` | `history.jsonl` index + `projects/{path}/{uuid}.jsonl` sessions |
| Codex | `~/.codex/sessions/YYYY/MM/DD/` | `rollout-*.jsonl` per session |
| Gemini | `~/.gemini/tmp/{sha256}/chats/` | `session-*.json` per session |
| OpenClaw | `~/.openclaw/agents/main/sessions/` | `{uuid}.jsonl` per session |
| Dataclaw | HuggingFace exports | `conversations.jsonl` (one session per line) |

## Format Auto-Detection

`discovery.py` probes the first 10 lines (up to 8KB) of a file to determine its format. Returns `list[FormatMatch]` sorted by confidence (0.0-1.0).

Detection heuristics use structural field presence (e.g., `"type": "user"` for Claude Code, `"contents"` + `"parts"` for Gemini).

## Diagnostics

`DiagnosticsCollector` tracks parse quality per session:

| Metric | Description |
|--------|-------------|
| `skipped_lines` | Malformed JSONL lines skipped |
| `orphaned_tool_calls` | `tool_use` without matching `tool_result` |
| `orphaned_tool_results` | `tool_result` without matching `tool_use` |
| `completeness_score` | 0.0-1.0 overall parse quality |

## Fast Metrics Scanner

`fast_metrics.py` extracts aggregate metrics from raw JSONL files without full Pydantic parsing. Used by `LocalStore._enrich_skeleton_metrics()` for fast startup.

Scans line-by-line to accumulate: input/output/cache tokens, tool call count, model name, message count, and timestamps (for duration). Deduplicates by message ID to handle streaming chunks.

## Index Builder

`index_builder.py` builds skeleton trajectories (metadata only, no steps) from all agent parsers. Called by `LocalStore._full_rebuild()`.

Pipeline: collect skeletons (fast index or full parse) -> deduplicate and validate -> enrich continuation chain refs.

## Index Cache

`index_cache.py` provides persistent JSON cache at `~/.vibelens/index_cache.json` for fast startup. Tracks file mtimes to detect staleness:

- All mtimes match: cache hit (instant restore)
- < 30% files changed: incremental update (re-parse stale only)
- >= 30% files changed: full rebuild

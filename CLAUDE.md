# CLAUDE.md — VibeLens

Agent trajectory analysis and visualization platform. Parses, normalizes, and visualizes conversation histories from multiple coding agent CLIs.

## Project Structure

```
src/vibelens/
├── ingest/                # Format-specific parsers and analysis
│   ├── base.py            # BaseParser ABC with shared helpers
│   ├── claude_code.py     # Claude Code JSONL parser
│   ├── codex.py           # Codex CLI rollout parser
│   ├── gemini.py          # Gemini CLI session parser
│   ├── dataclaw.py        # Dataclaw HuggingFace export parser
│   ├── correlator.py      # Cross-agent session correlation
│   ├── tool_normalizers.py # Tool categorization and summary extraction
│   ├── diagnostics.py     # Parse quality metrics (DiagnosticsCollector)
│   ├── fingerprint.py     # Format auto-detection with confidence scoring
│   ├── tool_graph.py      # Tool call dependency DAG construction
│   ├── phase_detector.py  # Session conversation phase classification
│   └── parallel.py        # Multi-file parallel parsing (ProcessPoolExecutor)
├── models/                # Pydantic domain models
│   ├── message.py         # Message, ToolCall, TokenUsage, ContentBlock, SubAgentSession
│   ├── session.py         # SessionSummary, SessionDetail, ParseDiagnostics
│   ├── requests.py        # API request/response models
│   └── analysis.py        # Analytics result models
├── analysis/              # Session analytics and pattern detection
├── api/                   # FastAPI routes
├── sources/               # Data source connectors (local, HuggingFace)
├── targets/               # Data target connectors (MongoDB, HuggingFace)
├── utils/                 # Shared utilities (timestamps, paths, JSON helpers, logging)
├── config.py              # Pydantic settings
├── db.py                  # SQLite persistence
├── cli.py                 # Typer CLI entrypoint
└── app.py                 # FastAPI app factory
tests/
├── ingest/                # Parser tests
├── models/                # Model tests
├── test_timestamps.py     # Timestamp validation tests
└── ...                    # Other module tests
```

## Agent Data Directories (macOS)

- **Claude Code:** `~/.claude/` — `history.jsonl` index + `projects/{encoded-path}/{uuid}.jsonl` sessions. Sub-agents in `{uuid}/subagents/agent-*.jsonl`.
- **Codex CLI:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — One rollout file per session. Uses OpenAI Responses API format.
- **Gemini CLI:** `~/.gemini/tmp/{sha256-hash}/chats/session-*.json` — Single JSON per session. Hash dirs resolved via `.project_root` file or `projects.json`.
- **Dataclaw:** HuggingFace JSONL exports — One complete session per line in `conversations.jsonl`.

## Documentation References

- `docs/CLAUDE_LOCAL_STRUCTURE.md` — Claude Code `~/.claude/` directory structure and JSONL format
- `docs/codex/CODEX_LOCAL_STRUCTURE.md` — Codex CLI `~/.codex/` directory structure and rollout format
- `docs/gemini-cli/GEMINI_LOCAL_STRUCTURE.md` — Gemini CLI `~/.gemini/` directory structure and session format
- `docs/PRODUCT_SPEC.md` — Product specification
- `docs/TECHNICAL_DESIGN.md` — Technical design document
- `docs/ANALYSIS_DESIGN.md` — Analytics module design

Links:
- [Deep Dive: How Claude Code's /insights Command Works](https://www.zolkos.com/2026/02/04/deep-dive-how-claude-codes-insights-command-works.html)


## General Rules

- One function does one thing. If you need the word "and" to describe what it does, split it.
- Functions should be short enough to fit on one screen (~30 lines). If longer, extract helpers.
- No magic numbers or strings. Use named constants with ALL_CAPS.
- No dead code. Delete unused imports, variables, functions, and commented-out blocks. Version control remembers.
- No copy-paste duplication. If you write the same logic twice, extract it. Three times means you needed an abstraction yesterday.
- Fail fast, fail loud. Validate inputs at the boundary. Raise specific exceptions with actionable messages, not generic ones.
- Return early. Use guard clauses to eliminate nesting. Avoid deep if-else chains.
- Limit function arguments to 3. If you need more, group them into a dataclass, dict, or config object.
- Add typing annotation to function input parameters.

## Python Conventions

- **Linter:** Ruff. All code must pass before commit.
- **Imports:** Grouped (stdlib, third-party, local). No wildcards. No in-function imports.
- **Types:** Annotate all function signatures. Use `Optional[X]`.
- **Docstrings:** Google style on all public functions/classes/modules.
- **Errors:** Catch specific exceptions. Never bare `except:`.
- **Strings:** f-strings in code, lazy `%s` in logger calls.
- **Do NOT use:** `from __future__ import annotations`, section-divider comments.
- **Comment**: Add typing annotation for methods. No blank lines after section comment headers (# ─── ...).
- **Prompts**: Use the """ triple-quoted string conversion for long-text prompts. Not use \ line continuations to separate a single line.

## Architecture Rules

- All parsers extend `BaseParser` (ABC in `ingest/base.py`).
- Sub-agent messages must NOT be merged into the main session message list. Use `SubAgentSession` for cascade hierarchy.
- Tool calls are enriched with `category`, `summary`, and `output_digest` via `tool_normalizers.py` and `BaseParser.enrich_tool_calls()`.
- Timestamps: use `normalize_timestamp()` from `utils/timestamps.py` for auto-detection of format (ISO-8601, ms-epoch, s-epoch). All timestamps are validated against `MIN_VALID_EPOCH`/`MAX_VALID_EPOCH`.
- JSONL reading: use `BaseParser.iter_jsonl_safe()` for OSError-resilient parsing. Pass a `DiagnosticsCollector` to track parse quality.
- Content extraction: use `coerce_to_string()` from `utils/json_helpers.py` for polymorphic content fields.
- IDs for generated objects: use `deterministic_id()` from `utils/json_helpers.py` instead of `uuid4()` for repeatable identifiers.
- Format detection: use `fingerprint_file()` / `parse_auto()` from `ingest/fingerprint.py` for unknown file formats.

## Testing

- Tests organized in sub-directories matching source layout: `tests/ingest/`, `tests/models/`.
- Tests should log detailed output with `print()` for manual verification, not just assertions.
- Run: `pytest tests/ -v -s` (use `-s` to see print output).
- Ruff: `ruff check src/ tests/`

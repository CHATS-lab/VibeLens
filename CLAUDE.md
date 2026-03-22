# CLAUDE.md — VibeLens

Agent trajectory analysis and visualization platform. Parses, normalizes, and visualizes conversation histories from multiple coding agent CLIs using the ATIF v1.6 trajectory model.

## Project Structure

```
src/vibelens/
├── api/               # FastAPI route handlers. Thin HTTP layer delegating to services/.
├── analysis/          # Pure computation on trajectories → analytics results.
│                      # No Pydantic model definitions here — output models live in models/analysis/.
├── config/            # Pydantic Settings model, YAML config loading, auto-discovery.
├── ingest/            # Raw data → ATIF trajectories. Parsers, discovery, fingerprinting.
│   └── parsers/       # One parser per agent CLI format (Claude Code, Codex, Gemini, Dataclaw).
├── llm/               # LLM utilities — pricing, model name normalization, semantic analysis.
│   └── pricing/       # Pricing table (reference data), model name resolution, cost lookup.
├── models/            # Pydantic domain models (no business logic, no I/O).
│   ├── analysis/      # Output models for analytics (dashboard stats, phases, tool graphs, correlator, pricing).
│   └── trajectories/  # ATIF v1.6 trajectory model (Step, ToolCall, Observation, Metrics, etc.).
├── services/          # Orchestration layer: caching, I/O, store integration, export.
├── storage/           # Trajectory storage backends (read-only TrajectoryStore ABC + DiskStore, LocalStore).
├── utils/             # Shared utilities (logging, timestamps, paths, JSON helpers, zip).
├── static/            # Frontend build assets served by FastAPI.
├── deps.py            # Singleton DI: get_settings(), get_store(), is_demo_mode().
├── app.py             # FastAPI app factory (mode-aware lifespan).
└── cli.py             # Typer CLI entrypoint.
config/                # Configuration templates (self-use.yaml, demo.yaml).
frontend/              # React + Vite + Tailwind UI.
│   └── src/
│       └── components/  # Session viewer, dashboard charts, shared UI.
tests/                 # Unit and integration tests mirroring src/ structure.
```

## Key Concepts

- **Trajectory**: Root container for a single agent session — includes steps, agent metadata, final metrics, and cross-references.
- **Step**: One turn in a conversation (user prompt, agent response, or system message) with optional tool calls and observations.
- **TrajectoryRef**: Cross-reference linking trajectories — `last_trajectory_ref` for session continuation, `parent_trajectory_ref` for sub-agent lineage, `subagent_trajectory_ref` on observation results for spawn linkage.
- **TrajectoryStore**: Read-only ABC in `storage/`. `LocalStore` reads from `~/.claude/`, `DiskStore` reads/writes JSON files.

## Agent Data Directories (macOS)

- **Claude Code:** `~/.claude/` — `history.jsonl` index + `projects/{encoded-path}/{uuid}.jsonl` sessions. Sub-agents in `{uuid}/subagents/agent-*.jsonl`.
- **Codex CLI:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — One rollout file per session. Uses OpenAI Responses API format.
- **Gemini CLI:** `~/.gemini/tmp/{sha256-hash}/chats/session-*.json` — Single JSON per session. Hash dirs resolved via `.project_root` file or `projects.json`.
- **Dataclaw:** HuggingFace JSONL exports — One complete session per line in `conversations.jsonl`.

## Reference Repos

- [Claude-Run](https://github.com/kamranahmedse/claude-run). Beautiful UI.
- [CooperBench Website](https://github.com/cooperbench/website). Many analysis indicator.

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
- Add detailed comments to complex code.

## Python Conventions

- **Linter:** Ruff. All code must pass before commit.
- **Imports:** Grouped (stdlib, third-party, local). No wildcards. No in-function imports.
- **Types:** Annotate all function signatures. Use `Optional[X]`.
- **Docstrings:** Google style on all public functions/classes/modules.
- **Errors:** Catch specific exceptions. Never bare `except:`.
- **Strings:** f-strings in code, lazy `%s` in logger calls.
- **Do NOT use:** `from __future__ import annotations`, section-divider comments.
- **Comment**: Add typing annotation for methods. No section comment headers (# ─── ...).
- **Prompts**: Use the """ triple-quoted string conversion for long-text prompts. Not use \ line continuations to separate a single line.
- **BaseModel**: All Pydantic `BaseModel` fields must use `Field(description=...)` to document their purpose.

## Testing

- Ruff: `ruff check src/ tests/`
- Run: `pytest tests/ -v -s` (use `-s` to see print output).
- Tests should log detailed output with `print()` for manual verification, not just assertions.

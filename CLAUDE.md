# CLAUDE.md — VibeLens

Agent trajectory analysis and visualization platform. Parses, normalizes, and visualizes conversation histories from multiple coding agent CLIs using the ATIF v1.6 trajectory model.

## Project Structure

```
src/vibelens/
├── ingest/                # Format-specific parsers and ingestion pipeline
│   ├── parsers/           # Format-specific parser implementations
│   │   ├── base.py        # BaseParser ABC with shared helpers
│   │   ├── claude_code.py # Claude Code JSONL parser
│   │   ├── codex.py       # Codex CLI rollout parser
│   │   ├── gemini.py      # Gemini CLI session parser
│   │   ├── dataclaw.py    # Dataclaw HuggingFace export parser
│   │   └── vibelens.py    # VibeLens Export v1 parser
│   ├── discovery.py       # Recursive session file finder for all agent formats
│   ├── diagnostics.py     # Parse quality metrics (DiagnosticsCollector)
│   ├── fingerprint.py     # Format auto-detection with confidence scoring
│   └── parallel.py        # Multi-file parallel parsing (ProcessPoolExecutor)
├── models/                # Pydantic domain models
│   ├── trajectories/      # ATIF v1.6 trajectory model
│   │   ├── trajectory.py  # Root Trajectory container
│   │   ├── step.py        # Step (user/agent/system turn)
│   │   ├── agent.py       # Agent metadata (name, version, model)
│   │   ├── tool_call.py   # Tool invocation with arguments
│   │   ├── observation.py # Tool execution result container
│   │   ├── observation_result.py # Individual tool result
│   │   ├── metrics.py     # Per-step token metrics
│   │   ├── final_metrics.py # Session-level aggregate metrics
│   │   ├── trajectory_ref.py # Cross-references (continuation, sub-agent)
│   │   └── content.py     # Multimodal content (text, image, PDF)
│   ├── enums.py           # AgentType, AppMode, StepSource, ContentType
│   ├── analysis.py        # Analytics result models
│   └── requests.py        # API request/response models
├── stores/                # Trajectory storage backends
│   ├── base.py            # TrajectoryStore ABC (read-only interface)
│   ├── disk.py            # DiskStore — JSON file persistence for demo/uploads
│   └── local.py           # LocalStore — reads ~/.claude/ with lazy parsing
├── services/              # Business logic layer
│   ├── session_service.py # Session listing, retrieval, donation
│   ├── upload_service.py  # Zip upload pipeline (receive → extract → parse → store)
│   └── demo_loader.py     # Demo mode startup: load example trajectories
├── analysis/              # Session analytics and pattern detection
│   ├── correlator.py      # Cross-agent session correlation
│   ├── phase_detector.py  # Conversation phase classification
│   ├── tool_graph.py      # Tool call dependency DAG
│   ├── agent_behavior.py  # Agent behavior analysis
│   └── user_preference.py # User preference analysis
├── api/                   # FastAPI routes
│   ├── sessions.py        # Session CRUD + export + donate endpoints
│   ├── upload.py          # File upload endpoint
│   ├── analysis.py        # Analytics endpoints
│   └── system.py          # System config endpoints
├── config/                # Configuration package
│   ├── settings.py        # Pydantic Settings model (AppMode, UploadSettings)
│   └── loader.py          # YAML config loading and auto-discovery
├── utils/                 # Shared utilities
│   ├── log.py             # File logging setup
│   ├── timestamps.py      # Timestamp parsing and validation
│   ├── paths.py           # Path encoding and project name extraction
│   ├── json_helpers.py    # JSON serialization helpers
│   └── zip.py             # Zip archive utilities
├── deps.py                # Singleton DI: get_settings(), get_store(), is_demo_mode()
├── app.py                 # FastAPI app factory (mode-aware lifespan)
└── cli.py                 # Typer CLI entrypoint
config/                    # Configuration templates
├── self-use.yaml          # Self-use mode (reads ~/.claude/)
├── demo.yaml              # Demo mode with pre-loaded examples
└── vibelens.example.yaml  # Full reference config
frontend/                  # React + Vite + Tailwind UI
└── src/
    ├── app.tsx            # AppContext (fetchWithToken, appMode)
    ├── types.ts           # TypeScript types mirroring ATIF trajectory model
    ├── utils.ts           # Formatting helpers
    └── components/
        ├── session-list.tsx       # Filterable session list with view modes
        ├── session-view.tsx       # Session viewer with metadata + step rendering
        ├── message-block.tsx      # Step rendering with tool-specific views
        ├── step-timeline.tsx      # Visual timeline with elapsed time indicators
        ├── sub-agent-block.tsx    # Recursive sub-agent hierarchy display
        ├── prompt-nav-panel.tsx   # Right sidebar prompt navigation
        ├── upload-dialog.tsx      # File upload wizard
        └── ...                    # Shared UI components
tests/
├── ingest/                # Parser tests (claude_code, codex, gemini)
├── config/                # Config loading tests
├── conftest.py            # Shared fixtures with store singleton reset
└── test_e2e.py            # End-to-end API tests
```

## Key Concepts

- **Trajectory**: Root container for a single agent session — includes steps, agent metadata, final metrics, and cross-references.
- **Step**: One turn in a conversation (user prompt, agent response, or system message) with optional tool calls and observations.
- **TrajectoryRef**: Cross-reference linking trajectories — `last_trajectory_ref` for session continuation, `parent_trajectory_ref` for sub-agent lineage, `subagent_trajectory_ref` on observation results for spawn linkage.
- **TrajectoryStore**: Read-only ABC. `LocalStore` reads from `~/.claude/`, `DiskStore` reads/writes JSON files.

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

## Testing

- Ruff: `ruff check src/ tests/`
- Run: `pytest tests/ -v -s` (use `-s` to see print output).
- Tests should log detailed output with `print()` for manual verification, not just assertions.

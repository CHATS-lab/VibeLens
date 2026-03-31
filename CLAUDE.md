# CLAUDE.md — VibeLens

Agent trajectory analysis and visualization platform. Parses, normalizes, and visualizes conversation histories from multiple coding agent CLIs using the ATIF v1.6 trajectory model.

## Project Structure

```
src/vibelens/
├── api/               # FastAPI route handlers. Thin HTTP layer delegating to services/.
├── config/            # Pydantic Settings model, YAML config loading, auto-discovery.
├── ingest/            # Raw data → ATIF trajectories. Parsers, discovery, fingerprinting.
│   └── parsers/       # One parser per agent CLI format (Claude Code, Codex, Gemini, Dataclaw, OpenClaw).
├── llm/               # LLM utilities — pricing, model name normalization, semantic analysis.
│   └── pricing/       # Pricing table (reference data), model name resolution, cost lookup.
├── models/            # Pydantic domain models (no business logic, no I/O).
│   ├── analysis/      # Output models for analytics (dashboard stats, phases, tool graphs, correlator, pricing).
│   └── trajectories/  # ATIF v1.6 trajectory model (Step, ToolCall, Observation, Metrics, etc.).
├── schemas/           # API request/response schemas (HTTP boundary models).
├── services/          # Orchestration layer: caching, I/O, store integration, export.
│   ├── session/       # Session CRUD, search, sharing, flow analysis, demo loading, correlator, phases, tool graph.
│   ├── dashboard/     # Dashboard loading/caching, export, stats, analytics, tool usage, pricing.
│   ├── upload/        # ZIP upload processing, session visibility management.
│   ├── friction/      # Friction analysis, digest, store, mock, step signals.
│   └── skill/         # Skill analysis (retrieval, creation, evolvement), digest, store, mock.
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

## Agent Data Directories (macOS)

- **Claude Code:** `~/.claude/` — `history.jsonl` index + `projects/{encoded-path}/{uuid}.jsonl` sessions. Sub-agents in `{uuid}/subagents/agent-*.jsonl`.
- **Codex CLI:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` — One rollout file per session. Uses OpenAI Responses API format.
- **Gemini CLI:** `~/.gemini/tmp/{sha256-hash}/chats/session-*.json` — Single JSON per session. Hash dirs resolved via `.project_root` file or `projects.json`.
- **Dataclaw:** HuggingFace JSONL exports — One complete session per line in `conversations.jsonl`.
- **OpenClaw:** `~/.openclaw/agents/main/sessions/{uuid}.jsonl` — Event-based JSONL with `type: "message"` wrapping `role: user/assistant/toolResult`. Index at `sessions.json`.

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
- **Types:** Annotate all function signatures.
- **Docstrings:** Google style on all public functions/classes/modules.
- **Errors:** Catch specific exceptions. Never bare `except:`.
- **Strings:** f-strings in code, lazy `%s` in logger calls.
- **Do NOT use:** `from __future__ import annotations`, section-divider comments.
- **Comment**: Add typing annotation for methods. No section comment headers (# ─── ...).
- **Prompts**: Use the """ triple-quoted string conversion for long-text prompts. Not use \ line continuations to separate a single line.
- **BaseModel**: All Pydantic `BaseModel` fields must use `Field(description=...)` to document their purpose.

## Frontend Conventions (React + Vite + Tailwind)

- **Build:** `npm run build` in `frontend/`. Must pass with zero TypeScript errors before commit.
- **Component size:** One component per file, max ~200 lines. If longer, extract sub-components into separate files.
- **Shared UI:** Reusable primitives live in `components/` (e.g., `modal.tsx`, `tooltip.tsx`, `confirm-dialog.tsx`). Domain-specific shared components live in their feature folder (e.g., `skills/skill-badges.tsx`, `skills/skill-shared.tsx`).
- **Constants:** Extract repeated strings, colors, and config objects into dedicated `*-constants.ts` files. Global constants go in `styles.ts`.
- **Modals:** Always use the shared `Modal` / `ModalHeader` / `ModalBody` / `ModalFooter` from `components/modal.tsx`. Never hand-roll fixed-inset overlay markup.
- **Tooltips:** Always use the shared `Tooltip` from `components/tooltip.tsx`. It renders via portal, shows instantly, and auto-flips. Never use native `title` attributes — they have delayed display and unstyled appearance. Pass `className="min-w-0"` when the Tooltip wraps a truncated flex child.
- **Sidebar widths:** All right-side panels (prompt nav, friction history, skills history) must use the shared `SIDEBAR_DEFAULT_WIDTH`, `SIDEBAR_MIN_WIDTH`, `SIDEBAR_MAX_WIDTH` from `styles.ts`. Never hardcode panel widths locally.
- **Toggle buttons:** When a button toggles between labels of different lengths (e.g., "Project" / "Time"), use a fixed width (`w-[Npx]`) with `justify-center` to prevent layout shift.
- **Color theme:** Dark zinc base with semantic accent colors:
  - **Cyan** — navigation, primary accents, session ID tags, nav panel background (`bg-[#0d1520]`)
  - **Violet** — sub-agents, continuation chains, skills tab
  - **Teal** — plan/auto-prompt entries
  - **Blue** — view mode toggles
  - **Rose** — donate button, destructive actions
- **Dropdowns:** Use custom dropdown components (button + absolute menu) instead of native `<select>` elements. Native selects break the dark theme.
- **No dead imports:** Remove unused imports immediately. TypeScript strict mode catches these.
- **File splitting pattern:** For feature panels, use this structure:
  - `*-panel.tsx` — thin orchestrator (~100-150 lines) with tab routing and top-level state
  - `*-tab.tsx` — one file per tab with its own state management
  - `*-cards.tsx` — card and detail popup components
  - `*-shared.tsx` — reusable sub-components (search bars, filter bars, empty states)
  - `*-constants.ts` — color maps, label maps, config arrays

## Testing

- Ruff: `ruff check src/ tests/`
- Run: `pytest tests/ -v -s` (use `-s` to see print output).
- Tests should log detailed output with `print()` for manual verification, not just assertions.

## Release

1. **Version bump**: Update `version` in both `pyproject.toml` and `src/vibelens/__init__.py`.
2. **Changelog**: Add entry to `CHANGELOG.md` under `## [x.y.z] - YYYY-MM-DD`.
3. **Commit & push**: `git commit` then `git push origin main`.
4. **Tag**: `git tag v{version} {commit_sha}` then `git push origin v{version}`.
5. **GitHub Release**: `gh release create v{version} --title "v{version}" --latest --notes "..."`.
6. **PyPI**: `rm -rf dist/ && python -m build && twine upload dist/*`.

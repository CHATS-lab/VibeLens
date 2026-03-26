# Changelog

## [0.9.2] - 2026-03-25

### Fixed
- **Featured skill install**: Download complete skill directories from GitHub (SKILL.md + templates, scripts, etc.) instead of generating a stub.
- **Skill sync error**: Handle symlinked skill directories (e.g. from skillshub) when syncing to agent interfaces.
- **Skill history not loading**: Fix API route mismatch — frontend now calls correct `/api/skills/analysis/` endpoints.
- **Refresh button**: Force backend cache invalidation on manual refresh so deleted/added skills are reflected immediately.
- **CI**: Skip live LLM tests when `ANTHROPIC_API_KEY` is not set.

### Changed
- **Skill detail popup**: Render SKILL.md content as markdown instead of raw text. Enlarged title and tags for readability.
- **Main tab buttons**: Equal minimum width (`min-w-[100px]`) for consistent layout.

### Added
- **GitHub skill downloader**: `utils/github.py` — recursively downloads skill directories from GitHub via the Contents API with raw file fallback.

## [0.9.1] - 2026-03-25

### Added
- **Multi-agent skill ecosystem**: Central skill store (`~/.vibelens/skills/`) aggregates skills from Claude Code and Codex on startup. Cross-agent sync API copies skills between interfaces.
- **Featured skill catalog**: Browse and install community skills from the Anthropic registry via the new Explore Skills tab.
- **LLM-powered skill analysis**: Three modes — retrieval (recommend existing skills), creation (generate new SKILL.md), evolution (suggest edits) — with persistent history.
- **Context extraction & session batching**: Reusable modules for compressing trajectories into LLM-ready batches, shared by friction and skill analysis.
- **Shared UI components**: Extracted `Modal`, portal-based `Tooltip`, and skill UI primitives (badges, search bar, filter bar, empty states) into reusable files.
- **Separated LLM config**: Decoupled `LLMConfig` into `config/llm.yaml` with hot-reload support.

### Changed
- **Storage restructure**: Conversation stores moved to `storage/conversation/`; skill stores expanded with `CentralSkillStore` and `CodexSkillStore`.
- **Friction service refactor**: Split into `services/friction/` sub-package (`analysis.py`, `store.py`, `digest.py`). Reworked prompt templates.
- **Skills panel refactor**: Split 1,777-line monolith into 7 focused files (~138-line orchestrator). Unified violet theme across all sub-tabs.
- **Renamed** `get_managed_skill_store` → `get_central_skill_store`.
- **CLAUDE.md**: Added frontend conventions (component size, shared UI patterns, color theme, file splitting).

### Removed
- Deleted `llm/digest_friction.py`, `models/analysis/behavior.py`, `models/skill.py`, and legacy `storage/base.py`/`disk.py`/`local.py` (all moved or consolidated).

## [0.9.0] - 2026-03-24

### Added

**Friction Analysis** *(Roadmap §6)*
- **LLM-powered friction detection**: Multi-session analysis identifies wasted effort, wrong approaches, excessive retries, and other friction patterns. Produces severity-rated events with root causes, evidence, and actionable mitigations.
- **CLAUDE.md suggestions**: LLM generates concrete CLAUDE.md rules derived from observed friction, with section placement and rationale linking back to source events.
- **StepRef model**: Reusable locator for step or step range within a session, supporting point refs, range refs, and tool call pinning. Shared across friction and skill analysis.
- **Friction analysis UI**: Full-page panel with severity-colored event cards, mode summary stats, CLAUDE.md suggestion cards, and LLM config section. History sidebar lists past analyses with load/delete.
- **Friction persistence**: JSON-based store (`~/.vibelens/friction/`) with full result + lightweight metadata files for fast listing.

**Skill Management** *(Roadmap §9)*
- **Skill storage abstraction**: `SkillStore` ABC in `storage/skill/` with `SkillInfo` model using `AgentType` enum. `ClaudeCodeSkillStore` reads `~/.claude/skills/`, parses YAML frontmatter, detects subdirectories (scripts, references, agents, assets).
- **Skill CRUD API**: `GET /api/skills/local`, `GET /api/skills/local/{name}`, `POST /api/skills/install`, `PUT /api/skills/local/{name}`, `DELETE /api/skills/local/{name}`, `GET /api/skills/search?q=...`.
- **Skills UI**: New "Skills" tab with search bar, expandable skill cards showing allowed tools/subdirectories/path, create/edit dialog with SKILL.md editor, and delete confirmation.
- **Skill personalization spec**: Comprehensive design document (`docs/spec-skill-personalization.md`) for LLM-powered skill retrieval, creation, and evolution from trajectory analysis.

**LLM Inference Backend**
- **Pluggable inference**: `InferenceBackend` ABC with `LiteLLMBackend` (supports 100+ models via litellm) and subprocess backends (claude-cli, codex-cli).
- **Runtime hot-swap**: `POST /api/llm/configure` to change API key and model without restart. `GET /api/llm/status` reports backend availability.
- **Jinja2 prompt templates**: System and user prompts for friction analysis rendered from `.j2` templates with `AnalysisPrompt` model.
- **Step signals**: `StepSignal` model packages trajectory steps with session context for LLM digest, with configurable truncation limits.

**Ingest Improvements**
- **Index builder**: `index_builder.py` constructs skeleton trajectories from parser indexes for fast session listing without full file I/O.
- **Parsed trajectory parser**: `ParsedTrajectoryParser` reads pre-parsed ATIF JSON files, enabling round-trip save/load.
- **Parser discovery methods**: Each parser now implements `discover_session_files()` for agent-specific file filtering, replacing centralized discovery functions.
- **Auto-prompt detection**: Claude Code parser classifies plan mode and automated workflow prompts (`is_auto_prompt` extra field).

### Changed

**Architecture**
- **TrajectoryStore ABC refactor**: Unified index pattern with `_index` and `_metadata_cache`. Concrete methods (list_metadata, load, exists, session_count, get_metadata) operate on shared structures. Subclasses only implement `initialize()`, `save()`, and `_build_index()`.
- **LocalStore simplification**: Uses `LOCAL_PARSER_CLASSES` list and delegates to parser `discover_session_files()`. Removed manual per-agent discovery logic.
- **DiskStore simplification**: Streamlined save with incremental index updates. Uses rglob for subdirectory session discovery.
- **Parser `AGENT_NAME` → `AGENT_TYPE`**: All parsers now use `AgentType` enum instead of string identifiers.
- **Schema layer**: Extracted API boundary models into `schemas/` package (session, share, upload, friction, llm). Deleted standalone model files (`session_requests.py`, `share.py`, `upload.py`).
- **Dependency injection**: Added `get_friction_store()`, `get_skill_store()`, `get_inference_backend()`, `set_inference_backend()`, `is_test_mode()` singletons.
- **Settings expansion**: Added `skills_dir`, `friction_dir`, and LLM config fields (`llm_backend`, `llm_api_key`, `llm_model`, `llm_timeout`, `llm_max_tokens`).
- **AppMode.TEST**: New test mode for isolated testing with mock backends.

**Frontend**
- **Four-tab navigation**: Added "Friction" (amber) and "Skills" (violet) tabs alongside Conversation and Dashboard.
- **Session deep linking**: URL params `?session=...&step=...` for direct navigation to specific sessions and steps.
- **Flow diagram improvements**: Reworked phase grouping, layout engine, and tool chip rendering.
- **Session list**: Client-side pagination, improved search with debouncing, sticky project headers.

**Dependencies**
- Added `litellm>=1.40.0` and `jinja2>=3.1.0` to core dependencies.

### Removed
- **Fingerprint module**: Deleted `ingest/fingerprint.py` (format auto-detection via confidence scoring). Replaced by direct parser dispatch.
- **Legacy model files**: Removed `models/session_requests.py`, `models/share.py`, `models/upload.py` (migrated to `schemas/`).
- **Old frontend assets**: Cleaned up stale bundled JS/CSS from previous builds.

## [0.8.1] - 2026-03-22

### Added

**UI Polish**
- **Session header collapse toggle**: Chevron button to expand/collapse meta pills and token stats rows, keeping the title row always visible.
- **Title hover tooltip**: Hovering truncated first-message title shows the full text in a native tooltip.
- **MetaPill hover interaction**: Subtle background brightness boost on hover for interactivity cue.
- **Consistent icons**: Added icons to all token stat labels (Input, Output, Cache Read, Cache Write, Total, Est. Cost) and all dashboard section headers (Peak Hours, Agent/Model/Tool Distribution, Project Activity).

**Dashboard**
- **Per-project details**: Project Activity rows now show messages count, token count, and estimated cost per project with inline icons.
- **Dashboard loading fallback**: Direct API fetch when background cache preload hasn't arrived, preventing stuck loading state.

### Fixed
- **Dashboard stuck loading**: Added fallback fetch when cache prop is null, resolving infinite loading spinner.
- **Double dollar sign**: Removed redundant `DollarSign` icon from project row cost display where `formatCost()` already returns `$X.XX`.

## [0.8.0] - 2026-03-22

### Added

**Cost Tracking** *(Roadmap §1)*
- **Cost estimation**: Model-aware pricing engine covering 45+ models across 12 providers. Per-step and per-trajectory USD cost computed from token metrics. Dashboard surfaces total cost, cost-by-model breakdown, and per-session cost.

**Session Graphs** *(Roadmap §4)*
- **Conversation flow diagram**: Phase-grouped visualization of user → agent → tool interactions with color-coded tool chips and hover-based dependency highlighting. Lazy-loaded via Timeline/Flow toggle.

**Sharing & Integration** *(Roadmap §10)*
- **Shareable session links**: Generate permalink URLs to share session details. Backend persists trajectory snapshots on disk; frontend renders a read-only shared view.

**Dashboard**
- **Tool distribution chart**: Horizontal stacked bar chart showing per-tool call counts, percentages, avg/session, and error rates.
- **Cache warming**: Background pre-computation of dashboard stats on startup for instant first page load.

**Packaging** *(Roadmap §7)*
- **PyPI metadata**: MIT license, authors, classifiers, project URLs, PEP 561 `py.typed` marker.
- **CI/CD**: GitHub Actions workflows for tests and PyPI publishing.
- **Auto-open browser**: `vibelens serve` opens the browser automatically (`--no-open` to disable).

### Changed

**Architecture**
- **Layered module split**: Enforced strict `api → services → analysis → models` dependency direction. All Pydantic models extracted from `analysis/` into `models/analysis/`. Monolithic `dashboard_service.py` split into focused computation modules (`dashboard_stats.py`, `session_analytics.py`, `tool_usage.py`). Request models split by domain. Export and flow logic extracted into dedicated services.
- **`llm/` package**: New top-level package for LLM utilities — model name normalization (`llm/normalizer.py`) and pricing table + lookup (`llm/pricing.py`).
- **`stores/` → `storage/`**: Renamed for clarity.
- **Tool graph rework**: Nodes and edges now use tool call IDs with refined relation types (read_before_write, search_then_read, write_then_test, multi_edit, error_retry).

## [0.7.1] - 2026-03-21

### Added
- **Image support**: Multimodal content rendering for image content blocks with click-to-expand lightbox.
- **Step timestamps**: Clock time alongside elapsed time (`33:51 · 1:23 PM`) with gap-since-previous indicator.
- **Usage chart crosshair**: X-axis hover snaps to nearest data point with vertical dashed indicator line.
- **Settings dialog**: Gear icon in top nav opens settings dialog.

### Changed
- **Timeline redesign**: Narrow dot-and-line rail with inline time header, replacing wide stacked layout.
- **Dashboard stat cards**: Added description subtitles and per-row tooltips with token breakdowns.

## [0.7.0] - 2026-03-21

### Added

**Session Graphs** *(Roadmap §4)*
- **Analytics dashboard**: Stat cards (sessions, messages, tokens, duration), usage-over-time chart, GitHub-style activity heatmap, peak hours, model distribution, and project ranking. Supports project filtering and CSV/JSON export.

**Multi-Agent Analytics** *(Roadmap §3)*
- **Agent filter**: Sidebar dropdown filters sessions by agent type. Configurable via `visible_agents`.

**Agent Parsers** *(Roadmap §5)*
- **Codex parser improvements**: Structured output parsing, reasoning extraction, session metadata, error detection, tool result metadata.

## [0.6.2] - 2026-03-20

### Added
- **Session header tooltips**: Metadata pills show descriptive tooltips on hover.
- **Prompts / Skills split**: Separate prompt and skill counts in session header.
- **Auto-expand short results**: Tool results ≤20 lines display inline without collapse.

### Changed
- **UI cleanup**: Removed redundant header, fixed text overflow, improved message type differentiation.
- **Logging**: One log file per module, overwritten each restart.

## [0.6.1] - 2026-03-18

### Added

**Privacy & Security** *(Roadmap §8)*
- **Upload isolation**: Session-token scoped uploads for multi-tab browser safety.
- **Donate consent dialog**: Consent form with attribution and agreement checkbox.

### Changed
- Upload result reports main session count instead of total trajectory count.
- Increased default upload limits: 10 GB zip, 20 GB extracted, 10K files.

### Removed
- Unused settings and VibeLens Export parser.

## [0.6.0] - 2026-03-18

### Added

**Architecture**
- **ATIF v1.6 trajectory model**: `Trajectory` → `Step` hierarchy with multimodal content support (text, image, PDF).
- **Service layer**: Business logic extracted from API routes into `session_service`, `upload_service`, `demo_loader`.
- **Storage backends**: `LocalStore` reads from `~/.claude/`; `DiskStore` for demo mode and uploads.

**Session Insights** *(Roadmap §2)*
- **Step timeline**: Visual timeline with elapsed time between steps and step-source indicators.

**Agent Parsers** *(Roadmap §5)*
- **Session file discovery**: Recursive finder for Claude Code, Codex, and Gemini session directories.

## [0.5.0] - 2026-03-17

### Added
- Two-mode system: self-use (default) and demo mode with in-memory storage.
- Pre-loaded example sessions, per-tab client isolation, TTL cleanup for demo uploads.
- Config templates and example sessions.

### Fixed
- Claude Code parser: timestamp, duration, token counts, project path extraction.
- Gemini parser: empty content, token aggregation, project resolution.

## [0.4.0] - 2026-03-16

### Added
- File upload with auto-format detection.
- Session export, view modes (By Time / By Project), resizable panels.

## [0.3.0] - 2026-03-15

### Added
- MongoDB target/source with push/pull API.
- YAML-first configuration package.
- Frontend session viewer with message rendering, sub-agent display, and prompt navigation.

## [0.2.0] - 2026-03-15

### Added

**Session Insights** *(Roadmap §2)*
- Phase detection and tool dependency graph with typed edges.

**Multi-Agent Analytics** *(Roadmap §3)*
- Cross-agent correlation by project path with overlapping time windows.

**Agent Parsers** *(Roadmap §5)*
- Codex CLI and Gemini CLI parsers with auto-detection.

## [0.1.0] - 2026-03-14

### Added
- Project skeleton: FastAPI backend, React frontend, Typer CLI.
- Claude Code and Dataclaw parsers.
- SQLite database, Pydantic models, test suite.

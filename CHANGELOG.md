# Changelog

## [0.9.16] - 2026-04-01

### Added
- **Git-enriched donations**: Donation ZIPs now include `git bundle --all` for each repository referenced by donated sessions. Enables matching agent edits to git commits for edit-persistence analysis.
- **Git utilities** (`utils/git.py`): `resolve_git_root()`, `create_git_bundle()`, `compute_repo_hash()` for repo resolution, bundling, and deduplication.
- **Repo-to-session mapping**: Manifest `repos` array lists bundles with `session_ids` linking back to sessions. Per-session `repo_hash` and `git_branch` fields added.

### Changed
- **Donation ZIP layout**: Migrated from flat `raw/`+`parsed/` to `sessions/raw/`+`sessions/parsed/`, with new `repos/` directory for git bundles.
- **Donation sender**: `_resolve_repo_bundles()` deduplicates by both `project_path` string (avoids redundant subprocess calls) and resolved git root (avoids duplicate bundles). Returns a mapping instead of mutating sessions. Bundle creation runs via `asyncio.to_thread`.
- **Friction panel**: Renamed "Top Recommendations" to "Top Productivity Tips".
- **Skill analysis UI**: Restyled result header, summary card, section headers, and metadata footer to match friction panel. Moved Workflow Patterns section to bottom. Removed count badges from section headers.
- **Analysis welcome**: Moved session-selection hint into a tooltip on the disabled button.
- **Tooltip**: Skip rendering portal when text is empty.
- **README**: Added comic blurb, new screenshots (01-06), grouped figures, linked `docs/blurb.md`, updated feature table and supported agents.

## [0.9.15] - 2026-03-31

### Changed
- **Per-user upload stores**: Replaced single `DiskStore(upload_dir)` with per-user upload stores keyed by `session_token`. Visibility is now enforced at the storage level -- each user's stores only contain their uploads. Eliminates full rglob rebuild after every upload, cross-user cache invalidation, and runtime visibility filtering.
- **Upload registry**: New `register_upload_store()` and `reconstruct_upload_registry()` in `deps.py`. Uploads register a per-upload DiskStore under the user's token instead of invalidating the global store index. Registry is rebuilt from `metadata.jsonl` on server restart.
- **Store resolver**: `list_all_metadata()`, `load_from_stores()`, and `get_metadata_from_stores()` now accept `session_token` and iterate per-user stores in demo mode, falling back to the example store when a user has no uploads.
- **Projects endpoint**: `/api/projects` now accepts `x-session-token` header for per-user project listing.
- **Rule Anonymizer**: Expand path section with Windows/WSL modes

### Removed
- **visibility.py**: Deleted `filter_visible()` and `is_session_visible()` (11 call sites across 8 service files). Access control is now implicit via store-level isolation.
- **`_all_metadata` field**: Removed from `TrajectoryStore` base class and `DiskStore`. No longer needed since duplicate session_ids across users don't coexist in a single store.
- **`_require_disk_store()`**: Removed from `processor.py`. Demo mode check uses `is_demo_mode()` directly.
- **`invalidate_index()` on refresh/upload**: Removed from `api/sessions.py` (refresh) and `processor.py` (post-upload). Per-user stores are self-contained.

## [0.9.14] - 2026-03-31

### Changed
- **Spotlight tutorial**: Replaced modal onboarding dialog with a step-by-step spotlight tour that highlights UI elements in place. Works in both self and demo modes. Relaunch via Settings > Start Tutorial.
- **Donation consent dialog**: Rewrote consent copy for clarity. Anonymization is now handled by the research team (removed self-review burden). Added permissions reminder, non-commercial use clause, and right-to-delete. Migrated to shared Modal components.
- **Prompt nav panel**: Starts collapsed as a thin strip with expand button. Redesigned with cyan-tinted dark background, card-style entries, and active-state highlighting for sub-agents.
- **User prompt collapse**: Long user prompts (>15 lines) now auto-collapse with a "Show full prompt" toggle.
- **Session list polish**: Upload and Donate buttons use larger text. Agent filter uses custom dropdown instead of native `<select>`. View mode toggle uses fixed width to prevent layout shift. First project auto-expands on load. Session messages truncate with ellipsis instead of multi-line clamp. Search defaults include session_id.
- **Tab bar**: Stronger bottom border with shadow. "Pain Points" renamed to "Productivity Tips" with updated empty-state description. AI tabs grouped with `data-tour` attributes.
- **Friction panel**: Sidebar width constants unified from shared `styles.ts`.

### Fixed
- **Session row overflow**: Project name and timestamp no longer push each other off-screen in narrow sidebars (`truncate`, `shrink-0`, `whitespace-nowrap`).

## [0.9.13] - 2026-03-30

### Fixed
- **Stateless session visibility**: Eliminated in-memory state (`_token_uploads` dict, `_rebuilt_from_disk` flag) that became stale after the first metadata rebuild. Visibility is now a pure function of `_session_token` metadata tags written into each upload's `index.jsonl`.
- **Upload isolation between browser tabs**: Each upload's DiskStore `default_tags` now includes `_session_token` (the browser's UUID) alongside `_upload_id`, enabling stateless per-user visibility filtering.
- **Duplicate session_id dedup ordering**: Sorted `rglob` index discovery so newer upload directories (timestamp-prefixed) are processed last, ensuring the most recent upload wins dedup for `get_metadata()`/`load()`.
- **Multi-upload metadata preservation**: Added `_all_metadata` list to `TrajectoryStore` so `list_metadata()` returns ALL entries (including duplicate session_ids from different uploads), enabling `filter_visible()` to correctly match per-upload tokens.

## [0.9.12] - 2026-03-30

### Changed
- **Donation ZIP wrapping directory**: Donation ZIPs now unzip to a single `{donation_id}/` directory containing `manifest.json`, `raw/`, and `parsed/`. Previously files were at the ZIP root.
- **Upload-then-donate raw files**: When donating uploaded sessions, `raw/` now contains the original upload ZIP instead of parsed JSON duplicates. Multiple sessions from the same upload share a single deduplicated ZIP entry.
- **Donation manifest**: Includes `donation_id` field and optional `source_upload_id` per session entry. Raw file paths include the wrapping directory prefix.
- **Donation receiver**: Reads `donation_id` from manifest for ZIP filename (falls back to generated ID for legacy ZIPs). Manifest discovery searches both root and one-level deep for backward compatibility.
- **Donation index**: Uses `donation_id` field instead of `upload_id` in index entries.

## [0.9.11] - 2026-03-29

### Added
- **Anonymize test suite**: 97 tests in `tests/ingest/anonymize/` covering patterns, path hasher, redactor, traversal, rule anonymizer, and stubs. Full coverage of credential/PII detection, camelCase name variant derivation, path hashing, and deep trajectory tree walking.
- **Batch anonymization script**: `scripts/anonymize_sessions.py` CLI for batch-anonymizing all local Claude Code sessions with dry-run and output modes, per-file error handling, and summary reporting.
- **Anonymization report**: `docs/reports/anonymization-report.md` documenting two-round batch testing across 309 sessions with zero-leak verification.
- **Concise view mode**: New "Concise" toggle in session viewer strips tool calls and thinking blocks, showing only user prompts and agent text responses for quick conversation overview.
- **Plan step navigation**: Auto-prompt steps (plan mode) now appear in the prompt nav panel with teal-colored Plan badges and previews instead of being hidden.

### Fixed
- **camelCase name variant anonymization**: `PathHasher` now splits camelCase usernames (e.g. `JohnDoe`) into name parts and derives space/underscore/hyphen-separated variants with case variations. Eliminates username leaks in author fields, filenames, and free text. Path anonymization coverage increased 38% in batch testing.
- **Partial parse failure handling**: `scripts/anonymize_sessions.py` now handles file-level parse failures independently — sub-agent files are still processed when the main session file fails.

### Changed
- **Test directory reorganized**: Moved misplaced test files to mirror `src/` structure — `tests/llm/` for cost estimator and pricing, `tests/services/` for context extraction and session batcher. Added missing `tests/friction/__init__.py`.
- **Sidebar redesigned**: Donate button promoted to top of session list with full-width styling. Download button moved to footer alongside pagination. View mode toggle (Project/Time) compacted into a single switch button. Upload toolbar only renders in demo mode.
- **Tab styling refreshed**: Main navigation tabs use distinct accent colors with inner shadow — indigo for Browse, cyan for Analyze, amber for Pain Points, teal for Personalization. "Friction" tab renamed to "Pain Points", "Skills" tab renamed to "Personalization".
- **Auto-prompt styling**: Auto-prompt steps restyled from violet to teal with "Plan" label replacing "Auto".

## [0.9.10] - 2026-03-29

### Added
- **Donation service**: New `services/donation/` package with sender and receiver modules. Self-use instances package raw session files + parsed trajectories into a ZIP and POST to the configured donation server. Demo instances receive and store donated ZIPs with append-only index. New `POST /donation/receive` endpoint.
- **Trajectory anonymization**: Pluggable `ingest/anonymize/` package with `BaseAnonymizer` ABC and rule-based implementation. `RuleAnonymizer` chains credential, PII, high-entropy, and custom-string redaction with path username hashing. Deep traversal engine walks ATIF trees applying transforms to text fields while preserving structural data. Configurable via `AnonymizeConfig` with per-category toggles.
- **Session file resolution**: `BaseParser.get_session_files()` returns all files for a session (main + sub-agents). `ClaudeCodeParser` overrides to include `subagents/agent-*.jsonl` files.
- **Store source lookup**: `TrajectoryStore.get_session_source()` returns the file path and parser for any session, enabling donation to locate raw files.
- **LocalStore data dir access**: `LocalStore.get_data_dir()` exposes per-parser data directories for computing relative ZIP paths in donations.
- **Multi-store resolver**: New `services/session/store_resolver.py` extracts `list_all_metadata`, `load_from_stores`, `get_metadata_from_stores` — primary-then-fallback-to-examples business logic separated from DI.
- **Donation config**: `donation_url` and `donation_dir` settings with YAML mapping in `config/loader.py`.
- **Examples dir setting**: `examples_dir` field in Settings for demo mode example storage location.

### Changed
- **deps.py registry pattern**: Replaced 13 module-level globals and `global` statements with a single `_registry` dict and `_get_or_create()` helper. Added `reset_singletons()` for complete test isolation (previously only 2 of 13 globals were reset between tests).
- **Upload visibility scoping**: Tokens with uploads now see only the **last** upload's sessions — example sessions are hidden. Previous behavior showed all uploads plus examples. `_token_uploads: dict[str, set[str]]` replaced with `_token_last_upload: dict[str, str]`.
- **Upload button demo-only**: Upload toolbar button only renders in demo mode (`appMode === "demo"`).
- **Upload dialog redesigned**: New multi-step flow with confirmation screen and dedicated result screen showing session count with check icon, progress bar, and detailed stats.
- **Dashboard refresh on upload**: `dashboardPreloaded` ref and cache state reset when `refreshKey` changes. `DashboardView` remounts via `key={refreshKey}` to reflect uploaded data immediately.
- **Upload processor refactored**: Removed hardcoded `DATASETS_ROOT` global; all paths derive from `settings.upload_dir`. Upload metadata stored in append-only `metadata.jsonl` instead of per-upload `metadata.json`. Sub-agent-only files skipped during parsing.
- **Demo store uses settings**: `deps.py` demo mode store switched from `DiskStore(DATASETS_ROOT)` to `DiskStore(settings.upload_dir)`.
- **Donation endpoint moved**: `POST /sessions/donate` moved from `api/sessions.py` to dedicated `api/donation.py` router. Business logic extracted from `services/session/crud.py` to `services/session/donation.py`.
- **DiskStore index filename**: Renamed `_index.jsonl` → `index.jsonl` throughout DiskStore and docstrings.
- **Index cache filename**: Renamed `index_cache.json` → `session_index.json` with `indent=2` formatting.
- **macOS resource fork filtering**: `discover_all_session_files()` and `ClaudeCodeParser.discover_session_files()` skip `._*` Apple Double files.

## [0.9.9] - 2026-03-28

### Added
- **OpenClaw parser**: New `openclaw.py` parser for `~/.openclaw/agents/main/sessions/` event-based JSONL format. Registered in discovery, local store, and settings with `openclaw_dir` config field.

### Fixed
- **Think block ordering**: ThinkingBlock (reasoning_content) now renders BEFORE message text in timeline view, matching the actual agent workflow (think first, then respond).
- **Flow mode interleaving**: Phase groups in flow view are now split at user prompt boundaries, so user prompts appear interleaved between agent steps instead of being clustered after a single phase block.

### Changed
- **CLAUDE.md updated**: Added OpenClaw to parsers list and agent data directories. Added Release section with versioning workflow.

## [0.9.8] - 2026-03-28

### Added
- **Multi-agent skill stores**: Added 9 new agent interfaces (Cursor, OpenCode, Antigravity, Kimi CLI, OpenClaw, OpenHands, Qwen Code, Gemini CLI, GitHub Copilot) with skill directory scanning and auto-import into the central store on startup.
- **Agent skill registry**: `AGENT_SKILL_REGISTRY` maps each agent to its default skills directory. Only agents installed on disk are activated.

### Changed
- **Skill storage refactored**: Replaced `ClaudeCodeSkillStore` hierarchy with `DiskSkillStore` as the shared concrete base. All agent stores are now parallel peers — Claude Code and third-party agents are plain `DiskSkillStore` instances, `CodexSkillStore` and `CentralSkillStore` extend it for agent-specific behavior.
- **AgentType expanded**: Added 9 skill-only agent types. `SkillSourceType` mirrors all `AgentType` values, keeping a single source of truth.

### Removed
- `claude_code.py` — logic moved to `disk.py`.
- `AgentSkillStore` class — replaced by plain `DiskSkillStore` instances.

## [0.9.7] - 2026-03-27

### Changed
- **Services restructured**: Grouped 13 root-level service files into domain subdirs (`session/`, `dashboard/`, `upload/`). Merged `analysis/` package into consuming service subdirs. Deleted obsolete `services/mock/` package.
- **Skill analysis split**: Split monolithic `skill/analysis.py` into `retrieval.py`, `creation.py`, `evolvement.py` with thin dispatcher in `skill/__init__.py`.
- **CSV export expanded**: Added `agent`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd` columns. Eliminated duplicated aggregation logic by reusing `aggregate_session()` from stats.
- **Pricing cleanup**: Removed `__all__` and dead re-exports from `pricing.py`. Consumers now import `normalize_model_name` and `lookup_pricing` from their source modules.
- **Skill store renamed**: `skill/analysis_store.py` → `skill/store.py`.

## [0.9.6] - 2026-03-27

### Added
- **Pre-flight cost estimation**: New `POST /friction/estimate` endpoint and `CostEstimateDialog` modal show estimated LLM cost (min/max range) before running friction analysis. Users must confirm before incurring charges.
- **Onboarding dialog**: Two-step welcome guide on first visit covering privacy guarantees and LLM cost transparency. Shown once per browser (`localStorage`), re-triggerable from Settings.
- **Cost estimator module**: `llm/cost_estimator.py` computes input/output token costs with optimistic/pessimistic output ratios and synthesis call estimates.
- **Session ID remapping**: `IdMapping` and `_IndexTracker` in context extraction replace verbose UUIDs with 0-indexed integers in LLM prompts, reducing token usage. `_resolve_synthetic_ids()` converts back after inference.
- **User prompt truncation**: Long user prompts (>2000 chars) are truncated to head (1500) + `[...truncated...]` + tail (500) to save tokens.
- **Compaction interleaving**: Compaction summaries are inserted at their chronological position among steps instead of being grouped at the top, giving the LLM better temporal context.
- **Step-boundary session splitting**: Oversized sessions that exceed the batch token budget are split at `[step_id=...]` boundaries with the session header preserved on each part.
- **Affinity-based batch packing**: Session batcher seeds each batch then greedily fills by project affinity and time proximity, keeping related sessions together.

### Changed
- **Mitigation model simplified**: `action_type` + `target` fields replaced with a single `action` label (e.g., "Update CLAUDE.md code style section"). Backward-compatible `model_validator` migrates old data.
- **Multiple top mitigations**: `top_mitigation` (singular) → `top_mitigations` (list of up to 3), ranked by batch severity and deduplicated by content.
- **Friction events grouped by project**: UI groups events by project name instead of session ID, with per-group session count display.
- **Prompt quality**: Max events per batch reduced from 7 to 5 with minimum severity 2 threshold. Added recurring-pattern prioritization, merge instructions for same-type events, and noise filtering guidance.
- **Models reorganized**: Moved `models/analysis/dashboard.py` → `models/dashboard/`, `models/analysis/pricing.py` → `models/pricing.py`, `models/analysis/prompts.py` → `models/prompts.py`, `models/analysis/skills.py` → `models/skill/skills.py`. Imports unchanged via re-exports.
- **Tests reorganized**: Friction tests moved to `tests/friction/` subdirectory. Expanded session batcher tests covering affinity packing, chain preservation, and step-boundary splitting.

### UI
- **Mitigation tags enlarged and highlighted**: Bigger tags (`text-sm font-semibold`) with vivid colors — violet for CLAUDE.md, emerald for tests, cyan for skills, amber for linting, rose for workflows, teal default.
- **First friction event auto-expanded**: The highest-severity event in the first project group starts expanded, matching the skill panel pattern.
- **Resizable history sidebar**: Drag-to-resize (180–400px range) with collapse/expand toggle buttons.
- **Cost confirmation dialog**: Modal with session count, batch count, token breakdown, model name, and estimated cost range before analysis runs.
- **Event cards**: Inline session ID badge, "Jump" button to open step in new tab, project-grouped layout sorted by max severity.

## [0.9.5] - 2026-03-26

### Added
- **Friction synthesis LLM call**: After per-batch analysis, a lightweight LLM call synthesizes all batch results into a cohesive user-facing report with title, summary, per-type descriptions, cross-session patterns, and top mitigations.
- **Friction synthesis prompts**: New Jinja2 templates (`friction_synthesis_system.j2`, `friction_synthesis_user.j2`) and `FRICTION_SYNTHESIS_PROMPT` registration.
- **Synthesis output model**: `FrictionSynthesisOutput` with title, summary, type descriptions, cross-session patterns, and 0-3 structured mitigations.
- **Type descriptions**: `TypeSummary` now carries an optional LLM-generated `description` field explaining the specific friction pattern observed.
- **Category logging**: Refactored logging to use shared category log files (`parsers.log`, `analysis-friction.log`, `analysis-skill.log`) instead of per-module files. Multiple modules in the same category share a single FileHandler.
- **Friction API error handling**: Unexpected exceptions in the friction analysis endpoint now return structured 500 responses with type and message.

### Changed
- **Non-blocking dashboard cache warming**: Cache warming now loads sessions in batches of 20 with GIL-releasing sleeps between batches. Runs as an async background task instead of a blocking thread. Friction history, LLM status, and skill endpoints respond in 1-3 seconds on cold start instead of waiting ~55 seconds for cache warming to finish.
- **Friction prompts rewritten for users**: Synthesis prompt writes for a developer audience — no references to batches, chunks, or internal processing. Summary capped at 80 words (down from 150) for scanability.
- **Cross-session patterns**: Renamed `cross_batch_patterns` → `cross_session_patterns` throughout models, prompts, and templates.
- **Synthesis mitigations override batch mitigations**: If the synthesis call produces mitigations, the first one replaces the per-batch `top_mitigation`.
- **Batch token budget**: Default `max_batch_tokens` increased from 24K to 80K for fewer batches and better context per analysis call.
- **Session load resilience**: `_extract_all_contexts` now catches and skips sessions that fail to load instead of aborting the entire analysis.
- **Claude Code parser guard**: `_read_persisted_agent_id` rejects paths longer than 1024 chars or containing newlines before touching the filesystem.

### Removed
- **Helpfulness badge**: Removed `HelpfulnessBadge` from friction event cards, along with `HELPFULNESS_LABELS`, `HELPFULNESS_COLORS` constants, and `Heart` icon import.
- **Batch count in UI**: Removed batch count display from the friction result header subtitle.

### UI
- **Session severity sort**: Friction events section now sorts session groups by max event severity (highest first).
- **Analysis title**: Result header displays the LLM-generated title (falls back to "Friction Analysis").
- **Cross-session patterns**: Summary section renders cross-session patterns as a bullet list.
- **Type descriptions**: Friction type cards show the LLM-generated description below the badge row.
- **History card titles**: History sidebar cards display the analysis title when available.

## [0.9.4] - 2026-03-26

### Added
- **Fast metrics scanner**: New `ingest/fast_metrics.py` extracts aggregate token counts, tool call counts, model name, and duration from raw JSONL without full Pydantic parsing. Deduplicates assistant entries by message ID.
- **Persistent index cache**: New `ingest/index_cache.py` serializes session metadata and file mtimes to `~/.vibelens/index_cache.json` for near-instant startup. Incremental updates re-parse only changed files (< 30% threshold; full rebuild otherwise).
- **Metadata-based dashboard stats**: `compute_dashboard_stats_from_metadata()` computes all dashboard charts from enriched metadata cache, eliminating full trajectory loading for the dashboard.
- **Friction analysis logging**: Each LLM call saves `system_prompt.txt`, `user_prompt_{N}.txt`, and `raw_output_{N}.txt` to `logs/friction/{YYYYMMDD_HHMMSS}/`. Persists even on inference errors.
- **Friction analysis summary log**: Append-only `logs/analysis-friction.log` records session IDs, batch composition, token counts, and model for each run.
- **Session continuation refs**: `TrajectoryStore.load()` enriches loaded trajectories with `last_trajectory_ref`/`continued_trajectory_ref` from the metadata cache, fixing missing continuation tags in the UI.

### Fixed
- **Flow mode scroll navigation**: Clicking user prompts in the right sidebar now scrolls to the correct position in the flow diagram. Added matching `id` and `scrollMarginTop` to flow anchor divs.
- **Missing "Spawned by" tag**: Sessions with `parent_trajectory_ref` now show both the link icon in the sidebar and the "Spawned by" navigation tag in the session header.
- **Overlapping x-axis dates**: Usage Over Time chart skips the last-point label when it overlaps the previous interval label (< 40px gap).
- **LLM returning markdown instead of JSON**: Strengthened prompt enforcement with "Your entire response must be a single JSON object" directive and explicit zero-friction JSON template.
- **Duplicate "History" label**: Removed inner "HISTORY" text from `FrictionHistory` component; only the panel header label remains.
- **History sidebar toggle**: Sidebar now stays visible when clicking a history item instead of collapsing.
- **Parser log spam**: Downgraded "Cannot read file" and "Invalid JSON" warnings to DEBUG level for edge case test files.

### Changed
- **Friction store → single JSONL**: Replaced per-analysis `.meta.json` files with a single append-only `meta.jsonl` file. Delete rewrites the file minus the removed entry.
- **Friction type sort**: Type summary section now sorts by average severity (descending) instead of event count.
- **Friction ID → server-side UUID**: Removed `friction_id` from LLM output schema. `FrictionEvent` generates a UUID via `default_factory`. Removed `related_friction_ids` field entirely — each event is self-contained.
- **Default LLM model → Haiku**: Changed default from `anthropic/claude-sonnet-4-5` to `anthropic/claude-haiku-4-5` for faster, cheaper analysis. Frontend model presets reordered accordingly.
- **LLM config path**: Default config moved from `config/llm.yaml` to `~/.vibelens/llm.yaml` with legacy fallback.
- **Friction prompt word limits**: Added explicit max word counts — `user_intention` (15), `friction_detail` (20), `summary` (50), `mitigation.content` (30).
- **Loading animation**: Friction panel now uses the shared `LoadingSpinner` (triple-ring animation) instead of a simple spinner.
- **History sidebar UI**: Cards show amber/green event badges, violet session count, amber cost icon, split date/time with calendar+clock icons, and whiter text for readability.
- **Background startup**: Skill import, mock seeding, and cache warming run in a background thread so the server accepts requests immediately.

## [0.9.3] - 2026-03-26

### Added
- **Token-based batch budgeting**: New `llm/tokenizer.py` module using tiktoken for accurate token counting. Session batcher now packs batches by token budget instead of character count.
- **Skill creation & evolution prompts**: Dedicated Jinja2 prompt templates for skill creation (`skill_creation_system.j2`, `skill_creation_user.j2`) and evolution (`skill_evolution_system.j2`, `skill_evolution_user.j2`) LLM pipelines.
- **Install target dialog**: New `install-target-dialog.tsx` for choosing which agent interface to install skills into.
- **Sync after save dialog**: New `sync-after-save-dialog.tsx` for cross-agent skill sync after editing.
- **Mock service modules**: Extracted mock data into `services/friction/mock.py` and `services/skill/mock.py` for cleaner test/demo separation.

### Fixed
- **Missing sessions**: Claude Code Desktop sessions not in `history.jsonl` are now discovered via orphaned file fallback in the index builder.
- **Explore tab crash**: `TypeError: Q.map is not a function` — handle paginated API response (`{items, total}`) instead of assuming flat array.
- **Log spam**: Downgraded 13K+ repeated Pydantic validator warnings (orphaned tool calls, observation mismatches) to DEBUG level.
- **Tab switching stale content**: Switching between Retrieve/Create/Evolve tabs now clears the previous analysis result.
- **Session refresh**: Added `refresh=true` parameter to `/sessions` endpoint for cache invalidation on page load.

### Changed
- **Skill analysis views**: Richer UI with icons, confidence progress bars, color-coded edit kinds, auto-expanding first pattern card, and improved mock data covering all edge cases.
- **API rename**: `skills.py` → `skill_management.py` for clarity.
- **Settings**: Replaced `max_batch_chars` with `max_batch_tokens` for token-based budgeting.

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

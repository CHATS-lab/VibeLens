# Changelog

## [Unreleased]

## [1.0.3] - 2026-04-20

### Added
- **Hermes agent parser** (`ingest/parsers/hermes.py`) covering JSONL stream + snapshot formats, state.db enrichment, chat-surface project paths, and `system_prompt` / `base_url` surfaced in trajectory `extra`.
- **Frontend test harness** (Vitest + jsdom + @testing-library). 34 tests covering every API client and the highest-value hooks. `npm run test` runs the full suite in under 1s. Wired into CI.
- **Per-domain API clients** in `frontend/src/api/`: `analysis.ts` (friction + 3 personalization modes, shares `baseUrl`), `llm.ts`, `sessions.ts`, `dashboard.ts`, `upload.ts`, `donation.ts`. Components no longer call `fetchWithToken` directly.
- **Reusable frontend hooks** in `frontend/src/hooks/`: `useJobPolling` (terminal-state job polls), `useCostEstimate` (POST-estimate → dialog flow), `useCopyFeedback` (clipboard + tri-state feedback), `useResetOnKey` (monotonic reset signal), `useSessionData` (trajectories + stats + flow), `useShareSession` (share dialog + link copy), `useDashboardData`, `useDashboardExport`.
- **Frontend CI job** (`.github/workflows/ci.yml`) running `tsc --noEmit`, `npm run test`, and `npm run build` on every push and PR, in parallel with the existing Python matrix.
- **Sticky back button** on extension detail pages (Local + Explore + Recommend/Customize/Evolve) that stays pinned at the top-left while scrolling.

### Changed
- **Renames**: `ingest/parsers/claude_code.py` → `claude.py` (class `ClaudeCodeParser` → `ClaudeParser`); `claude_code_web.py` → `claude_web.py` (`ClaudeCodeWebParser` → `ClaudeWebParser`). External `AgentType` values (`"claude"`, `"claude_web"`) unchanged.
- **`BaseParser.iter_jsonl_safe`** accepts either a `Path` (file streaming) or `str` (in-memory content), replacing the private per-parser JSONL loops that lived in claude, codex, hermes, openclaw.
- **Agent-specific system-tag prefixes** moved out of base into their owning parsers (`_CODEX_SYSTEM_TAG_PREFIXES` in codex, claude's already in claude). Base's union renamed to `_ALL_KNOWN_SYSTEM_TAG_PREFIXES` and documented as an agent-agnostic fallback for demo-mode ATIF loading.
- **Route-level code splitting** via `React.lazy`. Main bundle dropped from 924 KB to 302 KB (gzip 260 KB → 89 KB, ~3× smaller). Heavy dependencies (markdown renderer 103 KB gzip, syntax highlighting, flow diagram) now load on demand.
- **`session-view.tsx`: 814 → 407 lines.** Data fetching extracted to `useSessionData`, share flow to `useShareSession`, top-bar rendering to `SessionViewHeader`.
- **`dashboard-view.tsx`: 707 → 629 lines.** Three fetching effects extracted to `useDashboardData`; export flow extracted to `useDashboardExport`.
- **`extension-detail-view.tsx`: shared layout extracted to `detail-shell.tsx`** so catalog and local detail views share scaffolding without duplication.
- **Extension detail back-button label** shortened from "Back to extensions" / "Back to local extensions" to just "Back".
- **Shared frontend timing constants** (`COPY_FEEDBACK_MS`, `JOB_POLL_INTERVAL_MS`, `RESIZE_DEBOUNCE_MS`) consolidated in `frontend/src/constants.ts`. Previously duplicated across four files with drifted values.
- **`CLAUDE.md` / `DESIGN.md`** updated to describe the `api/`, `hooks/`, and `test/` layers, the factory-client pattern, testing conventions, and the `useEffect`-to-notify-parent anti-pattern.

### Fixed
- **Claude duplicate-step-id regression**: some `~/.claude` sessions (12 out of 3,357 observed locally) were rejected by the `Trajectory` validator because Claude Code re-emitted identical JSONL entries after compaction replay. Entries are now deduplicated by `uuid` before step assembly.
- **Gemini missing `agent.model_name`**: the agent-level model was never populated (0% local coverage). Derived it from the most recently-seen step model, restoring 100% coverage.
- **Sub-tab bar now hides for every detail page** (Local, Explore, and the Recommend/Customize/Evolve analysis detail views), not just Local. Viewing an extension no longer shows the noisy sub-tab header.
- **Filter-bar skill counts refresh after uninstall** from the detail view. Previously "Claude (5)" stayed stale after deleting the last Claude-synced skill.
- **Re-clicking the top-level "Personalization" nav** while on a detail page returns to the list. Previously it was a no-op because `setMainView("skills")` was already the current state.
- **File-tree filename truncation** now shows ellipsis for long paths. The `Tooltip` wrapper's `inline-flex` span was not forwarding width, so the inner `truncate` class never triggered.

## [1.0.2] - 2026-04-19

### Fixed
- **Windows install**: lazy-import `fcntl` (POSIX-only) and add a `msvcrt.locking` fallback so `vibelens` installs and runs on Windows. The previous top-level `import fcntl` in `utils/json.py` crashed the CLI at startup.
- **`Path.home()` captured at import time**: `StorageConfig` / `UploadConfig` / `DonationConfig` default paths and the `PLATFORMS` dict both froze the user home at module import, so tests monkey-patching `HOME` or `Path.home` saw stale state. Defaults now use `default_factory`; `PLATFORMS` gets a `rebuild_platforms()` helper for fixtures that need a fresh build.
- **`test_agents_endpoint` / `test_plugin_routes`**: fixtures now call `rebuild_platforms()` on setup/teardown so the platform table reflects the patched tmp home.
- **npm wrapper Python discovery on Windows**: `npm/bin/vibelens.js` preferred the `py` launcher over `python3` / `python` on Windows, which could resolve to a different Python interpreter than the one on PATH where `pip install vibelens` ran. The wrapper now prefers PATH-based `python3` / `python` first and falls back to `py` only if neither has vibelens installed. A two-pass search (`vibelens-installed` first, then `any Python ≥3.10`) keeps the `not installed` error path working for end users who haven't installed the package yet.

### Changed
- **Publish workflow** (`.github/workflows/publish.yml`) now creates a GitHub Release (with changelog-extracted release notes and dist/ artifacts attached) after PyPI upload succeeds. Previously the workflow only pushed to PyPI and the GitHub Releases page was not auto-updated.

### Docs
- `.github/workflows/npm-publish.yml`: header note flagging that `NPM_TOKEN` must be a granular automation token with 2FA bypass (classic personal access tokens now get a 403 from the registry).

## [1.0.1] - 2026-04-18

### Added
- **Local extensions tab** now manages skills, subagents, commands, and plugins under one "Local" header with a pill-style type selector. Each type gets install, uninstall, sync-to-agents, and (for editable types) inline editing. Cards click through to a full detail page.
- **Extension detail page** (shared by Local and Explore) with a collapsible file-tree sidebar, per-file preview/code modes, optional Save in code mode, and a sticky "On this page" TOC that follows scroll. Non-markdown files (`json`, `yaml`, `py`, `sh`, …) render in syntax-highlighted code blocks; JSON is pretty-printed.
- **Explore pill-style type selector** replacing the type dropdown. Plugin pill sits between Skill and Subagent; Local tab mirrors the same ordering.
- **Per-type tree/file API**: `GET /api/extensions/{type}s/{name}/tree` and `/files/{path}` expose the on-disk directory for any locally-installed extension. Path-traversal guarded, 500-entry walk cap, 200 KB file-read cap. Catalog gets an equivalent `/catalog/{id}/tree` + `/files/{path}` pair that walks GitHub's Contents API.
- **Claude plugin discovery** across every marketplace. `ClaudePluginStore` now scans `~/.claude/plugins/cache/<marketplace>/<name>/<version>/` instead of a single `vibelens/` bucket, so plugins installed via `/plugin install` (superpowers, local-plugins, etc.) surface in Local. Plugins auto-import into the central VibeLens store on startup, mirroring the skill flow.
- **Uninstall confirmation dialog** shared by the card and the detail page. Lists every agent the item is synced to and warns that confirming removes it from all of them.
- **Topics "+N more" toggle** on the detail page when an item has more than 5 topics.
- `scripts/build_catalog.py` converts `agent-tool-hub` output into the bundled two-tier catalog (summary + offsets + per-type JSONs).
- `MCP_SERVER` extension type.
- `SessionToolUsage` model + `tool_usage_cache` module backing the per-session warming cache.
- `build_partial_session_index` for path-scoped trajectory-index rebuilds.

### Fixed
- **Explore detail content** returned "No content available" for every subagent and command. The catalog emits `tree/.../file.md` URLs for ~5,700 single-file items; `_resolve_content` appended `/SKILL.md` to any tree URL, producing 404s. A new `is_github_single_file_tree` heuristic (extension whitelist) routes single-file sources through the correct raw URL.
- **Catalog plugin install + content fetch for bare-repo URLs**. Around 10% of catalog plugins use `https://github.com/owner/repo` without a `/tree/` suffix. Added `GITHUB_REPO_RE` + a shared `parse_github_url` normalizer; `download_directory`, `list_github_tree`, and `fetch_github_tree_file` all accept bare-repo URLs now (walked from default branch root).
- **Plugin content display**. `_resolve_content` has a plugin branch that fetches `README.md` first, then `.claude-plugin/plugin.json`, instead of always looking for `SKILL.md`. Non-plugin bare-repo URLs fall back to the repo's top-level README at HEAD.
- **Subagent / command install layout**. Single-file items land at `{dir}/{name}.md`, matching what `uninstall_extension` expected. Directory-shaped items keep the `{dir}/{name}/` layout.
- **Recommendation L4 crash** when catalog items had `description=None`. Extracted template building into `_build_rationale_candidates` with `item.description or ""` coercion; the pipeline now returns rationales end-to-end instead of raising `AttributeError`.
- **LiteLLM pricing**: Kimi / DeepSeek / Qwen rates corrected against official sources; `claude-opus-4-7` pricing added + normalizer prefix extended.
- **Files that produce no parseable trajectory** (Claude Code Desktop file-history snapshots, etc.) are memoized in the index cache and skipped on subsequent startups, eliminating the per-startup parse-and-fail loop.

### Changed
- **Catalog schema migrated to `agent-tool-hub` format**. `AgentExtensionItem` field names aligned to the hub; `tags → topics`, `license_name → license`. Detail-only fields (`scores`, `item_metadata`, `readme_description`, `repo_description`, `author`, `author_followers`, `contributors_count`, `created_at`, `discovery_origin`, `validation_errors`) load on demand via byte offsets.
- **Catalog list API** drops `category` and `platform` query parameters (accepted-but-ignored for backward compatibility). Metadata endpoint returns `topics` instead of `categories`.
- **Catalog scoring weights** rebalanced (relevance 50%, quality 30%, popularity 15%, composability 5%) since platforms is unavailable this release.
- **Plugin store layout**: central store remains at `~/.vibelens/plugins/` (canonical Claude layout); Claude agent store widens to `~/.claude/plugins/cache/` and walks two levels (`<marketplace>/<name>/`).
- **Cache gating** in `services/extensions/catalog`: `_content_cache` / `_tree_cache` only cache successful results, so a transient GitHub 503 no longer pins an hour of errors.
- **Type selector** (Local + Explore) uses the DESIGN.md Apple-style pill pattern (`bg-control` track with `bg-panel shadow-sm` active pill) instead of the old segmented toggle or dropdown.
- **Recommendation card background** matches the Explore list card (`border-card bg-panel hover:bg-control/80`).
- **Startup latency** increases ~1–3s to warm the new catalog. The legacy `~/.vibelens/catalog/` user cache is deleted on startup (contents not migrated).
- **Trajectory-index cache** uses per-file invalidation instead of all-or-nothing. Touching one session JSONL re-parses only that file (~200 ms) rather than rebuilding the whole index (~12 s). Cache file `~/.vibelens/session_index.json` schema bumps to v3; pre-existing v2 caches are discarded cleanly on first startup.
- **Dashboard tool-usage warming** uses a persisted per-session cache at `~/.vibelens/tool_usage_cache.json`. Warm restarts skip ~99% of trajectory loading and complete in <1 s instead of ~2 m 43 s. Cold start cost is unchanged but writes the cache for subsequent runs.

### Removed
- Catalog `install_content` / `install_method` payloads. Every install now fetches from `source_url` at install time.
- Frontend "Category" and "Platform" filter dropdowns in the Explore tab.

### Disabled (temporarily)
- `_enrich_continuation_refs` is commented out — the chain extractor has a bug that misses some links. Re-enable once the bug is fixed.

### Unsupported this release
- HOOK install from the catalog returns 501. Hook items still browse and view fine.
- MCP_SERVER install from the catalog returns 501.
- REPO install from the catalog returns 501 (the hub does not emit REPO items).

## [1.0.0] - 2026-04-17

### Added
- **Unified extensions system**: `BaseExtensionService[T]` generic base with Skill, Command, Subagent, and Hook services. Central + per-agent store architecture with install/sync/unsync lifecycle.
- **Extensions API package**: Consolidated 5 standalone routers into a single `api/extensions/` package with typed factory and per-type endpoints.
- **Typed frontend extensions client**: `ExtensionsClient` with context provider, replacing raw fetch calls across all extension components.
- **Catalog install via services**: Skills, commands, subagents, and hooks route through their respective services for central + agent sync instead of direct file writes.
- **CatalogInstallButton component**: Reusable install/manage button for catalog and recommendation cards with sync target dialog.
- **Install target dialog**: Diff-based dialog showing add/remove changes per platform, with central-only fallback.
- **GitHub auth for downloads**: `GITHUB_TOKEN`/`GH_TOKEN` env var support raises API rate limit from 60 to 5000 req/hr.
- **Domain-based logging**: Routing table maps logger prefixes to 8 domains with per-domain log files and configurable levels.
- **Donation UI**: Donation history, withdraw form links, and redesigned consent/result dialogs.
- **One-liner install scripts**: `install.sh` (macOS/Linux) and `install.ps1` (Windows) bootstrap uv and run `uvx vibelens serve`.
- **Recommendation pipeline**: L1-L4 engine with TF-IDF retrieval, multi-signal scoring, LLM profiling, and frontend view.
- **Light mode**: Full light/dark/system theme with CSS custom property tokens and semantic color migration.
- **Catalog explorer**: Browse, search, filter, and install from 1499 catalog items with GitHub metadata enrichment.
- **Context extraction framework**: Pluggable `ContextExtractor` ABC with metadata, summary, and detail extractors.
- **LLM config UI**: Redesigned form with CLI badges, LiteLLM presets, and expanded pricing.
- **Font selector**: Atkinson Hyperlegible and other font families with live preview.

### Changed
- **Extensions refactor**: Renamed `catalog_install` to `catalog_resolver`. Migrated all services to `BaseExtensionService` with string agent keys. Unified extension schemas.
- **Frontend restructure**: Renamed `conversation/` to `session/`, `analysis/` to `dashboard/`, extracted shared components, split large files.
- **Backend model reorganization**: New `models/recommendation/`, `models/creation/`, `models/evolution/`, `models/friction/`, `models/session/` packages.
- **Inference config persistence**: Only saves fields that differ from defaults so users pick up new defaults on upgrade.
- **Demo guard routes**: Updated blocked routes for `/extensions` prefix.
- **GitHub downloads**: Reuse single `httpx.Client` across recursive directory fetches instead of one per request.
- **Installable platform stores**: Created eagerly (with `create=True`) so catalog installs succeed even if the directory doesn't exist yet.

### Fixed
- **ExtensionSource StrEnum**: Use plain string values instead of `AgentType.XXX` references, which stored repr strings on some Python versions.
- **Installed extension management**: "Installed" badge replaced with actionable "Manage" button to change sync targets.
- **Partial install error reporting**: Frontend throws with per-platform failure messages instead of silently succeeding.
- **Python 3.10 compatibility**: `datetime.UTC` to `timezone.utc`, `StrEnum` shim, minimum Python raised to 3.10.
- **Personalization prompt hardening**: Guard against LLM hallucinations in recommendation/creation parsers.

### Removed
- **Legacy modules**: Deleted `retrieval.py`, old `storage/conversation/`, `catalog/` module, `services/catalog/`, analysis shared code.

## [0.9.31] - 2026-04-12

### Added
- **Recommendation pipeline**: L1-L4 engine with TF-IDF retrieval, multi-signal scoring, LLM profiling/rationale, catalog loader, API endpoints, and frontend view.
- **Recommend CLI**: `vibelens recommend` with backend auto-discovery and lightweight compaction-based extraction.
- **Catalog CLI**: `vibelens build-catalog` and `vibelens update-catalog` commands.
- **Light mode**: Full light/dark/system theme with CSS custom property tokens, semantic color migration across all components, and settings toggle.
- **Expanded tool categories**: Added interact, browser, and infra groups.

### Fixed
- **Recommendation 404**: Bundled catalog with static assets to resolve missing route.
- **Python 3.10 compatibility**: Replaced `datetime.UTC` with `timezone.utc`, added `StrEnum` shim, raised minimum Python to 3.10.

### Changed
- **Frontend restructure**: Renamed `conversation/` to `session/`, `analysis/` to `dashboard/`, extracted `friction/` and `upload/` directories, split large components (step-block, friction-panel, skill-analysis-views), promoted shared state components to root.
- **Backend model reorganization**: New `models/recommendation/`, `models/creation/`, `models/evolution/`, `models/friction/`, `models/session/` packages. Moved prompts to `src/vibelens/prompts/`.
- **GEMINI_CLI merged**: Consolidated `GEMINI_CLI` into `GEMINI` enum across backend and frontend.
- **Naming updates**: `AgentType`/`BackendType` renamed to official product names. `cached_input_per_mtok` to `cache_read_per_mtok`.

## [0.9.30] - 2026-04-09

### Added
- **Skill importer**: New `services/skill/importer.py` auto-imports agent skills from Claude Code, Codex, and third-party agent skill directories at startup.
- **Skill download service**: New `services/skill/download.py` for fetching featured skills from the catalog.
- **Upload zip commands**: Extracted per-agent zip commands to `services/upload/commands.py` for cleaner upload processor.
- **Utility modules**: Added `utils/content.py` (text extraction helpers), `utils/identifiers.py` (timestamped ID generation), `utils/json.py` (JSONL locking, reading).
- **Trajectory storage package**: New `storage/trajectory/` package replacing `storage/conversation/` with clearer naming (`BaseTrajectoryStore`, `DiskTrajectoryStore`, `LocalTrajectoryStore`).
- **Store tests**: Added `tests/storage/test_disk_store.py` and `tests/storage/test_local_store.py` with full ABC compliance tests.
- **Session route tests**: Added `tests/api/test_session_routes.py`.

### Fixed
- **Analysis session index alignment**: LLM sometimes used batch indices (e.g. `"12"`) instead of session UUIDs in StepRef outputs, causing all step references to be silently dropped. Added `session_index` field to `SessionContext`, index-to-UUID fallback in `SessionContextBatch.resolve_step_ref`, and per-batch 0-based reindexing in the session batcher.
- **Example analyses invisible in result view**: `is_example` flag was on Meta schemas but missing from `FrictionAnalysisResult` and `SkillAnalysisResult` models. Pydantic silently stripped the flag when loading full results, so the "Example" badge never appeared on result detail views. Added `is_example` to both result models.
- **Extraction index gaps on skipped sessions**: `extract_all_contexts` used `enumerate()` causing index gaps when sessions were skipped. Now uses `len(contexts)` for sequential 0-based indices.

### Changed
- **Storage rename**: `storage/conversation/` renamed to `storage/trajectory/`. `TrajectoryStore` to `BaseTrajectoryStore`, `DiskStore` to `DiskTrajectoryStore`, `LocalStore` to `LocalTrajectoryStore`. All imports updated across the codebase.
- **Skill store unification**: Removed `storage/skill/codex.py` (`CodexSkillStore`). Codex skills now use `DiskSkillStore` with `SkillSourceType.CODEX`, matching the Claude Code skill store pattern.
- **Dependency renames**: `get_store()` to `get_trajectory_store()`, `get_skill_store()` to `get_claude_skill_store()`.
- **Utils consolidation**: `utils/text.py` merged into `utils/content.py` (`extract_text` renamed to `content_to_text`). `utils/json_helpers.py` merged into `utils/json.py`. Removed `utils/paths.py`, `utils/github.py`, `utils/json_extract.py`.
- **Upload processor simplified**: Extracted zip commands, replaced `uuid4()` with `generate_timestamped_id()`, reduced module from ~460 to ~250 lines.
- **Analysis loading UI**: Stop button moved above informational text in both friction and skill analysis waiting screens. Text reordered: "Usually takes 2-5 minutes" before "Running in background".
- **Background startup**: Renamed `_lightweight_startup` to `_run_background_startup`, now runs `import_agent_skills()` and `seed_example_analyses()`.

### Removed
- **Deleted modules**: `storage/conversation/` (replaced by `storage/trajectory/`), `storage/skill/codex.py`, `utils/github.py`, `utils/json_extract.py`, `utils/json_helpers.py`, `utils/paths.py`, `utils/text.py`.
- **Deleted tests**: Removed outdated tests for deleted modules (`tests/api/test_e2e.py`, `tests/config/`, `tests/ingest/anonymize/`, `tests/live/`, `tests/services/friction/`, `tests/services/session/`, `tests/utils/`).

## [0.9.29] - 2026-04-08

### Added
- **Example analyses in self-use mode**: Pre-built friction and skill analysis examples are now loaded alongside user analyses in self-use mode, not just demo mode. Configured via `examples.sessions` in `self-use.yaml`.
- **`is_example` flag**: Added `is_example` field to `FrictionMeta` and `SkillAnalysisMeta` schemas. Injected during startup file copy so frontend can distinguish bundled examples from user-generated analyses.
- **Example badge on result headers**: Friction and skill analysis result headers show an amber "Example" badge when viewing a bundled example analysis.

### Changed
- **Example badge logic**: History cards now use `is_example` flag (or `model.startsWith("mock/")` fallback) instead of demo-mode check, so badges appear correctly in both demo and self-use modes.
- **Store resolver in self-use mode**: `list_all_metadata()`, `load_from_stores()`, `load_from_all_stores()`, and `get_metadata_from_stores()` now include example store sessions alongside user sessions in self-use mode.
- **Example seeding refactored**: Startup copies pre-built analysis JSON files from `examples/recipe-book/` into user stores (appending to existing index), replacing the previous demo-only mock generation approach.
- **Donation consent dialog redesign**: Wider modal with colored icons per consent item, card layout, cyan intro banner, and Heart icon in header and button.
- **Refresh button feedback**: Session list refresh button shows spin animation and disabled state while loading.

## [0.9.28] - 2026-04-08

### Changed
- **Donate consent dialog redesign**: Each consent item now has a colored icon, card layout, and a highlighted research team banner. Wider modal, Heart icon in header and Donate button.
- **Example badge on mock results**: Friction and skill analysis result headers show an "Example" badge when `backend_id` is `mock`, replacing the demo-mode-only badge on history cards.
- **History "Example" badge logic**: Friction and skill history cards now show "Example" based on `model.startsWith("mock/")` instead of `isDemo`, so real analyses in demo mode are not mislabeled.
- **"Analyze your own sessions" tooltip**: New button tooltip on friction and skill result headers replaces generic "Analyze new sessions".
- **Seed example friction analysis**: App startup now seeds a mock friction analysis alongside skill analyses, so new users see example results in the Productivity Tips history.
- **Tutorial tour improvements**: Reworded all tour step titles and descriptions for clarity. Added "Conversation" step targeting the browse tab. Reordered Personalization before Productivity Tips. Back-navigation now correctly skips missing targets instead of always advancing forward.
- **Refresh button loading state**: Session list refresh button is disabled and spins while loading.
- **Config path cleanup**: Demo config uses `~/.vibelens/donations` and `~/.vibelens/uploads` (removed `-v2` suffix).

## [0.9.27] - 2026-04-08

### Fixed
- **Shared uploaded sessions 404**: Share links for uploaded sessions failed with "Share not found or has been revoked" because the share endpoint resolved sessions using the viewer's token (which differs from the uploader's). Added `load_from_all_stores()` that searches all upload stores regardless of token, used by share resolution endpoints.

## [0.9.26] - 2026-04-08

### Changed
- **Removed summary and user_profile fields**: Dropped `summary`, `user_profile` from all analysis models (friction, skill retrieval/creation/evolution), LLM prompts, synthesis templates, mock data, and frontend types. Analysis results now show only title, tips/recommendations, and issue cards.
- **Self-explanatory titles**: All LLM prompt templates now enforce a 10-word max self-explanatory `title` that readers can understand without reading the rest of the report.
- **Plain-language friction types**: Removed hardcoded friction type taxonomy from prompts. LLM now generates plain-language kebab-case labels (e.g. "changed-wrong-files") instead of fixed categories. Frontend converts kebab-case to Title Case dynamically.
- **Audience section in all prompts**: Added "Audience" block to all analysis and skill prompt templates requiring plain, everyday language with no coding jargon.
- **Rationale format standardized**: All rationale Field descriptions and prompt rules now enforce "one sentence (max 15 words), then `\n-` bullets (max 10 words each)" across friction and skill models.
- **Tutorial banners**: Added `TutorialBanner` component shown on welcome pages, loading screens, and result pages explaining how each analysis feature works.
- **Collapsible rationale sections**: "Why This is Useful" renamed to "Why this helps" and made collapsible (expanded by default) across all card types: MitigationCard, RecommendationCard, CreatedSkillCard, EvolutionCard.
- **Section label renames**: "Addressed Issues" renamed to "What this fixes", "Addressed Workflow Patterns" to "What this covers", "Issues Found" to "What Went Wrong", "Workflow Patterns" to "How You Work".
- **Section heading font size**: Section headers (friction and skill panels) enlarged from `text-base` to `text-lg`.
- **Demo mode guards**: Added `useDemoGuard` hook that intercepts write actions (create/edit/delete skills, install, sync) in demo mode and shows the install-locally dialog instead. Applied across local-skills-tab, explore-skills-tab, skill-cards, skill-analysis-views, friction-history, skills-history.
- **Example badge in history**: Friction and skill history cards show an "Example" badge when in demo mode.
- **Share dialog redesign**: Session share flow now opens a modal with a copyable URL input instead of inline "Link copied!" text. Demo mode blocks sharing uploaded sessions with an explanation dialog.
- **Session download via fetch**: Export button now uses `fetchWithToken` (supporting auth tokens) instead of direct `<a>` link navigation.
- **Header collapse toggle**: Session header collapse toggle moved from a separate button to clicking the header row itself, using `ChevronRight`/`ChevronDown` instead of `ChevronUp`/`ChevronDown`.
- **Prompt nav default state**: Prompt navigation sidebar now starts expanded instead of collapsed.
- **Skill detail popup polish**: Tags and Allowed Tools sections switched from stacked to inline row layout. Description text lightened. Font sizes increased for stats, source links, and sync buttons.
- **Install locally dialog extracted**: `InstallLocallyDialog` extracted from `analysis-welcome.tsx` to its own file for reuse by demo guard hooks.
- **Demo store resolver**: Demo mode now always shows example sessions alongside user uploads, instead of showing only uploads when present.
- **Session export logging**: Added structured logging to session export and download endpoints for debugging 404s.
- **CopyButton on mitigation tips**: MitigationCard action text now has a copy button.
- **Hidden detail sections**: Added `SHOW_ANALYSIS_DETAIL_SECTIONS` constant (default `false`) to hide "What Went Wrong" and "How You Work" sections, keeping the UI focused on tips and recommendations.

### Removed
- **Friction type taxonomy**: Removed the 10-item hardcoded taxonomy from the analysis prompt. LLM now freely names friction types.
- **`FRICTION_TYPE_LABELS` map**: Removed the static label lookup in favor of dynamic kebab-to-title conversion.
- **`SHARE_STATUS_RESET_MS` constant**: No longer needed with the modal-based share flow.
- **Example data files**: Removed `examples/claude-example-v2/` (session data, friction analyses, skill analyses) from tracked files.

## [0.9.25] - 2026-04-08

### Changed
- **Skill evolution color theme**: Replaced amber accent with teal to match recommendation cards across all evolution UI elements (borders, badges, buttons, icons, confidence bars).
- **Skill selection dialog for evolution**: Users now choose which installed skills to evolve before analysis starts, with checkbox list and select-all toggle. Selection passed through API to filter skills sent to LLM.
- **Skill Description label**: All skill cards (Recommendation, Creation, Evolution) now display a bold "Skill Description:" prefix before the description text.
- **BulletText markdown rendering**: Rewrote component to parse `**bold**` into `<strong>` elements and handle `\n\n` robustly between bullets.
- **Model field descriptions**: Refined `rationale`, `summary`, and `user_profile` field descriptions across all skill models for conciseness and plain language with explicit bullet-point format guidance.
- **LLM prompt bullet format rules**: All skill prompt templates now enforce bullet-point format for rationale, summary, and user_profile via two concise lines in Output Rules. No over-emphasis.
- **Waiting page text styling**: Unified analysis loading text to `text-sm text-zinc-400` for better readability.

### Fixed
- **Tooltip overlap on Reference buttons**: Removed nested `<Tooltip>` wrappers from `FrictionRefList` and `StepRefList`, keeping only individual button tooltips.
- **Duplicate evolution proposals**: Added server-side dedup keeping first proposal per skill, plus prompt-level "one proposal per skill" rule in evolution proposal template.

## [0.9.24] - 2026-04-07

### Changed
- **Friction panel redesigned**: Productivity Tips (MitigationCard) restyled as sectioned cards with title, action, "Why This is Useful" rationale, and expandable "Addressed Issues" with step reference links. Added `rationale` field to `Mitigation` model.
- **Issues Found cards**: Boxed card layout with severity badge left of title, description always visible, and clickable whole-block toggle for Details section showing Impact (steps, duration, tokens) and Reference step links.
- **Workflow Patterns cards**: Redesigned to match Issues Found style with frequency badge left of title, description visible, whole-block clickable toggle for Reference links.
- **Unified Reference style**: Both friction and skill analyses now use the same enlarged Reference label (`text-sm`, `w-4 h-4` icon) and step buttons (`text-xs`, `px-3 py-1.5`).
- **Impact section**: Added "Impact:" highlight title with Zap icon and concise tooltips ("Steps affected", "Duration affected", "Tokens affected") replacing verbose descriptions.
- **Friction type names enlarged**: `text-sm` to `text-base` in both Issues Found cards and Addressed Issues within MitigationCards.
- **`user_profile` bullet format**: Propagated "one-sentence + bullet points" format across all friction and skill models, prompt templates, mock data, and example JSONs.
- **Tab persistence**: Personalization sub-tab selection saved to localStorage and respected during demo auto-load.
- **Enlarged font sizes**: Skill names, card titles, section labels ("Why This is Useful", "Addressed Issues") enlarged from `text-xs`/`text-sm` to `text-sm`/`text-base`.
- **Legacy friction migration removed**: All `model_validator` migration methods and `Any`/`model_validator` imports removed from `friction.py`. Example data updated to new `friction_types` format.

## [0.9.23] - 2026-04-07

### Changed
- **Structured output format for all LLM analysis**: Summary, rationale, and description fields across friction, retrieval, creation, and evolution models now require "one-sentence conclusion + bullet points" format with explicit word limits, replacing free-form prose.
- **Title field descriptions tightened**: All LLM-generated titles capped at 8 words with "clear, reader-friendly" guidance.
- **Skill description propagated to recommendations and evolutions**: `SkillRecommendation` and `SkillEvolution` now carry a `description` field; `SkillCreation` gains `addressed_patterns`.
- **`WorkflowPattern.gap` removed**: Redundant with pattern description; removed from model, types, templates, and UI.
- **Skill analysis views redesigned**: Summary and user profile merged into a single card with divider. Purple/violet theme replaced with zinc/teal to match recommendation cards. Workflow pattern cards now expandable inline within each skill card.
- **Prompt templates refined**: All skill and friction Jinja2 templates updated for tighter output constraints, consistent bullet-point formatting, and reduced verbosity.
- **Model field ordering**: `SkillAnalysisResult` and `SkillEvolution` fields reordered for logical grouping (metadata, content, metrics, warnings).
- **`SkillEdit` model relocated**: Moved after `SkillEvolutionProposalResult` for better reading order in `evolution.py`.
- **Demo examples updated**: Friction and skill analysis example JSONs in `examples/claude-example-v2/` refreshed to match new model shapes.

### Fixed
- **Friction panel UI**: Mitigation `title` field added to model and displayed in friction cards. User profile card styling and confidence score placement improved.
- **Sub-agent block and flow diagram**: Minor layout and color adjustments for readability.
- **Collapsible pill**: Styling tweak for consistent appearance.

## [0.9.22] - 2026-04-06

### Added
- **Cost estimate dialog for skill analysis**: Pre-flight cost confirmation before running retrieval, creation, and evolution analyses, matching friction's existing flow. Shared `CostEstimateDialog` component used by both panels.
- **`SessionContext` domain model**: New `models/context.py` consolidates session context, step-ref resolution, and trajectory aggregation into a single Pydantic model, replacing loose tuples and `IdMapping`/`remap_session_ids`.
- **Agent message extraction**: Context extraction now includes truncated agent text messages alongside tool calls, controlled by new `ContextParams` fields.
- **Analysis ID log correlation**: All log records during an analysis run are tagged with `[analysis_id]` via a `ContextVar`, making it easy to trace multi-batch runs in logs.
- **`max_analysis_sessions` setting**: Configurable limit (default 30) on sessions per analysis request, exposed via `/api/settings` and enforced in the frontend with a warning banner.
- **`user_profile` and `confidence` on friction results**: Friction analysis now returns a user working-style profile and per-mitigation confidence scores.

### Changed
- **Friction model overhaul**: Flattened `FrictionLLMEvent`/`FrictionLLMBatchOutput`/`FrictionSynthesisOutput` into a single `FrictionAnalysisOutput`. Renamed fields (`friction_detail` to `description`, `estimated_cost` to `friction_cost`, `events` to `friction_events`). Removed per-type aggregation (`TypeSummary`), `claude_helpfulness`, `friction_id`, `project_path`, and `cross_batch_patterns`.
- **Friction panel UI**: Events grouped by friction type with collapsible sections. Severity descriptions reworded to second-person. Human-readable friction type labels.
- **Trajectory field renames**: `last_trajectory_ref` to `prev_trajectory_ref`, `continued_trajectory_ref` to `next_trajectory_ref`.
- **Session view modes**: `"timeline"` renamed to `"detail"`, `"flow"` to `"workflow"`.
- **Share service rewritten**: Registry-based model (`shared.json`) instead of per-token snapshot files. Shares load from the normal trajectory store at read time.
- **Session batcher restructured**: `SessionBatch` replaced by `SessionContextBatch`. Oversized session splitting happens before chaining. Clearer function naming throughout.
- **Skill prompt caps tightened**: Per-batch proposals capped at 3 patterns and 3 proposals. Synthesis caps: 5 patterns, 5 creation proposals, 8 evolution proposals.
- **Models reorganized**: `models/inference.py`, `models/pricing.py`, `models/prompts.py` moved to `models/llm/` subpackage.
- **Friction and skill analysis share more infrastructure**: Extracted `log_analysis_summary()`, `format_batch_digest()`, and `merge_batch_refs()` as shared helpers.

### Removed
- **`services/friction/digest.py`**: Merged into `analysis_shared.format_batch_digest()`.
- **`StepSignal` model and signal-based digest path**: All analysis uses `SessionContext` exclusively.
- **Two-step proposal/create API**: Removed `/api/skills/analysis/proposals` and `/api/skills/analysis/create` endpoints; consolidated into single analysis flow.
- **Share snapshot files**: Per-token `.json`/`.meta.json` files on disk no longer created.

## [0.9.21] - 2026-04-05

### Changed
- **Consistent skill field naming**: `SkillCreationProposal.name` → `skill_name`, `SkillRecommendation.match_reason` → `rationale`. All three skill modes now share `skill_name`, `rationale`, and `addressed_patterns` fields.
- **Structured evolution proposal result**: `_infer_skill_evolution_proposals` returns `SkillEvolutionProposalResult` instead of a raw 6-tuple, matching the creation pipeline pattern.
- **Session filtering for deep creation**: Proposals with `relevant_session_indices` now load only the referenced sessions instead of all sessions, reducing token cost.
- **Skill template naming convention**: Renamed to `{mode}_{stage}_{role}.j2` -- `deep_creation_*` → `creation_*`, `deep_edit_*` → `evolution_*`, `proposal_*` → `creation_proposal_*`.
- **Template prompt consistency**: Added missing `title` field to retrieval pattern instructions, `addressed_patterns` to evolution proposal rules, "Output Rules" section to retrieval system prompt, and batch titles to all synthesis user prompts.
- **Diagnostic logging**: Token budget breakdown and truncation stats in `truncate_digest_to_fit`. Proposal and recommendation names logged after LLM generation in all three skill services.

## [0.9.20] - 2026-04-04

### Added
- **Claude Web parser**: New `claude_code_web` parser for claude.ai "Export Data" ZIP files. Upload dialog shows dedicated instructions when this source is selected. Multi-conversation files are split into independent sessions automatically.
- **Agent-level dashboard filtering**: Clicking an agent row in the distribution chart drills down into that agent's stats. Breadcrumb navigation shows `Agent / Project` hierarchy with clickable segments.
- **Skill preview dialog**: Unified `SkillPreviewDialog` replaces the old inline-edit and direct-install flows. Users can read, edit, and confirm SKILL.md content before installing or updating -- used for catalog recommendations, new creations, and evolution suggestions.
- **CLI model selector**: LLM config now shows available models per CLI backend with inline pricing. Backends declare `available_models`, `default_model`, and `supports_freeform_model`. New `GET /llm/cli-models` endpoint powers the selector.
- **LLM pricing in status bar**: `GET /llm/status` and `POST /llm/configure` now return `pricing` (input/output per MTok) for the configured model.
- **Skill evolution selection step**: New LLM-powered pre-filter asks which installed skills are relevant before loading full SKILL.md content, reducing context bloat for large skill collections.
- **Featured skill preview**: `GET /skills/featured/{slug}/content` fetches raw SKILL.md from GitHub with 1-hour cache, enabling preview-before-install in the Explore tab.

### Changed
- **Shared analysis infrastructure**: Extracted `analysis_shared.py` with `require_backend()`, `run_batches_concurrent()`, `build_digest_from_contexts()`, and other helpers that were duplicated across friction, retrieval, creation, and evolution services.
- **Configurable context extraction**: Replaced hardcoded truncation constants with `ContextParams` dataclass and three presets (`PRESET_CONCISE`, `PRESET_MEDIUM`, `PRESET_DETAIL`). Added path shortening (`$HOME` → `~`).
- **Batched skill analysis**: Retrieval, creation, and evolution now use the same batch + synthesis pattern as friction -- concurrent LLM calls per batch with a synthesis pass when multiple batches exist.
- **Skill models split**: Monolithic `models/skill/skills.py` split into `patterns.py`, `retrieve.py`, `create.py`, `evolve.py`, `results.py` with mode-specific output types replacing the catch-all `SkillLLMOutput`.
- **Simplified `SkillEdit` model**: Dropped `kind`/`target`/`replacement`/`conflict_type` enum pattern in favor of `old_string`/`new_string`/`replace_all` -- mirrors text editor semantics and is less ambiguous for LLM output.
- **Template directory reorganization**: Flat `templates/` Jinja2 files moved into `templates/friction/`, `templates/highlights/`, `templates/skill/` subdirectories.
- **Two-tier search index**: Replaced single-tier 5-minute-TTL index with lazy two-tier architecture -- Tier 1 (metadata-only) loads synchronously at startup for instant search; Tier 2 (full text) builds asynchronously in a thread pool. Incremental `add_sessions_to_index()` after uploads instead of full invalidation.
- **Evolution diff view**: Now computes real 1-based line numbers from original file content and shows grey context lines alongside red/green diff rows.
- **Gemini CLI system prompt**: System prompt now passed via `GEMINI_SYSTEM_MD` env var temp file instead of stdin concatenation. OpenCode CLI gained `--system` flag support.
- **CLI backend model resolution**: When user config has the LiteLLM default or is empty, falls back to each backend's own `default_model`.
- **Skills tab labels**: "Discover" renamed to "Recommend". "Apply & Edit" renamed to "Preview & Update". Explore tab gains a "Recommend" shortcut button.
- **Tour steps**: Single "AI-Powered Insights" stop split into "Productivity Tips" and "Personalization" with distinct icons.
- **Nav tooltips**: Native `title` attributes replaced with shared `Tooltip` components on all main-nav tab buttons.
- **`WorkflowPattern.pain_point` renamed to `gap`** across models, templates, and UI.

### Removed
- **StepSignal-based digest path**: Deleted `services/friction/signals.py` and `services/skill/digest.py`. All analysis now uses the `SessionContext` path from `context_extraction.py`.
- **`skill_creation.py` prompt**: Single-call creation prompt removed; creation now uses the proposal + deep-creation two-phase pipeline exclusively.
- **Dead skill constants**: `EDIT_KIND_*`, `CONFLICT_TYPE_*`, `MODE_COLORS` removed from frontend constants.

## [0.9.19] - 2026-04-03

### Fixed
- **CLI tempfile concurrency**: `generate()` now isolates temp files per call via save/restore, preventing concurrent coroutines from deleting each other's files.
- **Amp NDJSON parsing**: `AmpCliBackend` no longer sets `supports_native_json = True` (which skipped schema instructions). Overrides `_parse_output` to extract the last valid JSON line from the NDJSON stream.
- **Overly broad exception in LiteLLM cost extraction**: Narrowed `except Exception` to `except (ValueError, litellm.exceptions.NotFoundError)` in `_extract_cost()` so unexpected errors surface instead of being silently swallowed.

### Changed
- **`model` property on `InferenceBackend` ABC**: Added a concrete `model` property (default `"unknown"`) to the base class, overridden in `CliBackend` and `LiteLLMBackend`. Removed the duplicated `_get_backend_model()` helper from 4 service files.
- **Shared `monotonic_ms()`**: Deduplicated identical `_now_ms()` functions from `cli_base.py` and `litellm_backend.py` into `utils/timestamps.monotonic_ms()`.
- **Top-level `import importlib`**: Moved from inside `_create_cli_backend()` to the module's stdlib import group in `backends/__init__.py`.

## [0.9.18] - 2026-04-02

### Added
- **Background job system**: Friction and skill analyses now run as background async jobs with polling, cancellation, and a periodic cleanup task. New `job_tracker` service and `/jobs/{id}` + `/jobs/{id}/cancel` endpoints for both pipelines.
- **Skill proposals + deep creation**: Two-phase skill creation workflow. `POST /skills/analysis/proposals` generates lightweight proposals; `POST /skills/analysis/create` produces full SKILL.md content for an approved proposal.
- **CLI backend expansion**: Added Gemini, Cursor, Kimi, OpenClaw, OpenCode, Aider, and Amp CLI backends via a lazy-import registry (`_CLI_BACKEND_REGISTRY`), replacing the monolithic `SubprocessBackend`.
- **Skill evolution diff view**: PR-review-style unified diff UI for evolution suggestions with two-column line number gutters, red/green diff lines, hunk separators, and conflict type badges.

### Changed
- **Analysis endpoints return jobs**: `POST /friction` and `POST /skills/analysis` now return `AnalysisJobResponse` instead of blocking until completion. Frontend polls for results.
- **Frontend job-aware panels**: Friction and skill panels accept `activeJobId`, poll for completion, and show a cancellable "running in background" spinner.
- **LLM config form**: CLI backends hide API key, model, and advanced settings. Shows a "uses local installation" hint instead.
- **Text readability**: Brightened and enlarged body text across skill analysis views and friction panel for better contrast on dark backgrounds.

## [0.9.17] - 2026-04-01

### Fixed
- **Donation: upload store resolution**: Donation sender now includes per-user upload stores when searching for sessions, fixing "Source file not found" errors when donating uploaded sessions in demo mode.

### Changed
- **Donation error logging**: All error paths in the donation pipeline now emit `WARNING`-level log messages with diagnostic context (store names, file paths, parser types, tracebacks). Previously errors were only returned to the frontend with no server-side logging.
- **Parser file read errors**: `BaseParser.parse_file` OSError logging upgraded from `DEBUG` to `WARNING` with exception detail.
- **Store load failures**: `TrajectoryStore.load` now logs a warning when a parser returns no trajectories for an indexed session.

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

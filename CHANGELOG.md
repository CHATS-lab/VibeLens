# Changelog

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

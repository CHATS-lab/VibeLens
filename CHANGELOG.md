# Changelog

## [0.6.0] - 2026-03-18

### Added
- **ATIF v1.6 trajectory model**: Replaced session/message model with `Trajectory` → `Step` hierarchy in `models/trajectories/`. Full multimodal content support (text, image, PDF).
- **Service layer** (`services/`): `session_service.py`, `upload_service.py`, `demo_loader.py` — business logic extracted from API routes and stores.
- **`LocalStore`** (`stores/local.py`): Reads directly from `~/.claude/` with lazy parsing. No intermediate SQLite layer.
- **`DiskStore`** (`stores/disk.py`): JSON-file-based storage for demo mode and uploads. Supports subdirectory organization.
- **Step timeline** (`step-timeline.tsx`): Visual timeline with elapsed time between steps and step-source indicators.
- **Session file discovery** (`ingest/discovery.py`): Recursive file finder for Claude Code, Codex, and Gemini session directories.


## [0.5.0] - 2026-03-17

### Added
- Two-mode system: self-use (default) and demo mode with in-memory or SQLite storage.
- Pre-loaded example sessions, per-tab client isolation, TTL cleanup for demo uploads.
- Config templates (`config/`), example sessions (`examples/`).
- VibeLens Export v1 parser, zip upload, batch download, sub-agent count.

### Fixed
- Claude Code parser: timestamp, duration, token counts, project path extraction.
- Gemini: empty content handling, token aggregation, project resolution, JSON fingerprinting.

## [0.4.0] - 2026-03-16

### Added
- File upload with auto-format detection.
- Session export, view modes (By Time / By Project), resizable panels.
- Parsers refactored into `ingest/parsers/` sub-package.

## [0.3.0] - 2026-03-15

### Added
- MongoDB target/source with push/pull API.
- Config package with YAML-first configuration.
- Frontend: session viewer, message rendering, sub-agent display, prompt navigation.

## [0.2.0] - 2026-03-15

### Added
- Codex CLI and Gemini CLI parsers.
- Cross-agent correlation, tool normalization, parse diagnostics.
- Tool dependency graph, phase detection, format auto-detection, parallel parsing.

## [0.1.0] - 2026-03-14

### Added
- Project skeleton: FastAPI backend, React frontend, CLI.
- Claude Code and Dataclaw parsers, LocalSource, HuggingFace source.
- SQLite database, Pydantic models, test suite.

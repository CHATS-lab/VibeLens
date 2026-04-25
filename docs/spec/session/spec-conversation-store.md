# Trajectory Storage

Storage layer for agent trajectories. Provides a unified interface for listing, loading, and saving parsed session data across app modes.

## Purpose

All services (dashboard, session viewer, friction analysis, skill analysis, upload, donation) access session data through a common `TrajectoryStore` interface. Two implementations serve different modes: `DiskStore` for demo/upload workflows, `LocalStore` for self-use with local agent data directories.

## Architecture

```
                     API / Services
  dashboard  session.crud  upload  friction  skill  donation
      |           |          |        |        |       |
      +-----+-----+----+----+--------+--------+-------+
            |           |
       get_store()   store_resolver
       (deps.py)     (session/store_resolver.py)
            |           |
            v           v
   +-----------------------------+
   |   TrajectoryStore (ABC)     |  base.py
   |                             |
   |  list_metadata()  load()    |
   |  exists()  session_count()  |
   |  invalidate_index()         |
   +----------+----------+------+
              |          |
     +--------+--+  +----+--------+
     | DiskStore |  | LocalStore  |
     | (demo)    |  | (self)      |
     +--------+--+  +------+------+
              |            |
       JSON files     4 agent parsers
       + JSONL index  scanning local dirs
```

## Key Files

| File | Role |
|------|------|
| `storage/trajectory/base.py` | `TrajectoryStore` ABC with shared index pattern and read methods |
| `storage/trajectory/disk.py` | `DiskStore` -- file-based persistence for demo mode and uploads |
| `storage/trajectory/local.py` | `LocalStore` -- multi-agent local discovery (read-only) |
| `services/session/store_resolver.py` | Per-user store resolution and session isolation |
| `ingest/index_builder.py` | Skeleton builder for LocalStore full/incremental rebuilds |
| `ingest/index_cache.py` | Persistent cache for fast LocalStore startup |
| `ingest/fast_metrics.py` | Line-by-line metrics scanner for skeleton enrichment |

## Store Selection

`get_store()` in `deps.py` selects the store based on app mode:

| Mode | Store | Backing |
|------|-------|---------|
| `demo` | `DiskStore` | `datasets/` directory (JSON files + JSONL index) |
| `self` | `LocalStore` | Local agent data directories (`~/.claude/`, `~/.codex/`, etc.) |

## TrajectoryStore ABC

### Internal State

| Field | Type | Purpose |
|-------|------|---------|
| `_index` | `dict[str, tuple[Path, BaseParser]]` | Maps session_id to (filepath, parser) for on-demand loading |
| `_metadata_cache` | `dict[str, dict] | None` | Maps session_id to summary dict (no steps); `None` = not yet built |

### Abstract Methods

| Method | Purpose |
|--------|---------|
| `initialize()` | Set up backing store (create dirs, etc.) |
| `save(trajectories)` | Persist a trajectory group (DiskStore only) |
| `_build_index()` | Populate `_index` and `_metadata_cache` from backing store |

### Concrete Read Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `list_metadata()` | `list[dict]` | All trajectory summaries (no steps) |
| `list_projects()` | `list[str]` | Unique project paths, sorted |
| `load(session_id)` | `list[Trajectory] | None` | Full trajectory group via parser from `_index` |
| `exists(session_id)` | `bool` | Check index membership |
| `session_count()` | `int` | Total indexed sessions |
| `get_metadata(session_id)` | `dict | None` | Single session summary |
| `invalidate_index()` | `None` | Clear cache, forces rebuild on next access |

### Load Pipeline

```
load(session_id)
  1. _ensure_index()        <- lazy-build if cache is None
  2. Lookup (path, parser) from _index
  3. parser.parse_file(path)
  4. _enrich_refs_from_index()  <- restore continuation refs from cached metadata
  5. _sort_trajectories()       <- main first, then sub-agents by timestamp
```

## DiskStore

File-system persistence using JSON files and a JSONL index. Used in demo mode and for uploaded sessions.

### Storage Layout

```
{root}/
+-- {session_id}.json       <- Full trajectory array (JSON)
+-- _index.jsonl            <- One summary line per session
+-- uploads/                <- Upload subdirectory
    +-- {upload_id}/
        +-- _index.jsonl
        +-- {session_id}.json
```

### Save Flow

1. Extract main trajectory, compute summary via `to_summary()`
2. Write `{session_id}.json` (full trajectory array)
3. Append summary to `_index.jsonl`
4. Update in-memory cache if already initialized

## LocalStore

Multi-agent read-only store. Scans local agent data directories for sessions.

### Agent Directories

| Agent | Default Directory | Config Override |
|-------|-------------------|-----------------|
| Claude Code | `~/.claude/` | `settings.claude_dir` |
| Codex | `~/.codex/sessions/` | `settings.codex_dir` |
| Gemini | `~/.gemini/tmp/` | `settings.gemini_dir` |
| OpenClaw | `~/.openclaw/` | `settings.openclaw_dir` |

### Session ID Format

- Claude Code: `{uuid}` (as-is)
- Other agents: `{agent_type}:{stem}` (prefixed to avoid collisions)

### Index Build Pipeline

```
_build_index()                              <- thread-safe via _build_lock
  1. _discover_files()                      <- parser.discover_session_files() per agent
  2. _try_load_from_cache()
     +-- Cache hit (all mtimes match)       -> restore from cache
     +-- Partial staleness (<30%)           -> incremental update
     +-- Cache miss or heavy staleness      -> full rebuild
  3. _full_rebuild()
     +-- build_session_index()              -> parse all files into skeletons
     +-- _enrich_skeleton_metrics()         -> fast-scan for tokens/tools/duration
     +-- save_cache()                       -> write persistent cache
```

## DiskStore vs. LocalStore

| Feature | DiskStore | LocalStore |
|---------|-----------|------------|
| App mode | Demo | Self |
| Writable | Yes (`save()`) | No (read-only) |
| Data sources | Single root directory | 4 agent data directories |
| Discovery | `_index.jsonl` recursion | Parser-based file scanning |
| Persistent cache | No | Yes (`~/.vibelens/index_cache.json`) |
| Incremental updates | N/A | Mtime-based staleness detection |
| Thread safety | No internal lock | `_build_lock` for concurrent rebuilds |
| Parser | `ParsedTrajectoryParser` | 4+ agent-specific parsers |

## Session Isolation (Demo Mode)

In demo mode, each browser tab gets a `crypto.randomUUID()` session token (never persisted). Uploads are registered per-token via `register_upload_store()` in `deps.py`. The `store_resolver.py` routes all listing/loading requests to the correct per-user stores.

On server restart, `reconstruct_upload_registry()` reads `metadata.jsonl` and restores per-token store mappings.

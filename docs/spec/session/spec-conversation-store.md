# Trajectory Storage

The unified store interface every service uses to list and load parsed trajectories.

## Motivation

Two very different "where do sessions come from" stories exist in VibeLens:

- **Demo mode** runs as a public service. Sessions are explicit uploads written to a per-user disk subtree, and the dashboard, session viewer, search, friction, personalization, and donation features all need to query those uploads under per-tab isolation.
- **Self mode** runs on the user's own machine. Sessions live in whatever shape each agent decided to write them — Claude's `~/.claude/projects/...`, Codex's day-bucketed rollouts, Cursor's SQLite, Hermes's mix of JSONL and JSON, and so on. There's no upload step; we read straight from the agent's data directory.

A single store interface lets every consumer treat the two modes identically: ask for `list_metadata()`, ask for `load(session_id)`, get back the same shapes. The differences (writability, multi-agent discovery, per-tab isolation) live behind that interface.

## Architecture

```
                    API / services
   dashboard  session  upload  donation  friction  personalization
       │         │       │        │         │            │
       └─────┬───┴───┬───┴────────┴────┬────┴─────┬──────┘
             │       │                 │          │
        get_store   store_resolver   register_upload_store
        (deps.py)   (services/session/store_resolver.py)
             │       │
             ▼       ▼
   ┌─────────────────────────────┐
   │   BaseTrajectoryStore (ABC) │
   │   list_metadata · load      │
   │   exists · session_count    │
   │   get_metadata · invalidate │
   └────────────┬────────────────┘
                │
       ┌────────┴────────┐
       ▼                 ▼
   DiskStore          LocalStore
   (demo / upload)    (self mode)
```

The base ABC owns the shared index pattern: every concrete store maintains `(session_id → file path + parser)` for on-demand loading and `(session_id → summary dict)` for cheap metadata listing. Subclasses override how those two structures get built.

## Modules

| Path | Role |
|---|---|
| `storage/trajectory/base.py` | `BaseTrajectoryStore` ABC |
| `storage/trajectory/disk.py` | `DiskStore` — writable, file-based persistence |
| `storage/trajectory/local.py` | `LocalStore` — read-only multi-agent local discovery |
| `services/session/store_resolver.py` | Per-token store routing for demo mode |
| `ingest/index_builder.py` | Skeleton builder used by `LocalStore` cold rebuild |
| `ingest/index_cache.py` | Persistent cache used by `LocalStore` warm path |

## Store selection

`get_store()` in `deps.py` picks the implementation off the active `AppMode`:

- **demo** → `DiskStore` rooted at the demo dataset directory; per-token uploads add additional `DiskStore` instances scoped to that token.
- **self** → a single `LocalStore` reading every registered local parser's data directory.
- **test** → small `DiskStore` against a fixture root.

## DiskStore — writable, file-backed

Used by demo dataset hosting and by every upload.

```
{root}/
├── {session_id}.json       full trajectory group (JSON array)
├── index.jsonl            append-only summary index, one line per session
└── uploads/{upload_id}/
    ├── {session_id}.json
    └── index.jsonl
```

`save(trajectories)` extracts the main trajectory's `to_summary()`, writes the full JSON file, appends a line to `index.jsonl`, and (if the index is already in memory) updates the cache so the new session is visible without a rebuild. `index.jsonl` appends use the shared `locked_jsonl_append` helper so concurrent uploads don't interleave bytes.

Loads go through `ParsedTrajectoryParser`, which deserialises the on-disk JSON back to ATIF `Trajectory` objects.

## LocalStore — read-only, multi-agent

Used in self-mode. Each registered local parser declares the directory it expects to find data under (`~/.claude/`, `~/.codex/...`, etc.); `LocalStore` walks them all, dispatches per-file work to the parser that owns the path, and unifies the result.

The cold / warm path mechanics — partial vs. full rebuild, the `[mtime_ns, size]` cache key, `parse_skeleton_for_file`, the staleness window — live in [`spec-session-loading.md`](spec-session-loading.md).

Session ID convention: Claude sessions keep the agent's UUID; sessions from other agents are namespaced as `{agent_type}:{stem}` so no two agents can collide on the same id.

## DiskStore vs. LocalStore

| Aspect | DiskStore | LocalStore |
|---|---|---|
| Writable | Yes (`save`) | No |
| Data sources | one root + per-upload subdirs | every registered local parser's data dir |
| Discovery | `index.jsonl` walk | parser-driven file scanning |
| Persistent cache | none (the on-disk JSON *is* the cache) | `~/.vibelens/session_index.json` |
| Concurrency | `locked_jsonl_append` for index writes | `_build_lock` around index rebuilds |

## Per-tab isolation in demo mode

Each browser tab generates a `crypto.randomUUID()` on page load and sends it as `X-Session-Token` on every request. `register_upload_store(token, store)` binds a per-upload `DiskStore` to that token; `store_resolver` returns:

- demo + the token has registered uploads → only those stores.
- demo + no registered uploads → the shared example store.
- self → the single `LocalStore`, no token filtering.

On server restart, `reconstruct_upload_registry()` replays `~/.vibelens/uploads/metadata.jsonl` to rebuild the token-to-stores mapping so existing browser tabs keep their uploads visible.

## What the ABC guarantees

- `list_metadata()` always returns a list of summary dicts (no `steps`).
- `load(session_id)` always runs the parser; the trajectory is never served from cached step data.
- `exists` / `session_count` / `get_metadata` operate on the in-memory cache; they're effectively free after the first `list_metadata`.
- `invalidate_index()` drops the in-memory cache; the next access rebuilds.
- After load, continuation references (`prev/next_trajectory_ref`) are restored from the cached skeleton metadata so a single `load` returns a self-consistent multi-segment trajectory group.

## Out of scope

- Cross-process locking. The store assumes single-process VibeLens; if that ever changes, `index.jsonl` writes still serialise via `flock`, but the in-memory caches go stale.
- Remote stores (S3, NFS, etc.). Both implementations assume the local filesystem.

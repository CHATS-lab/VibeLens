# Session Loading

Reads agent session files from the local filesystem and exposes a metadata index that the sidebar, search, and dashboard consume. Designed to make a fresh-process startup fast on a multi-GB corpus, and to make subsequent reloads near-instant when nothing has changed.

## Purpose

Self-use VibeLens points at one or more agent data directories (`~/.claude/`, `~/.codex/`, etc.). The user expects:

- The sidebar to populate within a second on a cold launch, even with thousands of sessions and multi-GB total content.
- Reload-during-active-session to feel instant, even when the user just typed another prompt and one large JSONL grew by a few hundred bytes.
- New sessions to appear without restarting the process.
- Stale state to never persist silently — if a file is rewritten, the cache must notice.

The session-loading subsystem owns these properties.

## Architecture

```
                            LocalTrajectoryStore.list_metadata()
                                       |
                                       v
                          +-------------------------+
                          |  _ensure_index()        |
                          |  (lazy, thread-safe)    |
                          +-----+-------------------+
                                |
                                v
                +---------------+----------------+
                |  _try_partial_rebuild()        |
                |  (cache-driven warm path)      |
                +---+----------+-----------+----+
                    |          |           |
         fast path  |          | partial   | cache miss /
       (all unchanged)         | (some     | corruption
                    |          |  changed) |
                    v          v           v
        +------------------+   +-----------------+   +-----------------+
        | hydrate from     |   | _partial_rebuild|   | _full_rebuild() |
        | metadata cache   |   |  partition.changed |
        +--------+---------+   +--------+--------+   +--------+--------+
                 |                      |                     |
                 |                      |                     v
                 |                      |       +-----------------------------+
                 |                      |       |  build_session_index()      |
                 |                      |       |   1. parser.parse_session_index() (fast index per parser)
                 |                      |       |   2. _build_orphaned_skeletons() (parallel)
                 |                      |       |   3. _build_file_parse_skeletons() (fallback, parallel)
                 |                      |       +-----------------------------+
                 |                      |                     |
                 |                      v                     v
                 |       +------------------------------+   +-----------------------+
                 |       | build_partial_session_index()|   |  full skeleton list   |
                 |       +------------------+-----------+   +----------+------------+
                 |                          |                          |
                 |                          v                          v
                 |       +-------------------------------+   +-----------------------+
                 |       | _enrich_skeleton_metrics()    |   | _enrich_skeleton_     |
                 |       |  parser.parse_file per file   |   |   metrics()           |
                 |       |  (no incremental fast-path)   |   |  parser.parse_file    |
                 |       +-------------------------------+   +-----------------------+
                 |                          |                          |
                 +----------+---------------+--------------------------+
                            |
                            v
              +----------------------------+
              | self._metadata_cache       |  session_id -> meta dict
              | self._index                |  session_id -> (path, parser)
              +-------------+--------------+
                            |
                            v
                 +---------------------+
                 |  save_cache()       |  ~/.vibelens/session_index.json
                 |  (atomic JSON       |  CACHE_VERSION = 10
                 |   write)            |
                 +---------------------+
```

## Key Files

| File | Role |
|------|------|
| `storage/trajectory/local.py` | `LocalTrajectoryStore` — top-level orchestrator, partition logic, enrichment, cache write |
| `ingest/index_builder.py` | Skeleton builder — `build_session_index`, `build_partial_session_index`, parallel orphan + file-parse paths |
| `ingest/index_cache.py` | Persistent JSON cache — `load_cache`, `save_cache`, `collect_file_mtimes`, `CACHE_VERSION = 10` |
| `ingest/parsers/base.py` | `BaseParser.parse_skeleton_for_file` hook (default: full-parse fallback) |
| `ingest/parsers/claude.py` | `ClaudeParser.parse_skeleton_for_file` — head-of-file user-message scan |

## Lifecycle and entry points

| When | Path | Result |
|---|---|---|
| First call after process start | `__init__` walks data dirs → `list_metadata` → `_build_index` → `_try_partial_rebuild` → cache hit or partial / full rebuild | Sidebar populated |
| Subsequent calls within `_STALENESS_CHECK_MIN_INTERVAL_S` (10 s) | In-memory `_metadata_cache` returned directly | <1 ms |
| After 10 s idle | `_invalidate_if_stale` walks disk; if mtimes match the snapshot, in-memory cache stays valid | <100 ms |
| After file change between calls | `_invalidate_if_stale` clears `_metadata_cache`; next `list_metadata` re-runs `_build_index` → partial rebuild | ~100 ms (warm) to a few seconds (large append) |

## Cache schema (CACHE_VERSION = 10)

Schema version history:

- **v7** — added `[mtime_ns, size]` stat tuples (D2). Catches in-place rewrites.
- **v8** — invalidates v7 caches whose entries still carry the old `total_cache_read` / `total_cache_write` (and Metrics `cached_tokens` / `cache_creation_tokens`) field names.
- **v9** — invalidates v8 caches that don't carry Codex sub-agent linkage (`parent_trajectory_ref` populated from session_meta source / `forked_from_id`, and `extra.agent_role` / `extra.agent_nickname`).
- **v10** — invalidates v9 caches whose `final_metrics.total_steps` was populated from the fast scanner's `message_count` (JSONL line count, structurally larger than `len(steps)` by 1.6–4.6× on Claude data). v10 entries are written via `parser.parse_file`, so `total_steps == len(traj.steps)` and `daily_breakdown.messages` sums to the same — the contract the dashboard relies on.


`~/.vibelens/session_index.json`:

```json
{
  "version": 7,
  "written_at": <epoch>,
  "file_mtimes": {
    "/path/to/session.jsonl": [<mtime_ns>, <size_bytes>],
    ...
  },
  "dropped_paths": {
    "/path/to/empty.jsonl": [<mtime_ns>, <size_bytes>],
    ...
  },
  "path_to_session_id": { "/path/...": "<sid>", ... },
  "continuation_map": {},
  "entries": {
    "<sid>": { "session_id": ..., "first_message": ..., "agent": {...}, "final_metrics": {...}, "timestamp": "...", ... },
    ...
  }
}
```

The compact-entry pass (`_compact_entry`) strips the largest fields (`agent.tool_definitions`, `extra.system_prompt`) before write — saves ~42 % of file size on observed data.

## Cold path — `_full_rebuild`

```
_full_rebuild()
  1. capture pre_rebuild_mtimes  (collect_file_mtimes from current _index)
  2. build_session_index(_index, _data_dirs) ----> [skeletons, dropped_paths]
       |
       +-- per parser:
       |     skeletons = parser.parse_session_index(data_dir)   # fast index per format
       |     orphans  = _build_orphaned_skeletons(parser, ...)   # files not in fast index
       |     files    = _build_file_parse_skeletons(parser, ...) # parsers without a fast index
       |
       +-- _build_orphaned_skeletons / _build_file_parse_skeletons
              dispatch parser.parse_skeleton_for_file(path)
              in a ThreadPoolExecutor (cap = min(8, cpu_count()))
  3. _enrich_skeleton_metrics(trajectories, _index)
       |
       +-- per skeleton: parser.parse_file(path)
           → adopt full_traj.final_metrics (real total_steps = len(steps),
             real daily_breakdown, real tokens / cost / tool_calls)
  4. model_dump → _metadata_cache
  5. save_cache(...)
```

## Warm path — `_try_partial_rebuild`

```
_try_partial_rebuild()
  1. cache = load_cache()                    # 4-5 ms, single JSON read
  2. cached_stats = _coerce_stats(...)       # tolerates legacy shapes
  3. _remap_index(cached_path_map)           # restore real session_ids
  4. partition, fresh_dropped = _partition_files(_index, cached_stats, cached_dropped)
       |
       +-- per file: stat once, compare [mtime_ns, size]:
              cached  ==  current   -> unchanged
              cached  !=  current   -> changed
              not in cache          -> new
              in cached, gone now   -> removed
  5. if partition has no changed/new/removed:
       fast path -- hydrate _metadata_cache from cached entries -> done
     else:
       _partial_rebuild(partition, cached_entries, fresh_dropped)
```

`_partial_rebuild` re-parses every changed and new file via `parser.parse_file`. There is no fast-scanner incremental path — appended files pay a full re-parse of that one file (~hundreds of ms; ~1.6 s worst-case for 80 MB). The previous incremental optimization was reverted in v10 because the dashboard needs `len(steps)` truth and step counts cannot be reconciled from a byte delta without re-running parser merge logic.

```
_partial_rebuild(...)
  1. hydrate unchanged sids from cached_entries
  2. only_paths = changed ∪ new
  3. partial_skeletons = build_partial_session_index(only_paths)
  4. _enrich_skeleton_metrics(partial_skeletons, _index)
       |
       +-- per skeleton: parser.parse_file(path)
           → adopt final_metrics (real total_steps, daily_breakdown, ...)
  5. drop sids whose path is in partition.removed_paths
  6. save_cache(...)
```

## The `BaseParser.parse_skeleton_for_file` hook

```
class BaseParser(ABC):
    def parse_skeleton_for_file(self, file_path) -> Trajectory | None:
        """Default: full-parse, then clear steps. Slow but always correct."""
        trajs = self.parse_file(file_path)
        if not trajs:
            return None
        main = trajs[0]
        main.steps = []
        return main
```

`ClaudeParser` overrides this with a head-of-file scan that reads only until the first meaningful user message:

```
class ClaudeParser(BaseParser):
    def parse_skeleton_for_file(self, jsonl_file) -> Trajectory | None:
        first_message = None
        project_path = None
        start_ts = None
        with jsonl_file.open("rb") as fh:
            for line in fh:
                entry = orjson.loads(line.strip())
                if project_path is None:
                    project_path = entry.get("cwd")
                if start_ts is None:
                    start_ts = normalize_timestamp(entry.get("timestamp"))
                if entry.get("type") != "user":
                    continue
                text = _scan_user_text(entry["message"]["content"])
                if text and _is_meaningful_prompt(text):
                    first_message = self.truncate_first_message(text)
                    break
        if not first_message:
            return None
        return Trajectory(
            session_id=jsonl_file.stem,
            project_path=project_path,
            timestamp=start_ts,
            first_message=first_message,
            ...
        )
```

Other parsers (codex, openclaw, hermes, gemini, claude_web) inherit the default. They have their own per-format fast indexes (`state_5.sqlite`, `sessions.json`, etc.) that handle the common path; the default hook is the orphan-fallback only.

## Critical design decisions — before / after

### D1. Stop using `history.jsonl` for the Claude session index

| | Before | After |
|---|---|---|
| Source of truth for session listing | `~/.claude/history.jsonl` (`display` field — the user's typed text) | Each session's `<sid>.jsonl` head, scanned until first meaningful user turn |
| Symptom | Title and search field used the user's typed text. Diverged from on-record content when Claude Code rewrote the prompt (pasted screenshots → first message in JSONL is `[Image #1] ...` but `display` is whatever the user actually typed before paste). | Title and search field are sourced from the same content the session view shows. |
| Test scenario | Session with pasted screenshot prompt: sidebar showed "always run build after you change the frontend" (a later user turn). Title and search both incorrect. | Sidebar and search both show "[Image #4] Update frontend: beautify the friction → copy all button dialog. ..." (the actual first turn). |
| Cost | history.jsonl read + group-by-session (~15 ms for 1.4 K sessions) | rglob + open + parse-until-first-user-message (~880 ms for 1.3 K sessions sequential, ~1 s with overhead in `build_session_index`) |

The trade is correctness for ~1 s of cold-start cost. The cost is recovered later in this same spec.

### D2. `[mtime_ns, size]` cache key (R1)

| | Before | After |
|---|---|---|
| Cache key | `mtime_ns` only | `[mtime_ns, size]` |
| Failure mode | An editor that rewrites a file in place fast enough that mtime resolution doesn't tick (or that explicitly preserves mtime) → cache silently serves stale data. | Size mismatch forces a re-parse. |
| Cost | One stat per file. | One stat per file (same `os.stat` call already returns size — free). |
| Cache schema | v6 | v7 (auto-invalidates v6 caches on first run) |

### D3. Lightweight `parse_skeleton_for_file` hook (R3)

Before R3, the index builder had no way to ask a parser for "just enough to populate the sidebar". Orphan and file-parse paths called `parser.parse_file(path)` — the full trajectory parser, with tool-result pairing, sub-agent linkage, observation building, classify_user_message, full Pydantic validation per step.

| | Before | After |
|---|---|---|
| API | `parser.parse_file(path)` always | `parser.parse_skeleton_for_file(path)` (hook); default = old behavior |
| Claude per-file cost | Full parse: ~35 ms / file (sample) | Head scan: <1 ms / file |
| Other parsers | Unchanged (still full parse via default hook fallback) | Unchanged |
| Sub-agent linkage on listing | Performed (wasted work — sidebar doesn't show it) | Deferred to `get_session()` |
| Tool-result pairing on listing | Performed (wasted work) | Deferred to `get_session()` |

The hook is a parser opt-in: each parser overrides only when its format permits a head-only extraction.

### D4. Parallelize `_build_file_parse_skeletons` and `_build_orphaned_skeletons` (R4)

| | Before | After |
|---|---|---|
| Per-file work dispatch | Sequential `for sid, fpath, p in entries: parse(...)` | `ThreadPoolExecutor(max_workers=min(8, cpu_count())).map(...)` |
| Speedup observed | 1.0× | 1.98× on a 50-file sample |
| Why threads work here | The default `parse_skeleton_for_file` (full parse) holds the GIL most of the time, but the *time* is dominated by file I/O — the `open` + `read` releases the GIL. Threads overlap reads. |
| Why threads don't always work | Once R3 makes the lightweight scan dominant, per-file work is so cheap (<1 ms) that thread scheduling overhead overwhelms the parallelism gain. We accept this — the parallel path is already strictly faster than sequential for the orphan / fallback cases that need full parse. |

### D5. `orjson` on hot paths (R6)

| | Before | After |
|---|---|---|
| `BaseParser._iter_parsed_jsonl` | `json.loads` | `orjson.loads` (subclass-compatible exceptions) |
| `ClaudeParser.parse_skeleton_for_file` | `json.loads` | `orjson.loads` |
| Per-line cost on 80 MB file | ~30 µs | ~10 µs |

orjson releases the GIL during parsing, but the surrounding Python (the dict accumulation, isinstance checks, set ops) does not — that's why a thread pool around `_enrich_skeleton_metrics` doesn't scale (D7 below).

### D7. Thread vs. process pool for `_enrich_skeleton_metrics`

| Strategy | Time on 300-file 342 MB sample | Speedup vs sequential | Decision |
|---|---|---|---|
| Sequential | 935 ms (fast scanner era) / ~6 s (parser.parse_file era, v10) | 1.0× | Ship |
| `ThreadPoolExecutor(8)` | 951 ms | **0.98×** (regression) | Reject — GIL serializes the post-orjson dict work |
| `ProcessPoolExecutor(8)` | 276 ms | **3.4×** (real win) | Reject — silently breaks when launched without a re-importable `__main__` (e.g. `python -c`); each worker pays ~50–100 ms spawn cost on macOS |

The decision is documented in the function's docstring so a future optimizer who sees "I/O-bound, just add threads" doesn't waste time re-discovering this. Process pool is the right move if someone wants to take it further, gated on a `__main__` check with a sequential fallback.

### D8. Incremental append-only enrichment (R2) — REVERTED in v10

The fast-scanner-based incremental path landed earlier (R2) and gave a 33× speedup on appended active sessions (4.25 s → 130 ms). It was **reverted in v10** because the dashboard's `messages == len(traj.steps)` contract cannot be maintained from a byte delta — step counts depend on parser merge logic (multiline user messages, streaming assistant chunks, sub-agent linkage) that operates on the full file. Mixing fast-scanner deltas with parser-derived totals produced the cache divergence v10 fixes.

| | Before v10 | After v10 |
|---|---|---|
| Active-session append (one new line on 80 MB) | ~5 ms (incremental scan + merge) | ~600–1500 ms (full re-parse of that one file) |
| Source of `final_metrics` | fast scanner (line-level) | `parser.parse_file` (step-level truth) |
| Code complexity | `scan_session_metrics_incremental`, `_prev_metrics_from_entry`, `_apply_scanned_metrics`, `incremental_seeds` partition logic | none — `_enrich_skeleton_metrics` calls `parser.parse_file` for every changed/new file |
| `final_metrics.total_steps` accuracy | stale once the dashboard ran twice (off by 1.6–4.6×) | exact `len(traj.steps)` |

The trade is ~10× on the active-session path for ~10,000× on accuracy: the dashboard is now correct on every refresh, with no cache-flip drift.

## Comparison with `claude-code-history-viewer` (Rust + Tauri)

The reference repo is a single-purpose viewer for Claude Code conversation history. We ported its session-loading shape (cache + incremental + parallelism) into VibeLens while keeping the multi-agent / analytics surface that VibeLens has on top.

### Side-by-side feature matrix

| Aspect | claude-code-history-viewer | VibeLens (this branch) |
|---|---|---|
| **Cache scope** | Per-project file: `<project>/.session_cache.json` | Single global file: `~/.vibelens/session_index.json` |
| **Cache key** | `(file path, mtime, size, last_byte_offset)` | `(file path, mtime_ns, size)` |
| **Append-only incremental parse** | Yes — seeks to `last_byte_offset`, parses delta only | **No (v10) — reverted; see D8.** Full re-parse of changed files for accuracy |
| **Two-phase per-file parsing** | Yes — first 100 lines deeply parsed, rest scanned via substring + thin classifier | No — `parse_skeleton_for_file` does head-only scan for sidebar listing; enrichment then runs full `parser.parse_file` |
| **Parallelism** | Rayon `into_par_iter` for the per-file parse step | `ThreadPoolExecutor(8)` for orphan + file-parse skeleton building |
| **JSON parser** | `serde_json` (Rust) | `orjson` (Python C extension) |
| **File I/O** | `BufReader::with_capacity(64K, file)`, `memmap2` | Default Python buffered I/O |
| **Atomic cache write** | `write` → `rename` with nanosecond nonce | `atomic_write_json` (`write` → `rename`) |
| **Cache compaction** | n/a (compact format) | `_compact_entry` strips heavy never-read fields (~42 % size reduction) |
| **Sidechain/sub-agent linkage** | Counted, no graph linkage | Full linkage: spawn step, parent ref, agentId map |
| **Continuation chains (`claude --resume`)** | Detected, shown in title | Detected, modeled as `prev/next/parent_trajectory_ref` |
| **Multi-agent** | Claude (with limited Codex/OpenCode) | Claude, Codex, Gemini, Hermes, OpenClaw, Claude Web |
| **Search** | Substring | BM25F over user/agent/tool, two-tier (metadata + full text) |
| **Dashboard analytics** | Token/cost stats | + daily breakdown, friction, skill, cost backfill |

### Performance side-by-side

Test corpus: `~/.claude/projects/`, 1,337 main sessions / 4,099 JSONL files / 2.98 GB.

| Scenario | Reference (Rust) | VibeLens, baseline | VibeLens, v10 |
|---|---|---|---|
| Cold start (no cache) | 0.4 s | ~46 s | **~25–30 s** |
| Warm start (cache hit) | 40 ms | ~100 ms | **~100 ms** |
| One small file touched | 50 ms | ~1.7 s | **~300 ms** (full re-parse of that file) |
| One large (80 MB) file appended | 50 ms | ~4 s | **~600–1500 ms** (full re-parse) |

Cold start widened from ~5.4 s (R6 era) to ~25–30 s in v10 because every session goes through `parser.parse_file` for accurate `len(steps)` instead of the fast scanner's line count. The active-session path (touch / append) widened from ~130 ms to a few hundred ms for the same reason. The trade is documented in D8: accuracy over speed, because the dashboard cannot tolerate the 1.6–4.6× over-count the fast scanner produced.

### Robustness comparison

| Concern | Reference | VibeLens |
|---|---|---|
| Malformed JSON line | Skipped | Skipped + diagnostic counter |
| Truncated file | Stops at last good line | Same |
| File rewritten in place, same mtime | Caught by size check | Caught by size check (D2) |
| File grew between runs | Incremental | Full re-parse (D8 reverted) |
| Cache schema drift | Version bump | Version bump (D2 → 7 → 10) |
| Concurrent writer | Atomic rename | Atomic rename |
| Subagent linkage broken | n/a (no linkage) | Warns + records diagnostic |
| `messages` count accuracy | Line-count approximation | Exact `len(traj.steps)` (v10) |

## What's not in scope for this subsystem

- **Search index** — built on top of `list_metadata` and `load`, lives in `services/session/search/`. See [`spec-session-search.md`](spec-session-search.md).
- **Dashboard analytics** — consumes `final_metrics` populated here but does its own aggregation. See [`spec-dashboard.md`](spec-dashboard.md).
- **Trajectory rendering** — the session view calls `load(session_id)`, which goes through the parser's full `parse_file`. The skeleton-only listing path is strictly upstream of that.
- **Friction / skill analysis** — read trajectories via `load`, do not depend on the listing path.

## Future work

| Item | Estimated payoff | Notes |
|---|---|---|
| Process-pool enrichment with `__main__` gating | ~3× cold start (~10 s) | Rejected today as too operationally fragile; revisit when there's a clean way to detect spawn safety at runtime. |
| Per-project cache split | Faster cache writes for users with many projects | Replace single `~/.vibelens/session_index.json` with `~/.vibelens/cache/<project_hash>.json`. |
| Directory mtime watcher (`fsevents` / `inotify`) | Eliminates the ~90 ms rglob on warm | Replace polling rglob with event-driven invalidation. |
| Lazy step-count for sidebar listing | Sub-1 s cold | Defer `parser.parse_file` until the dashboard is opened; sidebar shows skeleton-only fields. UX call — the dashboard would briefly lag on first open after a cold start. |

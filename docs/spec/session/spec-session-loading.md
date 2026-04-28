# Session Loading

How VibeLens enumerates the user's local agent sessions and keeps that listing fresh.

## Motivation

Self-use VibeLens points at one or more agent data directories (`~/.claude/`, `~/.codex/`, `~/.gemini/`, …). The user expects four properties at the same time, and these are in tension:

1. **Cold start is fast** — the sidebar populates within ~a second on a multi-GB corpus.
2. **Reload is near-instant** — opening the app a second time, or re-running an analysis, doesn't repay the cold-start cost.
3. **Active sessions are visible immediately** — when the user just typed another prompt and a JSONL grew by a few hundred bytes, the new turn shows up.
4. **Stale state never persists silently** — if a file is rewritten in place (some editors preserve `mtime`), we must notice.

A naive "walk + parse on every list call" satisfies (3) and (4) but not (1) or (2). A simple in-memory cache satisfies (2) but bloats memory and breaks (4). The session-loading subsystem is the layer that satisfies all four, with a persistent cache, a partial-rebuild fast path, and a strict invalidation contract.

## Architecture

```
LocalTrajectoryStore.list_metadata()
        │
        ▼
  ensure index built  (lazy, thread-safe)
        │
        ▼
  try partial rebuild  ──── cache hit (all unchanged) ─→  hydrate from cache
        │                                                  (warm path, ~100 ms)
        │
        ├── some files changed ──→  partial rebuild        re-parse only those
        │                                                  files, splice with
        │                                                  cached entries
        │
        └── cache miss / drift ──→  full rebuild           build_session_index
                                                            across data dirs

result → in-memory metadata cache → save_cache()
                                       │
                                       ▼
                            ~/.vibelens/session_index.json
```

The store also rate-limits stat-walks: within a 10 s window after a successful list, we reuse the in-memory cache without touching disk.

## Key files

| File | Role |
|---|---|
| `storage/trajectory/local.py` | `LocalTrajectoryStore` — orchestrator: partition cached vs. current, rebuild, persist |
| `ingest/index_builder.py` | Per-data-dir skeleton building: parser fast index → orphan fallback → full-parse fallback |
| `ingest/index_cache.py` | Persistent JSON cache (`CACHE_VERSION`, atomic write, `[mtime_ns, size]` stats) |
| `ingest/parsers/base.py` | `BaseParser.parse_skeleton_for_file` hook |
| `ingest/parsers/claude.py` | Head-of-file fast skeleton extractor for Claude JSONL |

## Cache contract

The on-disk cache lives at `~/.vibelens/session_index.json`. It carries:

- a `version` integer — `index_cache.CACHE_VERSION`. A mismatch on read invalidates the cache and forces a full rebuild.
- per-file stat tuples `[mtime_ns, size]` — both fields, because some editors rewrite in place without ticking `mtime` and some explicitly preserve it; size catches those cases.
- the set of "dropped" paths (parsed to zero sessions) so we don't re-attempt them on every cold start.
- compact metadata entries — the writer strips the largest never-listed fields (`agent.tool_definitions`, `extra.system_prompt`) before persisting.

Versioning policy: bump on shape change, don't migrate. A release that changes the entry shape forces one cold rebuild and is otherwise free.

## The two paths

### Warm path — partial rebuild

1. Load the cache.
2. `stat` every file currently in the index, compare against cached `[mtime_ns, size]`.
3. Partition into `unchanged / changed / new / removed`.
4. If nothing changed — hydrate the in-memory cache from cached entries and return.
5. Otherwise — re-parse only the `changed` and `new` files, splice with the cached `unchanged` entries, drop `removed`.

This is what makes "open VibeLens, look around, close it, open it again" feel free.

### Cold path — full rebuild

When the cache is missing, version-mismatched, or otherwise unusable:

1. `build_session_index(data_dirs)` — for each parser, prefer the parser's own fast index (`state.db`, `sessions.json`, etc.) where available, fall back to the orphan/file-parse paths for files the fast index missed.
2. Skeleton paths run in a small `ThreadPoolExecutor` (capped at `min(8, cpu_count())`) — most of the per-file time is in I/O, which releases the GIL.
3. Enrich skeletons by running `parser.parse_file` on each — the skeleton step alone produces only the listing fields; final metrics (`total_steps`, `daily_breakdown`, tokens, cost) come from the full parse so that downstream consumers get the same step counts the session view shows.

Cold start is dominated by step 3 — see "Why we don't shortcut enrichment" below.

## The `parse_skeleton_for_file` hook

Most listing fields (project path, first user message, start timestamp) can be extracted by reading just the head of the file. `BaseParser.parse_skeleton_for_file` is the per-parser opt-in for that:

- Default: full-parse, then drop `steps`. Slow but always correct.
- `ClaudeParser` overrides it with a head-of-file scan that stops at the first meaningful user message.

Other parsers (`codex`, `openclaw`, `hermes`, `gemini`, `claude_web`, …) carry their own format-native fast indexes and use the default fallback only for orphans.

## Why enrichment runs the full parser

A line-count scan or byte-delta merge would be much faster, but step counts can't be reconciled from raw bytes — multiline user messages, streaming assistant chunks, and sub-agent linkage all collapse multiple JSONL lines into a single step, with logic that lives only in the parser. So `final_metrics` is always parser-derived: every changed file pays a full re-parse, and `total_steps` always equals `len(traj.steps)`. The dashboard's `messages == len(steps)` invariant depends on this.

## What's not in this subsystem

- **Search** — built on top of `list_metadata` and `load`. See [`spec-session-search.md`](spec-session-search.md).
- **Dashboard analytics** — consumes `final_metrics` populated here but does its own aggregation. See [`spec-dashboard.md`](../spec-dashboard.md).
- **Session view rendering** — calls `load(session_id)` and goes through the parser's full `parse_file`; the listing path is strictly upstream.
- **Friction / skill analysis** — read trajectories via `load`, never via the listing path.

## Robustness rules

- Malformed JSON line → skipped, recorded in the parser's diagnostic counter.
- Truncated file → stops at last good line.
- File rewritten in place with same mtime → caught by size mismatch.
- Cache schema drift → version bump invalidates old caches.
- Concurrent writers → cache is written via `atomic_write_json` (write-temp + rename).
- Sub-agent linkage broken → warned and recorded; doesn't block the listing.

## Open design space

- **Process-pool enrichment** — faster cold start, but breaks when the parent isn't re-importable (`python -c`, some shells). Gated on a runtime spawn-safety check.
- **Per-project cache shards** — replace the single `session_index.json` with one file per data-dir hash; lowers warm-write cost for users with many projects.
- **Filesystem watcher** (`fsevents` / `inotify`) — replace the rglob-on-stat-window polling with event-driven invalidation.

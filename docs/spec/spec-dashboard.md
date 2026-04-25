# Analytics Dashboard

Aggregate-usage view: stat cards, time-series charts, tool usage, and per-session analytics. Pure computation — no LLM dependency. Every number traces to a parsed session trajectory or its cached metadata.

## What it answers

Which tools do I invoke most? When are my peak coding hours? Which project consumes the most cost? How does this week compare to last? The dashboard sits on top of session loading and pricing, and adds aggregation, caching, and the API surface the frontend reads from.

## Two paths

A request first checks the in-memory TTL cache. On a cache miss the dashboard takes one of two routes, decided by whether enough metadata entries already carry token totals — a strict-majority vote across the filtered set.

The **fast path** sums per-session aggregates that ingest already wrote into the metadata cache. No trajectories are loaded. Used on every typical request because ingest fills the cache up front.

The **slow path** loads every filtered trajectory in parallel, re-aggregates from per-step metrics, then runs a reconciliation pass that adds failed-to-parse sessions back into the totals so the dashboard never undercounts what the sidebar shows. Used only when metadata lacks token totals (rare — happens for stores that bypass enrichment).

Both paths produce the same response model and respect the same filters.

### Lifecycle walkthrough

What a user actually experiences from install through one full day, in one timeline:

```
  t=0         $ vibelens serve              (first install, no cache)
              └─ rglob disk + parser.parse_file × 1480       ≈ 25–30 s
              └─ write session_index.json (v10)
              └─ warm dashboard cache (default, no filter)
  t≈30 s      server ready
  ────────────────────────────────────────────────────────────────────────
  t=35 s      user opens browser
              GET /api/dashboard
              └─ TTL cache HIT (warmed at startup)              < 1 ms
              UI: numbers appear instantly
  ────────────────────────────────────────────────────────────────────────
  t=40 s      user clicks project filter
              GET /api/dashboard?project_path=…
              └─ cache MISS (new key)
                 └─ majority enriched → FAST PATH               ~ 18 ms
              UI: brief spinner, then new numbers
  ────────────────────────────────────────────────────────────────────────
  t=45 s      user clicks back to "All projects"
              └─ cache HIT (default key)                        < 1 ms
  ────────────────────────────────────────────────────────────────────────
  t=50 s      user clicks a session row → detail page
              GET /api/sessions/{id}/stats
              └─ never cached → load trajectory + analytics     ~ 4 ms
  ────────────────────────────────────────────────────────────────────────
  t=5 min     another terminal: user types a prompt in Claude Code
              disk: that session JSONL gets appended
              (vibelens does not auto-detect — no request fires)
  ────────────────────────────────────────────────────────────────────────
  t=5 min+    user refreshes the browser tab
              └─ cache HIT (TTL not expired)                    < 1 ms
              UI: pre-append numbers (stale by one step)
  ────────────────────────────────────────────────────────────────────────
  t=5 min+    user clicks the dashboard refresh control
              GET /api/dashboard?refresh=true
              ├─ invalidate_cache() clears the TTL caches
              ├─ list_metadata sees one file's mtime changed
              │   └─ partial rebuild: parse_file on that file   ~ 300 ms
              └─ FAST PATH on fresh metadata                    ~ 18 ms
              UI: current numbers
  ────────────────────────────────────────────────────────────────────────
  t=1 h       TTL expires on the default cache key (no user action)
              next request rebuilds via FAST PATH on demand
  ────────────────────────────────────────────────────────────────────────
  t=2 h       user ^C and runs `vibelens serve` again
              ├─ load_cache → v10 matches → partial rebuild
              │   └─ stat 1480 files, all unchanged             ~ 50 ms
              └─ warm cache via FAST PATH                       ~ 18 ms
              server ready in ~ 150 ms (no full parse)
  ────────────────────────────────────────────────────────────────────────
  weeks later, after upgrade …
  ────────────────────────────────────────────────────────────────────────
  t=N         pip install -U vibelens && vibelens serve
              └─ load_cache → version mismatch → full rebuild   ≈ 25–30 s
              (one-time hit, equivalent to the first install)
```

Three things from this timeline are worth pulling out. The only visible wait is a one-time ~30 s cold start (first install or after a schema bump); every other path the user touches finishes in 18 ms or less. Active sessions writing in another terminal never auto-propagate to an open dashboard tab — the user has to click the refresh control, which both invalidates the TTL cache and triggers a partial index rebuild for the changed file. Each unique filter combination occupies its own cache key, so switching between two project filters is fast on the first hit and instant after that.

## The messages contract

A "message" means one trajectory step, irrespective of source (USER, AGENT, or SYSTEM). This is the contract end-to-end: ingest writes `total_steps == len(steps)` and a daily breakdown whose per-day messages sum to the same value; the dashboard's fast and slow paths both honour it. The contract is locked by ten invariant tests across `test_stats.py`, `test_loader.py`, and `test_helpers_messages_invariant.py`. Any future change that filters out a step source will fail at least one of them.

## Time bucketing

A session is *one event in time* for some statistics and a *stream of activity over time* for others. Session count, peak-hour, weekday heatmap, project distribution, and average-per-session metrics anchor on the trajectory's creation timestamp. Daily and period messages, tokens, and cost bucket per step, so a session that crossed midnight contributes to both days' bars. Duration and per-period subtotals like tool calls stay anchored to the creation day. The two-mode bucketing happens in one pass per session and is covered by the cross-day test suite.

## Caching

In-memory TTL cache (one hour) keyed by the full filter tuple — a global view and a project-filtered view never collide. A second TTL cache holds the tool-usage response with the same key shape. Both clear on `?refresh=true` or `invalidate_cache()`. Tool-usage data also persists per session on disk, keyed by source-file mtime so warm restarts skip sessions that didn't change. The session-index metadata cache itself lives one layer below in `~/.vibelens/session_index.json` (schema version 10) and follows the rules described in [`spec/session/spec-session-loading.md`](session/spec-session-loading.md).

## API

All routes mount under `/api/`. Every query accepts project, date range, and agent filters, plus a per-tab session token for multi-user demo isolation.

| Path | Returns |
|------|---------|
| `GET /api/dashboard` | Aggregate stats payload (`?refresh=true` clears the cache first) |
| `GET /api/tool-usage` | One row per tool, sorted by call count desc |
| `GET /api/sessions/{id}/stats` | Per-session analytics — token breakdown, tool frequency, phase segments, cost. Recomputed every request |
| `GET /api/dashboard/export?format=csv\|json` | Streaming download honouring the same filters |

## Cost

Per-step cost is written by ingest into `step.metrics.cost_usd` from a pricing lookup keyed by canonical model name. Both paths sum populated step costs for the session-level total; the fast path additionally falls back to an aggregate-token lookup when per-step data is absent. Sessions whose model is unknown are excluded from the per-model cost breakdown but still count toward grand totals. Pricing lives in `llm/pricing.py` so it stays available to non-dashboard callers.

## Reconciliation

Some session files fail to parse cleanly (truncated JSONL, format drift). The sidebar lists every metadata entry, so the dashboard's totals must too — otherwise users see N sessions in the list and only M < N reflected in the cards. After the slow path aggregates whatever parsed, the reconciliation pass re-derives `total_sessions` and the period counts from metadata timestamps, and adds the unparsed sessions to the project distribution and daily activity. The fast path is naturally consistent (it operates on metadata only) so it skips this step.

## Filtering and edge cases

Filter values become part of the cache key, so views cache independently. Sessions without a timestamp are excluded from time-dimension charts but still contribute to grand totals and distributions. Missing model and project fields fall back to "unknown" and "(no project)" placeholders. Parser-emitted sentinels like `<synthetic>` are filtered out of model distributions but still counted toward session totals.

## Verification

Numbers below come from `scripts/dashboard/bench.py` and `scripts/dashboard/dump_stats.py` running against the local `~/.claude/projects/` corpus on the development machine.

### Environment

| Item | Value |
|---|---|
| Platform | macOS Darwin 24.6.0 (arm64) |
| Python | 3.10–3.12 |
| Session count | 1480 |
| Fast-path eligible | Yes (every metadata entry carries token totals after v10 enrichment) |
| Cache TTL | 3600 s |

### Performance

Median over three back-to-back runs.

| Path | Median wall time | What it covers |
|---|---|---|
| Fast path (typical request) | **~18 ms** | Aggregating 1480 metadata entries into the response payload |
| Slow path compute | ~180 ms | Re-aggregating from already-loaded trajectories |
| Slow path reconciliation | ~1 ms | Period-count override and failed-parse re-injection |
| Slow path trajectory load | ~26 s | One-off; loads 1480 trajectories in parallel from disk |
| Per-session analytics | ~4 ms | Single-trajectory roll-up, recomputed per request |
| Cache hit | sub-millisecond | TTL dict lookup |

The fast path is what the frontend hits on every interaction. The slow path is reserved for cache-miss scenarios on stores whose metadata lacks token totals.

### Tests

Locked by 49 tests across six files. Behaviour tests guarantee the response shape; invariant tests guard the messages contract; loader tests guard dispatch and reconciliation; pricing tests guard cost.

| File | What it covers |
|---|---|
| `tests/services/dashboard/test_stats.py` | Full and fast path totals, distributions, period boundaries, cost aggregation, cross-day bucketing, fast-path daily breakdown, and the five `TestMessageCountInvariant` cases |
| `tests/services/dashboard/test_loader.py` | Fast-vs-slow dispatch threshold, reconciliation behaviour, TTL cache key isolation, invalidation |
| `tests/services/dashboard/test_tool_usage_cache.py` | Persistent on-disk tool-usage cache, mtime invalidation, drop-missing handling |
| `tests/ingest/parsers/test_helpers_messages_invariant.py` | Ingest-side guarantee that `total_steps == len(steps)` and the daily breakdown sums to it |
| `tests/ingest/parsers/test_cost_enrichment.py` | Per-step cost enrichment during ingest; preserves pre-populated cost; no-model and unknown-model fallbacks |
| `tests/llm/test_pricing.py` | Pricing lookup, per-step and aggregate cost computation |

### Results

Verified end-to-end via `scripts/dashboard/dump_stats.py --full` after the v10 cache rebuild.

| Check | Outcome |
|---|---|
| Per-session `cache.total_steps == len(traj.steps)` | 1477 / 1480 (3 explained: 2 active sessions racing on mtime, 1 fixture file from the pre-v10 era) |
| Per-session `sum(daily_breakdown.messages) == total_steps` | 1480 / 1480 |
| Per-session fast-path messages == slow-path messages | 1476 / 1477 (1 fixture mismatch as above) |
| Top-line aggregates fast vs slow on inactive sessions | Identical |
| Top-line aggregates across two back-to-back runs | Identical except for active-session deltas (the conversation file appended between runs) |

## Future work

The TTL cache lives in memory only — a process restart always pays one fast-path computation (~18 ms) before the first request. Persisting it would shave that off but isn't worth the invalidation complexity yet. Filter state in the frontend doesn't round-trip through the URL, so shared dashboard links always show the global view. The metadata fast path lacks per-day cost detail, so per-day cost breakdowns are derived from session-level totals; if per-day step cost ever matters for the cached path, the session index would need to carry the breakdown itself.

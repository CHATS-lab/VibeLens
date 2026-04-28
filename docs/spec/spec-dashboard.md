# Analytics Dashboard

Aggregate-usage view: stat cards, time-series charts, tool usage, per-session analytics. Pure computation — no LLM dependency. Every number traces back to a parsed trajectory or its cached metadata.

## Motivation

VibeLens already has a parser tier (per-agent → ATIF), a storage tier (`session_index.json`), and a session-view tier. The dashboard answers a different question: **"taken across all my sessions, what's going on?"** — which tools dominate, when do I work, which project costs the most, how does this week compare to last.

Two constraints shape the design:

- **It must feel free.** The user reaches the dashboard before doing anything else and revisits it constantly. A round-trip should rarely cost more than a TTL-cache lookup.
- **It must agree with the sidebar.** If the sidebar lists 1 480 sessions, the dashboard's session count, daily breakdown, and project distribution must add up to 1 480 too — even when some files failed to parse cleanly.

## Two paths

The dashboard request first checks the in-memory TTL cache. On a cache miss it picks one of two compute paths, decided by a strict-majority vote: do enough metadata entries (within the active filter) already carry token totals?

- **Fast path** — sum the per-session aggregates that ingest wrote into the metadata cache. No trajectories are loaded. This is the typical case because session loading enriches metadata up front.
- **Slow path** — load every filtered trajectory in parallel, re-aggregate from per-step metrics, then run a reconciliation pass that re-injects sessions which failed to parse so the totals match what the sidebar shows. Reserved for stores whose metadata bypasses enrichment.

Both paths produce the same response model and respect the same filters. Sub-millisecond cache hits dominate; cache miss on the fast path is on the order of milliseconds; the slow path is multiple seconds because of the trajectory-load step.

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

A "message" means **one trajectory step**, regardless of `source` (`user` / `agent` / `system`). The contract is enforced end-to-end:

- Ingest writes `final_metrics.total_steps == len(traj.steps)`.
- The daily breakdown's per-day `messages` sum to `total_steps`.
- The dashboard's fast and slow paths both honour this.

The contract is locked by invariant tests in `tests/services/dashboard/` and `tests/ingest/parsers/test_helpers_messages_invariant.py`. Any future change that filters out a step source has to either update the contract everywhere or fail at least one of those tests.

## Time bucketing

A session is *one event in time* for some statistics and a *stream of activity over time* for others.

- **Anchored on session start** — session count, peak-hour, weekday heatmap, project distribution, average-per-session metrics.
- **Bucketed per step** — daily and per-period messages, tokens, cost. A session that crossed midnight contributes to both days.
- **Anchored on session start, period-internal** — duration and per-period subtotals like tool calls.

The two-mode bucketing happens in one pass per session.

## Caching

- **In-memory TTL cache** (one hour) keyed by the full filter tuple. Different filters get different cache entries; switching back and forth is fast on the first hit and instant after that. A second TTL cache holds the tool-usage response with the same key shape. Both clear on `?refresh=true` or `invalidate_cache()`.
- **Persistent tool-usage cache** — per-session, keyed by source-file mtime, so warm restarts skip sessions whose source didn't change.
- **Session-index cache** — one layer below in `~/.vibelens/session_index.json`. See [`spec-session-loading.md`](session/spec-session-loading.md) for its rules.

## API

All routes mount under `/api/`. Every dashboard query accepts project, date-range, and agent filters, plus a per-tab session token for multi-user demo isolation.

| Path | Returns |
|---|---|
| `GET /api/dashboard` | Aggregate stats payload. `?refresh=true` clears the cache first. |
| `GET /api/tool-usage` | One row per tool, sorted by call count desc. |
| `GET /api/dashboard/export?format=csv\|json` | Streaming download honouring the same filters. |
| `GET /api/sessions/{id}/stats` | Per-session analytics — token breakdown, tool frequency, phase segments, cost. Recomputed every request. |

## Cost

Per-step cost is written by ingest into `step.metrics.cost_usd` from a pricing lookup keyed by canonical model name. Both paths sum populated step costs for the session-level total; the fast path additionally falls back to an aggregate-token lookup when per-step data is absent. Sessions whose model is unknown are excluded from the per-model cost breakdown but still count toward grand totals. Pricing lives in `llm/pricing.py` so it's available to non-dashboard callers too.

## Reconciliation

Some session files fail to parse cleanly (truncated JSONL, format drift). The sidebar lists every metadata entry, so the dashboard's totals must too — otherwise users see N sessions in the list and only M < N reflected in the cards. After the slow path aggregates whatever parsed, the reconciliation pass re-derives `total_sessions` and the period counts from metadata timestamps, and adds the unparsed sessions back into project distribution and daily activity. The fast path is naturally consistent (it operates on metadata only) so it skips this step.

## Filtering and edge cases

- Filter values become part of the cache key; views cache independently.
- Sessions without a timestamp are excluded from time-dimension charts but still contribute to grand totals and distributions.
- Missing model and project fields fall back to `"unknown"` and `"(no project)"`.
- Parser-emitted sentinels like `<synthetic>` are filtered out of model distributions but still counted toward session totals.

## Active sessions

VibeLens does not auto-detect appends to a session that's still being written to in another terminal. The dashboard refresh control invalidates the TTL caches *and* triggers a partial index rebuild, so one click suffices to see the latest data.

## Out of scope

- Persisting the TTL cache across restarts.
- Round-tripping filter state through the URL — shared dashboard links show the global view.
- Per-day cost detail in the cached path — derived from session-level totals; gaining per-day step cost would require the session index to carry the breakdown itself.

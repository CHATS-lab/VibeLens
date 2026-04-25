# Session Search

Weighted per-field BM25 search over parsed session trajectories, with a session_id exact/prefix tier. Powers the session list's search input.

## Purpose

A VibeLens user may accumulate thousands of sessions totalling ~100M tokens. The existing substring-filter implementation has three problems:

1. **No ranking.** Matches come back in metadata order (most recent first), useless when a query returns 400 sessions.
2. **Poor recall.** "react component" does not match "react components" because the filter is literal substring — no tokenization, no stemming. "Python testing" misses "pytest" because there is no token-level match.
3. **Memory growth with session size.** A full Tier-2 build parses every JSONL and retains the `Trajectory` objects in the `_SearchEntry` closure during extraction, then the extracted text strings stay resident forever. For the measured workload (1,362 sessions, ~100M tokens), the build takes ~24 s.

The new design replaces substring filtering with field-weighted BM25 ranking, shares its core engine with the extension catalog search, and reduces memory by dropping trajectories immediately after extraction. It does **not** persist any on-disk cache — cold build cost is accepted as a one-time-per-process startup tax.

## Non-goals

Explicitly out of scope for v1 so the change stays reviewable:

- **No on-disk cache** of search text, tokens, or parsed trajectories. Reviewed and rejected: a per-session JSON cache of ~100 MB for ~1,500 sessions offers a 24 s → ~1–2 s warm-restart win that is not worth the disk footprint today.
- **No ranking signals beyond BM25F + session_id tier.** Recency/popularity/quality rescoring left for a follow-up if real usage demands it.
- **No snippet highlighting in results.** Frontend keeps its existing card rendering; only the ordering of results changes.
- **No server-side suggestion / autocomplete feed.** Frontend already debounces at `SEARCH_DEBOUNCE_MS`.
- **No persistence of the built index** (no pickle, no numpy `.npz`).
- **No search-log domain split.** Search logs stay inside the `session` domain.

## Architecture

```
User types query
      |
      v
  search_sessions(query, session_token, top_k)
      |
      v
  get_session_index()   (module singleton, built lazily in background)
      |
      v
  SessionSearchIndex
      |
      +--> session_id tier         (dict lookup: exact / first-segment prefix)
      +--> AND-mask + BM25F scoring
           over (user_prompts, agent_messages, tool_calls, session_id)
      |
      v
  rank_tiered() from shared search core
      |
      v
  list[ScoredSession]  (session_id, composite_score)
```

Two tiers populate the index:

- **Tier 1 (metadata)**: Built synchronously at startup from `list_all_metadata()`. Serves `session_id` + `first_message` matches in <100 ms. Unchanged behavior from today.
- **Tier 2 (full text)**: Built asynchronously in a FastAPI lifespan task. Parses every session, extracts lowercased text per field, tokenizes once, inserts into the shared `InvertedIndex`, then discards the trajectory. Takes ~24 s on 1,362 sessions. Searches during build fall back to Tier 1.

## Migration plan

The refactor touches `services/extensions/search/` — a currently-shipping module with 100+ tests. To keep those tests green throughout, the implementation lands in **three commits**:

1. **Extract shared core.** Move `services/extensions/search/tokenizer.py` into new `services/search/` package. Split `services/extensions/search/index.py` into generic `InvertedIndex` (shared core) + domain-specific `CatalogSearchIndex` (stays in extensions). All existing extension tests must pass unchanged after this commit.
2. **Build session search.** New `services/session/search/` package on top of the shared core. Add new tests. Legacy `services/session/search.py` stays in place, untouched.
3. **Swap session search callers.** Flip `app.py`, `api/sessions.py`, and `services/upload/processor.py` to the new module. Delete the old `services/session/search.py`. Update the frontend. Ship as one atomic commit with the API contract change.

Each commit is independently reviewable. Commits 1 and 2 are safe to revert. Commit 3 is the breaking change.

## Key Files

### New: shared search core (`src/vibelens/services/search/`)

Extracted from `services/extensions/search/` so the session engine can reuse it. No behavior change for the extension catalog path.

| File | Responsibility |
|---|---|
| `tokenizer.py` | Moved verbatim from `extensions/search/tokenizer.py`. Pure function `tokenize(text) -> list[str]`. |
| `inverted_index.py` | Generic field-weighted BM25 + sparse `int32` posting lists + prefix map. No domain-specific signals. Accepts `{field_name: weight}` at construction. |
| `ranking.py` | Generic `rank_tiered(index, query_tokens, tier_scores, composite, weights)` helper. |

### New: session-search package (`src/vibelens/services/session/search/`)

Replaces the single `services/session/search.py` file.

| File | Responsibility |
|---|---|
| `__init__.py` | Public API: `search_sessions`, `build_search_index`, `build_full_search_index`, `add_sessions_to_index`, `refresh_search_index`, `invalidate_search_index`, `get_session_index`. |
| `index.py` | `SessionSearchIndex` — Tier 1/Tier 2 state, per-field extraction, session_id lookup dict, parallel `session_timestamp` float array, incremental add/refresh, atomic swap-under-lock. |
| `scorer.py` | Session-specific `rank_sessions(index, query, top_k)` — session_id tier dominates; BM25F within tier. |
| `query.py` | `ScoredSession` (slotted dataclass). |

### Modified: `services/extensions/search/`

| File | Change |
|---|---|
| `tokenizer.py` | Deleted — re-exported from the shared core. |
| `index.py` | Refactored to compose `InvertedIndex` from the shared core. Extension-specific signals (quality, popularity, recency) stay here. |
| `scorer.py` | Uses shared `rank_tiered()` helper instead of its own tiering loop. |

### Modified: app.py, api/sessions.py, services/upload/processor.py

- `app.py` lifespan already schedules `build_full_search_index` — unchanged call site, new implementation.
- `api/sessions.py` `/search` endpoint returns ranked `[{"session_id": str, "score": float}, ...]` instead of a flat session-id list.
- `services/upload/processor.py` continues to call `add_sessions_to_index(new_ids, token)` after upload — same API, new backend.

### Modified: frontend

- `api/sessions.ts`: `search()` returns `ScoredSession[]`.
- `components/session/session-list.tsx`: stops re-sorting search results by timestamp when a query is active.
- `components/session/search-options-dialog.tsx`: remove the source checkboxes (see API section).

## Data Flow

### Browse

```
GET /api/sessions/search?q=react
      |
      v
search_sessions(q="react", token=...)
      |
      v
SessionSearchIndex.search(query="react")
      |
      +---- if Tier 2 built: rank_sessions() -> BM25F + tier
      |                       returns [ScoredSession(sid, score), ...]
      +---- else:             Tier 1 substring over (session_id, first_message)
                              returns [ScoredSession(sid, 0.0), ...]
                              UI rendering is identical; score=0.0 placeholder.
      |
      v
FastAPI JSON: [{"session_id": "...", "score": 12.3}, ...]
```

**Empty query**: `search_sessions("")` returns `[]`. Unchanged from today.

**Tier 2 mid-build UX**: during the ~24 s window between startup and Tier 2 ready, queries against `agent_messages` or `tool_calls` content silently return zero results (Tier 1 only covers `session_id` and `first_message`). No loading indicator today; no change planned. A future follow-up could add `/api/sessions/search/status` if users complain.

**Error handling during parse/extract**: if parsing a session file raises or extraction hits a malformed `ContentPart`, the failure is logged at DEBUG and that session is skipped. One bad session does not abort the index build. Matches today's behavior.

### Tier 2 build (background, ~24s cold)

```
Lifespan task:
  summaries = list_all_metadata()
  per_session_ms = []
  with ThreadPoolExecutor(8):
    for sid, meta in summaries:
      start = monotonic_ms()
      trajectories = load_from_stores(sid, token)   # parse JSONL
      if trajectories is None: continue
      fields = _extract_per_field(trajectories)     # dict[field, lowercased_text]
      tokens = {f: tokenize(t) for f, t in fields.items()}
      ts = parse_iso_timestamp(meta.get("timestamp"))
      new_entries[sid] = (fields, tokens, ts)
      per_session_ms.append(monotonic_ms() - start)
      # trajectories goes out of scope here -> GC reclaims it
  index.swap_in(new_entries)
  log_duration_summary(log, "build_full_search_index_per_session",
                       per_session_ms, wall_ms=..., loaded=len(new_entries))
```

Memory behavior: each trajectory is parsed, extracted, tokenized, then released before the next session starts. Only the tokens + lowercased strings (~50–200 KB per session, depending on length) stay resident. The 8-worker pool bounds peak resident trajectory memory to ~8 sessions at a time regardless of catalog size.

### Incremental add (post-upload)

`SessionSearchIndex.add_sessions(ids, token)` parses each new session, extracts its fields, tokenizes, and inserts into the underlying `InvertedIndex` under the existing lock. The lock protects the full-entries dict and the BM25 field arrays against concurrent reads from in-flight search requests.

### Periodic refresh (every 5 min)

Diff-based: add new sessions, remove stale ones. Sub-second when 0–5 sessions change, which is the common case.

### Explicit invalidation

`invalidate_search_index()` clears Tier 2 state under the lock; Tier 1 is preserved. After invalidation, queries fall back to Tier 1 until either the periodic refresh runs (up to 5 min later) or an explicit `build_full_search_index()` call rebuilds. Used primarily by tests and storage-layer reset hooks.

## Ranking

Two layers:

1. **session_id tier** — dominant key. If the full query string equals a `session_id` exactly (case-insensitive), that entry wins. If the query matches the **first dash-delimited segment** of a `session_id` (e.g., query `"abc"` matches sid `"abc-de-123"` but not `"xyz-abc-123"`), it takes the prefix band. Everything else is tier 0.
2. **Within-tier composite** — weighted BM25F across the four fields. AND semantics: every non-prefix query token must appear somewhere in the document.

Final sort: `(tier desc, composite desc, session_timestamp desc)`. The recency tiebreaker surfaces the most recent session when two entries score equally. `session_timestamp` is pulled from session metadata during Tier 2 build and held as a parallel `float` array on the index — no extra lookup at query time.

### Field weights (initial proposal, tuned before ship)

| Field | Weight | Rationale |
|---|---:|---|
| `session_id` | 8.0 | Rare exact match; when it hits, it's decisive |
| `user_prompts` | 4.0 | What users remember typing |
| `agent_messages` | 2.0 | Longer, lower signal-to-noise |
| `tool_calls` | 1.0 | High repetition (same Read/Grep patterns), noisy |

### Weight tuning methodology

The Field weights above are starting points, not final. Before ship:

1. Run `scripts/eval_session_search.py` (described under Verification). This produces a rank-1% and top-5% score against the golden query set.
2. Perturb weights in ±0.5 increments per field, re-run, record deltas.
3. Accept the configuration that maximizes top-5 pass rate with a secondary tiebreaker of rank-1 pass rate.
4. Record the final weights in `WEIGHTS_BY_FIELD` with a comment linking to the run that chose them.

## Tokenization

Reuses `services/search/tokenizer.py` unchanged. Lowercases, splits on non-alphanumeric, drops stopwords + tokens <2 chars, applies conservative stemming (`-ies→-y`, strip `-ing`/`-ed`/`-s`; no `-er`/`-es` since those collapsed unrelated words in prior testing).

## Text extraction (per field)

Moves from `search.py` top-level functions into `SessionSearchIndex` methods.

- **`user_prompts`**: concatenation of every step with `source=USER`, lowercased.
- **`agent_messages`**: concatenation of every step with `source=AGENT`, text content only (no tool data).
- **`tool_calls`**: for every agent step — tool `function_name`, string-valued arguments (truncated to `ARG_VALUE_MAX_LENGTH=500`), and observation results (truncated to `OBSERVATION_MAX_LENGTH=200`).
- **`session_id`**: the raw id, lowercased, held in a dict for O(1) exact/prefix lookup. **Not** passed through the BM25 tokenizer — session_ids are opaque identifiers, not natural language.

Truncation constants stay as-is; they prevent a single giant session from dominating the index with megabytes of tool output.

## Public types

```python
@dataclass(slots=True)
class ScoredSession:
    session_id: str
    composite_score: float     # BM25F composite within tier
    # tier_rank is internal; not exposed to the frontend
```

`search_sessions` keeps its existing positional signature; `session_token` stays a function arg rather than a query model field because it is a request-context concern (per-browser-tab isolation in demo mode), not user intent:

```python
def search_sessions(
    query: str,
    session_token: str | None = None,
    top_k: int | None = None,
) -> list[ScoredSession]
```

## API

### Before

```
GET /api/sessions/search?q=react&sources=user_prompts,session_id
200 ["sid-1", "sid-2", ...]           # order = metadata order
```

### After

```
GET /api/sessions/search?q=react
200 [{"session_id": "sid-1", "score": 12.3},
     {"session_id": "sid-2", "score": 8.1}, ...]
```

Breaking-change notes:

- `sources` param is **removed**. The frontend change in the same PR stops sending it; the backend ignores it if present (to tolerate any stale client tab still open during deploy). The engine always searches all four fields and lets BM25 weights do the selecting.
- Response shape changes from `list[str]` to `list[{session_id, score}]`. Frontend and backend ship together so deploy is atomic.
- Share endpoints (`/api/shares/{id}`) that do not perform search are untouched.
- 404/422/503 responses unchanged.

## Performance

Measured on 1,362 real sessions, ~100M tokens (see `scripts/bench_session_search.py`):

| Operation | Duration | Notes |
|---|---:|---|
| Tier 1 build | <100 ms | Pure metadata read |
| Tier 2 cold build (sequential) | **~24 s** | 85% in `parse_file`, 15% in extraction |
| Tier 2 cold build (8 threads) | **~23 s** | GIL contention; no parallel win |
| Per-session load + extract | mean 17 ms, p95 78 ms | Tail: one 986 ms outlier |
| Per-session tokenize | ~1 ms | Measured separately; small relative to parse |
| BM25F index insert (whole catalog) | ~0.5 s | 4 fields × ~1,362 docs |
| **Query p50** | **<50 ms (target)** | To be measured; extension catalog at 28K docs was 37 ms |
| **Query p95** | **<100 ms (target)** | To be measured |

RSS note: the current server's steady-state RSS is ~2.2 GB across all caches (dashboard, LLM, search, etc.); the session search index's share of that is not isolated in today's code. The new design discards each trajectory immediately after extraction, so the search index should contribute only ~50–200 KB per session of lowercased text + postings — roughly an order of magnitude less than holding trajectories would. Exact numbers to be measured with `bench_session_search.py` via `resource.getrusage`.

Target: every query returns under the 500 ms frontend debounce window with significant headroom.

## Verification

Split across two scripts + one test directory.

### `scripts/eval_session_search.py` (new)

20 golden queries covering:

- **Exact session_id match** → expected sid at rank 1.
- **session_id prefix match** (first-segment) → expected sid in top 3.
- **Multi-token content queries** ("react component", "python testing", "authentication bug") → expected sid substring in top 5.
- **Single-token content queries** ("pytest", "fastapi", "migration") → expected sid in top 5.
- **Nonsense query** → empty result.
- **Empty query** → empty result.

Reports rank-1% and top-5% pass rates per category and overall. Target: ≥90% top-5 overall.

Used by the Weight tuning methodology above.

### `scripts/bench_session_search.py` (new)

Benchmarks:

- Cold Tier 2 build duration.
- p50 / p95 / p99 query latency on 30 sample queries.
- RSS delta between pre-build and post-build (`resource.getrusage(RUSAGE_SELF).ru_maxrss`).

Targets: cold build <30 s on 1,500 sessions, query p95 <100 ms, RSS growth <200 MB.

### `tests/services/session/search/` (new)

Unit + integration:

- `test_extract.py` — per-field extraction correctness on synthetic trajectories (user_prompts, agent_messages, tool_calls, arg/observation truncation).
- `test_session_index.py` — insert, search, incremental add, refresh, invalidate lifecycle. Thread safety under concurrent search + add.
- `test_scorer.py` — tiering (exact, prefix, none), AND semantics, field-weight composition.
- `test_search_quality.py` — golden mini-catalog of 20 synthetic sessions, asserts the same invariants as the extension `test_search_quality.py`.

### Existing tests kept green

- `tests/services/extensions/search/` — must pass unchanged after commit 1 (shared core extraction).
- `tests/api/` — session list + search endpoint integration updated for the new response shape in commit 3.

## Dependencies

No new runtime dependencies. `rank-bm25>=0.2.2` is already in `pyproject.toml` from the extension search redesign. The shared `services/search/` core uses it; session search inherits.

## Future work (follow-up specs)

1. **Field-specific source selection.** Bring back the `sources` parameter as a real filter: when the user explicitly wants to search only `user_prompts`, skip BM25 scoring for the other three fields. Saves ~3× scoring work on the common case; deferred until someone asks for it.
2. **Per-session cache.** If process restarts become painful (e.g., cloud deployment with frequent cold starts), add `~/.vibelens/session-cache/{sid}.json` holding only the lowercased per-field text. Measured win: 24 s → 1–2 s warm rebuild. Rejected from v1 for disk cost.
3. **Recency rescoring.** Blend BM25 with `recency_signal` similar to extension DEFAULT mode. Requires UX decision on whether recent-but-weak-match should beat old-but-strong-match.
4. **Snippet highlighting.** Return matched spans so the frontend can bold them in result cards.
5. **Tier 2 readiness UX.** If users find the silent "agent_messages queries return nothing during build" confusing, add a `/api/sessions/search/status` endpoint + a small frontend badge ("full search available in ~15 s…").

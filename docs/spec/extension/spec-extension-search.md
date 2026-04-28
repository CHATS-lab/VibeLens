# Extension Catalogue Search

Field-weighted BM25 with tiered name-match ranking. Powers the catalogue browse UI (the explore tab) and the L3 retrieval step of the recommendation pipeline.

## Motivation

VibeLens ships a unified catalogue of extensions across multiple types (skills, plugins, sub-agents, slash commands, hooks, MCP servers, repositories) drawn from many ecosystems. The catalogue is large enough that ranking matters: typing the name of an item the user already has in mind has to put it at rank 1, not buried under alphabetical neighbours; multi-token queries have to find items that mention every word, not just one; profile-based recommendation has to rank candidates from the same engine that user typing does, so "browse" and "recommend" never produce subtly different results.

Earlier iterations used substring filtering for browse and a separate TF-IDF path for recommendation. Rankings diverged, exact name matches landed mid-list, and low-signal items polluted results. The current design consolidates both paths behind a single shared BM25 engine with a name-match tiering layer on top.

## Architecture

```
User types query                  Recommendation profile
       │                                  │
       ▼                                  ▼
  ExtensionQuery(search_text, sort)   ExtensionQuery(profile, sort=PERSONALIZED)
       │                                  │
       └──────────────┬───────────────────┘
                      ▼
              rank_catalog(query, top_k?)
                      │
                      ▼
              CatalogSearchIndex   (module singleton, built lazily)
                      │
                      ├─ type-filter mask
                      ├─ name-match tiers (raw tokens, no stemming)
                      ├─ field-weighted BM25  (AND across required tokens,
                      │                        OR-prefix on the trailing token)
                      └─ precomputed quality / popularity / recency signals
                      ▼
              top-k ScoredExtension
                      │
                      ▼
              list_extensions hydrates AgentExtensionItem
```

The shared core lives in `services/search/` (tokeniser, generic field-weighted BM25 + sparse postings, generic tiered ranking) and is reused by session search. Extension-specific signals (quality / popularity / recency) live in `services/extensions/search/`.

## Two-layer ranking

The final order is one `np.lexsort` over three keys: `(name_score desc, composite desc, name_lower asc)`. Bands are sized so a higher-tier name match always outranks a lower-tier one, regardless of composite.

- **`name_score`** — additive bands triggered by how strongly the query matches the item's name:
  - exact match (separator-insensitive: `mcp server` ≈ `mcp-server` ≈ `mcp_server`),
  - all raw query tokens appear as whole name tokens,
  - per-token bonus for partial token matches,
  - small substring bonus.

  Because the band sizes compound, an exact match always beats an all-tokens-but-not-exact match, which always beats a partial-token match.

- **`composite`** — blend of five signals normalised to `[0, 1]`:
  - `text` — weighted per-field BM25 over the user's typed query.
  - `profile` — weighted per-field BM25 over the user's `UserProfile.search_keywords`.
  - `quality`, `popularity`, `recency` — precomputed per-item.

  Each `SortMode` (`DEFAULT`, `PERSONALIZED`, `QUALITY`, `RECENT`, `NAME`) is a weight vector over those five signals (`NAME` skips the composite entirely and just uses the tier + alphabetical tiebreak). When an input is missing — empty `search_text`, no profile — the corresponding weight is zeroed and the others rescale to sum to 1.

## Match semantics

- **AND across required tokens.** A multi-token query like `python testing` returns only items where every token appears somewhere across the indexed fields. (BM25's default OR semantics flood with single-word matches, which is unhelpful.)
- **OR-prefix on the trailing token.** If the query doesn't end in whitespace and the trailing token isn't in any vocabulary, it's expanded to vocab tokens that share its prefix (capped, so `t` doesn't blow up). Earlier tokens still AND-match. Skipped when the user types a trailing space — that's the signal they finished the word.

## Field weights

Per-field BM25 contributions are weighted before summing, biased so name matches dominate description matches:

| Field | Source |
|---|---|
| `name` | `item.name` |
| `topics` | space-joined topics |
| `author` | author + repo full name |
| `description` | item description + repo description |
| `readme` | readme description |

Exact weights live in `FIELD_WEIGHTS` and are tunable via the eval harness.

## Tokenisation

Lowercase → split on non-alphanumeric → drop stopwords and tokens shorter than 2 chars → conservative stem (`-ies → -y`, strip `-ing` / `-ed` / `-s`; deliberately not `-er` / `-es`, those collapse unrelated domain nouns). Same tokeniser at index build and query time so stems match deterministically.

Name-match tiering uses the **raw** (un-stemmed) tokens — exact matches shouldn't depend on a stem coincidence.

## Index data structures

`CatalogSearchIndex` builds, in order:

- precomputed signal arrays (`quality_signal`, `popularity_signal`, `recency_signal`) — `numpy float32`, length = num items.
- `type_mask` — bool array per `AgentExtensionType` for O(1) type filtering.
- lowercased name array for exact-match detection, substring scan, and alphabetical tiebreak.
- per-item raw name-token sets for the all-tokens / partial-token tiers.
- per-field BM25 instances.
- per-field sparse inverted postings — `{token: int32-array of item indices}`. (Dense bool matrices were tried; they don't fit in memory at catalogue scale.)
- prefix map for autocomplete-style trailing-token expansion, capped at a reasonable maximum prefix length to bound memory.

The singleton is rebuilt lazily on first access after `reset_index()` (called by `reset_catalog_cache()`). Read access is lock-free — every index field is immutable after construction.

## Public types

- `ExtensionQuery` — `search_text`, optional `profile`, `sort`, optional `extension_type` filter.
- `ScoredExtension` — `extension_id`, `composite_score`, `signal_breakdown` (per-signal contribution, used by the recommendation engine to populate rationale data). `name_score` is internal.
- `SortMode` — `DEFAULT`, `PERSONALIZED`, `QUALITY`, `RECENT`, `NAME`. Legacy values (`popularity`, `relevance`) are coerced at the API boundary.

## API

`GET /api/extensions/catalog`

| Param | Type | Notes |
|---|---|---|
| `search` | str | Empty → browse mode. |
| `extension_type` | str | One of the `AgentExtensionType` values. |
| `sort` | str | See sort modes; legacy values coerced. |
| `page`, `per_page` | int | 1-indexed; per-page capped. |

Response `{items, total, page, per_page}`. With a non-empty `search`, `total` counts only items that passed the AND match — the frontend pagination bar reflects matching items, not the catalogue size.

`GET /api/extensions/catalog/meta` returns the topic vocabulary plus a `has_profile` flag the frontend uses to show or hide the `Personalized` sort option.

## Lifecycle

- **Startup.** Lifespan launches `warm_index()` as a background `to_thread()` task. The server accepts requests immediately; a request that arrives before the index finishes acquires the build lock and waits for it.
- **Catalogue reload.** `reset_catalog_cache()` calls `reset_index()`; the next query rebuilds.
- **Build failure.** If catalogue load fails, `warm_index()` logs and returns; the next real search retries.

## Performance shape

- **Cold build** is on the order of seconds; runs once per process on a background thread.
- **Query latency** stays well under the frontend's search debounce window. Hot-path optimisations: BM25 returns numpy arrays (no Python-level per-item loops), composite is a vectorised add over precomputed signal arrays, profile BM25 is skipped when profile keywords are empty, `top_k` is plumbed through so only returned items materialise as `ScoredExtension` dataclasses, prefix expansion fires only when the trailing token has no exact vocab match.
- **Memory** is dominated by the prefix map and the sparse postings; both scale with vocabulary size.

## Verification

Two scripts run against the bundled catalogue:

- `scripts/eval_search.py` — golden-query harness with intent-categorised pairs `(query, expected_name_substring)`. Reports rank-1 and top-5 pass rates per sort mode. Used for weight tuning: perturb `FIELD_WEIGHTS` or `SORT_WEIGHTS`, rerun, accept the configuration that maximises top-5 with rank-1 as tiebreak.
- `scripts/bench_search.py` — measures cold build time, query latency p50/p95/p99 over a representative query mix, and RSS delta. Used as a regression guard.

Unit tests under `tests/services/extensions/search/` cover tokenisation, index construction, scoring (tiering math, weight redistribution, AND semantics, NAME-mode behaviour with a query), query coercion, and the AND / prefix paths against a synthetic corpus. API-level tests under `tests/api/test_catalog_api.py` cover the HTTP contract: filter combinations, pagination stability, legacy sort coercion.

## Dependencies

- `rank-bm25` — pure Python, returns numpy arrays from `get_scores`.
- `numpy` — vectorised arithmetic, `lexsort`, posting-list arrays.

## Open design space

- Labelled-relevance weight tuning. The eval harness allows iteration; a labelled relevance set + hill-climbing would replace educated guesses with measured wins.
- Typo tolerance via bigram overlap on the trailing out-of-vocab token (the prefix path covers partial typing but not transpositions).
- Hand-curated synonym map (`k8s` ↔ `kubernetes`, `postgres` ↔ `postgresql`, `js` ↔ `javascript`).
- IDF-weighted partial-token bonus in `name_score`, so rare tokens count for more than common ones.

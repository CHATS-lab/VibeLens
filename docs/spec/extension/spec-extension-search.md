# Extension Catalog Search

Weighted per-field BM25 search with tiered name-match ranking. Powers the catalog browse UI (explore tab) and the L3 retrieval step of the recommendation pipeline.

## Purpose

Users browse ~28K extensions (skills, plugins, subagents, commands, hooks, MCP servers, repos) via a search box with a sort dropdown. The search must:

1. Return the item the user "had in mind" at rank 1 — exact-name matches dominate.
2. Compose text query with sort preference: typing narrows results, sort mode orders them within matches.
3. Serve L3 of the recommendation pipeline with the same ranker, so browse-quality ≡ recommend-quality.
4. Stay responsive under the frontend's 500 ms search debounce — per-query latency well under that window.
5. Rebuild cheaply when the catalog reloads; block no requests during startup.

The earlier implementation used substring filtering for browse and a separate TF-IDF path for recommendations. Rankings diverged, exact matches landed mid-list, and low-signal items polluted results. This module consolidates both paths behind a single engine.

## Architecture

```
User types query                   L2 recommendation profile
      |                                    |
      v                                    v
  ExtensionQuery(search_text, sort, ...)   ExtensionQuery(profile, sort=PERSONALIZED)
      |                                    |
      +---------------+--------------------+
                      v
             rank_catalog(query, top_k?)
                      v
             +--------+----------+
             |                   |
             v                   v
       get_index()        _extract_profile_keywords
             |
             v
  CatalogSearchIndex  (module singleton, built lazily)
             |
             v
       rank_extensions()
             |
             +------> type-filter mask
             +------> _name_match_tiers()   -> name_scores (int32)
             +------> _score_text_query()   -> AND-mask + weighted BM25 text_scores
             +------> quality / popularity / recency signals (precomputed at build)
             |
             v
       lexsort by (name_score desc, composite desc, name asc)
             |
             v
       top-k ScoredExtension objects
                      v
             list_extensions() hydrates full AgentExtensionItem via
             CatalogSnapshot.get_item(extension_id), returns page of dicts
```

## Key Files

### Backend

| File | Role |
|------|------|
| `services/extensions/search/__init__.py` | Public API: `rank_catalog`, `get_index`, `reset_index`, `warm_index`, types |
| `services/extensions/search/index.py` | `CatalogSearchIndex` — per-field BM25 + sparse inverted postings + precomputed signals |
| `services/extensions/search/scorer.py` | `rank_extensions` — tiered name-match + composite blending |
| `services/extensions/search/query.py` | `ExtensionQuery`, `ScoredExtension` (dataclass), `SortMode`, `coerce_legacy_sort` |
| `services/extensions/search/tokenizer.py` | `tokenize()` — regex split, stopwords, conservative stemming |
| `services/extensions/catalog.py` | `list_extensions` — browse-endpoint entry point, pagination, hydration |
| `services/recommendation/engine.py` | `_retrieve_and_score` — L3 of the recommendation pipeline |
| `api/extensions/catalog.py` | `GET /api/extensions/catalog` HTTP endpoint |
| `storage/extension/catalog.py` | `load_catalog` + `reset_catalog_cache` hook that calls `reset_index()` |
| `app.py` | FastAPI lifespan launches `warm_index()` as a background asyncio task |
| `scripts/eval_search.py` | Golden-query eval harness (~50 queries × 3 sort modes) |
| `scripts/bench_search.py` | Performance benchmark (build time, query latency percentiles, memory) |

### Frontend

| File | Role |
|------|------|
| `components/personalization/extensions/extension-explore-tab.tsx` | Search input, sort dropdown, paginated result grid |
| `components/personalization/extensions/extension-constants.ts` | `SORT_OPTIONS`, `DEFAULT_SORT` |

## Data Flow

### Browse flow

1. User types in the search box. 500 ms debounce (`SEARCH_DEBOUNCE_MS` in `constants.ts`).
2. Frontend calls `GET /api/extensions/catalog?search=<text>&sort=<mode>&page=1&per_page=50[&extension_type=skill]`.
3. `list_extensions_endpoint` → `list_extensions(search_text, extension_type, sort, page, per_page)`.
4. `list_extensions` (in `services/extensions/catalog.py`):
   a. Coerces the `sort` string with `coerce_legacy_sort` (handles deprecated `popularity` → `default` and `relevance` → `personalized`).
   b. Coerces `extension_type` string to the `AgentExtensionType` enum; unknown values are logged and treated as "no filter".
   c. Loads the latest `UserProfile` via `_load_latest_profile()`: the personalization store returns the most recent recommendation analysis; the profile is extracted from it. If no analyses exist or loading fails, returns `None`.
   d. Falls back from `PERSONALIZED` → `DEFAULT` if the profile is absent or has no `search_keywords`.
   e. Builds `ExtensionQuery(search_text, profile, sort, extension_type)` and calls `rank_catalog(query)`.
5. `rank_catalog` returns the full ranked list of `ScoredExtension`. With a non-empty query, only items matching the query survive (total shrinks).
6. `list_extensions` paginates the ranked list and hydrates each result via `CatalogSnapshot.get_item(extension_id)`, returning dicts.
7. Response: `{items: [...], total: N, page, per_page}`. **`total` is the post-match count, not the catalog size** — the frontend pagination bar reflects matching items only.

### Recommendation flow

1. L2 (LLM profile generation) produces a `UserProfile` with 20–30 `search_keywords`.
2. `engine.py::_retrieve_and_score(catalog, profile)` builds `ExtensionQuery(profile=profile, sort=PERSONALIZED)` (no `search_text`).
3. `rank_catalog(query, top_k=SCORING_TOP_K=100)` returns the top 100 candidates.
4. Engine hydrates each to `(AgentExtensionItem, composite_score)` via `catalog.get_full(...) or catalog.get_item(...)` and passes them to L4 for rationale generation.
5. With no `search_text`, the `text` weight is redistributed away (see "Missing-input redistribution" below); profile dominates ranking.

### Index lifecycle

- **Startup**: `app.py::lifespan` launches `warm_index()` as a background asyncio task via `asyncio.to_thread`. Build takes ~1 s on 28 K items. The server accepts requests immediately; a request arriving before the index finishes hits `get_index()`, which acquires the build lock and blocks until the background task finishes. No user-visible downtime; at most one request eats the 1 s cost.
- **Catalog reload**: `reset_catalog_cache()` (in `storage/extension/catalog.py`) calls `reset_index()`. The next `get_index()` lazily rebuilds from the fresh catalog.
- **Concurrency**: the singleton is protected by `threading.Lock`. Read access is lockless — `BM25Okapi` and the sparse postings are immutable after construction, and Python dict-slot reads are atomic under the GIL.
- **Error handling at startup**: if `load_catalog()` fails, `warm_index()` catches `ValueError`, logs an info line, and returns. The next real search retries the build.

## Ranking

### Two-layer ranking

The final order is a single `np.lexsort` over three keys:

```
primary key:   name_score   (int32, descending)
secondary:     composite    (float32, descending, always 0 for NAME mode)
tertiary:      name_lower   (object, ascending)
```

**Layer 1: `name_score`** — how strongly the item's name matches the query. Four additive bands; a higher-tier match always outranks a lower-tier match because band sizes compound, not interleave:

| Band | Contribution | Trigger |
|---|---|---|
| Exact | +1000 | Query equals `item.name` (separator-insensitive: `mcp server`, `mcp-server`, `mcp_server` all match a name of `mcp-server`) |
| All-tokens | +500 | Every raw query token (no stemming) appears as a whole name token |
| Partial-token | +10 × matched | Per raw query token that's a whole name token |
| Substring | +1 | Raw query string appears as a substring of the lowercased name |

Worked example — query `paper-writing` against item named `paper-writing`:
- Exact match → +1000
- Every token of `{paper, writing}` appears as a name token → +500
- 2 tokens match → +20
- "paper-writing" is in the name → +1
- **name_score = 1521**

Against item `ml-paper-writing`:
- Not exact → 0
- Every token in name → +500
- 2 partial matches → +20
- "paper-writing" substring present → +1
- **name_score = 521**

Against item `paper-plan`:
- Not exact → 0
- Not all tokens (only `paper`) → 0
- 1 partial match → +10
- No substring → 0
- **name_score = 10**

Because the gaps between bands are larger than the per-token bonus can ever be, order among these items is deterministic regardless of BM25 composite.

**Layer 2: `composite`** — blend of five [0, 1]-normalized signals:

| Signal | Source |
|---|---|
| `text` | Weighted per-field BM25 with AND semantics across required query tokens; optional OR prefix expansion on the last token |
| `profile` | Same BM25 pipeline, query = `UserProfile.search_keywords` joined with spaces |
| `quality` | `item.quality_score / 100.0`, clamped to [0, 1] |
| `popularity` | `item.popularity` (pre-normalized at catalog build time) |
| `recency` | `exp(-days_since_updated / 180)` — half-life ≈ 125 days; undated items score 0 |

Weight vectors per `SortMode` (each row sums to 1.0):

| Mode | text | profile | quality | popularity | recency |
|---|---|---|---|---|---|
| `DEFAULT` | 0.30 | 0.20 | 0.30 | 0.10 | 0.10 |
| `PERSONALIZED` | 0.20 | 0.50 | 0.20 | 0.05 | 0.05 |
| `QUALITY` | 0.20 | 0.00 | 0.80 | 0.00 | 0.00 |
| `RECENT` | 0.20 | 0.00 | 0.00 | 0.00 | 0.80 |
| `NAME` | (alphabetical within `name_score` tier — no composite) |

**Missing-input redistribution**: if `search_text` is empty OR no profile is available, the corresponding weight is zeroed and the remaining weights rescale to sum to 1.0. Example: `PERSONALIZED` with empty text becomes `(0.00, 0.625, 0.25, 0.0625, 0.0625)`. Implemented in `_effective_weights`.

### Match filtering (AND semantics for text query)

A multi-token query like `python testing` returns only items where **every** required token appears somewhere across the indexed fields (a BM25 default-OR result set would flood with items mentioning only one word). The AND mask is built token-by-token:

1. For each required token, union the per-field posting bitmasks (O(k) per field where k = items containing the token).
2. Intersect across tokens.
3. If the intersection is empty, return all-zeros → the caller gets an empty result list.

Items failing the AND check have their BM25 composite zeroed before normalization, so they can't contribute to the max-score denominator and can't appear in results.

### Prefix expansion (autocomplete fallback)

If the user's query doesn't end in whitespace and the last token isn't in any field's vocabulary, it's treated as a prefix:

1. Look up all indexed tokens starting with the prefix (from the pre-built prefix map, prefix lengths 3–12).
2. Cap at 10 expansions to avoid per-keystroke blowup (`test` would otherwise expand to ~40 tokens).
3. The expansions form an OR set: items matching at least one expansion pass.
4. All earlier tokens still need to AND-match.

Covers partial typing: `testg` → `testgen` because `testg` isn't a real vocab token. Skipped when the user types a trailing space (signal that they finished the word).

### SortMode.NAME behavior

`NAME` mode skips composite scoring entirely but **still uses `name_score` tiering**. Result: for query `paper-writing` + `sort=NAME`:

1. `paper-writing` exact match (name_score 1521) at rank 1.
2. Other items where all tokens appear in the name, alphabetical.
3. Items with only partial tokens, substring, or description-only matches further down.

Without tiering, `paper-writing` would be buried at rank 41 (alphabetical order puts `ablation-planner`, `alphaxiv`, and other `a`-names first) — this was the original bug that motivated the tiered design.

## Tokenization

`tokenizer.py` — pure functions, no state:

1. Lowercase.
2. Split on non-alphanumeric: `re.findall(r"[a-z0-9]+", text)`. Exposed as `_TOKEN_RE` for raw-token consumers (e.g. name-match tiering needs unstemmed tokens).
3. Drop stopwords (~180-word English list inlined) and tokens shorter than 2 chars.
4. **Conservative stem**: `-ies` → `-y`; then strip `-ing`, `-ed`, `-s` when the remaining stem is ≥ 3 chars. **Does NOT strip `-er` or `-es`** — those rules collapse unrelated domain nouns (`paper` → `pap`, `postgres` → `postgr`) and were removed after they broke real queries.

Same tokenizer runs at both index build time and query time, so stems match deterministically: `testing` and `tests` both reduce to `test`.

Name-match tiering uses the raw (unstemmed) tokens via `_TOKEN_RE` to avoid false matches that only appear through stemming.

## Index data structures

`CatalogSearchIndex.__init__` builds, in this order:

- **Precomputed signal arrays** (numpy, length = num_items):
  - `quality_signal` — float32, `quality_score / 100` clamped to [0, 1].
  - `popularity_signal` — float32, `popularity` clamped to [0, 1].
  - `recency_signal` — float32, `exp(-days_since_updated / 180)`. Uses `parse_iso_timestamp` from `utils/timestamps.py` (handles trailing `Z`, naive-to-UTC conversion, and out-of-range dates).
- **`type_mask`** — `dict[AgentExtensionType, np.ndarray[bool]]` for O(1) type-filter selection.
- **`names_lower_arr`** — dtype-object numpy array of lowercased item names. Used for exact-match detection, substring search, and alphabetical tiebreak via `np.lexsort`.
- **`_name_token_sets`** — per-item `set[str]` of raw name tokens (from `_TOKEN_RE`). Used for the all-tokens-are-name-tokens tier and the partial-token count.
- **Per-field `BM25Okapi`** instances (one per field with any content). `rank_bm25` owns IDF and length-norm math; we pass pre-tokenized corpora and receive float scores back as numpy arrays.
- **Per-field sparse inverted postings** — `dict[field, dict[token, np.ndarray[int32]]]`. Each value is a sorted array of item indices containing the token. Replaces the dense `bool` matrix (1 GB at 28 K items × 28 K tokens) with ~30 MB; build time dropped from 140 s to 1 s.
- **Prefix map** — `dict[str, set[str]]` mapping each token prefix (lengths 3–12) to the full tokens that start with it. Capped at length 12 to bound memory.

## Field weights

BM25 contributions are weighted by field before summing:

| Field | Source | Weight |
|---|---|---|
| `name` | `item.name` | 5.0 |
| `topics` | `" ".join(item.topics)` | 3.0 |
| `author` | `f"{item.author} {item.repo_full_name}"` | 2.0 |
| `description` | `f"{item.description or ''} {item.repo_description or ''}"` | 1.0 |
| `readme` | `item.readme_description` | 0.5 |

These are tunable constants in `FIELD_WEIGHTS` (in `index.py`). Raise `name` to bias harder toward name matches; raise `description` to surface items with rich documentation even when the name doesn't match. Tuning is guided by the eval harness (see Verification).

## Sort modes

| Mode | Label in UI | Behavior |
|---|---|---|
| `default` | Default | Blended — good for casual browsing |
| `personalized` | Personalized | Profile-dominant (renamed from "For You"; hidden when no profile exists) |
| `quality` | Quality | Highest-quality items first, text match as tiebreak |
| `name` | Name | Alphabetical within name_score tier; exact matches still float to rank 1 |
| `recent` | Recent | Most-recently-updated first |

Legacy `popularity` and `relevance` query-param values are accepted at the API boundary and coerced to `default` and `personalized` respectively (`coerce_legacy_sort`). One-release deprecation window.

## Public types

### `ExtensionQuery` (pydantic `BaseModel`)

| Field | Type | Purpose |
|---|---|---|
| `search_text` | `str` | User-typed query. Empty → browse mode. |
| `profile` | `UserProfile \| None` | Drives the `profile` signal. `None` → signal zeroed. |
| `sort` | `SortMode` | Weight vector selector. |
| `extension_type` | `AgentExtensionType \| None` | Pre-scoring type filter. `None` → all types. |

### `ScoredExtension` (dataclass with slots, NOT pydantic)

| Field | Type | Purpose |
|---|---|---|
| `extension_id` | `str` | Caller hydrates the full `AgentExtensionItem` via this id. |
| `composite_score` | `float` | Final weighted composite (NOT including `name_score`). |
| `signal_breakdown` | `dict[str, float]` | Per-signal contribution: `text`, `profile`, `quality`, `popularity`, `recency`. For debugging and for the recommendation pipeline to populate `RankedRecommendationItem.scores`. |

`name_score` is internal and not exposed — it only affects ordering, not a user-visible score.

## API

### `GET /api/extensions/catalog`

| Param | Type | Default | Notes |
|---|---|---|---|
| `search` | str | null | User-typed query text |
| `extension_type` | str | null | `skill` \| `plugin` \| `subagent` \| `command` \| `hook` \| `mcp_server` \| `repo` |
| `sort` | str | `default` | See sort modes; legacy values coerced |
| `page` | int | 1 | 1-indexed |
| `per_page` | int | 50 | Max 200 |
| `category`, `platform` | str | null | Deprecated; accepted for backward compat, ignored server-side |

Response: `{items: list[AgentExtensionItem dict], total: int, page: int, per_page: int}`.

**`total` semantics**: when `search` is non-empty, `total` counts only items that passed the AND-match filter. When `search` is empty, `total` equals the pre-filter (post-type-filter) count. The frontend pagination bar uses `total` directly.

**Error responses**:
- `404` if the catalog is unavailable (raised from `_get_catalog()` in the service).
- `422` on Pydantic validation failures (unknown sort value — in practice coerced, so rarely seen).
- `503` if `rank_catalog` raises `ValueError` during index build (catalog load failed between request acceptance and scoring).

### `GET /api/extensions/catalog/meta`

Returns `{topics: list[str], has_profile: bool}`. The frontend uses `has_profile` to show/hide the `Personalized` sort option.

## Performance

Benchmarked against the real 28 K-item catalog via `scripts/bench_search.py`:

| Metric | Target | Measured |
|---|---|---|
| Cold index build | < 1500 ms | ~1000 ms |
| Query latency p50 | < 60 ms | ~37 ms |
| Query latency p95 | < 150 ms | ~48 ms |
| Query latency p99 | < 250 ms | ~49 ms |
| Index RSS delta | < 150 MB | ~140–150 MB (near edge) |

The frontend's 500 ms debounce dominates perceived latency; the search cost is a rounding error inside it.

### Hot-path optimizations

- BM25 `get_scores` returns numpy arrays; no Python-level per-item loops.
- Signal arrays (`quality_signal`, `popularity_signal`, `recency_signal`) are precomputed at build; query-time composite is a vectorized add.
- Profile BM25 skipped entirely when `profile_keywords` is empty (saves one full BM25 pass).
- `np.lexsort` handles the final multi-key sort with no Python key function.
- `top_k` is plumbed through to the scorer so `ScoredExtension` dataclasses are only materialized for returned items — at 28 K items with `per_page=50`, 27 965 items never get a Python object allocated.
- Prefix expansion only fires when the last token has no exact vocab match — avoids blowing up on every keystroke.
- Sparse inverted postings (int32 index arrays, not bool matrices) cut memory by ~10× and build time by ~130×.

## Verification

Two scripts verify search: `eval_search.py` for quality, `bench_search.py` for performance. Both run against the real bundled catalog — no mocks — so pass/fail reflects production behavior.

### `scripts/eval_search.py` — quality harness

**What it does**:

1. Warms the catalog search index.
2. Iterates ~50 curated `(query_text, expected_name_substring)` pairs in `GOLDEN_QUERIES`, organized by intent category:
   - Exact-name matches (20 queries): `paper-writing`, `github`, `notion`, etc.
   - Multi-token intent (10): `python testing`, `sql postgres`, `code review`, etc.
   - Partial/prefix (4): `testg`, `paper-writ`, `postgr`, `markdo`.
   - Semantic / descriptive (6): `sql optimization`, `kubernetes deploy`, etc.
   - Category queries (3): `security audit`, `log analysis`, `dependency check`.
   - Author/org (1): `anthropic`.
   - Ambiguous popular (6): `test`, `lint`, `explain`, etc.
3. For each query, runs `rank_catalog()` under `DEFAULT`, `NAME`, and `RECENT` sort modes.
4. Finds the rank of the first result whose name contains `expected_name_substring`. Returns `-1` if no match.
5. Prints a table per mode with status prefix:
   - `OK ` — expected item ranked 1st
   - `T5 ` — expected item in top 5 but not 1st
   - `RK ` — expected item below rank 5
   - `X  ` — expected item not in results at all
6. Reports `rank-1 pass rate` and `top-5 pass rate` per mode.

**Current pass rates** (run against 28 015-item catalog):

| Sort | rank-1 | top-5 |
|---|---|---|
| `DEFAULT` | 49/50 (98%) | 50/50 (100%) |
| `NAME` | 47/50 (94%) | 50/50 (100%) |
| `RECENT` | 49/50 (98%) | 50/50 (100%) |

The three NAME-mode rank-1 misses all land in top 5 — typically cases where the catalog has no item exactly matching the expected substring (e.g. no item named literally `pdf-processing`; `PDF Processing Pro` wins on substring match).

**How to run**: `python -m scripts.eval_search`.

**How to extend**: add `(query, expected_name_substring)` pairs to `GOLDEN_QUERIES`. Re-run the script. New entries that fail at rank-1 but pass top-5 are acceptable; new rank-1 failures that drop below top-5 indicate a quality regression.

### `scripts/bench_search.py` — performance harness

**What it does**:

1. Loads the catalog synchronously, then resets the search index and runs GC. This ensures the measured RSS delta reflects only the index, not the catalog load.
2. Cold-builds the index via `get_index()` and records build time.
3. Takes a second RSS sample and reports the delta in MB.
4. Runs 3 warmup queries to amortize one-time Python costs (first numpy allocations, JIT, etc.).
5. Runs 30 representative queries and records each latency. Queries cover:
   - Simple single-token (`testgen`, `docker`, `mcp`, ...)
   - Multi-token (`python testing`, `machine learning`, `python fastapi react`, ...)
   - Prefix edge cases (`t`, `te`, `tes`, `test`, `testg`)
   - No-match stress (`xyzqqqq`)
6. Computes p50/p95/p99 and prints each vs. its target with PASS/FAIL.

**Targets** (regression guards; not user-facing SLOs because the 500 ms debounce dominates):

| Metric | Target | Rationale |
|---|---|---|
| Build | < 1500 ms | One-time cost in background lifespan |
| p50 | < 60 ms | Typical multi-token query |
| p95 | < 150 ms | Prefix fallback / no-match edge cases |
| p99 | < 250 ms | Worst observed |
| RSS delta | < 150 MB | Index-only (catalog preloaded) |

**How to run**: `python -m scripts.bench_search`.

**What triggers alerts**: RSS is currently at the 150 MB target edge. If the catalog grows substantially, the prefix map (longest contributor) and the sparse postings both scale with vocabulary size. If RSS fails, consider lowering the prefix-map max length (currently 12) or sharding postings by type.

### Unit and integration tests

- `tests/services/extensions/search/test_tokenizer.py` — splitting, casing, stopwords, stemming rules, determinism.
- `tests/services/extensions/search/test_index.py` — build with empty/single/multi items, reset, posting-list shape, type masks.
- `tests/services/extensions/search/test_scorer.py` — weight redistribution math, tier computation for exact/all-tokens/partial/substring, sort orders, deterministic tiebreaks, NAME-mode behavior with query.
- `tests/services/extensions/search/test_query.py` — `ExtensionQuery` type coercion, `coerce_legacy_sort` for all paths.
- `tests/services/extensions/search/test_search_quality.py` — AND semantics across a 50-item synthetic corpus (BM25 IDF stabilizes at N ≥ 10), prefix matching, empty result handling for nonsense queries.
- `tests/api/test_catalog_api.py` — HTTP-level filters, pagination stability across pages (tiebreak determinism), legacy sort coercion, deprecated `category`/`platform` params ignored.
- `tests/services/recommendation/test_engine.py` — recommendation engine constants and rationale shaping (engine's consumption of `rank_catalog`).

Total: 1119 backend tests (including 58 search-specific), 41 frontend tests. All pass.

## Dependencies

- `rank-bm25 >= 0.2.2` — pure Python; returns numpy arrays from `get_scores`.
- `numpy` — already transitive; used directly for vectorized arithmetic, `lexsort`, and posting-list arrays.

`scikit-learn` (previously used for TF-IDF) and its transitive `scipy` dependency were removed as part of this refactor — net install size reduction ~50 MB.

## Future work

- **Labeled-relevance weight tuning**: field weights and sort-mode weights are educated guesses. The eval harness lets us iterate, but we haven't yet built a labeled relevance set or hill-climbed weights against it.
- **Typo tolerance**: prefix expansion handles partial typing but not character transpositions (`tesging` doesn't match `testing`). Candidate: bigram overlap on the query's out-of-vocab tokens when no exact or prefix match exists.
- **Query synonym expansion**: `k8s` → `kubernetes`, `postgres` → `postgresql`, `js` → `javascript`. Currently users have to type both forms. A small hand-curated synonym map would cover the high-value cases without the complexity of learned embeddings.
- **Per-token IDF in `name_score`**: rare tokens are stronger signals than common ones, but the partial-token band currently weights every token equally at +10. Weighting by IDF would prefer items whose names share the rare terms of the query.
- **Typed-search scoping from the URL**: the frontend already lets users filter by type via pills; if we also accepted typed queries like `type:skill testgen` we could avoid a round-trip when power users want both filter and query in one field.

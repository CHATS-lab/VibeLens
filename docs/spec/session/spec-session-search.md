# Session Search

Field-weighted BM25 over parsed session trajectories, with a `session_id` exact / prefix tier on top. Powers the search input on the session sidebar.

## Motivation

Session listings reach into the thousands quickly. The original substring filter had three shortcomings:

- **No ranking** — matches came back in metadata order; useless when a query returned hundreds of sessions.
- **Poor recall** — literal substring matching missed `react components` for `react component`, `pytest` for `python testing`, etc. There was no tokenisation, no stemming.
- **Cost grew with content size** — substring scanning had to read every session's text on every query.

BM25F gives ranking and recall. The shared inverted-index core is the same one the extension catalogue uses, so improvements to one search benefit the other. The cost shape is different, though, and that drives the next section.

## Search is off by default

The full-text index dominates the server's resident memory. On a multi-thousand-session corpus the BM25 instances and the per-session token cache together account for the bulk of RSS, while most users never type into the sidebar's search box. The default is therefore "off"; enabling search is opt-in via `search.enabled = true` in `config/self-use.yaml` (or the `VIBELENS_SEARCH__ENABLED` env var).

When disabled:

- Lifespan startup skips both index tiers and the periodic refresh task.
- `GET /api/sessions/search` short-circuits to an empty list.
- `GET /api/settings` reports `search_enabled: false` so the frontend hides the search input.

The session list itself, project / agent filters, the dashboard, and every analysis path are unaffected — none of them depend on the search index.

## Architecture

```
User types query
      │
      ▼
search_sessions(query, session_token, top_k)
      │
      ▼
SessionSearchIndex
      │
      ├── session_id tier        exact / first-segment prefix lookup
      └── BM25F                  weighted over user_prompts,
                                 agent_messages, tool_calls, session_id
      │
      ▼
list[ScoredSession]   (session_id, composite_score)
```

The shared `services/search/` core (`inverted_index.py`, `ranking.py`, `tokenizer.py`) is domain-agnostic — sparse posting lists, prefix maps, generic field-weighted BM25, generic tiered ranking. `services/session/search/` adds the session-specific signal: how to extract per-field text from a `Trajectory`, the session-id tier, and the recency tiebreaker.

## Two tiers

- **Tier 1 (metadata).** Built synchronously during lifespan from `list_all_metadata()`. Covers `session_id` and `first_message`. Cheap, ready immediately.
- **Tier 2 (full text).** Built asynchronously in a background task: load each session, extract the four fields (lowercased), tokenise once, insert into the inverted index, then drop the trajectory. Memory stays bounded — only the lowercased text and postings stay resident, the parsed trajectory is collected after extraction.

Queries during the build window fall through to Tier 1; nothing in the API contract differs.

## Ranking

Two layers:

1. **`session_id` tier.** Exact match → top tier. First-segment prefix match (query `"abc"` matches `"abc-de-123"`, not `"xyz-abc-123"`) → prefix tier. Everything else → tier 0.
2. **Composite within the tier.** Weighted BM25F across the four fields with AND semantics — every non-prefix query token must appear somewhere in the document.

Final order: `(tier desc, composite desc, recency desc)`. Recency comes from a parallel float array of session timestamps held alongside the index, so there's no metadata lookup at query time.

Field weights bias the score by signal-to-noise: `session_id` weighted highest (rare exact match, decisive when it hits), then `user_prompts` (what users remember typing), `agent_messages`, then `tool_calls` (high repetition, lowest signal-to-noise).

## Tokenisation

Shared with extension search. Lowercases, splits on non-alphanumeric, drops stopwords and tokens shorter than 2 chars, applies conservative stemming (`-ies → -y`, strips `-ing` / `-ed` / `-s`; deliberately does not strip `-er` or `-es` — those collapse unrelated words).

## Per-field text extraction

- `user_prompts` — concatenation of every `source=user` step's text.
- `agent_messages` — concatenation of every `source=agent` step's text content (no tool data).
- `tool_calls` — for every agent step: tool name, string-valued arguments (truncated), and observation results (truncated). Truncation prevents one giant session from dominating the index with megabytes of tool output.
- `session_id` — held in a separate dict for O(1) exact / prefix lookup, **not** passed through the BM25 tokeniser (session ids are opaque, not natural language).

## API

```
GET /api/sessions/search?q=<query>
→ [{"session_id": "...", "score": 12.3}, ...]
```

- Empty query → `[]`.
- Search disabled → `[]`.
- Per-tab `X-Session-Token` scopes results to the requesting browser tab in demo mode.

The frontend stops re-sorting search results by timestamp when a query is active — the backend already ranked them.

## Lifecycle paths

- **Startup.** Lifespan task triggers Tier 1 sync, schedules Tier 2 build in the background.
- **Post-upload.** `add_sessions(ids, token)` parses each new session, extracts fields, tokenises, inserts under the index lock.
- **Periodic refresh.** Diffs current metadata against the indexed set; adds new sessions, removes removed ones. Sub-second when only a handful changed.
- **Explicit invalidate.** `invalidate_search_index()` clears Tier 2 under the lock; Tier 1 stays. Used by storage-layer reset hooks and tests.

The lock guards the entries dict and the BM25 field arrays against concurrent reads from in-flight search requests.

## Out of scope

- Persisting the index to disk. Each process build pays the warm-up cost; the saved disk footprint isn't justified yet.
- Snippet highlighting in results. Frontend renders cards as before; only the order changes.
- Recency / popularity rescoring beyond the tiebreaker. Reasonable next step if real usage warrants it.
- Server-side autocomplete / suggestions. The frontend already debounces.

## Open design space (if Tier 2 ever returns to default-on)

- Re-tokenise per-field strings on incremental rebuild instead of caching tokens — a measurable RSS save at the cost of seconds added to `add_sessions` and `refresh`.
- Replace the BM25 backend with a sparse-matrix variant — drop-in replacement, materially smaller resident footprint at equivalent recall.

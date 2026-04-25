# Hermes parser

Parses Hermes Agent sessions in two paired formats: a per-event JSONL stream from the gateway, and a CLI-snapshot JSON document.

Code: [`src/vibelens/ingest/parsers/hermes.py`](../../../src/vibelens/ingest/parsers/hermes.py).

## File layout

```
~/.hermes/
  state.db                              # SQLite — session-level totals
  sessions/
    <YYYYMMDD_HHMMSS_hex>.jsonl         # gateway stream (Slack/Telegram/etc.)
    session_<YYYYMMDD_HHMMSS_hex>.json  # CLI snapshot (overwritten per turn)
    sessions.json                       # gateway origin metadata
```

Each session has at most one of each:

- **JSONL only** — pure CLI? actually rare; CLI sessions normally produce a snapshot only.
- **Snapshot only** — pure CLI session.
- **Both** — gateway session whose paired snapshot adds `base_url` / `system_prompt` (absent from the stream).

`discover_session_files` deduplicates: jsonl wins when both exist; snapshots without a state.db row are dropped as stale intermediates (Hermes rewrites snapshots during active sessions and never cleans up the orphans).

## Wire format

### JSONL stream

```json
{"role": "session_meta", "model": "...", "platform": "...", "tools": [...]}
{"role": "user",         "timestamp": "...", "content": "..."}
{"role": "assistant",    "timestamp": "...", "content": "...",
                         "reasoning": "...", "finish_reason": "...",
                         "tool_calls": [{"id": "...", "function": {...}}]}
{"role": "tool",         "timestamp": "...", "tool_call_id": "...", "content": "..."}
```

### Snapshot JSON

```json
{
  "session_id": "...",
  "model": "...",
  "base_url": "...",
  "platform": "...",
  "session_start": "...",
  "system_prompt": "...",
  "tools": [...],
  "messages": [
    {"role": "user|assistant|tool", "content": "...", "tool_calls": [...]}
  ]
}
```

Snapshot messages have no per-message timestamps — all steps share `session_start` as a coarse timestamp.

### state.db (sessions table)

| column | use |
|--------|-----|
| `id`, `parent_session_id` | linkage |
| `started_at`, `ended_at`, `end_reason` | duration |
| `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens` | token totals |
| `estimated_cost_usd`, `actual_cost_usd`, `cost_status`, `cost_source`, `billing_provider` | cost |
| `source` | `cli`, `slack`, etc. |
| `title` | UI display |

Hermes is **session-level only** for tokens — per-message `token_count` is always 0 in observed data. We attach the totals as a single synthetic `Metrics` on the last assistant step so the dashboard's per-step aggregator can see real numbers.

## Parsing strategy

```
parse(content, source_path)
  ├─ _parse_one_session(content, source_path)   # → main Trajectory
  │   ├─ session_id from filename               # canonical id
  │   ├─ if .jsonl:                             # primary path
  │   │   ├─ iter_jsonl_safe                    # decode lines
  │   │   ├─ _build_steps_from_jsonl
  │   │   │   ├─ pre-scan tool records by tool_call_id
  │   │   │   └─ build user / assistant Steps
  │   │   └─ _load_snapshot                     # paired enrichment
  │   └─ else (snapshot path):
  │       ├─ _parse_snapshot
  │       └─ _build_steps_from_snapshot         # share session_start as timestamp
  │   ├─ _load_state_db                         # token + cost row
  │   ├─ _load_index_entry                      # sessions.json origin
  │   ├─ canonicalise model name (4.7 vs 4-7)
  │   ├─ _attach_session_metrics_to_last_assistant
  │   ├─ _build_final_metrics                   # state.db overrides aggregator
  │   └─ _derive_project_path                   # logical URI (no real cwd)
  └─ if main is top-level (no parent_trajectory_ref):
      └─ _load_subagent_trajectories            # state.db WHERE parent_session_id = ?
```

### Model-name canonicalisation

Hermes records Anthropic models with dotted versions (`anthropic/claude-opus-4.7`); VibeLens's pricing/normalizer expects dashes (`anthropic/claude-opus-4-7`). We pipe through `llm.normalize_model_name` and **keep the raw string when unknown** so the UI surfaces something rather than dropping the model field.

### Project path

Hermes doesn't persist a filesystem cwd. We synthesise a logical URI:

| input | output |
|-------|--------|
| Slack with chat_id | `slack://D0ATU26RX1Q` |
| `source: cli` | `hermes://cli` |
| other platform | `hermes://<platform>` |
| nothing | `hermes://local` |

This keeps related conversations bucketed by surface in the UI.

## Index path (skeleton listing)

`parse_session_index` returns `None` — no fast index. The fast index *could* be built from state.db (id, started_at, source, title), but the rich first-message preview that the UI needs isn't cached anywhere; recovering it would already require reading the JSONL. The default file-parse fallback is acceptable at the volumes Hermes sees.

## Sub-agent support

**Bidirectional**, via state.db's `parent_session_id` column.

**Child → parent**: `_parse_one_session` reads `parent_session_id` for the row matching `session_id` and surfaces it as `parent_trajectory_ref` on the trajectory. A child accessed directly returns just `[child]`.

**Parent → child** loading: when `parse()` runs on a top-level session, `_load_subagent_trajectories` queries `SELECT id FROM sessions WHERE parent_session_id = ?`, locates each child's primary file (jsonl preferred, snapshot fallback via `_locate_session_file`), and parses it through the same `_parse_one_session` helper. The parent's `parse()` returns `[main, *children]` so `store.load(main_sid)` materialises the whole tree in one call.

What's still missing vs Claude: spawn-step linkage. Hermes doesn't record which tool_call in the parent spawned the child, so the parent's `Observation.results[*].subagent_trajectory_ref` is empty. The frontend places children at the chronologically-correct main step using their `started_at` timestamp (Phase 2 of `session-view.tsx`'s placement logic). Wiring per-call linkage would require Hermes to write the spawn `tool_call_id` alongside `parent_session_id`.

## Edge cases / quirks

- **Stale snapshot dedup** (`_list_state_db_sessions`): when the active session is interrupted, Hermes leaves multiple `session_<id>.json` files on disk with prefix-of-each-other content. Only those with a `state.db` row survive `discover_session_files`. If state.db is missing entirely, we keep all snapshot-only files (better over-report than silently drop standalone sessions).
- **Snapshot lacks per-message timestamps**: all steps share `session_start`, so per-step duration is meaningless. Wall clock comes from `state.db.ended_at - started_at` instead.
- **`session_meta` enrichment chain**: model and tools are looked up in order: `session_meta` record → snapshot file → null.

## Tests

[`tests/ingest/parsers/test_hermes.py`](../../../tests/ingest/parsers/test_hermes.py) covers format decoding (JSONL + snapshot variants), state.db enrichment, snapshot/jsonl pairing, and stale-snapshot filtering.

# OpenClaw parser

Parses OpenClaw sessions in their native JSONL format.

Code: [`src/vibelens/ingest/parsers/openclaw.py`](../../../src/vibelens/ingest/parsers/openclaw.py).

## File layout

```
~/.openclaw/
  agents/
    <agent-name>/                              # typically "main"
      sessions/
        <session-id>.jsonl                     # one file per conversation
        sessions.json                          # index for fast listing
        <session-id>.jsonl.reset.<ISO>.Z      # historical resets — IGNORED
        *-clean.jsonl                          # test/clean files — IGNORED
```

## Wire format

Each JSONL line is one event with a top-level `type`:

```json
{"type": "session",          "id": "...", "version": "...", "cwd": "...", "timestamp": "..."}
{"type": "model_change",     "provider": "...", "modelId": "..."}
{"type": "thinking_level_change", "level": "..."}
{"type": "custom",           "customType": "model-snapshot",
                             "data": {"provider": "...", "modelId": "..."}}
{"type": "message",          "id": "...", "timestamp": "...",
                             "message": {"role": "user|assistant|toolResult", "content": ..., "usage": {...}}}
```

Important quirks vs Claude:

- Events are wrapped: `{"type": "message", "message": {...}}` (not flat).
- Tool calls are content blocks with `type: "toolCall"` (not `tool_use`).
- Tool results are **separate** `role: "toolResult"` messages, linked via `toolCallId`.
- Usage fields use short names (`input`, `output`, `cacheRead`, `cacheWrite`), and **cost is in source** under `usage.cost.total`.
- Session metadata can be split: `session` carries cwd, `model_change` carries the model, `custom: model-snapshot` carries it again.

## Parsing strategy

```
parse(file_path)                       # BaseParser orchestrates 4 stages
  ├─ _decode_file                      # iter_jsonl_safe → list[dict]
  ├─ _extract_metadata
  │    └─ _extract_session_meta        # one pass: id, cwd, model, provider
  │         ├─ first session event      → id, cwd
  │         ├─ first model_change       → "{provider}/{model}"
  │         ├─ first model-snapshot     → fallback model
  │         └─ first real assistant msg → final fallback model
  ├─ _build_steps
  │    ├─ pre-scan toolResult role messages → toolCallId map
  │    ├─ for each role=user|assistant message:
  │    │   ├─ _decompose_content   → text, thinking, tool_calls
  │    │   ├─ _build_metrics       → usage with cost.total
  │    │   └─ _build_observation   → link tool_calls to results
  │    └─ orphan detection (toolCalls vs toolResults)
  └─ _finalize                         # timestamp, first_message, final_metrics
```

### Per-step cost

Unlike Claude/Codex/Gemini where we look up pricing post-hoc, OpenClaw records `usage.cost.total` at message time. We pass it through to `Metrics.cost_usd` and `compute_final_metrics` skips the pricing lookup for that step.

### Model-name fallbacks

The first assistant message is allowed to populate `model_name` only if it isn't `delivery-mirror` (a placeholder OpenClaw uses for non-LLM events). This avoids polluting the agent's model field with a sentinel.

## Index path (skeleton listing)

`parse_session_index` reads `<data_dir>/agents/main/sessions/sessions.json`:

```json
{
  "<key>": {"sessionId": "...", "updatedAt": "..."}
}
```

The index gives session id and timestamp but **no first message**. Skeletons returned without `first_message` are dropped by the deduper, so this index alone wouldn't populate the listing — the skeletons are mostly used for quick existence/ordering checks. Real first-message previews come through `_build_orphaned_skeletons` which falls through to `parse_skeleton_for_file` (default — full parse + clear steps).

A future improvement: head-of-file scan in `parse_skeleton_for_file` (stop after first user message) the way Claude does. Not yet implemented.

## Sub-agent support

**None.** Per-task agent delegation isn't represented in observed OpenClaw session files. The `subagents` key in `openclaw.json` (e.g. `"subagents": {"maxConcurrent": 8}`) is a config knob, not a linkage signal — and it only ever appears inside tool-result text dumps of that config file.

OpenClaw does spawn a fresh session per Slack thread, written as `<sid>-topic-<thread-id>.jsonl`. Each topic file has its own unique `session_id` and no `parent_session_id` field; they are concurrent thread-bound sessions, not children of any master session. The parser treats them as independent top-level sessions.

## Edge cases / quirks

- **Reset files**: `*.jsonl.reset.<timestamp>.Z` are historical snapshots OpenClaw keeps after a session reset. They look like real session files but represent state-before-reset. `discover_session_files` filters them out via the `.reset.*` and `-clean.jsonl` suffix lists.
- **Sessions index excluded**: `sessions.json` is in the same dir as session JSONL files; we exclude it by name in `discover_session_files`.
- **Header events interleaved with system messages**: model/cwd metadata can appear between early `delivery-mirror` system messages and the first real user prompt. `_extract_session_meta` does NOT break at the first message — it scans the whole entry list.

## Tests

[`tests/ingest/parsers/test_openclaw.py`](../../../tests/ingest/parsers/test_openclaw.py) covers format decoding (toolCall/toolResult pairing, usage.cost.total, model fallback chain, reset-file exclusion).

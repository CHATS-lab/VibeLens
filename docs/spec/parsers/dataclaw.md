# Dataclaw parser

Parses HuggingFace dataclaw datasets — third-party-exported Claude Code conversation histories with privacy scrubbing applied.

Code: [`src/vibelens/ingest/parsers/dataclaw.py`](../../../src/vibelens/ingest/parsers/dataclaw.py).

## File layout

```
<extracted-dataset>/
  conversations.jsonl                  # one complete session per LINE
```

This is unlike the local CLI parsers: a single file packs many sessions, each as a self-contained JSON object on its own line. The file is the index AND the source of truth.

`discover_session_files` is **not implemented** — Dataclaw is a manual import format, not local agent discovery, so it is not in `LOCAL_PARSER_CLASSES`.

## Wire format

One self-contained session per JSONL line:

```json
{
  "session_id": "...",        // may be missing — derived from project + start_time
  "project": "/path/...",
  "start_time": "...",
  "model": "...",
  "messages": [
    {"role": "user|assistant",
     "timestamp": "...",
     "content": "...",          // string or list (coerced to text)
     "thinking": "...",         // optional reasoning for assistant
     "tool_uses": [             // tool name + args ONLY — outputs scrubbed
       {"tool": "...", "input": {...}}
     ]}
  ]
}
```

Key differences from native Claude/Codex/Gemini:

- **Tool outputs are stripped during privacy scrubbing.** Each `tool_use` carries name + input but no result; the parser produces `ToolCall` objects with no paired `Observation`.
- **No per-message metrics.** Token counts are not present; cost is recoverable only via post-hoc pricing lookup using `record.model`.
- **No native step IDs.** Dataclaw scrubs original IDs. The parser generates deterministic IDs from `(session_id, msg_idx, role)` so re-parsing the same file yields the same Trajectory shape.

## Parsing strategy

```
parse(file_path)                                  # multi-session-per-file: overrides parse()
  └─ for each non-empty JSONL line:
       └─ _record_to_trajectory(record)
            ├─ session_id from record OR deterministic_id(project, start_time)
            ├─ _build_steps (per message)
            │    ├─ deterministic step_id = id(msg, sid, idx, role)
            │    └─ _build_tool_calls   # name + input only, no result
            └─ self._finalize(traj, diagnostics)  # per-record finalize
```

## Index path (skeleton listing)

Not applicable. Dataclaw isn't local-discoverable; sessions are loaded only when the user uploads or imports the dataset. `parse_file` delegates to `iter_trajectories` for constant-memory streaming when the file is large.

## Sub-agent support

**None.** Privacy scrubbing strips tool outputs, including the agentId markers Claude embeds. There's no way to recover sub-agent linkage from the dataclaw output.

## Edge cases / quirks

- **Memory streaming**: `iter_trajectories(file_path)` yields one Trajectory at a time so multi-GB datasets don't have to fit in memory. `parse_file` materialises into a list for the standard parser API.
- **Missing session_id**: derive a deterministic one from project + start_time. Same input → same output across re-parses.
- **Per-step model**: only assistant steps get `model_name`; user steps leave it `None` (consistent with how the live Claude parser treats user turns).
- **Diagnostics per record**: a malformed record records `"invalid record"` in the diagnostics collector but doesn't fail the whole file.

## Tests

[`tests/ingest/parsers/test_dataclaw.py`](../../../tests/ingest/parsers/test_dataclaw.py) covers format decoding (multi-session-per-file, deterministic IDs, streaming).

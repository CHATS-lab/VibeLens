# Claude Web parser

Parses Anthropic claude.ai data exports.

Code: [`src/vibelens/ingest/parsers/claude_web.py`](../../../src/vibelens/ingest/parsers/claude_web.py).

## File layout

```
<extracted-export-zip>/
  conversations.json    # JSON ARRAY of all conversations
  users.json            # not parsed
  ...
```

The export comes from claude.ai's **Settings → Export Data** download. A single `conversations.json` packs every conversation into one JSON array — `parse` returns multiple Trajectories per file.

Manual import format, not local-discoverable; not in `LOCAL_PARSER_CLASSES`.

## Wire format

```json
[
  {
    "uuid": "...",            // session_id
    "name": "...",            // optional title → trajectory.extra.conversation_name
    "summary": "...",         // optional
    "chat_messages": [
      {"uuid": "...", "sender": "human|assistant", "created_at": "...",
       "content": [...],      // content blocks, see below
       "text": "...",         // fallback for human turns when content is empty
       "attachments": [...]}  // human-message attachments
    ]
  },
  ...
]
```

Content block types inside `chat_messages[*].content`:

- `text` — plain text.
- `thinking` — extended thinking (`thinking` field, not `text`).
- `tool_use` — `{id, name, input}`.
- `tool_result` — `{tool_use_id, content}`. **Inline in the same assistant message** — no cross-message pairing needed (this is the big format difference from the CLI).
- `token_budget` — metadata; skipped.

Most `tool_use` blocks have an `id`; some pairs have `None` for both the `tool_use.id` and the corresponding `tool_result.tool_use_id` (observed for artifact tools). We pair those positionally.

## Parsing strategy

```
parse(content)
  ├─ json.loads(content)               # one big JSON array
  └─ for each conversation:
       └─ _parse_conversation
            ├─ steps = _build_steps(chat_messages)
            │     ├─ human    → _build_human_step (text + attachments)
            │     └─ assistant→ _build_assistant_step
            │           └─ _decompose_assistant_content
            │                 ├─ tool_use_counter for deterministic call IDs
            │                 ├─ tool_id_map[native_id] = generated_id
            │                 └─ tool_result blocks paired in order
            └─ assemble_trajectory
```

### Inline tool-result pairing

Because tool_results are in the same message as the tool_use that produced them, we walk the content list in order and pair as we go:

1. `tool_use` → assign deterministic call ID, remember `native_id → call_id` in `tool_id_map`.
2. `tool_result` with `tool_use_id` → look up via map.

When `tool_use.id` is `None` (artifact tools), the map entry is keyed by `None` — works because the result also has `tool_use_id: None`, so the most recent `None`-keyed call wins.

### Deterministic step / call IDs

The export doesn't always carry IDs. We fall back to `deterministic_id("msg", session_id, msg_idx, role)` and `deterministic_id("tc", session_id, msg_idx, name, counter)` so re-parsing yields stable IDs.

## Index path (skeleton listing)

Not applicable. Manual import format; the whole `conversations.json` is the index.

## Sub-agent support

**None.** Web exports do not contain sub-agent data.

## Edge cases / quirks

- **`name` and `summary` extras**: surfaced under `Trajectory.extra.conversation_name` and `Trajectory.extra.summary` so the UI can display the export's conversation title.
- **Human attachments**: `content_blocks` may be empty when only an attachment was sent; we fall back to `msg.text` for the message body and surface attachments under `Step.extra.attachments`.
- **Empty assistant turns**: `content` blocks that yielded no text, no thinking, AND no tool_use produce `None` (skipped) — keeps message-only `token_budget` blocks from creating phantom steps.

## Tests

[`tests/ingest/parsers/test_claude_web.py`](../../../tests/ingest/parsers/test_claude_web.py) covers format decoding (inline tool_result pairing, attachments, deterministic IDs).

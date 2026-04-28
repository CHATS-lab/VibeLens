# Claude parser

Parses Claude Code CLI sessions in their native JSONL format.

Code: [`src/vibelens/ingest/parsers/claude.py`](../../../src/vibelens/ingest/parsers/claude.py).

## File layout

```
~/.claude/
  projects/
    <project-hash>/
      <session-id>.jsonl              # main session, one JSONL line per event
      <session-id>/
        subagents/
          agent-<agent-id>.jsonl      # spawned via Task/Agent tool
          acompact-<id>.jsonl         # auto-compaction sub-agent
  history.jsonl                       # NOT used as index source — see "Why no history.jsonl"
```

Each session is one JSONL file. Sub-agents (Task/Agent tool, plus auto-compaction) live in a sibling `<sid>/subagents/` directory.

## Wire format

Each JSONL line is one event with a top-level `type` field:

```json
{"type": "user",      "uuid": "...", "sessionId": "...", "timestamp": "...",
 "message": {"role": "user", "content": [...]} }
{"type": "assistant", "uuid": "...", "sessionId": "...", "timestamp": "...",
 "message": {"role": "assistant", "id": "msg_…", "model": "claude-…",
             "content": [...], "usage": {...}} }
{"type": "queue-operation", "operation": "enqueue|dequeue|remove",
 "timestamp": "...", "content": "..."}
```

Anthropic Messages API content blocks appear inside `message.content`:

- `text` — plain text.
- `image` — base64 source (paired pasted screenshots).
- `thinking` — extended thinking; saved as `Step.reasoning_content`.
- `tool_use` — `{id, name, input}`. ATIF `ToolCall`.
- `tool_result` — `{tool_use_id, content, is_error}`. **Lives in the next `user` message**, not in the same assistant message — this is the cross-message pairing every Claude-style parser has to do.

## Parsing strategy

```
parse(file_path)                       # BaseParser orchestrates 4 stages
  ├─ _decode_file                      # read JSONL text
  ├─ _extract_metadata
  │    └─ _scan_session_metadata       # one pass: sessionId, model, version, cwd, gitBranch
  ├─ _build_steps
  │    └─ _parse_content
  │         ├─ iter_jsonl_safe         # raw JSONL parse
  │         ├─ queue-operation         # synthetic user entries for enqueue+remove pairs
  │         ├─ deduplicate_by_uuid     # drop replayed lines (compaction)
  │         ├─ _collect_tool_results   # pre-scan user messages for tool_result blocks
  │         ├─ _group_entries_by_step  # streaming-chunk merge by message.id
  │         ├─ _decompose_raw_content  # text / images / thinking / tool_calls / observation
  │         └─ classify_user_message   # system / skill / auto-prompt / real user
  ├─ _finalize                         # timestamp, first_message, final_metrics
  └─ _load_subagents
       ├─ _build_agent_spawn_map       # raw scan: tool_use(name=Task|Agent) → agentId regex
       │                               # in tool_result text (or persisted-output file)
       ├─ parse each agent-*.jsonl as its own Trajectory
       └─ link parent step's observation back via subagent_trajectory_ref
```

### Streaming-chunk merging

Claude Code logs streaming responses as multiple JSONL lines all sharing the same `message.id`. We group them and merge their `content` arrays before turning them into a Step, so one assistant turn is one Step.

### Queue operations

When the user types while the agent is mid-turn, Claude Code emits a `queue-operation: enqueue` event. The message is later either:

- **dequeued** → followed by a regular `type: "user"` message — we drop the enqueue, the user message wins.
- **removed** → no follow-up user message exists. We synthesise a user entry from the enqueue so the user's intent is preserved.

Pairing is FIFO (`deque.popleft()`) by occurrence order — the dequeue records its own delivery timestamp, not the enqueue's, so timestamp matching wouldn't survive that drift.

### User-message classification

A `type: "user"` entry can carry:

- Real user text → `StepSource.USER`.
- `<system-reminder>`, `<command-name>`, `<local-command-stdout>`, etc. → `StepSource.SYSTEM`.
- `Implement the following plan` / `Execute the following plan` → `USER` with `extra.is_auto_prompt: True`.
- A multimodal `list[ContentPart]` (text + image from a paste) → always treated as real user, no classification.

Skill outputs ("Base directory for this skill: ..." messages with `sourceToolUseID` linking back to a prior `Skill` tool call) are **not emitted as their own step**. `_collect_tool_results` absorbs the SKILL.md text as the Skill tool call's `Observation`, so the UI renders skill activations through the unified `ToolCall.is_skill` pill instead of a separate user-source step. Two entries can target the same `tool_use_id` (a short "Launching skill: <name>" `tool_result` block plus the longer SKILL.md text); the SKILL.md text always wins.

The classification is gated to string messages so screenshot-paste turns don't get mis-classified (the bracket-style filter would have rejected `[image]`-suffixed multimodal text otherwise).

## Index path (skeleton listing)

`parse_skeleton_for_file` reads JSONL line-by-line, skipping system caveats and tool-relay entries until it finds the first meaningful user message. No fixed line cap — some sessions begin with long stretches of caveats before the real prompt. Threaded over all session files by [`index_builder._build_file_parse_skeletons`](../../../src/vibelens/ingest/index_builder.py).

### Why no `history.jsonl`

The user's typed text in `history.jsonl` (`display` field) diverges from the canonical first message when Claude Code rewrites the prompt — most visibly when a user pastes a screenshot, the display field is the user's original prompt but the on-record first message includes `[Image #N]` markers. Reading both and disagreeing was worse than reading neither, so the index reads from the JSONL.

## Sub-agent support

**Full.** Claude is the only parser with detailed sub-agent linkage:

- Sub-agent files: `<sid>/subagents/agent-<agent-id>.jsonl` (and `acompact-*.jsonl` for auto-compaction).
- Spawn detection: each Task/Agent `tool_use` has a `tool_result` whose text contains `agentId: <hex>`. Regex extracts the id and pairs it with the spawn `tool_call_id` and parent `step_id`.
- Persisted output: when the tool result was written to an external `.txt` file (>100KB, embedded as `<persisted-output>`), we read the file's tail to recover the agentId.
- Each sub-agent becomes its own Trajectory with `parent_trajectory_ref={session_id, step_id, tool_call_id, trajectory_path}`.
- The parent step's observation gets `subagent_trajectory_ref=[ref]` so the UI can navigate from the spawn observation to the sub-agent.
- Compaction agents are flagged with `extra.is_compaction_agent: True` so downstream code can hide them or treat them differently without coupling to filename conventions.

`get_session_files` returns `[main_jsonl, *agent_files]` so cache invalidation in LocalStore picks up sub-agent file changes.

## Edge cases / quirks

- **Multimodal first-message**: a turn with text + image is stored as `message: list[ContentPart]`. First-message detection joins only the text parts (using `step_text_only`, not `content_to_text`) — emitting `[image]` placeholders would trip the bracket-wrapped system-message filter.
- **`[Image: source: ...]` echo**: Claude Code follows up an image-paste turn with a text echo of the image path. We filter these out with `_IMAGE_SOURCE_PLACEHOLDER_RE` so the conversation doesn't carry duplicate clutter.
- **Tool-relay user messages**: a `type: "user"` entry containing only `tool_result` blocks (no human text) is **dropped** — its content is already injected into the preceding assistant step via the pre-scan `tool_results` map.
- **Continuation chains**: when a `claude --resume` brings prior turns into a new file, those entries carry the **previous** session's `sessionId`. The parser flags them with `is_copied_context=True`; first-message detection skips them.
- **Persisted-output regex safety**: `<persisted-output>` capture is rejected when the path is >1024 chars or contains a newline (guards against the regex matching a content blob).

## Tests

[`tests/ingest/parsers/test_claude.py`](../../../tests/ingest/parsers/test_claude.py) covers the format-specific decoding (queue ops, sub-agent linkage, streaming merge, user classification). Cross-parser concerns (helpers, diagnostics, first-message filter) live under `tests/ingest/`.

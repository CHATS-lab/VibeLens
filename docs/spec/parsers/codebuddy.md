# Code Buddy parser

Parses Code Buddy CLI sessions in their flat-event JSONL format.

Code: [`src/vibelens/ingest/parsers/codebuddy.py`](../../../src/vibelens/ingest/parsers/codebuddy.py).

## File layout

```
~/.codebuddy/
  projects/
    <project-hash>/                         # e.g. Users-JinghengYe-Documents-Projects-TS-Study
      <session-id>.jsonl                    # main session
      <session-id>/
        subagents/
          agent-<short-id>.jsonl            # spawned via Agent tool
  blobs/<hash>/<hash>.png                   # image blobs referenced by image_blob_ref parts
  history.jsonl                             # cross-session typed prompts; ignored
  sessions/<pid>.json                       # live process metadata; ignored
  traces/<pid>/trace_*.json                 # OTEL-style spans; ignored
  shell-snapshots/, logs/, local_storage/   # operational; ignored
  settings.json, user-state.json            # config; ignored
  tasks/, teams/                            # empty in observed install
```

The directory tree mirrors Claude Code's; **the wire format does NOT** — events are flat (no envelope) and shaped like the OpenAI Responses API rather than Anthropic Messages.

## Wire format

Each line is one event:

```
{"id": "<uuid>", "parentId": "<uuid|null>", "timestamp": <ms>,
 "type": "message|reasoning|function_call|function_call_result|topic|file-history-snapshot",
 "sessionId": "<sid>", "cwd": "<path>", ...type-specific fields}
```

Event-specific shapes (verified by exhaustive key-path enumeration):

| `type` | Key fields |
|---|---|
| `message` | `role`, `status`, `content[].{type, text}` (input_text/output_text/image_blob_ref), `providerData.{model, agent, messageId, rawUsage, usage, isSubAgent?, queuePosition?, queueTotal?, agentColor?}` |
| `reasoning` | `rawContent[].{type:"reasoning_text", text}` (the `content` array is empty); `providerData.{messageId, model, agent}` |
| `function_call` | `name`, `callId`, `arguments` (JSON string), `providerData.{argumentsDisplayText, messageId, model, rawUsage, usage, reasoning, agent}` |
| `function_call_result` | `name`, `callId`, `status`, `output.{type:"text", text}`, `providerData.toolResult.{content, renderer.{type, value}}` |
| `topic` | `topic` only (no id/parentId/sessionId) |
| `file-history-snapshot` | `snapshot.{messageId, trackedFileBackups}` |

`content[]` part types observed: `input_text`, `output_text`, `image_blob_ref` (with `blob_id, mime, size, blob_path`).

## Parsing strategy

```
parse(file_path)                                    # 4-stage pipeline
  ├─ _decode_file                                   # iter_jsonl_safe → list[dict]
  ├─ _extract_metadata                              # first sessionId + cwd
  ├─ _build_steps
  │    ├─ pre-scan function_call_result by callId
  │    ├─ detect is_subagent_file (any providerData.isSubAgent)
  │    ├─ for each event in time order:
  │    │    user message     → USER step (drops CLI command echoes — see below)
  │    │    assistant msg    → AGENT turn (grouped by providerData.messageId)
  │    │    reasoning        → adds to current AGENT turn's reasoning_content
  │    │    function_call    → ToolCall on current turn; observation paired by callId
  │    │    topic            → traj.extra.topic (most-recent wins)
  │    │    file-history-*   → drop (`// TODO(file-history)`)
  │    └─ flush trailing turn
  └─ _load_subagents                                # see "Sub-agent support" below
```

### CLI command echoes — dropped, not classified as SYSTEM

Code Buddy logs every CLI slash-command and stdout snapshot as a `user.message` with XML-tag content:

```
<command-name>/model</command-name>
<local-command-stdout>...</local-command-stdout>
<system-reminder data-role="command-caveat">...</system-reminder>
```

These have content but no conversational value. Earlier versions of this parser classified them as `StepSource.SYSTEM`, but that produces empty bubbles in the UI (the steps have no user-facing text after tag-stripping). Current behavior: **drop them entirely** via `_SYSTEM_TAG_PATTERN.match(text)` returning `None` from `_build_user_step`. Diagnostics records each drop as a skip.

The pattern matches both bare (`<command-name>`) and attribute-bearing (`<system-reminder data-role="...">`) tags.

### Multimodal screenshots

`image_blob_ref` parts reference an on-disk blob at `blob_path` (e.g. `~/.codebuddy/blobs/<hash>/<hash>.png`). The parser reads the file and inlines as base64 on `ContentPart.source.base64` so the UI can render it without sandboxing concerns; `path` is preserved alongside. Falls back to path-only if the blob file is missing.

### Tool call grouping

An assistant turn can be (a) a pure-text `message`, (b) a `reasoning` event followed by one or more `function_call`s, or (c) text + reasoning + tool calls. All events from one model call share `providerData.messageId`. The parser groups by `messageId`: when a new id arrives or a user message appears, the in-flight turn flushes into a single AGENT step.

## Sub-agent support

**Full bidirectional linkage.**

Parent → child:

```
function_call(name="Agent") → function_call_result with:
  providerData.toolResult.renderer.value JSON containing taskId  (PRIMARY)
  output.text matching `task_id:\s*(agent-\w+)`                  (FALLBACK)
```

The extracted `task_id` (e.g. `agent-8c36227f`) is stashed on `obs.extra.spawn_task_id` during `_build_steps`. `_load_subagents` then walks the parent's tool calls, locates `<sid>/subagents/<task_id>.jsonl`, parses recursively, and sets:

- Parent's `obs.subagent_trajectory_ref = [TrajectoryRef(session_id=<child-sid-uuid>)]`
- Child's `parent_trajectory_ref = TrajectoryRef(session_id=<parent-sid>, step_id, tool_call_id, trajectory_path)`

Note: the parent's `task_id` (e.g. `agent-8c36227f`) is the file basename, NOT the child's session_id. The child's `sessionId` is a separate UUID inside the child file.

Child's first user message is wrapped in `<teammate-message teammate_id="..." summary="...">`. The parser flags it via `Step.extra.is_spawn_prompt=True` so first-message detection picks the wrapped text.

## Edge cases

- **`is_error` is inferred, not verified.** All 19 observed `function_call_result.status` values are `"completed"`. The error sentinel (`status != "completed"`) is documented but unobserved.
- **`topic` events lack `sessionId`/`id`/`parentId`** — use most recent at parse-end as `Trajectory.extra.topic`.
- **`message.content` is always a list** (never a string), but parts can be heterogeneous (text + image_blob_ref mixed).
- **Empty session files** observed (1 of 2 in this user's install had 0 events). `_decode_file` returns `None`; BaseParser drops.

## Field coverage

### Populated

| ATIF | Source |
|---|---|
| `Trajectory.session_id` | top-level `sessionId` (or filename stem fallback) |
| `Trajectory.agent.{name, model_name}` | `AgentType.CODEBUDDY.value`, last seen `providerData.model` |
| `Trajectory.project_path` | first non-null `cwd` |
| `Trajectory.parent_trajectory_ref` | from `_load_subagents` (sub-agent files only) |
| `Trajectory.first_message` | derived |
| `Trajectory.timestamp` (created/updated) | derived from step timestamps |
| `Trajectory.final_metrics` | sum of step metrics |
| `Trajectory.extra.topic` | most-recent `topic` event |
| `Trajectory.extra.is_subagent` | `True` if any step has `providerData.isSubAgent` |
| `Step.id` | event `id` |
| `Step.source` | `role` → USER/AGENT (CLI echoes dropped, not converted) |
| `Step.message` | text-only → string; with images → `list[ContentPart]` |
| `Step.reasoning_content` | concat `reasoning` events' `rawContent[].text` |
| `Step.model_name` | `providerData.model` |
| `Step.timestamp` | event `timestamp` (ms → datetime) |
| `Step.metrics` | `Metrics.from_tokens(input=rawUsage.prompt_tokens, output=rawUsage.completion_tokens, cache_read=rawUsage.cache_read_input_tokens, cache_write=rawUsage.cache_creation_input_tokens, extra={"reasoning_output_tokens": ..., "credit": ...})` |
| `Step.extra.is_spawn_prompt` | `True` for sub-agent's first `<teammate-message>` user message |
| `Step.extra.spawn` | `{teammate_id, summary}` extracted from teammate-message wrapper |
| `Step.extra.message_id` | `providerData.messageId` |
| `ToolCall.id` | `callId` |
| `ToolCall.name` | `name` |
| `ToolCall.input` | parsed `arguments` JSON |
| `ToolCall.extra.arguments_display_text` | `providerData.argumentsDisplayText` |
| `ToolCall.extra.{queue_position, queue_total, agent_color}` | from `providerData` when set |
| `ObservationResult.text` | `output.text` |
| `ObservationResult.is_error` | `status != "completed"` (inferred) |
| `ObservationResult.subagent_trajectory_ref` | resolved by `_load_subagents` to child's session_id |
| `ObservationResult.extra.spawn_task_id` | task_id from spawn result (used by `_load_subagents`) |
| `ObservationResult.extra.renderer_type` | `providerData.toolResult.renderer.type` |

### Dropped / unparseable

| Source | Reason |
|---|---|
| User messages matching `_SYSTEM_TAG_PATTERN` (CLI echoes) | Conversation noise; emit-as-step would clutter UI with empty bubbles |
| `file-history-snapshot.snapshot.trackedFileBackups` | Not ATIF-shaped — `// TODO(file-history): future ATIF revision` |
| `providerData.rawUsage.{audio_tokens, accepted_prediction_tokens, rejected_prediction_tokens}` | Zero in observed data; not in ATIF metrics |
| `providerData.rawUsage.{cached_tokens, prompt_cache_miss_tokens}` | Redundant with canonical cache fields |
| `message.usage` (Anthropic-style summary nested under top-level `message`) | Redundant with `providerData.usage` |
| `providerData.skipRun` | Internal scheduler flag |
| `providerData.usage.requests` | Always 1; degenerate |
| `Metrics.cost_usd` (from `rawUsage.credit`) | `credit` is Tencent's billing unit, NOT verified to be USD; stashed on `Metrics.extra.credit` until verified |
| `~/.codebuddy/sessions/<pid>.json` | Process-bound (only valid for active CLI) |
| `~/.codebuddy/traces/<pid>/trace_*.json` | OTEL spans; redundant |
| `~/.codebuddy/{logs, local_storage, shell-snapshots}/` | Operational artifacts |
| `~/.codebuddy/history.jsonl` | Same display-vs-canonical divergence as Claude's history.jsonl |

## Tests

[`tests/ingest/parsers/test_codebuddy.py`](../../../tests/ingest/parsers/test_codebuddy.py) covers basic user/assistant pair, topic capture, sub-agent linkage via renderer.value JSON + regex fallback, teammate-message detection, malformed JSONL, subagents/ exclusion in discovery.

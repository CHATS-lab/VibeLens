# Copilot parser

Parses GitHub Copilot CLI sessions from their `events.jsonl` event stream.

Code: [`src/vibelens/ingest/parsers/copilot.py`](../../../src/vibelens/ingest/parsers/copilot.py).

## File layout

```
~/.copilot/
  session-state/
    <session-uuid>/
      events.jsonl              # PRIMARY — JSONL event stream
      workspace.yaml            # supplemental metadata (cwd, git_root, summary)
      plan.md                   # agent plan when created — NOT INGESTED (see TODO)
      session.db                # SQLite, todos only — ignored
      checkpoints/, files/, rewind-snapshots/   # operational, ignored
  agents/, logs/                # operational, ignored
```

One `<uuid>/events.jsonl` per session. `workspace.yaml` adds metadata but the JSONL is canonical.

## Wire format

Each line is one event with envelope `{type, data, id, timestamp, parentId}`.

Event types observed (verified by exhaustive key-path enumeration):

```
session.start            sessionId, copilotVersion, producer,
                         context.{cwd, gitRoot, branch, headCommit,
                                  repository, hostType, repositoryHost}
session.model_change     newModel, reasoningEffort
session.plan_changed     operation marker — drop
session.shutdown         shutdownType, totalApiDurationMs, totalPremiumRequests,
                         currentModel, *Tokens, codeChanges,
                         modelMetrics.<model>.{requests.{count,cost}, usage.{...}}
system.message           role, content — drop (system prompt)
user.message             content (raw user-typed), transformedContent,
                         attachments, interactionId
assistant.message        messageId, content, toolRequests[].{toolCallId, name,
                         arguments, intentionSummary?, toolTitle?},
                         outputTokens, reasoningOpaque (encrypted),
                         encryptedContent, requestId
assistant.turn_start/end bookkeeping — drop
tool.execution_start     toolCallId, toolName, arguments
tool.execution_complete  toolCallId, model, success, result.{content,
                         detailedContent}, toolTelemetry
subagent.started         toolCallId, agentName, agentDisplayName, agentDescription
subagent.completed       toolCallId, agentName, model, totalToolCalls,
                         totalTokens, durationMs
system.notification      kind.{type, agentId, agentType, status} — sub-agent
                         completion broadcast (non-conversational)
```

## Parsing strategy

```
parse(file_path)                              # 4-stage pipeline (BaseParser)
  ├─ _decode_file                             # iter_jsonl_safe → list[dict]
  ├─ _extract_metadata                        # session.start → header + extra
  ├─ _build_steps
  │    ├─ pre-scan tool.execution_complete by toolCallId
  │    ├─ pre-scan subagent.{started,completed} by toolCallId
  │    ├─ for each event in time order:
  │    │    session.model_change  → update current_model / reasoning_effort
  │    │    session.shutdown      → traj.extra (model_metrics, code_changes, ...)
  │    │    user.message          → USER step
  │    │    assistant.message     → AGENT step + ToolCalls (with paired observations
  │    │                            from execution_complete; in-flight calls emit
  │    │                            synthetic is_error=True observation)
  │    │    other dropped types   → skip
  │    └─ if model_metrics: build FinalMetrics from session aggregates
  └─ _finalize                                # default; aggregate metrics already set
```

### In-flight tool handling

Real session contains an unmatched `tool.execution_start` (call_id `call_luoiq...`) followed by `session.shutdown` 10 hours later — the user terminated the CLI mid-tool. The parser emits a synthetic `ObservationResult(text="", is_error=True, extra={"in_flight": True})` and calls `diagnostics.record_orphaned_call`. Without this, the spawn ToolCall would be orphaned and the UI couldn't surface the partial run.

### Per-step vs. session metrics

Copilot emits `outputTokens` per `assistant.message` but **not** per-message input or cache tokens. Per-step `Step.metrics` therefore captures only `output_tokens`. The session-level `modelMetrics` aggregate (in `session.shutdown`) is the source of truth for prompt + cache totals; we build `Trajectory.final_metrics` from it after walking steps. BaseParser's per-step rollup would understate everything except output.

Multi-model sessions (when `session.model_change` fires mid-stream) yield multiple keys in `modelMetrics`; we sum across all buckets.

## Sub-agent support

**Metadata-only.** Copilot does not record the sub-agent's conversation as a separate trajectory file — only `subagent.started` and `subagent.completed` summary events land in the parent's `events.jsonl`. We attach those onto the spawning ToolCall:

```
ToolCall.extra.subagent = {
    agent_name, agent_display_name, agent_description,
    model, total_tool_calls, total_tokens, duration_ms
}
```

No child Trajectory is emitted. If Copilot ever adds a separate sub-agent rollout file, the parser will need to discover it and emit children.

## Edge cases

- **Empty session-state dir** (workspace.yaml only, no events.jsonl): observed for one UUID. `discover_session_files` skips dirs without `events.jsonl`.
- **`reasoningOpaque` and `encryptedContent`** on assistant.message are encrypted; `Step.reasoning_content = None`.
- **`transformedContent`** (agent-augmented user prompt with `<ide_selection>`, `<current_datetime>` wrappers) goes to `Step.extra.transformed_content`; `Step.text` uses raw `content` so first-message detection sees the user's words.
- **`attachments`** (IDE selection, file refs) goes to `Step.extra.attachments`.
- **`intentionSummary` / `toolTitle`** are nullable per call; populated to `ToolCall.extra` only when non-null.

## Field coverage

### Populated

| ATIF | Source |
|---|---|
| `Trajectory.session_id` | `session.start.data.sessionId` (fallback: parent dir name) |
| `Trajectory.agent.{name, version}` | `AgentType.COPILOT.value`, `session.start.data.copilotVersion` |
| `Trajectory.agent.model_name` | last seen `session.model_change.newModel` |
| `Trajectory.project_path` | `session.start.data.context.cwd` |
| `Trajectory.timestamp` (created/updated) | derived from step timestamps |
| `Trajectory.first_message` | derived from first USER step |
| `Trajectory.final_metrics` | aggregate over all `modelMetrics` buckets — see "Per-step vs. session metrics" |
| `Trajectory.extra.cli_version` | `session.start.data.copilotVersion` |
| `Trajectory.extra.{producer, head_commit, host_type, repository, repository_host, git_branch}` | `session.start.data.{producer, context.*}` |
| `Trajectory.extra.code_changes` | `session.shutdown.data.codeChanges` |
| `Trajectory.extra.session_summary` | `session.shutdown.data.{totalApiDurationMs, totalPremiumRequests, sessionStartTime, shutdownType}` |
| `Trajectory.extra.token_breakdown` | `session.shutdown.data.{currentModel, currentTokens, systemTokens, conversationTokens, toolDefinitionsTokens}` |
| `Trajectory.extra.model_metrics` | `session.shutdown.data.modelMetrics` |
| `Step.source` | `user.message` → USER; `assistant.message` → AGENT |
| `Step.text` | `data.content` (raw user-typed for user; agent text for assistant) |
| `Step.timestamp` | event `timestamp` (ISO 8601 → datetime) |
| `Step.model_name` | most-recent `session.model_change.newModel` before this step |
| `Step.reasoning_effort` | most-recent `session.model_change.reasoningEffort` |
| `Step.metrics` | per-message `outputTokens` only (input/cache live at session level) |
| `Step.extra.{transformed_content, attachments, interaction_id}` | from user.message data |
| `Step.extra.{message_id, request_id, interaction_id}` | from assistant.message data |
| `ToolCall.id` | `toolCallId` from `assistant.message.toolRequests[]` |
| `ToolCall.name` | `name` from `toolRequests[]` |
| `ToolCall.input` | `arguments` (already an object) |
| `ToolCall.extra.intention_summary` / `tool_title` | when non-null |
| `ToolCall.extra.subagent` | combined `subagent.started` + `subagent.completed` payload (sub-agent spawns only) |
| `ObservationResult.text` | `tool.execution_complete.data.result.detailedContent` (preferred) or `result.content` |
| `ObservationResult.is_error` | `not tool.execution_complete.data.success` (or in-flight synthetic) |
| `ObservationResult.extra.{telemetry, model}` | from `tool.execution_complete.data` |
| `ObservationResult.extra.in_flight` | `True` for synthetic observations on unmatched starts |

### Dropped / unparseable

| Source | Reason |
|---|---|
| `assistant.message.encryptedContent` | Encrypted; opaque |
| `assistant.message.reasoningOpaque` | Encrypted; `Step.reasoning_content` stays `None` |
| `system.message.content` | System prompt; matches drop convention across parsers |
| `assistant.turn_start`, `assistant.turn_end` | Bookkeeping; no signal |
| `session.plan_changed` | Operation marker only; plan content lives in `plan.md` |
| `~/.copilot/session-state/<uuid>/plan.md` | `// TODO(copilot-plan): ingest when ATIF gets a slot for agent-authored plans` |
| `~/.copilot/session-state/<uuid>/{checkpoints, rewind-snapshots, files}/` | Operational |
| `~/.copilot/session-state/<uuid>/session.db` | Todos table only; not session content |
| `~/.copilot/{agents, logs}/` | Operational |
| `system.notification` events | Surface sub-agent completion; metadata already captured via subagent.completed |

## Tests

[`tests/ingest/parsers/test_copilot.py`](../../../tests/ingest/parsers/test_copilot.py) covers basic session flow, tool-call pairing, in-flight tool handling, empty session-state dir, malformed JSONL.

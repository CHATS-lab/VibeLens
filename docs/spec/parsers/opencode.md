# OpenCode parser

Parses OpenCode (sst/opencode) sessions from a single SQLite database that holds every session for a user.

Code: [`src/vibelens/ingest/parsers/opencode.py`](../../../src/vibelens/ingest/parsers/opencode.py).

## File layout

```
~/.local/share/opencode/
  opencode.db                  # PRIMARY — Drizzle SQLite (all sessions)
  opencode.db-shm/-wal         # WAL companions; the driver handles them
  storage/
    session_diff/<sid>.json    # redundant with session.summary_diffs — ignored
    migration                  # drizzle marker — ignored
  snapshot/<project-hash>/<sha>/   # Git-like file-content store — ignored
  log/<ts>.log                 # operational — ignored
```

## Schema (verified)

```
session(id, project_id, parent_id, slug, directory, title, version, share_url,
        summary_additions, summary_deletions, summary_files, summary_diffs,
        revert, permission, time_created, time_updated, time_compacting,
        time_archived, workspace_id)
message(id, session_id, time_created, time_updated, data)        -- data = JSON
part(id, message_id, session_id, time_created, time_updated, data)  -- data = JSON
todo(session_id, content, status, priority, position, ...)
project(id, worktree, vcs, name, icon_url, icon_color, icon_url_override,
        sandboxes, commands, time_created, time_updated, time_initialized)
session_share, account, account_state, control_account, permission,
event, event_sequence, session_entry, workspace, __drizzle_migrations
```

## Wire format — `message.data`

```
{role, agent, mode, modelID, providerID, parentID,
 path.{cwd, root}, cost, finish, time.{created, completed},
 tokens.{input, output, reasoning, total, cache.{read, write}},
 tools.{<tool-name>: bool},
 summary.diffs[{file, status, additions, deletions, patch}],
 error.{name, data.message},
 editorContext.{openTabs, shell}}        # only populated by Kilo
```

Top-level `modelID` is canonical; nested `model.modelID` is always null. `tools` is a `{<tool>: bool}` map (booleans gating which tools were enabled, NOT tool definitions). User-role messages have null `modelID`.

## Wire format — `part.data` per type

| `type` | Key fields |
|---|---|
| `text` | `text, time.{start?, end?}` (time is **optional** — present in only ~54% of observed text parts) |
| `reasoning` | `text, time.{start, end}, metadata.anthropic.signature` |
| `tool` | `tool, callID, state.{status, input, output|error, time.{start,end}, metadata, title}` |
| `step-start` | `snapshot` only (boundary marker) |
| `step-finish` | `snapshot, reason, cost, tokens` |
| `patch` | `hash, files: [path,...]` |

`state.input` is always a typed object (99/99 verified) — do NOT call `parse_tool_arguments`. `state.status ∈ {completed, error}` (98:1 in observed data); `is_error = state.status == "error"`. When error, `state.error` carries the message; when completed, `state.output` does.

## Parsing strategy

```
discover_session_files(data_dir)        → [opencode.db]   # singleton
parse(opencode.db) (overridden):
  open SQLite (?mode=ro — see WAL note below)
  for each session row, ORDER BY time_created:
    build Trajectory header from session.* + first message's path/model
    load messages WHERE session_id=? ORDER BY time_created
    load parts   WHERE session_id=? ORDER BY message_id, part.time_created
    group parts by message_id; per-message _build_step_from_message:
      text         → Step.text (joined)
      reasoning    → Step.reasoning_content (joined; signatures stashed in extra)
      tool         → ToolCall + ObservationResult; pair by callID within message
                     - is_error = state.status == "error"
                     - text = state.output when completed, state.error when error
                     - if tool=="task": ObservationResult.subagent_trajectory_ref
                       = TrajectoryRef(session_id=state.metadata.sessionId)
                     - state.metadata captured on ObservationResult.extra.metadata
                     - editorContext (Kilo only) → Step.extra.editor_context
      patch        → Step.extra.patches
      step-finish  → Step.extra.boundaries (forensic — preserves sub-turn structure)
    Step.metrics from message.tokens / message.cost
    if session.parent_id: traj.parent_trajectory_ref = TrajectoryRef(session_id=parent_id)
    self._finalize(traj, diagnostics)
```

### WAL safety (`?mode=ro`, NOT `immutable=1`)

`mode=ro` lets SQLite see uncommitted WAL pages from a live writer. `immutable=1` would skip WAL discovery and produce stale reads. We use `mode=ro` only — appropriate for production reads of a live `opencode.db`.

### Sub-agent linkage (bidirectional)

```
parent → child:  tool.state.metadata.sessionId  (when tool=="task", primary)
                 regex `task_id:\s*(ses_\w+)` on state.output  (fallback)
child  → parent: session.parent_id column
```

Verified on real data: 2 sub-agents, both linked correctly via metadata. The regex fallback is for future-proofing in case `state.metadata.sessionId` ever drops out.

## Edge cases

- **Sessions with 1 user message + 0 assistant**: real (8 such observed). User typed but never got a response. We keep them as USER-only trajectories.
- **Bedrock auth-failure messages** carry `error.{name:"UnknownError", data.message}` and zero tokens; surfaced to `Step.extra.error`.
- **Parts ordered by `(message_id, time_created)`** — sort by SQL `time_created` column, NOT `data.time.start` (optional, ~54%).
- **Tool argument shape** — `state.input` is a typed object (e.g. `{path, pattern}` for `glob`), not a JSON-string.
- **`session.directory` ≠ `project.worktree`** in some cases (one observed session targeted `~/.vibelens/friction`). Use `session.directory`.

## Field coverage

### Populated

| ATIF | Source |
|---|---|
| `Trajectory.session_id` | `session.id` |
| `Trajectory.agent.{name, version}` | `AgentType.OPENCODE.value`, `session.version` |
| `Trajectory.agent.model_name` | most-recent assistant message's `modelID` |
| `Trajectory.project_path` | `session.directory` |
| `Trajectory.parent_trajectory_ref` | `TrajectoryRef(session_id=session.parent_id)` when set |
| `Trajectory.timestamp` (created/updated) | from step timestamps |
| `Trajectory.first_message` | derived |
| `Trajectory.final_metrics` | sum of step metrics; cost from sum of `message.cost` |
| `Trajectory.extra.{slug, title, version, share_url, revert, workspace_id, time_compacting, time_archived}` | `session.*` columns |
| `Trajectory.extra.summary` | `{additions, deletions, files, diffs}` from `session.summary_*` |
| `Trajectory.extra.todos` | rows from `todo` table for that session |
| `Trajectory.extra.{project_worktree, project_vcs, project_name}` | joined from `project` table |
| `Step.id` | `message.id` |
| `Step.source` | `message.data.role` → USER / AGENT |
| `Step.text` | concat `text` parts in DB-column order |
| `Step.reasoning_content` | concat `reasoning` parts |
| `Step.tool_calls` / `observation.results` | `tool` parts; pair within message by callID |
| `Step.model_name` | top-level `message.data.modelID` |
| `Step.timestamp` | `message.time_created` (ms epoch) |
| `Step.metrics` | `Metrics.from_tokens(input=tokens.input, output=tokens.output, cache_read=tokens.cache.read, cache_write=tokens.cache.write, cost_usd=message.data.cost)` + `extra.reasoning_output_tokens` |
| `Step.extra.{agent_role, mode, provider_id, parent_message_id, finish_reason, path_cwd, path_root, message_summary_diffs, tools_enabled, error}` | per `message.data.*` |
| `Step.extra.editor_context` | `message.data.editorContext` (no-op for opencode; populates Kilo) |
| `Step.extra.patches` | aggregated `patch` parts within message |
| `Step.extra.boundaries` | per-`step-finish`: `{snapshot, reason, tokens, cost}` (forensic) |
| `Step.extra.reasoning_signatures` | per-part `metadata.anthropic.signature` |
| `ToolCall.{id, name, input}` | `state.{callID, ?, input}` — input is a typed object |
| `ToolCall.extra.{title, metadata, time}` | `state.{title, metadata, time}` |
| `ObservationResult.text` | `state.output` when completed; `state.error` when error |
| `ObservationResult.is_error` | `state.status == "error"` |
| `ObservationResult.subagent_trajectory_ref` | `state.metadata.sessionId` (primary) or regex on output (fallback) — task tool only |
| `ObservationResult.extra.metadata` | `state.metadata` (opaque, varies per tool) |

### Dropped / unparseable

| Source | Reason |
|---|---|
| `step-start` part (bare) | Boundary marker; `snapshot` reappears in `step-finish` |
| Per-`step-finish` tokens duplicating message-level totals | Aggregate kept; per-turn copy lives in `Step.extra.boundaries` |
| `tokens.total` | Derived (`input + output`) |
| `model.{modelID, providerID}` (nested duplicate) | Always null; redundant |
| `session.permission`, `session_share`, `permission` table | Auth/permission state |
| `account`, `account_state`, `control_account` tables | Credentials; security-sensitive; never ingested |
| `event`, `event_sequence` tables | Internal pub/sub; empty in observed install |
| `session_entry` table | Empty in observed install — `// TODO(session-entry): revisit when populated` |
| `__drizzle_migrations` | DB schema metadata |
| `~/.local/share/opencode/storage/session_diff/` | Redundant with `session.summary_diffs` |
| `~/.local/share/opencode/snapshot/` | Git-like file-content store; orthogonal to ATIF — `// TODO(snapshot): future revision could surface as replayable file states` |
| `~/.local/share/opencode/log/` | Operational logs |
| `project.{icon_url, icon_color, icon_url_override, sandboxes, commands}` | UI metadata |

## Tests

[`tests/ingest/parsers/test_opencode.py`](../../../tests/ingest/parsers/test_opencode.py) covers basic session, sub-agent linkage via state.metadata.sessionId, regex fallback, tool error path, editor_context capture, missing db file, malformed db file.

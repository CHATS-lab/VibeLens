# Codex parser

Parses OpenAI Codex CLI sessions in the rollout JSONL format.

Code: [`src/vibelens/ingest/parsers/codex.py`](../../../src/vibelens/ingest/parsers/codex.py).

## File layout

```
~/.codex/
  sessions/
    <YYYY>/<MM>/<DD>/
      rollout-<timestamp>-<session-id>.jsonl   # one file per thread
  state_5.sqlite                               # threads index
  logs_2.sqlite                                # not used by VibeLens
```

Sub-agent threads live in the same `sessions/` tree and are indexed in the SQLite `threads` table with a `source` JSON value.

## Wire format

Each JSONL line is a `RolloutItem` envelope:

```json
{"timestamp": "...", "type": "session_meta",   "payload": {"id": "...", "cwd": "...", ...}}
{"timestamp": "...", "type": "turn_context",   "payload": {"model": "...", "reasoning_effort": "..."}}
{"timestamp": "...", "type": "response_item",  "payload": {"type": "message|function_call|reasoning|...", ...}}
{"timestamp": "...", "type": "event_msg",      "payload": {"type": "token_count", "info": {...}}}
```

Codex follows the OpenAI Responses API. Important payload types:

- `message` — `role: user|assistant|developer`, `content: [...]` of blocks with `type: input_text|output_text`. We skip `developer` (system prompts, AGENTS.md injections).
- `function_call` / `custom_tool_call` — tool invocation with `call_id`, `name`, `arguments` (JSON string).
- `function_call_output` / `custom_tool_call_output` — tool result for a `call_id`. **Separate from the assistant message** (different rollout entries).
- `reasoning` — chain-of-thought, with `summary[].text` blocks.
- `event_msg` `token_count` — per-turn usage stats from the API.

## Parsing strategy

```
parse(content)
  ├─ iter_jsonl_safe                # raw JSONL parse
  ├─ _scan_session_metadata         # one pass: id, cli_version, model, cwd, source, forked_from_id
  ├─ _build_steps
  │    ├─ _collect_tool_outputs     # OrderedDict bounded at MAX_TOOL_RESULT_CACHE
  │    ├─ for each entry:
  │    │    ├─ turn_context  → update parse state (model, cwd, effort)
  │    │    ├─ response_item → _handle_response_item:
  │    │    │     ├─ message    → flush pending, append Step
  │    │    │     ├─ function_call(_output) → buffer in pending_tools
  │    │    │     └─ reasoning  → dedup-by-md5, buffer in pending_thinking
  │    │    └─ event_msg(token_count) → attach Metrics to last AGENT step
  │    └─ _flush_pending            # final flush at EOF
  └─ assemble_trajectory             # parent_ref from forked_from_id, extras from session_meta
```

### Buffer / flush model

Codex emits tool calls and reasoning as separate JSONL entries *between* message entries, with no explicit end-of-turn marker. We buffer them in `_CodexParseState.pending_tools` / `pending_obs_results` / `pending_thinking` and flush onto the preceding agent step at the next message boundary (or EOF).

### Reasoning dedup

Codex streaming recovery can re-emit identical `reasoning` blocks. We fingerprint each `summary[].text` with MD5 and skip duplicates. (MD5 is used as a content fingerprint, not for any security claim.)

### Structured tool output

Codex prepends a metadata block to tool outputs:

```
Exit code: 0
Wall time: 1.23s
Output:
<actual stdout>
```

`_parse_structured_output` strips the prefix and surfaces `{exit_code, wall_time_sec}` as the observation's `extra` metadata.

### Per-turn step extras

Each agent step's `extra` carries the live `cwd` and `reasoning_effort` from the most recent `turn_context`, so a session that switches models or cwd mid-stream is reconstructible.

## Index path (skeleton listing)

`parse_session_index` reads `state_5.sqlite` and builds skeletons straight from the `threads` table — no per-file parsing needed for the listing UI:

```sql
SELECT id, rollout_path, created_at, source, cwd, title,
       tokens_used, model, first_user_message, cli_version
FROM threads
```

Sub-agent rows (source JSON containing `subagent`) are kept and tagged with `parent_trajectory_ref` extracted from `source.subagent.thread_spawn.parent_thread_id`. The storage layer (`BaseTrajectoryStore.list_metadata`) hides them from the sidebar via the `parent_trajectory_ref` filter; the parent's `parse_file` re-reads them off disk and returns them nested.

## Sub-agent support

**Full bidirectional linkage in two modes.** Codex's `spawn_agent` tool has a `fork_context` parameter:

- `fork_context: false` (default — fresh sub-agent, Claude-style): the child gets a clean conversation, just the spawn `message`.
- `fork_context: true` (fork-and-handoff): the child rollout inherits the parent's full conversation history before a `<model_switch>` developer message marks the boundary where the child's own work begins.

### Identifying a sub-agent

Three signals, in order of strength. The parser uses whichever it finds first; all three are present for interactive sessions, fewer for `codex exec`:

1. **`session_meta.payload.forked_from_id`** — fork mode only.
2. **`session_meta.payload.source.subagent.thread_spawn.parent_thread_id`** — present in **both** fresh and fork mode. Codex writes this to the rollout itself, so it works without SQLite.
3. **`session_meta.payload.agent_role`** — set on every Codex sub-agent regardless of mode. Used as a final-fallback "is sub-agent" tag when neither id-bearing signal is present (extremely rare); the trajectory still gets hidden from the listing via `extra.agent_role` even when its parent is unknown.

### Stripping the fork prelude

Fork-mode children carry `parent's_history + <model_switch> + own_work` in their rollout. `_strip_fork_prelude` keeps the child's first `session_meta` and drops everything between it and the `<model_switch>` developer message, so:

- The child's first `user` message is the spawn instruction, not the parent's earliest prompt.
- The child's `turn_context` reflects the sub-agent's model (e.g. `gpt-5.4-mini`), not the parent's.
- Token-count events from the parent's earlier turns don't get attributed to the child's metrics.

Fresh-mode rollouts have no prelude — `_strip_fork_prelude` is a no-op for them.

### Discovering child rollouts when loading the parent

`parser.parse_file(parent_path)` returns `[main, *children]`, the same shape Claude's parser uses. Two lookup paths:

1. **SQLite primary**: `_find_subagent_rollouts(parent_id)` queries `state_5.sqlite` for rows whose `source` mentions `parent_thread_id`. Fast; used by interactive Codex.
2. **Filesystem fallback**: when SQLite returns nothing (`codex exec` mode), `_find_subagent_rollouts_via_filesystem` scans the parent's content for `spawn_agent` `function_call_output` JSON containing `agent_id`, then `rglob`s `~/.codex/sessions/` for files whose stem ends with the agent_id.

### Linking parent → child

`_extract_subagent_ref` parses each `spawn_agent` tool output (`{"agent_id": "<child-id>", "nickname": "..."}`) and sets `ObservationResult.subagent_trajectory_ref = [TrajectoryRef(session_id=agent_id)]` on the parent's spawn step. The UI reads this to render the child inline at the right spot in the parent's flow.

What's **not** populated on `parent_trajectory_ref`: the parent's spawn `step_id` and `tool_call_id`. Those would need a second pass over the parent's rollout when parsing the child, adding I/O for a weak win (the child's own steps tell you what it did; the link to the parent's step is mostly cosmetic). Not implemented.

## Edge cases / quirks

- **`info: null` in `token_count`**: when a turn fails before the usage block is produced. `payload.get("info") or {}` guards against it.
- **Bounded tool-result cache**: MAX_TOOL_RESULT_CACHE = 500 keeps long sessions from holding all results in memory. Calls older than that bound lose their result text but the call itself still appears.
- **`<environment_context>` / `<turn_aborted>` user messages**: Codex injects these as `role: user`. We reclassify to `StepSource.SYSTEM` via the prefix list in `_CODEX_SYSTEM_TAG_PREFIXES`.
- **`prompt_tokens` convention**: VibeLens stores `prompt_tokens = input_tokens + cache_read_tokens` (Anthropic convention). Codex's `cached_input_tokens` (or `input_tokens_details.cache_read_tokens`) is added on top of `input_tokens` for the prompt total.

## Tests

[`tests/ingest/parsers/test_codex.py`](../../../tests/ingest/parsers/test_codex.py) covers the format-specific decoding (response_item types, structured output, token_count attachment, fork linkage).

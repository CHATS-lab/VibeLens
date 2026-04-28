# Writing a new agent parser

Procedural guide. For the architecture overview see [README.md](README.md); for each existing parser's specifics read its `<parser>.md` neighbour. Read this end-to-end **before** writing code — most parser bugs trace to an assumption made without inspecting actual session files.

A parser is **done** when:

1. **Fidelity** — every ATIF field the source data can populate is populated. No invented values; no silent data loss.
2. **Robustness** — every session file on disk parses without raising, including stale snapshots, duplicates, format drift, malformed lines. Failures become diagnostics, not exceptions.
3. **Shape** — sub-agents link to parents, continuations to predecessors, sessions deduplicate against the format's ground-truth index.
4. **Capability completeness** — every supported feature in the [capability matrix](#capability-matrix) is either implemented or marked `// TODO(<format>-<capability>)` with a clear data-collection request.

---

## The closed-loop process

```
0. Data collection      ← real session files on your machine
1. Format research      ← official docs + reverse-engineering
2. Capability gating    ← one decision per capability: implement, defer, or NA
3. Design               ← write docs/spec/parsers/<agent>.md
4. Implementation       ← src/vibelens/ingest/parsers/<agent>.py
5. Testing              ← unit tests + on-disk audit
6. Validation           ← full suite + lint + docs
```

### 0 — Data collection

Install the agent locally. Run sessions covering each scenario in the [capability matrix](#capability-matrix) below: a long conversation that triggers compaction, a turn with an image attachment, a sub-agent spawn, a tool error, a session resume if the agent supports it. Open the on-disk files. Note total count, file extensions, filename patterns, paired siblings, index files.

### 1 — Format research

Answer these for the spec:

| Question | Why |
|---|---|
| File format (JSONL / JSON / SQLite / plaintext)? | Picks the decode helper |
| Role tagging — flat or wrapped envelope? | How `_build_steps` walks the data |
| Tool calls — content blocks inside assistant, or separate entries linked by call_id? | Drives pre-scan / pairing |
| Tool results — inline / next user turn / own role? | Same |
| Token usage — per-message? per-session? field names? | Per-step `Metrics` vs `final_metrics` |
| Cost — in source, or via pricing catalog? | Whether to set `Metrics.cost_usd` directly |
| Timestamps — per-record? format? | Ordering + duration |
| Sub-agent linkage — none / per-call ID / DB column / sibling files / inline tool result? | `_load_subagents` strategy |
| Continuation — does the agent resume prior sessions? | `prev_trajectory_ref` source |
| Compaction — in-stream marker / event type / agent role / external slash-command log? | Where to detect it |
| Image attachments — base64 inline / data URL / file path / blob ref? | Decoding strategy |
| Format drift — multiple known versions? renamed fields? | Accept old + new in parallel |

### 2 — Capability gating

Before writing the parser, walk the [capability matrix](#capability-matrix) and decide each row's status from real session data:

- **Implement** — data carries the signal; the parser will populate the corresponding ATIF field.
- **Defer** — feature exists in the agent but no session captures it yet. **Stop and ask the developer to generate one.** Do not guess at the wire format from documentation alone.
- **N/A** — the agent format genuinely doesn't support this feature (e.g. Hermes has no resume workflow). Note the absence in the parser's docstring.

### 3 — Design (write the spec doc)

Use [openclaw.md](openclaw.md) (simple) or [hermes.md](hermes.md) (complex, multiple sources) as a template. Required sections:

- File layout (directory tree with example filenames)
- Wire format (annotated JSON/JSONL example)
- Parsing strategy (high-level pipeline summary)
- Capability table — explicit status per row from §[capability matrix](#capability-matrix)
- Sub-agent support (none / partial / full + mechanism + direction)
- Edge cases / quirks
- Tests reference

Add a row to [README.md](README.md)'s comparison matrix.

### 4-6 — Implementation, testing, validation

Sections below.

---

## Capability matrix

The minimum each new parser must address. **Every row** needs an explicit status: ✓ implemented, ✗ N/A for this format, or `// TODO` with a data-collection request.

| Capability | What it means | What the parser must produce | Verify by |
|---|---|---|---|
| **Text content** | Every user / agent turn surfaces its text body | Populated `Step.message` (string or `list[ContentPart]`) | Sample any session — expect non-empty messages |
| **Reasoning content** | Thinking / chain-of-thought blocks the agent records | `Step.reasoning_content` populated when present | Run a session with `claude --thinking` / GPT-5 reasoning / etc. |
| **Tool calls** | Each invocation captured with id, name, arguments | `Step.tool_calls[].ToolCall` present | Trigger a tool — file read, web search, shell exec |
| **Tool observations** | Each result pairs back to its call | `Observation.results[].ObservationResult.source_call_id` matches the call; `is_error` reflects the format's native flag | Force a failing tool call (typo a path) |
| **Multimodal images** | Pasted / attached images survive end-to-end | `Step.message` becomes `list[ContentPart]` with `ContentPart(type=image, source=Base64Source(media_type, base64))` | Paste a screenshot in a user turn |
| **Sub-agents** | Spawned child sessions linked back to parent | Child `Trajectory.parent_trajectory_ref` set; parent observation's `subagent_trajectory_ref` lists the child | Trigger the agent's sub-agent / Task tool |
| **Compaction** | Mid-session context rewriting / truncation | Synthetic SYSTEM step or `extra.is_compaction=True` on affected steps; **summary content preserved verbatim** when the format records it | Run a session past the auto-compaction threshold, or invoke the explicit slash command if available |
| **Skills** | Skill-registry invocations distinguished from generic tools | `ToolCall.extra.is_skill = True` when name matches the shared `SKILL_TOOL_NAMES` set in `helpers.py` | Invoke any skill in the agent |
| **Continuation refs** | Resume / fork chains preserved | `prev_trajectory_ref` / `next_trajectory_ref` populated via the format's native linkage | Resume a previous session |
| **Persistent output files** | Tool outputs written to side files (Claude `>100KB`) | Observation content references or includes the external content | Trigger a tool that produces large output |

**Rule of thumb:** if a row has no on-disk evidence, *do not implement against documentation alone*. Stop and ask the developer to produce a session that exercises it. Implementing on guesses tends to over-fit and break on the first real example.

---

## `extra` field vocabulary

`Trajectory.extra` and `Step.extra` are flexible dicts. Reuse the keys below across parsers so the UI and downstream consumers can rely on stable semantics. Add a new key only when no existing one fits, and namespace anything format-specific (`hermes_*`, `copilot_*`).

### Step.extra (per-step metadata)

| Key | Type | Purpose | Set by |
|---|---|---|---|
| `is_compaction` | bool | This step is part of a compaction / summarisation boundary | codex, copilot, gemini, opencode, codebuddy |
| `is_truncation` | bool | Hard message-window truncation event (rarer than compaction) | copilot |
| `is_auto_prompt` | bool | The step text was auto-generated by the agent (e.g. "Implement the following plan") | claude |
| `is_subagent` | bool | The trajectory the step belongs to is a sub-agent (mirrored on every step for fast filtering) | codebuddy |
| `is_copied_context` | bool | The step came from a `--resume`-style continuation prelude, not the live conversation | claude |
| `is_queued_prompt` | bool | The user typed while the agent was busy; the prompt was queued | claude |
| `is_spawn_prompt` | bool | The user message that triggered a sub-agent spawn | codebuddy |
| `agent_role` | str | Logical role of the message inside the trajectory (e.g. `"compact"`, `"explore"`) | codebuddy, copilot, gemini |
| `agent_nickname` | str | Display name of the spawned agent | codebuddy, copilot |
| `agent_description` | str | Short description string the agent provides at spawn time | copilot |
| `agent_color` | str | UI-only color tag from the format | codebuddy |
| `attachments` | list[dict] | Attachment metadata (path, displayName, type) — bytes are inlined as `ContentPart` on `message` | copilot |
| `compaction` | dict | Format-specific compaction details (e.g. `{auto, overflow}`) supplementing `is_compaction` | opencode |
| `boundaries` | list[dict] | Step-finish snapshots (assistant turn boundaries) | opencode |
| `editor_context` | dict | Tracked open files / shell state at message time | kilo |
| `error` | dict | Native error payload from the agent's run | opencode |
| `finish_reason` | str | Why the assistant turn ended (e.g. `"end_turn"`, `"stop_sequence"`) | claude, hermes, opencode |
| `git_branches` | list[str] | Branches recorded for the session at this point | claude |
| `intention_summary` | str | Tool-call intent the agent recorded before invoking | copilot |
| `interaction_id` | str | Format-specific request grouping id | copilot |
| `message_id` | str | Source-format message id (preserved for cross-reference) | codebuddy, copilot |
| `model_metrics` | dict | Per-model usage breakdown | copilot |
| `path_cwd` / `path_root` | str | Working directory / repo root at message time | opencode |
| `patches` | list[dict] | Patch parts emitted alongside the assistant message | opencode |
| `pre_compaction_tokens` / `pre_truncation_tokens` / `tokens_removed` / etc. | int | Compaction / truncation accounting | copilot |
| `provider_id` / `mode` | str | Provider-specific routing metadata | opencode |
| `queue_position` / `queue_total` | int | Position when the message was queued for batched dispatch | codebuddy |
| `reasoning_effort` | str | Model effort tier the assistant ran at (`high`, `medium`, …) | claude, copilot |
| `reasoning_output_tokens` | int | Token count attributed to the reasoning trace | opencode, claude |
| `reasoning_signatures` | list[str] | Anthropic signatures attached to thinking blocks | opencode |
| `request_id` | str | Provider request id | copilot |
| `spawn_tool_call_id` | str | Tool call that spawned this sub-agent (set on the child) | copilot, gemini |
| `spawn_task_id` | str | CodeBuddy's `taskId` linking a sub-agent to its filename | codebuddy |
| `status` | str | Native status code from the source format | codex |
| `subagent_*` | int | Counts emitted by `subagent.completed` (totalToolCalls, tokens, durationMs) | copilot |
| `synthesized_inline` | bool | The step was synthesised from an inline tool result, not real recorded content | gemini |
| `tools_enabled` | dict | Per-message tool-availability map | opencode |

### Trajectory.extra (per-session metadata)

| Key | Type | Purpose | Set by |
|---|---|---|---|
| `is_skeleton` | bool | This Trajectory was built from a fast index without parsing per-step content | opencode, openclaw |
| `is_subagent` | bool | The trajectory is a sub-agent of another session | codebuddy |
| `agent_role` / `agent_nickname` / `agent_description` / `agent_color` | str | Sub-agent identity carried at trajectory level | codebuddy, copilot, gemini |
| `cli_version` / `producer` | str | CLI build identifier | copilot |
| `git_branch` / `git_branches` | str / list[str] | Repository branch(es) at session time | claude, copilot |
| `head_commit` | str | Commit SHA the session was running against | copilot |
| `host_type` / `repository_host` / `repository` | str | Origin metadata (GitHub, etc.) | copilot |
| `model_metrics` | dict | Session-level token / cost rollup grouped by model | copilot |
| `code_changes` | dict | Aggregate file-edit counts across the session | copilot |
| `session_summary` | dict | `session.shutdown` payload (durations, totals) | copilot |
| `token_breakdown` | dict | System / tool-definitions / conversation token split | copilot |
| `time_compacting` / `time_archived` | int | Timestamps of compaction / archival events | opencode |
| `summary` | dict | OpenCode `summary_*` columns (additions / deletions / files / diffs) | opencode |
| `slug` / `title` / `version` / `share_url` | str | OpenCode session metadata | opencode |
| `project_worktree` / `project_vcs` / `project_name` | str | Project directory context | opencode |
| `topic` | str | CodeBuddy session topic line | codebuddy |
| `team_name` | str | Multi-agent team identifier | codebuddy |
| `total_token_usage` | dict | Codex `tokens_used` rollup | codex |
| `synthesized_inline` | bool | Trajectory was synthesised from a tool-result text rather than its own file | gemini |
| `rollout_path` | str | On-disk path of the session file (used by index reconciliation) | opencode, openclaw |
| `diagnostics` | dict | Quality counters: skipped lines, orphans, completeness score | every parser via `_finalize` |

**Adding a new key:**

1. Check whether an existing key already covers the meaning. If yes, reuse it.
2. If the field is shared across agents (e.g. another compaction-shape), add it to this table.
3. If the field is format-specific, namespace it (`<agent>_<field>`) and document it in the parser's docstring rather than this table.
4. Avoid one-off keys for transient debug data — keep `extra` lean.

---

## When the developer hasn't generated the data yet

Before adding code for any capability, the parser author must show real session data carrying the relevant signal. If the data is missing:

1. **Stop implementation of that capability.**
2. **Tell the developer concretely what to do**, e.g.:
   - *Compaction*: "Run a long session in `<agent>` until the auto-compaction warning fires, or invoke `/compact` / `/compress` if the agent supports it. Send me the path."
   - *Sub-agents*: "Ask `<agent>` to delegate to a sub-agent / Task / Explore tool. Confirm the spawn appears in disk data."
   - *Images*: "Paste a screenshot in a user turn and send another message so the session is flushed to disk."
3. **Document the gap** in the parser's docstring with a `// TODO(<format>-<capability>): need <type-of-data>` line, plus what the developer needs to do to unblock it.
4. **Don't guess.** Format documentation is often outdated or incomplete; the wire format is the only reliable source of truth.

The developer should treat this prompt as part of the workflow: the parser author may legitimately request more session data more than once before a parser is complete.

---

## Design principles

These distinguish a parser that holds up over years of format drift from one that merely passes its first test run. Every item below is something a previous parser got wrong before we tightened it up.

**Trust the source, then the index, then yourself.** Most agents write multiple views of the same session: a raw stream (JSONL), a periodic snapshot (JSON), an authoritative index (SQLite, JSON manifest). These views disagree. Pick an explicit priority order in the file-level docstring. The narrowest, most authoritative source wins: if `state.db` lists 16 sessions and the directory has 39 files, the db is right. If a JSONL records a model change mid-session and the snapshot only the final model, trust the per-turn value for `Step.model_name` and the snapshot for `Agent.model_name`.

**Populate, don't invent.** Every field you set is a claim about the source data. Hardcoding constants leaks them into thousands of trajectories. If deleting the line that sets a field doesn't lose information that was actually in the source, delete the line. `None` is a truthful answer when the data isn't there.

**Idempotency.** Parsing the same file twice yields equal `Trajectory` objects. Sort `discover_session_files` results so test fixtures agree across OSes. Prefer `deterministic_id` over `uuid4()`. Don't iterate `set()` where emission order matters; sort or use an `OrderedDict`. Dashboards that cache by `session_id` depend on this — non-determinism makes cache invalidation impossible.

**`extra` is a pressure valve, not a dumping ground.** If a field is useful enough to surface in the UI for this agent, it goes in `Trajectory.extra` or `Step.extra` with a named key. If it's not useful, don't capture it — a noisy `extra` dict is worse than a missing field because downstream consumers start relying on it and then you can never delete it. Each key should be either universally meaningful across agents or clearly namespaced.

**Format drift is inevitable.** Agents version their formats. Two defences: accept old and new field names side by side; skip unknown block / event types silently. A parser that crashes on the first unfamiliar type blocks ingestion the day the agent ships a new feature.

**Diagnostics > exceptions.** `parse()` should never let an exception escape. Every skippable problem (bad line, orphaned tool result, missing timestamp) gets recorded on the `DiagnosticsCollector` so it surfaces in the UI as a quality warning. Exceptions bypass diagnostics and look like real breakage.

**Claude is the reference parser.** Whenever a capability ambiguity arises, the answer is "what does the Claude parser do?" Claude has the longest history of real-data feedback and the broadest feature coverage; mismatches against Claude's behaviour usually mean the new parser is wrong, not Claude.

---

## Implementation

The 4-stage pipeline is described in [`base.py`](../../../src/vibelens/ingest/parsers/base.py)'s docstring; consult it for hook contracts and ordering. Pick one of two parser shapes:

- **Single-session-per-file** (claude, codex, gemini, hermes, openclaw, codebuddy): implement `_decode_file`, `_extract_metadata`, `_build_steps`. Don't override `parse`.
- **Multi-session-per-file** (opencode, kilo, dataclaw, claude_web, parsed): override `parse(file_path)` directly and call `self._finalize` per record.

### Hook expectations

- `_decode_file` reads the wire format and returns a parsed structure or `None`. Catch only specific exceptions (`OSError`, `UnicodeDecodeError`, `json.JSONDecodeError`, `sqlite3.Error`).
- `_extract_metadata` builds the `Trajectory` header (`session_id`, `agent`, `project_path`, parent / continuation refs, `extra`). Leave `steps=[]`, no `timestamp`, no `final_metrics` — those are derived in `_finalize`.
- `_build_steps` walks raw data, builds ordered `Step`s. May mutate `traj` for legitimate per-step backfills (e.g. most-recent model). Set `ObservationResult.is_error` from the format's **native** error signal, never bake `[ERROR] ` into content.
- `_load_subagents` overrides discover-and-parse for spawned children. Return `[]` if the format has no sub-agent linkage.

For sub-agent files that reuse the parent's session id (Claude's `<sid>/subagents/`, Gemini's `kind: subagent`), use a synthetic id (filename stem) and put the parent's id in `parent_trajectory_ref`. The synthetic id avoids index collisions.

### Multi-source data

When the source spans multiple files (primary jsonl + paired snapshot + state.db row + sessions index — see Hermes), don't re-hit disk in every stage. Have `_decode_file` build a small dataclass that carries everything decoded once, then later stages destructure it in O(1). Cuts the per-parse I/O dramatically.

### Capability-specific guidance

**Sub-agents** — when the format embeds child IDs inside tool_results (Claude's `agentId: <hex>`, Codex's `spawn_agent` JSON output), set `result.subagent_trajectory_ref` directly in `_build_steps`. `_load_subagents` then only locates the child files. When the entire child conversation is interleaved in the parent's stream (Copilot's `agentId` tag on every event), group by that tag and build a child trajectory from the slice.

**Compaction** — three observed shapes; check which the format uses:

1. *Inline event* (Codex `event_msg.context_compacted`, OpenCode `part.type=compaction`) — synthesise a SYSTEM step at that point, tag with `extra.is_compaction=True`.
2. *Synthetic agent role* (CodeBuddy `providerData.agent="compact"`, Claude `acompact-` sub-agent prefix) — tag the affected steps as compaction-internal so the UI can render the boundary while preserving content.
3. *External log* (Gemini `/compress` slash command in `logs.json`) — cross-reference the side file, splice a SYSTEM marker step at the timestamp.

When the format includes a summary text (Copilot `summaryContent`, CodeBuddy assistant message under `agent=compact`), preserve it verbatim — it's the only record of what context survived.

**Images** — agents surface attachments three ways. Decode each into `ContentPart(type=image, source=Base64Source(media_type, base64))`:

1. *Anthropic-style content block* (Claude `{type: "image", source: {type: "base64", data, media_type}}`).
2. *Data URL* (OpenCode/Codex `image_url: "data:image/png;base64,..."`, OpenClaw `{type: "image", data}`).
3. *File path* (Copilot `attachments[].path` pointing to system tmp / clipboard cache) — read the file, encode, inline.

When images and text co-exist on the same turn, `Step.message` becomes `list[ContentPart]`. Pure-text turns stay strings.

**Skills** — when a tool name matches the shared `SKILL_TOOL_NAMES` constant in `helpers.py`, set `ToolCall.extra.is_skill=True`. The constant currently covers `{skill, Skill, activate_skill}`; add agent-specific aliases there, not in the parser.

### Discovery and discovery-time IDs

Set `DISCOVER_GLOB`. Override `discover_session_files` only when the layout is non-trivial (stale-snapshot dedup, sub-dir carve-outs, filtered files). Override `discover_sessions` when the canonical session id isn't the filename stem (Codex extracts UUID from `state_5.sqlite`, OpenCode queries the SQLite session table, Hermes strips `session_` from snapshot stems). The contract: the id `discover_sessions` returns must match `Trajectory.session_id` produced by `parse()` for that file/row.

### File layout convention

Inside a parser file: module docstring (file layout, source priority, capability matrix); imports; module-level constants; local dataclasses; parser class (lifecycle methods only); first-tier module functions (pipeline drivers); second-tier module functions (deep helpers).

Inside the class, methods follow lifecycle: `discover_session_files` → `discover_sessions` → `get_session_files` → `parse_session_index` → `parse_skeleton_for_file` → `_decode_file` → `_extract_metadata` → `_build_steps` → `_load_subagents`.

---

## Robustness

| Situation | Action |
|---|---|
| File read failure | `_decode_file` returns `None`; `logger.warning` |
| Whole-file decode failure | `_decode_file` returns `None` |
| Single bad JSONL line | `iter_jsonl_safe` records skip, continues |
| Missing session_id | Fall back to `file_path.stem` |
| Empty steps after build | Return `[]`; BaseParser drops the trajectory |
| Orphaned tool_use / tool_result | `diagnostics.record_orphaned_call/result` |
| Unknown block / event type | Skip silently |
| Sub-agent file unreadable | Skip that child, continue siblings |
| Image payload corrupt / non-base64 | Drop the image, keep the text |
| Compaction summary missing | Still emit the marker step, leave message empty |

**Hard rules:**

- `parse(file_path)` and `_decode_file` **never raise**.
- Don't invent fields — `None` is truthful when the source doesn't carry the value.
- Don't mutate `Trajectory` after `_finalize`. Stage 3 is the only allowed mutation point.
- Use `is_error: bool`, not string prefixes.
- Catch specific exceptions, never bare `except`.
- Keep agent-specific constants in your parser file. `helpers.py` is for what's identical across parsers.
- Prefer `deterministic_id(...)` over `uuid4()` so re-parsing yields stable IDs.

---

## Testing

`tests/ingest/parsers/test_<agent>.py`, pytest with `tmp_path`. Always test through `parser.parse(path)`. Per project convention, use `print()` for diagnostic output and run with `-v -s`.

**Minimum cases:** basic parse, tool-call/result pairing, tool error, missing session_id, malformed JSONL, sub-agent linkage if applicable, image roundtrip if applicable, compaction handling if applicable, skill tool tagging if the agent has skills.

**Real-data coverage audit** (recommended): a throwaway script that runs `parser.parse` over every session in `~/.<agent>/`, counts errors, and prints ATIF-field coverage. Reading the table:

- **100%** — expected.
- **Partial** — usually expected for optional fields. Document the shortfall.
- **Partial / 0% when source has the data** — bug. Add a failing unit test, fix the parser, re-run. Coverage should only go up.

Repeat the audit after every capability change, not just at the end.

---

## Final checklist

**Capability gating**

- [ ] Every row in the [capability matrix](#capability-matrix) decided: implemented / N/A / `// TODO` with a data-collection request.
- [ ] No capability implemented against unconfirmed data.
- [ ] Deferred capabilities have a `// TODO(<format>-<capability>)` line in the parser docstring.

**Code**

- [ ] `AgentType` enum extended; `AGENT_TYPE` set on the parser.
- [ ] `LOCAL_PARSER_CLASSES` updated (if local-discoverable).
- [ ] `LOCAL_DATA_DIR` set or explicitly `None`.
- [ ] `DISCOVER_GLOB` set, or `discover_session_files` overridden.
- [ ] `discover_sessions` overridden when the canonical session id isn't the filename stem.
- [ ] `_decode_file` / `_extract_metadata` / `_build_steps` implemented.
- [ ] `_load_subagents` overridden if format has parent→child linkage.
- [ ] `is_error` set from native error signal; no `[ERROR] ` prefixes.
- [ ] Per-call sub-agent linkage in `_build_steps` if format embeds child IDs.
- [ ] Compaction surfaced (synthetic step or `extra.is_compaction`) when the format records it.
- [ ] Image content blocks decoded into `ContentPart(image)` when present.
- [ ] Skill tools tagged via `is_skill_tool` from `helpers.py`.
- [ ] No `raise` from `parse` or `_decode_file`.
- [ ] `DiagnosticsCollector` threaded; skips and orphans recorded.
- [ ] Hard-coded literals are named constants with WHY comments.
- [ ] Function order: pipeline drivers first, deep helpers later.

**Tests**

- [ ] `test_<agent>.py` covers each code path.
- [ ] Tests use `parser.parse(path)`, not `parser.parse(content)`.
- [ ] At least one negative test (malformed input).
- [ ] Sub-agent linkage tests if applicable.
- [ ] Image roundtrip test if applicable.
- [ ] Compaction handling test if applicable.
- [ ] Real-data audit run; gaps fixed or documented.

**Validation**

- [ ] `uv run pytest tests/ingest/ tests/storage/ -q` — green.
- [ ] `uv run ruff check src/ tests/` — clean.
- [ ] `CACHE_VERSION` bumped in `index_cache.py` if cached `Trajectory` shape changed (additive optional fields don't need a bump).
- [ ] `frontend/src/types.ts` updated if a new field surfaces in UI; `cd frontend && npm run build` ran.

**Docs**

- [ ] `docs/spec/parsers/<agent>.md` written, with the parser's capability table.
- [ ] [README.md](README.md) comparison matrix updated.
- [ ] Per-file docstring describes file layout, source-priority order, and the capability matrix vs Claude.
- [ ] `CHANGELOG.md` `[Unreleased]` entry.
- [ ] Throwaway verify script deleted.

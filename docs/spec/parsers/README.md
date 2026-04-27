# Parsers — overview

Each parser converts a vendor-specific session file into ATIF [`Trajectory`](../spec-models-trajectory.md) objects. They share a thin [`BaseParser`](../../../src/vibelens/ingest/parsers/base.py) ABC plus the helpers in [`parsers/helpers.py`](../../../src/vibelens/ingest/parsers/helpers.py); everything else is per-parser.

## Lifecycle

```
Discovery  →  Indexing  →  Parsing  →  Building
```

| Stage | Hook | Default |
|---|---|---|
| Discovery | `discover_session_files(data_dir)` | rglob `DISCOVER_GLOB`; `[]` if no glob |
| Discovery | `get_session_files(session_file)` | `[session_file]` |
| Indexing | `parse_session_index(data_dir)` | `None` (no fast index) |
| Indexing | `parse_skeleton_for_file(file)` | full-parse + clear steps |
| Parsing | `parse(file_path)` | provided — orchestrates 4-stage pipeline below |
| Building | `build_agent` | concrete |

## The 4-stage pipeline (single-session-per-file parsers)

`BaseParser.parse(file_path)` runs this template; subclasses fill the three abstract hooks:

```
1. _decode_file       file_path → raw  (dict / list[dict] / format-specific)
2. _extract_metadata  raw       → Trajectory header (steps stay [])
3. _build_steps       raw + traj → list[Step], paired tool calls + per-call subagent_trajectory_ref
4. _finalize          (provided) backfill timestamp / first_message / final_metrics, merge diagnostics
```

After stage 4, `_load_subagents(main, file_path)` runs to discover and parse direct sub-agents. Default returns `[]`.

| Hook | Purpose | Default |
|---|---|---|
| `_decode_file(file_path)` | Read + parse the raw format. Return `None` to skip. | abstract |
| `_extract_metadata(raw, file_path)` | Build a Trajectory with session-level fields filled and `steps=[]`. Return `None` if invalid. | abstract |
| `_build_steps(raw, traj, file_path, diagnostics)` | Build ordered Steps. May mutate `traj` (e.g. backfill `traj.agent.model_name` when it depends on per-step data). Set `subagent_trajectory_ref` on observations when the format records spawn IDs (Claude, Codex). | abstract |
| `_load_subagents(main, file_path)` | Discover + parse direct children. Override when format records parent→child linkage. | `[]` |
| `_finalize(traj, diagnostics)` | Derive `timestamp` / `first_message` / `final_metrics`; merge diagnostics into `extra`. | provided |

### Multi-session-per-file parsers

`dataclaw`, `claude_web`, and `parsed` pack many sessions into one file. They override `parse(file_path)` directly and call `_finalize(traj, diagnostics)` per record to get the same auto-derived fields.

### Trajectory schema note

`Trajectory.steps` defaults to `[]` (no `min_length=1`). This lets `_extract_metadata` return a header-only Trajectory before steps are built. Empty trajectories are filtered by `_parse_trajectory` (returns `None` when `_build_steps` produces no steps), so they never leak to consumers.

## Comparison matrix

| Parser | File layout | Index source | Streaming chunks | Sub-agents | Cost in source |
|--------|-------------|--------------|------------------|------------|----------------|
| [claude](claude.md) | `~/.claude/projects/<hash>/<sid>.jsonl` + `<sid>/subagents/agent-*.jsonl` | none — head-of-file scan | yes (merged by `message.id`) | full bidirectional, in-step linkage (agentId regex inside tool_result during `_build_steps`) | computed via pricing |
| [codex](codex.md) | `~/.codex/sessions/<date>/rollout-*.jsonl` | SQLite `state_5.sqlite` | no | full bidirectional, in-step linkage (3-way signal: `forked_from_id` / `source.subagent.parent_thread_id` / `agent_role`) | computed via pricing |
| [gemini](gemini.md) | `~/.gemini/tmp/<hash>/chats/session-*.json` | none | no | bidirectional, no per-call linkage (sibling-file scan from main; UI uses timestamp placement) | computed via pricing |
| [hermes](hermes.md) | `~/.hermes/sessions/<sid>.jsonl` + `session_<sid>.json` snapshot | `state.db` | no | bidirectional, no per-call linkage (state.db `parent_session_id` reverse query) | from `state.db` |
| [openclaw](openclaw.md) | `~/.openclaw/agents/<name>/sessions/<sid>.jsonl` | `sessions.json` | no | none observed | from `usage.cost.total` |
| [copilot](copilot.md) | `~/.copilot/session-state/<uuid>/events.jsonl` | none — directory rglob | no | metadata-only (no separate sub-agent file; `subagent.started/completed` summaries fold onto spawn ToolCall) | from `session.shutdown.modelMetrics.<m>.requests.cost` |
| [cursor](cursor.md) | `~/.cursor/chats/<workspace-hash>/<sid>/store.db` (SQLite blobs ordered by rowid); JSONL transcripts in `~/.cursor/projects/<project>/agent-transcripts/<sid>/` are partial export only | none — direct rowid walk | no | full bidirectional via sibling `subagents/<child-sid>.jsonl` files, no per-call linkage (Cursor's `Subagent` tool_use lacks an id) | computed via pricing |
| [opencode](opencode.md) | `~/.local/share/opencode/opencode.db` | `session` table | no | full bidirectional (`tool.state.metadata.sessionId` + `session.parent_id`) | from `message.data.cost` and `step-finish.cost` |
| [kilo](kilo.md) | `~/.local/share/kilo/kilo.db` (subclass of OpencodeParser) | `session` table | no | same as opencode | same as opencode |
| [kiro](kiro.md) | `~/.kiro/sessions/cli/<sid>.jsonl` + `<sid>.json` snapshot | snapshot only — no fast index | no | inline-only (`subagent` tool's report text — child Steps not persisted; we synthesise a 2-step Trajectory) | computed via pricing |
| [codebuddy](codebuddy.md) | `~/.codebuddy/projects/<hash>/<sid>.jsonl` + `<sid>/subagents/agent-*.jsonl` | none — head-of-file scan | no | full bidirectional via filename + `task_id` regex (renderer.value JSON primary) | not USD-verified — `credit` stashed on `Metrics.extra` |
| [dataclaw](dataclaw.md) | exported `conversations.jsonl`, one session per line | n/a (whole file is the index) | no | none (privacy-stripped) | not present |
| [claude_web](claude_web.md) | Settings → Export `conversations.json`, one array of sessions | n/a (whole file is the index) | no | none | not present |
| [parsed](parsed.md) | DiskStore-saved Trajectory JSON | n/a | n/a | mirror of source | mirror of source |

### Capability flags vs Claude reference

| Parser | text | reasoning | tools+obs | sub-agents | images | compaction | skills (typed) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| claude | ✓ | ✓ | ✓ | ✓ file-based + acompact | ✓ | sub-agent (`acompact-*`) | ✓ tool=`Skill` |
| codex | ✓ | ✓ | ✓ | ✓ spawn_agent | ✓ `input_image` | ✓ `context_compacted` | n/a |
| codebuddy | ✓ | ✓ | ✓ | ✓ sibling files | ✓ `image_blob_ref` | ✓ `agent="compact"` (in-stream tag) | ✓ tool=`Skill` |
| copilot | ✓ | ✗ encrypted | ✓ | ✓ `agentId` grouping | ✓ attachments | ✓ `compaction_complete` + `truncation` | n/a |
| cursor | ✓ | ✗ encrypted | ✓ | ✓ sibling files | ✓ Uint8Array hex | ✓ `isSummary` flag | ✗ system-prompt injection |
| gemini | ✓ | ✓ `thoughts[]` | ✓ | ✓ legacy file + inline | ✓ `inlineData` | ✓ `/compress` (logs.json) | ✓ tool=`activate_skill` |
| hermes | ✓ | ✗ no signal | ✓ | ✓ `parent_session_id` | ✗ no data yet | ✗ no signal | n/a |
| kilo | ✓ | ✓ | ✓ | ✓ parent_id | ✓ data URL | ✓ `compaction` part | ✓ tool=`skill` |
| kiro | ✓ | ✗ not persisted | ✓ | ✓ inline-synthesised | ✓ byte array | ✓ `kind: Compaction` | ✗ system-prompt injection |
| openclaw | ✓ | ✓ `thinking` | ✓ | ✗ no data yet | ✓ inline base64 | ✗ no signal | n/a |
| opencode | ✓ | ✓ | ✓ | ✓ parent_id | ✓ data URL | ✓ `compaction` part | ✓ tool=`skill` |

`Step.is_compaction` and `ToolCall.is_skill` are the **typed first-class flags**; cells marked with a tool name set the `is_skill=True` flag, cells with a compaction mechanism set `is_compaction=True`. `n/a` means the agent has no Skill tool. `✗ system-prompt injection` means the agent does have skills but activates them by injecting the prompt — no structural session-log signal we can read.

## Helpers all parsers can reach for

In [`parsers/helpers.py`](../../../src/vibelens/ingest/parsers/helpers.py):

- `iter_jsonl_safe(source, diagnostics)` — JSONL iterator over a file path or content string, blank-line + decode-error tolerant.
- `parse_tool_arguments(raw)` — decode an OpenAI-style JSON-string `arguments` field.
- `step_text_only`, `is_meaningful_prompt`, `truncate_first_message`, `find_first_user_text` — first-message detection that handles multimodal content correctly (skips placeholders rather than emitting `[image]` markers).
- `compute_final_metrics`, `build_diagnostics_extra` — used by `BaseParser._finalize`.
- Constant `ROLE_TO_SOURCE` — `{"user": USER, "assistant": AGENT}` mapping.

Errors are signalled structurally via `ObservationResult.is_error: bool`, not string prefixes — set the bool when constructing the `ObservationResult` from the format's native error signal.

## What "shared" means

A pattern only belongs in `helpers.py` when it is **identical across parsers** (e.g. JSONL iteration with the same blank-line/error behaviour, first-message detection that filters bracket-wrapped system strings the same way). When parsers diverge — tool-call/result pairing, content-block decomposition, project-path inference — the logic stays in the parser file, even if the *shape* looks similar at first.

## Reference: writing a new parser

A new single-session-per-file parser follows this skeleton (~40 lines for a simple format):

```python
class MyParser(BaseParser):
    AGENT_TYPE = AgentType.MY_AGENT
    LOCAL_DATA_DIR = Path.home() / ".myagent"
    DISCOVER_GLOB = "*.jsonl"  # or override discover_session_files

    def _decode_file(self, file_path):
        try:
            return list(iter_jsonl_safe(file_path))
        except OSError:
            return None

    def _extract_metadata(self, raw, file_path):
        meta = next((r for r in raw if r.get("type") == "session"), None)
        if meta is None:
            return None
        return Trajectory(
            session_id=meta["id"],
            agent=self.build_agent(model=meta.get("model")),
            project_path=meta.get("cwd"),
        )

    def _build_steps(self, raw, traj, diagnostics):
        # ... format-specific step building
        return steps

    # _load_subagents — override only if format has parent→child linkage
```

That's all. `parse(file_path)`, sub-agent dispatch, timestamp derivation, first-message extraction, final-metrics computation, and diagnostics merging all happen for free in BaseParser.

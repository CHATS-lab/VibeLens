# Writing a new agent parser

Procedural guide. For the architecture overview see [README.md](README.md); for each existing parser's specifics read its `<parser>.md` neighbour. Read this end-to-end **before** writing code — most parser bugs trace to an assumption made without inspecting actual session files.

A parser is **done** when:

1. **Fidelity** — every ATIF field the source data can populate is populated. No invented values; no silent data loss.
2. **Robustness** — every session file on disk parses without raising, including stale snapshots, duplicates, format drift, malformed lines. Failures become diagnostics, not exceptions.
3. **Shape** — sub-agents link to parents, continuations to predecessors, sessions deduplicate against the format's ground-truth index.

---

## The closed-loop process

```
0. Data collection     ← real session files on your machine
1. Format research     ← official docs + reverse-engineering
2. Design              ← write docs/spec/parsers/<agent>.md
3. Implementation      ← src/vibelens/ingest/parsers/<agent>.py
4. Testing             ← unit tests + on-disk audit
5. Validation          ← full suite + lint + docs
```

### 0 — Data collection

Install the agent locally. Run sessions covering: short, long (50+ turns, ideally with compaction), with sub-agents / spawn calls, with a tool error, resumed if applicable. Open the on-disk files. Note total count, file extensions, filename patterns, paired siblings, index files.

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
| Sub-agent linkage — none / per-call ID / DB column / sibling files? | `_load_subagents` strategy |
| Continuation — does the agent resume prior sessions? | `prev_trajectory_ref` source |
| Format drift — multiple known versions? renamed fields? | Accept old + new in parallel |

### 2 — Design (write the spec doc)

Use [openclaw.md](openclaw.md) (simple) or [hermes.md](hermes.md) (complex, multiple sources) as a template. Required sections:

- File layout (directory tree with example filenames)
- Wire format (annotated JSON/JSONL example)
- Parsing strategy (pseudo-code of pipeline)
- Sub-agent support (none / partial / full + mechanism + direction)
- Edge cases / quirks
- Tests reference

Add a row to [README.md](README.md)'s comparison matrix.

### 3-5 — Implementation, testing, validation

Sections below.

---

## Implementation

```
parse(file_path)                              ← BaseParser, no override
  └─ _parse_trajectory(file_path)
      ├─ _decode_file(path, diag)             ← stage 1, abstract
      ├─ _extract_metadata(raw, path, diag)   ← stage 2, abstract
      ├─ _build_steps(raw, traj, path, diag)  ← stage 3, abstract
      └─ _finalize(traj, diag)                ← stage 4, provided
  └─ _load_subagents(main, path)              ← optional, default []
```

Two parser shapes:

- **Single-session-per-file** (claude, codex, gemini, hermes, openclaw): implement the three abstract hooks. Don't override `parse`.
- **Multi-session-per-file** (dataclaw, claude_web, parsed): override `parse(file_path)` directly. Iterate records → build per-record `Trajectory` → call `self._finalize(traj, diagnostics)` so derived fields stay consistent.

### Hook contracts

**`_decode_file(file_path, diagnostics) → raw | None`**

Read + parse the wire format. Return `None` on read failure or empty content. Catch only specific exceptions (`OSError`, `UnicodeDecodeError`, `json.JSONDecodeError`, `sqlite3.Error`).

**`_extract_metadata(raw, file_path, diagnostics) → Trajectory | None`**

Build a Trajectory **header**: `session_id`, `agent`, `project_path`, `parent_trajectory_ref`, `prev_trajectory_ref`, `extra`. Leave `steps=[]`. **Don't** set `timestamp`, `first_message`, or `final_metrics` — `_finalize` derives them.

For sub-agent files that reuse the parent's session id (Claude's `<sid>/subagents/agent-*.jsonl`, Gemini's `kind: subagent`), use a **synthetic id** (filename stem) and put the parent's id in `parent_trajectory_ref`. The synthetic id avoids index collisions.

`Trajectory.session_id` validates against path traversal (no `/`, `\`, `..`, null bytes).

**`_build_steps(raw, traj, file_path, diagnostics) → list[Step]`**

Walk raw data, build ordered Steps. May mutate `traj` when fields legitimately depend on per-step content (e.g. gemini backfills `traj.agent.model_name` from the most recent step model).

Set `ObservationResult.is_error` from the format's **native** error signal (`tool_result.is_error`, `msg.isError`, `status == "error"`). Never bake `[ERROR] ` into content.

When the format embeds child IDs inside tool_results (Claude's `agentId: <hex>`, Codex's `spawn_agent` JSON output), set `result.subagent_trajectory_ref` directly here. `_load_subagents` then only **locates** files.

**Copied-context detection** (Claude's `--resume`): compare each entry's sessionId against the **in-file canonical** sessionId from `_scan_session_metadata`, **not** `traj.session_id`. Sub-agent files use a synthetic `traj.session_id` (filename stem) but their entries carry the parent's id; comparing wrong blanks `first_message`.

**`_load_subagents(main, file_path) → list[Trajectory]`**

Override when the format records parent→child linkage. Discover children, parse each via `self._parse_trajectory(child_path)`, set `parent_trajectory_ref`. Return `[]` if no sub-agents.

### Reference template (single-session)

```python
class MyAgentParser(BaseParser):
    AGENT_TYPE = AgentType.MY_AGENT
    LOCAL_DATA_DIR = Path.home() / ".myagent"
    DISCOVER_GLOB = "sessions/*.jsonl"

    def _decode_file(self, file_path, diagnostics):
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", file_path, exc)
            return None
        entries = list(iter_jsonl_safe(content, diagnostics=diagnostics))
        return entries or None

    def _extract_metadata(self, raw, file_path, diagnostics):
        meta = next((e for e in raw if e.get("type") == "session"), None)
        return Trajectory(
            session_id=(meta or {}).get("id") or file_path.stem,
            agent=self.build_agent(model_name=(meta or {}).get("model")),
            project_path=(meta or {}).get("cwd"),
        )

    def _build_steps(self, raw, traj, file_path, diagnostics):
        ...  # format-specific
```

### Discovery

Set `DISCOVER_GLOB` (`*.jsonl`, `session-*.json`, etc.). Override `discover_session_files` only when the layout is non-trivial: stale-snapshot dedup (hermes), sub-dir carve-outs (claude's `subagents/`), filtered files (openclaw's reset/clean files).

### Required helpers

| Helper | When |
|---|---|
| `iter_jsonl_safe(source, diagnostics)` | Every JSONL parser. Path or content. |
| `parse_tool_arguments(raw)` | OpenAI-style JSON-string `arguments` |
| `Metrics.from_tokens(input=, output=, cache_read=, cache_write=, cost_usd=)` | Anthropic token convention (`prompt_tokens = input + cached`) |
| `ROLE_TO_SOURCE` | role → `StepSource` for "user"/"assistant" |
| `normalize_model_name(raw) or raw` from `vibelens.llm` | **Always** with the `or raw` fallback so unknown models don't drop |
| `deterministic_id(prefix, *parts)` from `vibelens.utils` | Stable IDs when source omits one. Prefer over `uuid4()` |
| `coerce_to_string`, `normalize_timestamp`, `parse_iso_timestamp` from `vibelens.utils` | Coercion |

### File layout convention

```
1. Module docstring (file layout, source priority, format quirks)
2. Imports (stdlib, third-party, vibelens)
3. Module-level constants
4. Local dataclasses / NamedTuples
5. Parser class (lifecycle methods only — keep helpers out)
6. First-tier module functions: pipeline drivers, per-stage builders
7. Second-tier module functions: deep helpers
```

Inside the class, methods follow lifecycle: `discover_session_files` → `get_session_files` → `parse_session_index` → `parse_skeleton_for_file` → `_decode_file` → `_extract_metadata` → `_build_steps` → `_load_subagents`.

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

**Hard rules:**

- `parse(file_path)` and `_decode_file` **never raise**. Failure modes return `None` / `[]`. Exceptions bypass diagnostics and look like real breakage.
- Don't invent fields — `None` is truthful when the source doesn't carry the value.
- Don't mutate `Trajectory` after `_finalize`. Stage 3 is the only allowed mutation point (for backfills like `agent.model_name`).
- Use `is_error: bool`, not string prefixes.
- Catch specific exceptions, never bare `except`.
- Keep agent-specific constants in your parser file. `helpers.py` is for what's identical across parsers.
- Prefer `deterministic_id(...)` over `uuid4()` so re-parsing yields stable IDs.

---

## Code style

Project [`CLAUDE.md`](../../../CLAUDE.md) global rules apply. Parser-specific:

- **Constants:** `ALL_CAPS`, module-private with `_` prefix, comment **why** if non-obvious (don't comment what `re.compile(...)` does).
- **Docstrings:** class 2–3 lines; public method one line; internal helper one line if non-obvious else nothing. WHY not WHAT.
- **Function length:** ~30 lines max; extract a helper when longer.
- **Naming:** variables nouns, functions verbs, booleans questions, no abbreviations unless universal.
- **Imports:** grouped (stdlib, third-party, vibelens). No `from __future__`.
- **Comments:** WHY only. Don't narrate the change, don't reference the PR, don't restate what well-named code already says.
- **Markdown paragraphs:** one source line per paragraph in this doc and any spec doc you write — no soft-wrapping inside a paragraph.

---

## Testing

`tests/ingest/parsers/test_<agent>.py`, pytest with `tmp_path`. Always test through `parser.parse(path)`:

```python
def test_basic(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text("...JSONL...\n", encoding="utf-8")
    trajs = _parser.parse(path)
    assert len(trajs) == 1
```

Per project convention, use `print()` for diagnostic output and run with `-v -s`.

**Minimum cases:** basic parse, tool-call/result pairing, tool error (`result.is_error is True`, content verbatim), missing session_id, malformed JSONL (`parse(corrupt) == []`), sub-agent linkage if applicable.

**Real-data coverage audit** (recommended): a throwaway script that runs `parser.parse` over every session in `~/.<agent>/`, counts errors, and prints ATIF-field coverage. Reading the table:

- **100%** — expected.
- **Partial** — usually expected for optional fields (`parent_trajectory_ref` only on sub-agents). Document the shortfall.
- **Partial / 0% when source has the data** — bug. Add a failing unit test, fix the parser, re-run. Coverage should only go up.

---

## Final checklist

**Code**

- [ ] `AgentType` enum extended; `AGENT_TYPE` set on the parser.
- [ ] `LOCAL_PARSER_CLASSES` updated (if local-discoverable).
- [ ] `LOCAL_DATA_DIR` set or explicitly `None`.
- [ ] `DISCOVER_GLOB` set, or `discover_session_files` overridden.
- [ ] `_decode_file` / `_extract_metadata` / `_build_steps` implemented.
- [ ] `_load_subagents` overridden if format has parent→child linkage.
- [ ] `is_error` set from native error signal; no `[ERROR] ` prefixes.
- [ ] Per-call sub-agent linkage in `_build_steps` if format embeds child IDs.
- [ ] No `raise` from `parse` or `_decode_file`.
- [ ] `DiagnosticsCollector` threaded; skips and orphans recorded.
- [ ] Hard-coded literals are named constants with WHY comments.
- [ ] Function order: pipeline drivers first, deep helpers later.

**Tests**

- [ ] `test_<agent>.py` covers each code path.
- [ ] Tests use `parser.parse(path)`, not `parser.parse(content)`.
- [ ] At least one negative test (malformed input).
- [ ] Sub-agent linkage tests if applicable.
- [ ] Real-data audit run; gaps fixed or documented.

**Validation**

- [ ] `uv run pytest tests/ingest/ tests/storage/ -q` — green.
- [ ] `uv run ruff check src/ tests/` — clean.
- [ ] `CACHE_VERSION` bumped in `index_cache.py` if cached `Trajectory` shape changed (additive optional fields don't need a bump).
- [ ] `frontend/src/types.ts` updated if a new field surfaces in UI; `cd frontend && npm run build` ran.

**Docs**

- [ ] `docs/spec/parsers/<agent>.md` written.
- [ ] [README.md](README.md) comparison matrix updated.
- [ ] Per-file docstring describes file layout + source-priority order.
- [ ] `CHANGELOG.md` `[Unreleased]` entry.
- [ ] Throwaway verify script deleted.

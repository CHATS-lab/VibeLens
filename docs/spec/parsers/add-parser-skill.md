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

## Design principles

These distinguish a parser that holds up over years of format drift from one that merely passes its first test run. Every item below is something a previous parser got wrong before we tightened it up.

**Trust the source, then the index, then yourself.** Most agents write multiple views of the same session: a raw stream (JSONL), a periodic snapshot (JSON), an authoritative index (SQLite, JSON manifest). These views disagree. Pick an explicit priority order in the file-level docstring. The narrowest, most authoritative source wins: if `state.db` lists 16 sessions and the directory has 39 files, the db is right. If a JSONL records a model change mid-session and the snapshot only the final model, trust the per-turn value for `Step.model_name` and the snapshot for `Agent.model_name`.

**Populate, don't invent.** Every field you set is a claim about the source data. Hardcoding `agent.base_url = "https://api.anthropic.com"` for every Claude session leaks a constant into thousands of trajectories. If deleting the line that sets a field doesn't lose information that was actually in the source, delete the line. `None` is a truthful answer when the data isn't there.

**Idempotency.** Parsing the same file twice yields equal `Trajectory` objects. Sort `discover_session_files` results so test fixtures agree across OSes. Prefer `deterministic_id` over `uuid4()`. Don't iterate `set()` where emission order matters; sort or use an `OrderedDict`. Dashboards that cache by `session_id` depend on this — non-determinism makes cache invalidation impossible.

**`extra` is a pressure valve, not a dumping ground.** If a field is useful enough to surface in the UI for this agent, it goes in `Trajectory.extra` or `Step.extra` with a named key (`platform`, `chat_id`, `finish_reason`). If it's not useful, don't capture it — a noisy `extra` dict is worse than a missing field because downstream consumers start relying on it and then you can never delete it. Each key should be either universally meaningful across agents or clearly namespaced (`hermes_`, `codex_`).

**Format drift is inevitable.** Agents version their formats: Gemini added `projectHash`, Claude renamed `Agent` to `Task`, Codex added new tool-call types mid-year. Two defences: accept old and new field names side by side (Claude does `{"Agent", "Task"}`); skip unknown block / event types silently. A parser that crashes on the first unfamiliar type blocks ingestion the day the agent ships a new feature.

**Diagnostics > exceptions.** `parse()` should never let an exception escape. Every skippable problem (bad line, orphaned tool result, missing timestamp) gets recorded on the `DiagnosticsCollector` so it surfaces in the UI as a quality warning. Exceptions bypass diagnostics and look like real breakage.

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

### Reference template (multi-session-per-file)

When one file contains many sessions (export dumps, JSONL-of-conversations), override `parse(file_path)` and call `_finalize` per record:

```python
class MyExportParser(BaseParser):
    AGENT_TYPE = AgentType.MY_EXPORT
    LOCAL_DATA_DIR = None  # manual import only

    def parse(self, file_path: Path) -> list[Trajectory]:
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cannot parse %s: %s", file_path, exc)
            return []
        diagnostics = DiagnosticsCollector()
        out: list[Trajectory] = []
        for record in raw if isinstance(raw, list) else [raw]:
            traj = self._record_to_trajectory(record)
            if traj is not None and traj.steps:
                out.append(self._finalize(traj, diagnostics))
        return out

    def _record_to_trajectory(self, record: dict) -> Trajectory | None:
        ...  # build header + steps; return None if invalid
```

### Multi-source data: collect once in stage 1

When the source format spans multiple files (a primary jsonl plus paired snapshot, plus state.db row, plus a sessions index — see hermes), don't re-hit disk in every stage. Have `_decode_file` build a small dataclass that carries everything decoded once:

```python
@dataclass
class _MyAgentRaw:
    session_id: str
    records: list[dict] | None     # JSONL records
    snapshot: dict | None          # paired snapshot
    db_row: dict | None            # state.db row
    origin: dict | None            # sessions.json index entry
```

Later stages destructure this in O(1) without re-reading. Hermes uses exactly this shape; cuts the per-parse I/O by ~3x compared to letting each stage open the db separately.

### Skipping a re-decode in `_load_subagents`

When `_load_subagents` already parsed a candidate sibling file's JSON (to filter by some header field like `kind: subagent`), don't pass the file path to `self._parse_trajectory(...)` because that re-decodes. Add a tiny shortcut that runs stages 2 → 3 → finalize on the already-parsed dict:

```python
def _parse_decoded(self, data: dict, file_path: Path) -> Trajectory | None:
    diagnostics = DiagnosticsCollector()
    traj = self._extract_metadata(data, file_path, diagnostics)
    if traj is None:
        return None
    traj.steps = self._build_steps(data, traj, file_path, diagnostics)
    if not traj.steps:
        return None
    return self._finalize(traj, diagnostics)
```

Gemini does this — siblings get one read instead of two.

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

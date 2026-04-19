# Writing a new agent parser

## Objective

**A parser turns one agent's session dump into ATIF `Trajectory` objects that the rest of VibeLens can treat identically to every other agent's.** Everything downstream — the dashboard, friction analysis, skill recommendations, donation flows, demo mode — reads `Trajectory` only. It has no idea whether the session came from Claude Code, Codex, Gemini, Hermes, OpenClaw, or a new agent you're adding today.

That means the parser is the single point where agent-specific reality meets the shared model. Everything the parser gets right flows through the whole pipeline; everything it gets wrong either corrupts analytics silently or forces every downstream consumer to special-case your agent, which defeats the point of a shared model.

A parser is "done" when it satisfies all three:

1. **Fidelity.** Every ATIF field the source data can populate is populated. No field is invented from constants that weren't in the source. No field drops data silently on the way through.
2. **Robustness.** Every session file on disk parses without raising, including stale snapshots, duplicated entries, format drift between agent versions, malformed lines. Parse failures are recorded as diagnostics, not exceptions.
3. **Shape.** Cross-session identifiers resolve correctly: sub-agents link to their parents, continuations link to their predecessors, sessions are deduplicated against whatever ground-truth index the agent maintains.

Bias of this doc: it was written right after adding the Hermes parser and refactoring the existing five. The pitfalls named below are the ones that actually tripped us.

This doc walks the three phases: **design → code → verify**.

## The contract

Every parser subclasses `BaseParser` (`src/vibelens/ingest/parsers/base.py`) and produces a list of `Trajectory` objects. The contract is small:

| Method | Required? | Purpose |
| --- | --- | --- |
| `AGENT_TYPE` (class attr) | yes | Your `AgentType` enum value. |
| `LOCAL_DATA_DIR` (class attr) | optional | `Path.home() / ".your-agent"` if the agent keeps sessions on disk locally. Set to `None` for import-only formats. |
| `parse(content, source_path)` | yes | Convert one file's raw content into `list[Trajectory]`. Almost always returns a one-element list. Multi-trajectory cases: sub-agent spawn maps, web exports that pack many conversations. |
| `discover_session_files(data_dir)` | if local | Return the list of session file paths under `data_dir`. Include the dedup/exclusion logic specific to your format (stale snapshots, index files, resource forks, etc.). |
| `get_session_files(session_file)` | only for multi-file sessions | Return every file belonging to a session (main + subagents, paired snapshot, etc.). |
| `parse_session_index(data_dir)` | optional optimisation | Return skeleton trajectories from a fast index (sqlite, history.jsonl) to avoid full parsing during list views. Return `None` if the index can't produce skeletons rich enough to be useful (e.g. no `first_message` cached). |

Helpers provided by `BaseParser` that you should reuse rather than reinvent:

- `iter_jsonl_safe(source, diagnostics=None)` accepts either a `Path` (stream a file) or `str` (content already in memory). One helper for every JSONL-like format.
- `build_agent(version=..., model=...)` wires up `Agent.name` from `AGENT_TYPE`.
- `build_diagnostics_extra(collector)` produces the `extra.diagnostics` dict when the collector recorded parse-quality issues.
- `assemble_trajectory(...)` auto-computes `first_message` and `final_metrics` from steps; you pass `session_id`, `agent`, `steps`, and optional `project_path` / `prev_trajectory_ref` / `parent_trajectory_ref` / `extra`.
- `find_first_user_text(steps)` filters slash commands, system tags, and skill outputs out when picking the preview message.
- `truncate_first_message(text)` caps preview text at `MAX_FIRST_MESSAGE_LENGTH` (200 chars).

Helpers in nearby modules that are almost always the right choice:

- `vibelens.llm.normalize_model_name(raw)` turns raw model strings (with provider prefixes, date suffixes, dotted Anthropic versions, etc.) into the canonical key used by the pricing catalog. Use this rather than writing a local regex.

## What makes a parser *good*

Mechanical correctness is the floor. These subtleties separate a parser that merely works from one that holds up as the format evolves and the data gets weird.

### Trust the source, then the index, then yourself

Most agents write multiple views of the same session: a raw stream (JSONL), a periodic snapshot (JSON), and sometimes an authoritative index (SQLite, JSON manifest). These views disagree. A good parser picks an explicit priority order and writes it down.

Rule of thumb: **the narrowest, most authoritative source wins.** If `state.db` lists exactly 16 real sessions and the `sessions/` directory has 39 files, the db is right — the other 23 are stale snapshots from interrupted runs. If the JSONL records a model change mid-session but the snapshot holds only the final model, trust the per-turn value for `Step.model_name` and the snapshot value for `Agent.model_name`. Never let both fight in the same code path.

This ordering should be visible in the parser's top-of-file docstring, not buried inside a helper.

### Populate, don't invent

Every field you set is a claim about the source data. A parser that hardcodes `base_url = "https://api.anthropic.com"` for every Claude session isn't populating a field — it's leaking a constant into 3,000+ trajectories, where it survives long enough to confuse a cost audit.

The test for every field: *if I delete the line that sets this field, does any trajectory lose information that was actually in the source file?* If no, delete the line. `None` is a truthful answer when the data isn't there.

The one admitted exception is `Agent.name`, which always equals `AGENT_TYPE.value` by construction — that's identity, not invention.

### Preserve raw, provide canonical

When you canonicalise data (model names, project paths, timestamps), keep an escape hatch for the raw form. Use `normalize_model_name(raw) or raw`, not `normalize_model_name(raw)`: when a new model lands before the catalog learns about it, the UI should still display the raw name rather than going blank. Same for timestamps: if parsing fails, drop the field but don't crash.

### Idempotency and determinism

Parsing the same file twice must yield equal `Trajectory` objects. That means: don't call `uuid4()` unless you have no stable id to fall back to, and when you do, derive it from the content (e.g. the filename stem) so repeat parses don't churn. Don't let `discover_session_files` return files in filesystem order; sort, so test fixtures on different OSes agree. Don't iterate over `set()` when emission order matters; use tuples or sort first.

Dashboards that cache by `session_id` depend on this. A non-deterministic parser makes cache invalidation impossible.

### Dedup at the right layer

Duplicates can appear in three places: same session emitted by multiple files (hermes snapshots vs jsonl), same record emitted multiple times within one file (claude compaction replay), same step id emitted twice inside the parser (streaming consolidation bugs). Each needs its own fix:

- **File-level dedup** lives in `discover_session_files`. Pick a single primary file per `session_id`.
- **Record-level dedup** lives at the top of `parse()` or inside `_build_steps`. Drop repeated entries by `uuid` before building steps.
- **Step-level dedup** is already enforced by the Trajectory validator. If it fires, your step-id assignment is wrong — fix the cause, don't silence the check.

### Ordering and timestamps

Steps should be in chronological order. When the source format has per-record timestamps, sort on them. When it doesn't (hermes snapshots), rely on the order of records in the file and say so explicitly — don't pretend the timestamps are accurate by synthesising them from session start + index.

Missing timestamps are fine (`Step.timestamp = None`). Wrong timestamps are much worse: downstream duration-based analytics will quietly produce meaningless numbers.

### `extra` is a pressure valve, not a dumping ground

If a field is useful enough to surface in the UI for this one agent, it goes in `Trajectory.extra` or `Step.extra` with a named key (`platform`, `chat_id`, `finish_reason`). If it's not useful, don't capture it — a noisy `extra` dict is worse than a missing field because downstream consumers start relying on it, and then you can never delete it.

Each extra key should be either (a) universally meaningful across agents and documented somewhere central, or (b) genuinely agent-specific and clearly namespaced (`hermes_`, `codex_`).

### Format drift is inevitable

Agents version their formats. Gemini added `projectHash`, Claude renamed `Agent` to `Task`, Codex added new tool-call types mid-year. Every parser needs two defences:

1. **Accept the old and the new** side by side. Hermes does this for tokens (`input_tokens` and legacy `prompt_tokens`); Claude does it for subagent tool names (`{"Agent", "Task"}`).
2. **Skip unknown block/event types silently**, don't raise. A parser that crashes on the first unfamiliar block type blocks ingestion the day the agent ships a new feature.

### Diagnostics > exceptions

`parse()` should never let an exception escape unless the input is so malformed that returning `[]` would be wrong. Every skippable problem (bad line, orphaned tool result, missing timestamp) gets recorded on the `DiagnosticsCollector` so it surfaces in the UI as a quality warning. Exceptions bypass diagnostics and look like real breakage; save them for genuine breakage.

## Phase 1 — Design

Before writing any code, answer these questions by *inspecting actual session files on disk*. Parser bugs usually trace back to an assumption made without reading the format.

### 1.1 Where does the agent put sessions?

Pick one or two real sessions and open them. Document in the file-level docstring exactly what directory tree the parser reads. For example:

```
~/.your-agent/
  sessions/<session-id>.jsonl    # one file per session
  sessions/index.json            # optional: fast listing
  state.db                       # optional: sqlite with tokens/cost
```

### 1.2 What is the on-disk schema?

For each file type, note:

- **File format.** JSONL? Single JSON object? SQLite table? Plain text?
- **Role tagging.** How does the agent distinguish user / assistant / tool-result messages? Is the role on the line itself or nested under a `message` field?
- **Tool calls.** Are they content blocks inside the assistant message (Anthropic-style) or separate lines linked by a call id (OpenAI-style)?
- **Tool results.** Same question — inline, in the *next* user message, or as their own records with a `role: "tool"` marker?
- **Token usage.** Per-message? Per-session? Both? In what field names?
- **Cost.** Present at all? If so, already computed or do we need the pricing catalog?
- **Timestamps.** Per-record? Session-level only? What format (ISO 8601, unix seconds, unix ms)?

### 1.3 Which fields does ATIF need?

Map each ATIF field to the source record that populates it. The goal is to populate every field that the source data supports, and to *not* hallucinate fields that aren't in the source.

| ATIF field | Typical source |
| --- | --- |
| `Trajectory.session_id` | filename stem, header record, or SQLite id |
| `Trajectory.project_path` | `cwd` field, or synthesised URI for chat-surface agents |
| `Trajectory.timestamp` | first user/assistant record's timestamp |
| `Trajectory.first_message` | computed by `assemble_trajectory`, don't set manually |
| `Trajectory.prev_trajectory_ref` | `last_session_id` or equivalent continuation field |
| `Trajectory.parent_trajectory_ref` | only for sub-agent sessions with a spawning parent |
| `Trajectory.final_metrics` | computed by `assemble_trajectory` from step metrics |
| `Trajectory.extra` | format-specific: base_url, system_prompt, platform, chat origin |
| `Agent.name` | always your `AGENT_TYPE.value` |
| `Agent.version` | agent CLI version, if the session records it |
| `Agent.model_name` | session-level model, canonicalised via `llm.normalize_model_name` |
| `Agent.tool_definitions` | tool schema list, if the session persists it |
| `Step.source` | `USER` / `AGENT` / `SYSTEM` |
| `Step.message` | plain text body |
| `Step.reasoning_content` | thinking / reasoning text, if the format carries it |
| `Step.timestamp` | per-record timestamp |
| `Step.model_name` | per-turn model, if the format varies mid-session |
| `Step.metrics` | per-step prompt/completion/cache tokens |
| `Step.tool_calls` | list of `ToolCall` on the assistant turn |
| `Step.observation` | `Observation` with `ObservationResult` per tool call |

If your answer to any row is "not in the data", leave it `None`. Don't invent values — a correctly-None field is better than a wrong one.

### 1.4 What are the edge cases?

Always walk through these before coding:

- **Sub-agents.** Does the agent spawn child sessions? If yes, are they separate files (claude) or separate rows in a table (codex)? Build a parent→child map so `parent_trajectory_ref` is populated.
- **Continuations.** Does the agent resume prior sessions under a new id? If yes, capture the prior id as `prev_trajectory_ref`.
- **Duplicate entries.** Some formats (claude after compaction replay) re-emit the same line. Dedup by the closest thing to a stable id (`uuid`, `message.id`) before assembling steps, or the Trajectory model will reject the result with a duplicate-step-id validation error.
- **Stale files.** CLI agents sometimes leave partial snapshots from interrupted sessions. Filter them out in `discover_session_files` using whatever ground-truth source is available (an sqlite table, a pairing rule).
- **System-injected content.** Agents inject XML-wrapped context into `role: "user"` messages. Maintain a module-level tuple of the specific prefixes *your* agent emits (see `_CODEX_SYSTEM_TAG_PREFIXES` in `codex.py` for an example) and reclassify those steps as `StepSource.SYSTEM`. Don't add them to `base.py` — that module's prefix list is the cross-agent fallback for demo mode only.

### 1.5 Write the design spec

Put the design in `docs/superpowers/specs/YYYY-MM-DD-<agent>-parser-design.md`. The spec should answer: the data sources (1.1–1.2), the ATIF coverage table (1.3), the edge cases (1.4), the source-priority order (see "Trust the source, then the index, then yourself" above), and the module layout you plan to use.

## Phase 2 — Code

### 2.1 File layout

Start with one flat module: `src/vibelens/ingest/parsers/<agent>.py`. Split into a package only when a file grows past ~800 lines *and* has clearly separable subsystems. Splitting prematurely imposes boundaries the code doesn't naturally have.

Every parser file opens with a docstring that describes the on-disk format in concrete terms, including one representative filename and the source-priority order:

```python
"""<Agent> session parser.

Session storage (~/.<agent>/):
  sessions/<id>.jsonl            # stream (preferred when present)
  sessions/<id>.json             # snapshot (fallback)
  state.db                       # sqlite, authoritative for listing

Source priority: state.db for existence and tokens/cost; jsonl for
per-record timestamps and content; snapshot for session-level
metadata (base_url, system_prompt) that the stream omits.

One Trajectory per session_id.
"""
```

### 2.2 Constants first, logic second

Every literal with semantic meaning gets a module-level `ALL_CAPS` constant with a one-line *why* comment above it:

```python
# Rewrite Anthropic dotted versions (claude-opus-4.7) before prefix
# match so the pricing catalog lookup succeeds.
_ANTHROPIC_DOT_VERSION_RE = re.compile(r"^(claude-[a-z]+-\d+)\.(\d+)")
```

Leave inline only the field names of the external schema itself (`entry["role"]`, `msg["content"]`). Naming those adds noise.

Constants go in one block at the top of the file, right after imports. Scattering them next to the function that uses them makes the file harder to scan and invites duplication — several parsers ended up with two copies of the same regex before we tightened this up.

### 2.3 Loop bodies should use the shared helpers

Every parser that reads JSONL should call `BaseParser.iter_jsonl_safe(source, diagnostics=...)`. If you find yourself writing `for line in content.splitlines(): json.loads(...)`, stop and use the helper.

Every parser that produces a `Trajectory` should go through `self.assemble_trajectory(...)` so `first_message` and `final_metrics` stay consistent across formats.

Every model name that will be used for pricing lookup should go through `vibelens.llm.normalize_model_name(raw) or raw` (the `or raw` fallback keeps the raw string around when the model isn't in the catalog yet).

### 2.4 Diagnostics

Create a `DiagnosticsCollector` at the start of `parse()` and thread it through the helpers. Record:

- `record_skip("reason")` when a JSONL line fails to decode.
- `record_orphaned_call(tool_use_id)` when a tool_use has no matching tool_result.
- `record_orphaned_result(tool_use_id)` when a tool_result has no matching tool_use.
- `record_tool_call()` / `record_tool_result()` for denominator counts.

Use `self.build_diagnostics_extra(collector)` to get the `{"diagnostics": ...}` dict and merge it into `Trajectory.extra` only when issues were recorded.

### 2.5 When a function grows past ~30 lines

Extract a helper. The main parser method should read like a short script: scan metadata, build steps, enrich, assemble. Big in-line transformations belong in helpers with single clear names (`_build_steps_from_jsonl`, `_collect_tool_results`, `_parse_metrics`).

## Phase 3 — Verify

Unit tests pin specific behaviours; real-data audits surface the fields your fixtures forgot to cover. You need both.

### 3.1 Unit tests

For every parser, add `tests/ingest/parsers/test_<agent>.py` covering:

- Tiny synthetic JSONL / JSON fixtures exercising each code path: user-only turn, assistant with tool call, tool result pairing, system-tagged user reclassification, duplicate-line dedup, snapshot fallback, orphaned tool result.
- One test per non-obvious helper: model normalisation, session id extraction, project path derivation.
- Negative tests: `test_all_invalid_json_returns_empty`, malformed tool result, missing session id.

The VibeLens convention (see project `CLAUDE.md`) is that tests log detailed output with `print()` so manual runs can verify the trajectory shape, not just the boolean assertion. Run with `uv run pytest tests/ingest/parsers/test_<agent>.py -v -s`.

### 3.2 Coverage audit against real data

Synthetic fixtures exercise the code paths you thought of; real sessions exercise the ones you didn't. Before declaring the parser done, run it across your full `~/.<agent>/` tree and audit ATIF-field coverage.

A throwaway script does the job:

```python
# scripts/verify_<agent>.py  (delete after landing the parser)
import vibelens.models.trajectories  # noqa: F401  (defeat a circular import)
from pathlib import Path
from vibelens.ingest.parsers import YourParser

parser = YourParser()
files = parser.discover_session_files(Path.home() / ".your-agent")
trajectories = []
errors = []
for f in files:
    try:
        trajectories.extend(parser.parse_file(f))
    except Exception as exc:
        errors.append((f, exc))
print(f"{len(files)} files, {len(trajectories)} trajectories, {len(errors)} errors")

fields = [
    ("project_path", lambda t: bool(t.project_path)),
    ("agent.model_name", lambda t: bool(t.agent.model_name)),
    ("final_metrics.total_prompt_tokens",
     lambda t: t.final_metrics and t.final_metrics.total_prompt_tokens > 0),
    # ... etc
]
for name, fn in fields:
    hits = sum(1 for t in trajectories if fn(t))
    pct = 100 * hits / len(trajectories) if trajectories else 0.0
    print(f"{name:40s} {pct:5.1f}% ({hits}/{len(trajectories)})")
```

### 3.3 Reading the coverage table

Every row is one of three things. A good parser knows which is which for every field *before* declaring done:

- **100% — expected.** The field is present in every source record and the parser is extracting it. Nothing to do.
- **Partial (e.g. 60%) — expected.** The field is structurally optional (`parent_trajectory_ref` only exists for sub-agents, `prev_trajectory_ref` only for resumed sessions). Document the expected shortfall in the design spec and move on.
- **Partial or 0% — bug.** The source has the data but the parser isn't reading it. Add a reproducing unit test with a tiny synthetic fixture, fix the parser, re-run.

The third category is where most real bugs hide. The parser "works" (no exceptions), tests pass (they didn't cover the case), but 40% of sessions lose a field the data clearly contains. Coverage auditing is the only tool that surfaces this.

### 3.4 The verification loop

1. Run the verify script, note each field with <100% coverage.
2. For each gap you classify as a bug, write a failing unit test that reproduces it with a tiny synthetic fixture.
3. Fix the parser. Run the unit test until it passes.
4. Re-run the verify script. Coverage should only go up, never down. If a 100% field dropped, the fix introduced a regression — investigate before committing.
5. Stop when every remaining gap has a documented reason.

### 3.5 Final checklist before landing

- `uv run ruff check src/ tests/` — clean.
- `uv run pytest tests/ingest/` — all green.
- File-level docstring describes the on-disk format, the source-priority order, and the enrichment sources.
- Every hard-coded literal with meaning is a named constant with a "why" comment.
- Every ATIF field the source supports is populated; every field that isn't has a documented reason.
- `__init__.py` re-exports the new parser class.
- `discovery.py`'s `_PARSERS_BY_TYPE` has the new entry.
- `LOCAL_PARSER_CLASSES` in `parsers/__init__.py` includes the new class (only if `LOCAL_DATA_DIR` is set).
- `scripts/verify_<agent>.py` deleted.
- CHANGELOG `[Unreleased]` has an entry describing the new parser.

## Common pitfalls

Every item below is something a previous parser got wrong.

- **Hallucinated fields.** Setting `agent.base_url = "https://..."` when the data doesn't say so leaks a constant into every trajectory and makes downstream analytics lie. If the source doesn't record it, leave it `None`.
- **Agent-specific logic in base.** Moving a Claude-only XML tag set into `base.py` looks like reuse; in practice it bloats the module every other parser depends on. Keep agent-specific constants with their parser; `base.py` holds only logic *every* parser shares.
- **Parallel helpers instead of one.** If you find yourself writing a second variant of an existing base helper ("but mine takes a string, not a Path"), extend the helper instead. See the unified `iter_jsonl_safe` that accepts both.
- **Trying to split a module you don't understand yet.** Break a file into a package only after the code has told you where the seams are. Premature splits lock in boundaries that don't match reality and make it harder to refactor later.
- **Silent data loss on unknown models.** `normalize_model_name` returns `None` for unknown models so the catalog knows to give up. A parser that stores that `None` drops the raw model string and the UI shows nothing. Use `normalize_model_name(raw) or raw`.
- **Mutable-default arguments.** `def f(x=[]):` bites every Python codebase eventually; parsers that accumulate state across calls are a particular magnet for it. Use `None` defaults and initialise inside.
- **Forgetting the circular-import guard in ad-hoc scripts.** If you hit `ImportError: cannot import name 'BaseParser' from partially initialized module`, add `import vibelens.models.trajectories  # noqa: F401` before importing anything from `vibelens.ingest`. Running via `uv run pytest` avoids this because pytest imports the test modules in the right order.
- **Exceptions escaping `parse()`.** The ingest pipeline treats an exception as a hard failure and drops the whole file. If your parser can tolerate a bad line, record it on the `DiagnosticsCollector` and keep going.
- **Letting filesystem ordering into trajectories.** `Path.iterdir()` and `rglob` are order-unspecified on some filesystems. Sort before returning from `discover_session_files` or downstream caches will churn between runs.

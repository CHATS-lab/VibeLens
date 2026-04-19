# Writing a new agent parser

VibeLens's ingest layer turns vendor-specific session dumps into a single
shared trajectory model (ATIF). A parser is the small adapter that does
the translation for one agent. This doc walks through the three phases
every new parser goes through: **design → code → verify**.

## The contract

Every parser subclasses `BaseParser` (`src/vibelens/ingest/parsers/base.py`)
and produces a list of `Trajectory` objects. The contract is small:

| Method | Required? | Purpose |
| --- | --- | --- |
| `AGENT_TYPE` (class attr) | yes | Your `AgentType` enum value. |
| `LOCAL_DATA_DIR` (class attr) | optional | `Path.home() / ".your-agent"` if the agent keeps sessions on disk locally. Set to `None` for import-only formats. |
| `parse(content, source_path)` | yes | Convert one file's raw content into `list[Trajectory]`. Almost always returns a one-element list. Multi-trajectory cases: sub-agent spawn maps, web exports that pack many conversations. |
| `discover_session_files(data_dir)` | if local | Return the list of session file paths under `data_dir`. Include the dedup/exclusion logic specific to your format (stale snapshots, index files, resource forks, etc.). |
| `get_session_files(session_file)` | only for multi-file sessions | Return every file belonging to a session (main + subagents, paired snapshot, etc.). |
| `parse_session_index(data_dir)` | optional optimisation | Return skeleton trajectories from a fast index (sqlite, history.jsonl) to avoid full parsing during list views. Return `None` if the index can't produce skeletons rich enough to be useful (e.g. no `first_message` cached). |

Helpers provided by `BaseParser` that you should reuse rather than
reinvent:

- `iter_jsonl_safe(source, diagnostics=None)` accepts either a `Path`
  (stream a file) or `str` (content already in memory). One helper for
  every JSONL-like format.
- `build_agent(version=..., model=...)` wires up `Agent.name` from
  `AGENT_TYPE`.
- `build_diagnostics_extra(collector)` produces the `extra.diagnostics`
  dict when the collector recorded parse-quality issues.
- `assemble_trajectory(...)` auto-computes `first_message` and
  `final_metrics` from steps; you pass `session_id`, `agent`, `steps`,
  and optional `project_path` / `prev_trajectory_ref` /
  `parent_trajectory_ref` / `extra`.
- `find_first_user_text(steps)` filters slash commands, system tags,
  and skill outputs out when picking the preview message.
- `truncate_first_message(text)` caps preview text at
  `MAX_FIRST_MESSAGE_LENGTH` (200 chars).

Helpers in nearby modules that are almost always the right choice:

- `vibelens.llm.normalize_model_name(raw)` turns raw model strings
  (with provider prefixes, date suffixes, dotted Anthropic versions,
  etc.) into the canonical key used by the pricing catalog. Use this
  rather than writing a local regex.

## Phase 1 — Design

Before writing any code, answer these questions by *inspecting actual
session files on disk*. Parser bugs usually trace back to an assumption
made without reading the format.

### 1.1 Where does the agent put sessions?

Pick one or two real sessions and open them. Document in the file-level
docstring exactly what directory tree the parser reads. For example:

```
~/.your-agent/
  sessions/<session-id>.jsonl    # one file per session
  sessions/index.json            # optional: fast listing
  state.db                       # optional: sqlite with tokens/cost
```

### 1.2 What is the on-disk schema?

For each file type, note:

- **File format.** JSONL? Single JSON object? SQLite table? Plain text?
- **Role tagging.** How does the agent distinguish user / assistant /
  tool-result messages? Is the role on the line itself or nested under
  a `message` field?
- **Tool calls.** Are they content blocks inside the assistant message
  (Anthropic-style) or separate lines linked by a call id
  (OpenAI-style)?
- **Tool results.** Same question — inline, in the *next* user message,
  or as their own records with a `role: "tool"` marker?
- **Token usage.** Per-message? Per-session? Both? In what field names?
- **Cost.** Present at all? If so, already computed or do we need the
  pricing catalog?
- **Timestamps.** Per-record? Session-level only? What format
  (ISO 8601, unix seconds, unix ms)?

### 1.3 Which fields does ATIF need?

Map each ATIF field to the source record that populates it. The goal is
to populate every field that the source data supports, and to *not*
hallucinate fields that aren't in the source.

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

If your answer to any row is "not in the data", leave it `None`. Don't
invent values — a correctly-None field is better than a wrong one.

### 1.4 What are the edge cases?

Always walk through these before coding:

- **Sub-agents.** Does the agent spawn child sessions? If yes, are they
  separate files (claude) or separate rows in a table (codex)? Build a
  parent→child map so `parent_trajectory_ref` is populated.
- **Continuations.** Does the agent resume prior sessions under a new
  id? If yes, capture the prior id as `prev_trajectory_ref`.
- **Duplicate entries.** Some formats (claude after compaction replay)
  re-emit the same line. Dedup by the closest thing to a stable id
  (`uuid`, `message.id`) before assembling steps, or the Trajectory
  model will reject the result with a duplicate-step-id validation
  error.
- **Stale files.** CLI agents sometimes leave partial snapshots from
  interrupted sessions. Filter them out in `discover_session_files`
  using whatever ground-truth source is available (an sqlite table,
  a pairing rule).
- **System-injected content.** Agents inject XML-wrapped context into
  `role: "user"` messages. Maintain a module-level tuple of the
  specific prefixes *your* agent emits (see `_CODEX_SYSTEM_TAG_PREFIXES`
  in `codex.py` for an example) and reclassify those steps as
  `StepSource.SYSTEM`. Don't add them to `base.py` — that module's
  prefix list is the cross-agent fallback for demo mode only.

### 1.5 Write the design spec

Put the design in
`docs/superpowers/specs/YYYY-MM-DD-<agent>-parser-design.md`. The spec
should answer: the data sources (1.1–1.2), the ATIF coverage table
(1.3), the edge cases (1.4), and the module layout you plan to use.

## Phase 2 — Code

### 2.1 File layout

Start with one flat module: `src/vibelens/ingest/parsers/<agent>.py`.
Split into a package only when a file grows past ~800 lines *and* has
clearly separable subsystems. Splitting prematurely makes boundaries up
that the code doesn't naturally have.

Every parser file opens with a docstring that describes the on-disk
format in concrete terms, including one representative filename:

```python
"""<Agent> session parser.

Session storage (~/.<agent>/):
  sessions/<id>.jsonl            # stream (preferred when present)
  sessions/<id>.json             # snapshot (fallback)
  state.db                       # sqlite, authoritative for listing

One Trajectory per session_id. Tokens and cost live in state.db.
"""
```

### 2.2 Constants first, logic second

Every literal with semantic meaning gets a module-level `ALL_CAPS`
constant with a one-line *why* comment above it:

```python
# Rewrite Anthropic dotted versions (claude-opus-4.7) before prefix
# match so the catalog lookup succeeds.
_ANTHROPIC_DOT_VERSION_RE = re.compile(...)
```

Leave inline only the field names of the external schema itself
(`entry["role"]`, `msg["content"]`). Naming those adds noise.

Constants go in one block at the top of the file, right after imports.
Scattering them next to the function that uses them makes the file
harder to scan and invites duplication.

### 2.3 Loop bodies should use the shared helpers

Every parser that reads JSONL should call
`BaseParser.iter_jsonl_safe(source, diagnostics=...)`. If you find
yourself writing `for line in content.splitlines(): json.loads(...)`,
stop and use the helper.

Every parser that produces a `Trajectory` should go through
`self.assemble_trajectory(...)` so `first_message` and `final_metrics`
stay consistent across formats.

Every model name that will be used for pricing lookup should go through
`vibelens.llm.normalize_model_name(raw) or raw` (the `or raw` fallback
keeps the raw string around when the model isn't in the catalog yet).

### 2.4 Diagnostics

Create a `DiagnosticsCollector` at the start of `parse()` and thread it
through the helpers. Record:

- `record_skip("reason")` when a JSONL line fails to decode.
- `record_orphaned_call(tool_use_id)` when a tool_use has no matching
  tool_result.
- `record_orphaned_result(tool_use_id)` when a tool_result has no
  matching tool_use.
- `record_tool_call()` / `record_tool_result()` for denominator counts.

Use `self.build_diagnostics_extra(collector)` to get the
`{"diagnostics": ...}` dict and merge it into `Trajectory.extra` only
when issues were recorded.

### 2.5 When a function grows past ~30 lines

Extract a helper. The main parser method should read like a short
script: scan metadata, build steps, enrich, assemble. Big in-line
transformations belong in helpers with single clear names
(`_build_steps_from_jsonl`, `_collect_tool_results`, `_parse_metrics`).

## Phase 3 — Verify

Tests catch specific behaviours; real data catches missing fields.

### 3.1 Unit tests

For every parser, add `tests/ingest/parsers/test_<agent>.py` covering:

- Tiny synthetic JSONL / JSON fixtures exercising each code path:
  user-only turn, assistant with tool call, tool result pairing,
  system-tagged user reclassification, duplicate-line dedup, snapshot
  fallback, orphaned tool result.
- One test per non-obvious helper: model normalisation, session id
  extraction, project path derivation.
- Negative tests: `test_all_invalid_json_returns_empty`, malformed
  tool result, missing session id.

Run them with `uv run pytest tests/ingest/parsers/test_<agent>.py -v`.

### 3.2 Coverage audit against real data

Synthetic fixtures can't predict what the real format looks like after
edge cases accumulate. Before declaring the parser done, run it across
your full `~/.<agent>/` tree and audit ATIF-field coverage.

A throwaway script does the job:

```python
# scripts/verify_<agent>.py  (delete after)
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

# For each ATIF field, print coverage %
fields = [
    ("project_path", lambda t: bool(t.project_path)),
    ("agent.model_name", lambda t: bool(t.agent.model_name)),
    ("final_metrics.total_prompt_tokens",
     lambda t: t.final_metrics and t.final_metrics.total_prompt_tokens > 0),
    # ... etc
]
for name, fn in fields:
    hits = sum(1 for t in trajectories if fn(t))
    print(f"{name:40s} {100*hits/len(trajectories):5.1f}% ({hits}/{len(trajectories)})")
```

For every field below 100%, ask: *should the source data have this?*
If yes, it's a bug — add a reproducing unit test and fix the parser.
If no (e.g. `parent_trajectory_ref` only exists for sub-agents),
document the expected shortfall in the design spec.

### 3.3 The verification loop

The pattern that consistently works:

1. Run the verify script, note each field with <100% coverage.
2. For each gap you think is a bug, write a failing unit test that
   reproduces it with a tiny synthetic fixture.
3. Fix the parser. Run the unit test until it passes.
4. Re-run the verify script. Coverage should only go up, never down.
5. Stop when every remaining gap has a documented reason.

### 3.4 Final checklist before landing

- `uv run ruff check src/ tests/` — clean.
- `uv run pytest tests/ingest/` — all green.
- File-level docstring describes the on-disk format and the
  enrichment sources.
- Every hard-coded literal with meaning is a named constant with a
  "why" comment.
- Every ATIF field the source supports is populated; every field that
  isn't has a documented reason.
- `__init__.py` re-exports the new parser class.
- `discovery.py`'s `_PARSERS_BY_TYPE` has the new entry.
- `LOCAL_PARSER_CLASSES` in `parsers/__init__.py` includes the new
  class (only if `LOCAL_DATA_DIR` is set).
- CHANGELOG `[Unreleased]` has an entry describing the new parser.

## Common pitfalls

- **Hallucinated fields.** Setting `agent.base_url = "https://..."`
  when the data doesn't say so leaks a constant into every trajectory
  and makes downstream analytics lie. If the source doesn't record it,
  leave it `None`.
- **Agent-specific logic in base.** Moving a Claude-only XML tag set
  into `base.py` looks like reuse; in practice it bloats the module
  every other parser depends on. Keep agent-specific constants with
  their parser.
- **Parallel helpers instead of one.** If you find yourself writing a
  second variant of an existing base helper ("but mine takes a string,
  not a Path"), extend the helper instead. See the unified
  `iter_jsonl_safe` that accepts both.
- **Trying to split a module you don't understand yet.** Break a file
  into a package only after the code has told you where the seams are.
  Premature splits lock in boundaries that don't match reality.
- **Silent data loss on unknown models.** `normalize_model_name`
  returns `None` for unknown models so the catalog knows to give up.
  A parser that stores that `None` drops the raw model string and the
  UI shows nothing. Use `normalize_model_name(raw) or raw`.
- **Forgetting the circular-import guard in ad-hoc scripts.** If you
  hit `ImportError: cannot import name 'BaseParser' from partially
  initialized module`, add
  `import vibelens.models.trajectories  # noqa: F401` before importing
  anything from `vibelens.ingest`. Running via `uv run pytest` avoids
  this because pytest imports the test modules in the right order.

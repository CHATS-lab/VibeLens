# Friction Analysis

Two-phase LLM pipeline that detects user dissatisfaction in agent sessions, classifies it by type and severity, and emits actionable mitigations.

## Motivation

A coding agent can read 20 files, retry a tool 3 times, and burn through tokens — but if the user is satisfied with the outcome, none of that is "friction". Friction is exclusively a *user-side* signal: the user corrects the agent, re-explains the task, takes over manually, criticises output quality, or abandons the session.

That definition is what makes friction analysis tractable: instead of trying to score the agent's behaviour from the outside, we look only at evidence the user produced. Repeated failures alone are not friction; repeated failures *plus* the user expressing impatience or correcting the approach are.

Friction analysis sits next to the personalization modes (recommendation, creation, evolution): all four share the same context-extraction layer, the same job tracker, and the same persistence shape. They differ in what they emit. Friction emits an event log + mitigations; personalization emits installable extensions.

## Architecture

```
POST /api/analysis/friction
        │
        ▼
Phase 0 — Context extraction
   load trajectories → SessionContext per session → batch by token budget
        │
        ▼
Phase 1 — Per-batch inference (asyncio.gather)
   each batch: render prompt, call LLM, parse JSON output
        │
        ▼
Phase 2 — Merge + synthesis
   resolve step IDs → compute per-event cost from spans →
   validate refs → synthesis LLM call (title, summary, cross-batch patterns,
   top mitigations) → persist
        │
        ▼
FrictionAnalysisResult
   (in FrictionStore + in-memory TTL cache)
```

## Modules

| Path | Role |
|---|---|
| `services/friction/analysis.py` | Pipeline orchestration, LLM calls, merge, validation, caching. |
| `services/friction/store.py` | Persist, load, list, delete. |
| `services/context/...` | Context extraction + batching. Shared with personalization. |
| `services/job_tracker.py` | Background-task lifecycle. |
| `models/analysis/friction.py` | Domain models (`FrictionEvent`, `FrictionAnalysisResult`, `Mitigation`, `TypeSummary`, …). |
| `models/step_ref.py` | `StepRef` — step-range locator (start step + optional end step). |
| `api/friction.py` | HTTP surface, mounted at `/api/analysis/friction`. |
| `llm/prompts/friction_analysis.py` | System prompt + per-batch / synthesis Jinja2 templates. |

## Friction taxonomy

Ten types, each requiring user dissatisfaction evidence: `misunderstood-intent`, `wrong-approach`, `repeated-failure`, `quality-rejection`, `scope-violation`, `instruction-violation`, `stale-context`, `destructive-action`, `slow-progress`, `abandoned-task`.

Severity is on a 1–5 scale that reflects user impact rather than internal cost: 1 is a small correction the agent fixes immediately; 5 is task abandonment.

## Data shape

A `FrictionEvent` carries:

- a kebab-case `friction_type` from the taxonomy,
- a `span_ref: StepRef` locating the steps where the friction occurs,
- a 1–5 `severity`,
- short `user_intention` and `friction_detail` strings (what the user wanted, why the agent fell short),
- a list of `Mitigation` objects (each is `(action, content)` — a label and the exact text to apply, e.g. a CLAUDE.md edit),
- an `estimated_cost` derived from the step-span metrics.

A `FrictionAnalysisResult` aggregates events by type, picks the top mitigations across the batch, runs the synthesis call to produce a title, narrative summary, and cross-batch patterns, and records the model and total inference cost.

## API

`/api/analysis/friction/...` (one router, same endpoint shape as the personalization modes):

| Method | Path | Purpose |
|---|---|---|
| `POST /` | start an analysis (returns `job_id`) |
| `POST /estimate` | pre-flight token / cost estimate |
| `GET /jobs/{job_id}` | poll job status |
| `POST /jobs/{job_id}/cancel` | cancel a running job |
| `GET /history` | list persisted analyses |
| `GET /{analysis_id}` | load full result |
| `DELETE /{analysis_id}` | delete an analysis |

Analysis runs as a background `asyncio.Task` under the shared job tracker; the frontend polls.

## Pipeline details

### Phase 0 — Context extraction

For each requested session, load the trajectories, run them through `SummaryExtractor` (or a similar context level), and remap step UUIDs to compact zero-based indices so the LLM sees `[step_id=0]` style markers it can reference cheaply. The resolver later reverses the mapping.

### Phase 1 — Per-batch inference

Sessions are grouped into token-budgeted batches by the shared batcher. Each batch runs as one LLM call; all batches run concurrently via `asyncio.gather`. Per-batch constraints (max events, minimum severity, same-type merging) are enforced inside the prompt so partial / oversized outputs degrade rather than break.

### Phase 2 — Merge + synthesis

1. Resolve every reference's compact index back to the real step UUID; drop refs that fail to resolve.
2. Compute a per-event cost from the span: token totals + duration from the contained step metrics.
3. Sort by severity, deduplicate near-identical mitigations, aggregate per-type statistics.
4. Synthesis LLM call produces title, narrative summary, cross-batch patterns, and the top-N mitigations.

### Cost estimation

`POST /estimate` runs the loading and batching steps without any LLM calls and produces a token / cost range. The estimate accounts for both the per-batch and the synthesis calls.

## Persistence

```
{friction_dir}/
├── meta.jsonl            append-only metadata
└── {analysis_id}.json    full FrictionAnalysisResult
```

In-memory TTL cache fronts the store; entries are keyed by a hash of the sorted session-id list so a re-run of the same analysis hits cache.

## Edge behaviour

| Case | Behaviour |
|---|---|
| Empty session list | 400 |
| All sessions missing | 400 |
| LLM returns no events | synthesis skipped, empty result |
| LLM output truncated | best-effort JSON repair; partial events preserved |
| Invalid step ref | event dropped, warning logged |
| Severity outside 1–5 | clamped |
| Demo / test mode | mock results with real step IDs |
| No inference backend configured | 503 |
| Backend timeout | 502 |

# Friction Analysis

Two-phase LLM pipeline that identifies user dissatisfaction events in agent sessions, classifies them by type and severity, and generates actionable mitigations.

## Purpose

Friction is user dissatisfaction. If the user moves on without complaint, there is no friction -- even if the agent read 20 files or retried 3 times. Friction is detected only from user signals: corrections, re-explanations, manual takeover, criticism, abandonment.

The analysis pipeline: (1) extracts and compresses session context, (2) batches sessions for concurrent LLM inference, (3) merges batch results and runs a synthesis LLM call for a cohesive report, (4) persists results for history browsing.

## Architecture

```
POST /analysis/friction
         |
         v
Phase 0: Context Extraction
  Load trajectories -> extract context per session -> remap IDs (UUID -> 0-indexed)
         |
         v
Phase 1: Batched Inference
  build_batches() -> asyncio.gather(_infer_batch() per batch) -> FrictionLLMBatchOutput[]
         |
         v
Phase 2: Merge + Synthesis
  Resolve IDs -> merge events -> validate refs -> synthesis LLM call -> persist
         |
         v
FrictionAnalysisResult (persisted to FrictionStore, cached in-memory)
```

## Key Files

| File | Role |
|------|------|
| `services/friction/analysis.py` | Main orchestrator: pipeline, LLM calls, merge, validation, caching |
| `services/friction/store.py` | `FrictionStore`: save/load/list/delete (JSONL + JSON files) |
| `services/friction/mock.py` | Mock results for demo/test mode |
| `services/context_extraction.py` | `SessionContext`, `IdMapping`, `remap_session_ids` |
| `services/session_batcher.py` | Token-budgeted batch packing |
| `models/analysis/friction.py` | Domain models (FrictionEvent, Mitigation, etc.) |
| `models/analysis/step_ref.py` | `StepRef` -- step range locator |
| `schemas/friction.py` | `FrictionEstimateResponse`, `FrictionMeta` |
| `api/friction.py` | 5+ endpoints (analyze, estimate, history, load, delete, jobs) |
| `llm/prompts/friction_analysis.py` | Prompt definitions and Jinja2 templates |
| `llm/cost_estimator.py` | Pre-flight cost estimation |

## Friction Type Taxonomy

10 types, each requiring user dissatisfaction evidence:

| Type | Description |
|------|-------------|
| `misunderstood-intent` | Agent didn't understand what user wanted |
| `wrong-approach` | Agent chose a method the user disagrees with |
| `repeated-failure` | Agent keeps failing despite corrections |
| `quality-rejection` | User rejects agent output quality |
| `scope-violation` | Agent does more or less than asked |
| `instruction-violation` | Agent ignores explicit rules |
| `stale-context` | Agent forgets after context compaction |
| `destructive-action` | Agent makes unwanted changes |
| `slow-progress` | User grows impatient |
| `abandoned-task` | User gives up on the task |

### Severity Scale

| Level | Definition |
|-------|------------|
| 1 Minor | Small correction, agent fixes immediately |
| 2 Low | User re-explains once, agent succeeds on second attempt |
| 3 Moderate | Multiple corrections or visible frustration |
| 4 High | User takes over manually or reverts work |
| 5 Critical | User abandons task or session becomes unproductive |

## Data Models

### FrictionEvent (Server-Enriched)

| Field | Type | Description |
|-------|------|-------------|
| `friction_id` | `str` | Server-generated UUID |
| `friction_type` | `str` | Kebab-case type from taxonomy |
| `span_ref` | `StepRef` | Step span where friction occurs |
| `severity` | `int` | 1-5 (user impact) |
| `user_intention` | `str` | What user wanted (max 15 words) |
| `friction_detail` | `str` | Why agent failed (max 20 words) |
| `mitigations` | `list[Mitigation]` | Structured action + content pairs |
| `estimated_cost` | `FrictionCost` | Computed from step span metrics |
| `project_path` | `str | None` | From session metadata |

### FrictionAnalysisResult

| Field | Type | Description |
|-------|------|-------------|
| `analysis_id` | `str | None` | Set on persistence |
| `title` | `str | None` | Synthesis-generated title (max 10 words) |
| `summary` | `str` | Narrative overview (max 80 words) |
| `events` | `list[FrictionEvent]` | All events, sorted by severity descending |
| `type_summary` | `list[TypeSummary]` | Per-type aggregated statistics |
| `top_mitigations` | `list[Mitigation]` | 0-3 highest-impact mitigations |
| `cross_batch_patterns` | `list[str]` | Cross-session insights from synthesis |
| `model` | `str` | Model identifier |
| `cost_usd` | `float | None` | Total inference cost |
| `session_ids` | `list[str]` | Sessions analyzed |
| `batch_count` | `int` | Number of batches used |

### Mitigation

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | Human-readable label (e.g., "Update CLAUDE.md code style section") |
| `content` | `str` | Exact text to apply (max 30 words) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analysis/friction` | Start friction analysis (returns job_id) |
| `GET` | `/analysis/friction/jobs/{job_id}` | Poll job status |
| `POST` | `/analysis/friction/jobs/{job_id}/cancel` | Cancel running job |
| `POST` | `/analysis/friction/estimate` | Pre-flight cost estimate |
| `GET` | `/analysis/friction/history` | List persisted analyses |
| `GET` | `/analysis/friction/{analysis_id}` | Load full result |
| `DELETE` | `/analysis/friction/{analysis_id}` | Delete result |

Analysis runs as a background `asyncio.Task` via the shared job tracker. Frontend polls at 3s intervals.

## Pipeline Details

### Phase 0: Context Extraction

For each session: load trajectories, compress steps (truncate user messages, keep only agent steps with tool calls/errors, skip system steps), remap UUIDs to 0-based integers for compact prompts.

### Phase 1: Concurrent Batch Inference

Sessions grouped into token-budgeted batches (see [session batcher spec](spec-session-batcher.md)). All batches run in parallel via `asyncio.gather()`. Each batch: render prompts, call `backend.generate()`, parse JSON output.

Constraints per batch: at most 5 events, min severity 2, merge same-type events.

### Phase 2: Merge and Synthesis

1. Resolve synthetic IDs back to real UUIDs
2. Compute per-event cost from step span (timestamps + token metrics)
3. Validate step references (drop invalid)
4. Sort by severity, deduplicate mitigations, aggregate type statistics
5. Synthesis LLM call produces: title, summary, type descriptions, cross-session patterns, top mitigations

## Cost Estimation

`POST /analysis/friction/estimate` runs the same loading/batching pipeline without LLM calls to produce a cost range.

Per batch: `input_tokens = system_prompt + batch_digest`, output estimated at 25-60% of max output tokens. Synthesis cost added as fixed estimate.

## Persistence

`FrictionStore` uses disk-based storage:

```
{friction_dir}/
+-- meta.jsonl              <- Append-only, one FrictionMeta per line
+-- {analysis_id}.json      <- Full FrictionAnalysisResult per analysis
```

In-memory cache with 1-hour TTL, keyed by SHA-256 of sorted session IDs.

## Configuration

| Constant | Value | Purpose |
|----------|-------|---------|
| `FRICTION_OUTPUT_TOKENS` | 8,192 | Max output tokens per batch |
| `SYNTHESIS_OUTPUT_TOKENS` | 20,000 | Max output tokens for synthesis |
| `MAX_TOP_MITIGATIONS` | 3 | Final mitigations limit |
| `MAX_EVENTS_FOR_SYNTHESIS` | 7 | Top events passed to synthesis |
| `CACHE_TTL_SECONDS` | 3,600 | In-memory cache TTL |

## Edge Cases

| Case | Behavior |
|------|----------|
| Empty session_ids | 400 error |
| All sessions not found | 400 error |
| LLM returns no events | Synthesis skipped, empty result |
| LLM output truncated | JSON repair attempted; partial results preserved |
| Invalid step_id in event | Event dropped, warning logged |
| Severity out of [1, 5] | Clamped |
| Demo/test mode | Mock results with real step IDs |
| No inference backend | 503 error |
| Backend timeout | 502 error |

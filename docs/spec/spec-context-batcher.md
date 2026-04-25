# Session Batcher

Token-budgeted batch packing for concurrent LLM calls. Groups extracted session contexts into batches that respect token limits, preserve chain integrity, and maximize same-project affinity.

## Purpose

LLM context windows are finite. Sending all sessions in one prompt exceeds model limits; sending one per call wastes cost and time. The batcher solves a bin-packing problem with domain constraints: linked sessions stay together, same-project sessions share a batch, and no batch exceeds the token budget. Used by friction analysis, skill analysis, and any future batch-inference module.

## Key Files

| File | Role |
|------|------|
| `services/session_batcher.py` | `build_batches()` entry point, chain building, splitting, packing |
| `services/context_extraction.py` | `SessionContext` model (batcher input) |
| `llm/tokenizer.py` | Token counting via tiktoken `cl100k_base` |
| `tests/services/test_session_batcher.py` | 16 test cases |

## Pipeline

```
SessionContext[]
       |
       v
+--------------+
| build_chains |  Merge linked sessions into atomic chains
+------+-------+
       |
       v
+---------------------+
| split_oversized     |  Break chains exceeding budget
+------+--------------+
       |
       v
+--------------+
| pack_batches |  Affinity-based greedy bin packing
+------+-------+
       |
       v
  SessionBatch[]
```

Public entry point: `build_batches(session_contexts, max_batch_tokens)`.

## Data Models

### SessionContext (Input)

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Session identifier |
| `project_path` | `str | None` | Working directory |
| `context_text` | `str` | Compressed session text with `[step_id=N]` markers |
| `char_count` | `int` | Length of `context_text` |
| `last_trajectory_ref_id` | `str | None` | Predecessor session (backward link) |
| `continued_trajectory_ref_id` | `str | None` | Successor session (forward link) |
| `timestamp` | `datetime | None` | Session start time |

### SessionBatch (Output)

| Field | Type | Description |
|-------|------|-------------|
| `batch_id` | `str` | Sequential label (`batch-001`, `batch-002`, ...) |
| `session_contexts` | `list[SessionContext]` | Contexts in this batch |
| `total_tokens` | `int` | Sum of token counts |
| `project_paths` | `set[str]` | Distinct projects in batch |

## Phase 1: Chain Building

Sessions linked via `last_trajectory_ref_id` / `continued_trajectory_ref_id` form atomic chains that must stay together. Algorithm: index by ID, sort by timestamp, walk backward/forward to find chain boundaries.

```
Session A (continued_ref -> B)    Session B (last_ref -> A)    Session C (standalone)
        Chain 1: [A, B]                                        Chain 2: [C]
```

## Phase 2: Oversized Splitting

Chains exceeding the budget are handled in order:

1. Multi-session chain -> split into individual session chains
2. Individual session exceeding budget -> split at `[step_id=]` boundaries in `context_text`
3. Each part gets the session header prepended and a suffixed ID (`{session_id}__part1`)
4. If no step boundaries found -> stays as one oversized batch (warning logged)

## Phase 3: Affinity Packing

Greedy bin-packing with affinity-ranked candidate selection:

1. Sort all chains by (project, timestamp)
2. Pop first unplaced chain as "seed" for a new batch
3. Rank remaining chains by affinity: same-project first, then time-nearest
4. Greedily add highest-affinity chains that fit within budget
5. Emit batch, repeat

Affinity sort key: `(is_cross_project, time_distance_seconds)`

Priority order: chain integrity (atomic) > same-project, time-nearest > cross-project, time-nearest.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `max_batch_tokens` | `80,000` | Token budget per batch (from `Settings`) |

Budget leaves room for system prompt + output within typical 128K-200K context windows.

## Performance

| Scenario | Before (naive) | After (affinity packing) |
|----------|---------------|------------------------|
| 12 sessions | 9 batches | 2 batches |
| 17 sessions | 8 batches | 3 batches |
| Avg utilization | ~25% | ~85% |

## Edge Cases

| Case | Behavior |
|------|----------|
| Empty input | Returns `[]` |
| Single session | One batch |
| Session exceeds budget (with steps) | Split at step boundaries |
| Session exceeds budget (no steps) | One oversized batch (warning) |
| Multi-session chain exceeds budget | Chain broken into individual sessions first |
| All sessions same project | Packed by time proximity |
| Mixed projects | Same-project affinity wins over time proximity |

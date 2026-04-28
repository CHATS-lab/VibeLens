# Session Batcher

Token-budgeted batch packing for concurrent LLM calls.

## Motivation

Friction analysis, skill analysis, and any future "look at many sessions at once" feature face the same problem: an LLM context window is finite, but a user has dozens or hundreds of sessions. Sending them one at a time multiplies cost and round-trip latency; sending all of them at once exceeds the model's input limit.

The batcher is the bin-packing layer between context extraction and inference. It groups extracted `SessionContext`s into batches that:

- never exceed `max_batch_tokens`,
- keep linked sessions (continued conversations) together so chain semantics survive,
- prefer same-project neighbours so the LLM sees thematically coherent batches,
- otherwise pack greedily by time-nearest neighbours.

It lives in `vibelens.context.batcher` and is callable as `build_batches(contexts, max_batch_tokens) -> list[SessionContextBatch]`.

## Pipeline

```
SessionContext[]
       |
       v
  split oversized        (one session larger than the budget?
       |                  split it at step boundaries)
       v
  group into chains      (sessions linked via prev/next_trajectory_ref_id
       |                  become atomic chains)
       v
  enforce chain budget   (chain larger than budget? break apart)
       |
       v
  affinity pack          (greedy bin-packing on chains with
       |                  same-project + time-nearest tie-breaks)
       v
SessionContextBatch[]
```

## Inputs and outputs

### `SessionContext`

The extractor produces these. The batcher only reads four things off each context:

- `session_id`, `project_path`, `created_at` — identity and ordering.
- `context_text` — the compressed text that goes to the LLM. Token count is computed from this via `tiktoken cl100k_base`.
- `prev_trajectory_ref_id` / `next_trajectory_ref_id` — backward/forward links between continued sessions. The batcher walks these to assemble chains. (`parent_trajectory_ref_id` on a `Trajectory` exists for sub-agent lineage but is not relevant here — the batcher operates above sub-agent boundaries.)

### `SessionContextBatch`

Output container. Carries `contexts`, `total_tokens`, `project_paths` (set), and a sequential `batch_id` ("batch-001", …). The batch object is also LLM-call-aware: it resolves `StepRef`s against its members and exposes `all_trajectories` for downstream consumers.

## Phase details

### Oversized split

If a single session's `context_text` exceeds the budget, the batcher splits at step boundaries (`\n\n[step_id=…`) into multiple parts, each prepended with the session header and given a suffixed id (`{session_id}__part1`, `__part2`, …). Sessions with no parseable boundaries stay as one over-budget batch, with a warning logged — better to send too much to one call than to drop content silently.

### Chain building

Sessions linked through `prev_trajectory_ref_id` / `next_trajectory_ref_id` form a chain. The whole chain is treated as one atomic packing unit so a continued conversation never gets split across batches. Standalone sessions become single-element chains.

### Chain budget enforcement

When a multi-session chain still exceeds the budget after grouping, it's broken back into individual sessions and re-treated as standalone units. Chain integrity is a preference, not a hard constraint we'd violate the budget for.

### Affinity packing

Greedy first-fit, ranked by affinity. Seed each batch with the next unplaced chain in `(project, created_at)` order; rank remaining chains by `(is_cross_project, time_distance)` and pull in the highest-affinity chains that still fit. Result: batches dominated by a single project, then a single time window — exactly the structure the LLM benefits from.

## Configuration

`max_batch_tokens` is provided by callers, typically from `Settings`. The default (~80k) leaves headroom for the system prompt and output within current 128–200k context windows.

## Edge cases

| Case | Behaviour |
|---|---|
| Empty input | `[]` |
| Single session under budget | One batch |
| Session over budget with step boundaries | Split into parts |
| Session over budget without step boundaries | One over-budget batch, warning logged |
| Multi-session chain over budget | Chain broken; sessions packed as standalone |
| Mixed projects | Same-project affinity wins over time proximity |

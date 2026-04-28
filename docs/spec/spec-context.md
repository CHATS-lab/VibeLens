# Context

The layer that compresses raw `Trajectory` data into LLM-ready text.

## Motivation

LLM-powered services (friction analysis, skill analysis, future analysers) all face the same problem: a `Trajectory` is a structured Python object full of tool calls, observations, and metrics, but the model needs prose. Three things follow:

- The compression has to be **lossy in a service-specific way**. Skill analysis cares about user intent and patterns of tool use; friction analysis cares about repeated failures and dead ends; the dashboard cares only about identity and metrics. Different services need different levels of detail.
- The compression has to **preserve cross-references**. Step IDs become `[step_id=N]` markers in the text so the LLM can later cite back into the trajectory. The model also needs continuation / sub-agent linkage to be visible.
- The compression has to **stay below a token budget**. The output feeds the batcher, which packs results into LLM context windows.

The `vibelens.context` package is that layer. It lives between `models/trajectories` and the analysis services, so an analyser never reasons about parsed agent data directly — it asks for a `SessionContext` at the right level of detail and packs the results.

## Module shape

```
context/
├── base.py        ContextExtractor ABC + index tracking
├── extractors.py  MetadataExtractor, SummaryExtractor, DetailExtractor
├── params.py      ContextParams + presets (concise / medium / detail)
├── formatter.py   shared formatting helpers + budget constants
├── batcher.py     build_batches(contexts, max_batch_tokens)
└── sampler.py     sample_contexts(...) — bounded random selection
```

Dependency direction: `context/` reads from `models/` and `utils/` only (and `llm/tokenizer` from the batcher). It never depends on `services/` or `deps.py`, which keeps it usable from any analyser without circular imports.

## The three extractors

All extractors take a list of `Trajectory` objects and return a `SessionContext`. They share a metadata block (session id, timestamps, project path, step counts, tool summary, continuation refs) and differ only in how they format individual steps:

- **`MetadataExtractor`** — header only. No per-step text. Used when an analyser needs identity and aggregates but no content.
- **`SummaryExtractor`** — short per-step lines, leverages compaction-agent summaries when the trajectory contains them. Compaction sub-agents are themselves a pre-compressed view of earlier history, so passing their text through verbatim is both cheaper and higher-fidelity than re-summarising.
- **`DetailExtractor`** — full content per step (user message, agent reply, tool calls, observations) up to the configured truncation limits.

A subclass overrides `format_step()` only. The ABC handles header construction, compaction handling, and the index map (so step UUIDs ↔ small integers ↔ `[step_id=N]` markers stay consistent across the output and resolvers).

## ContextParams

`ContextParams` is the per-call knob set: max characters per user message, per agent message, per tool input/output, etc. Presets cover the common cases (`PRESET_CONCISE`, `PRESET_MEDIUM`, `PRESET_DETAIL`); a service can pass a custom `ContextParams` if it needs different limits.

## Step-ref round-trip

The format used by extractors (`[step_id=N]` with N a small integer) is what the LLM is asked to reference in its output. `SessionContext.resolve_step_ref` and `SessionContextBatch.resolve_step_ref` close the round-trip:

- LLM emits `step_id=12` → resolver maps `12` to the real step UUID.
- LLM emits a UUID directly → resolver validates it exists in the trajectory and passes it through.
- LLM emits a numeric string for `session_id` (the batch index instead of the real session UUID) → resolver falls back to the batch's index lookup.

Anything that can't be resolved is dropped with a warning rather than failing the whole batch — analysis output should degrade, not crash, on a hallucinated reference.

## Batcher and sampler

- `build_batches(contexts, max_batch_tokens)` is the bin-packer. See [`spec-context-batcher.md`](spec-context-batcher.md).
- `sample_contexts(contexts, n)` is the bounded-random selector for analyses that work on a sample rather than the full corpus.

Both stay parameterless on the configuration side — the caller passes the budget / sample size explicitly. This keeps the context module callable from tests and tooling without `get_settings()` on the import path.

## Out of scope

- LLM invocation — `context/` produces text and batches, never makes a call. Inference lives in `llm/` and is driven by the analysis services.
- Service-specific assembly (e.g. how friction analysis stitches a system prompt around the batched contexts). That logic stays in the service layer.

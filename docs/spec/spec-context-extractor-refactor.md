# Context Extractor Refactor Design

Refactor `services/context_extraction.py`, `services/context_params.py`, and `services/session_batcher.py` into a dedicated `src/vibelens/context/` module with a polymorphic extractor hierarchy.

## Problem

Context extraction is a reusable data transformation layer (trajectories to LLM-ready text) currently living flat in `services/`. Three distinct analysis scenarios require different compression levels, but the current code handles this via a single function with parameterized truncation limits. This conflates structurally different extraction modes (metadata-only vs. full-detail) under one code path with conditional branching.

Additionally, compaction sub-agents (which contain pre-compressed session summaries) are underutilized. The current code interleaves compaction summaries chronologically in the detail path, but the summary and metadata paths ignore these pre-compressed representations entirely.

## Goals

1. Clean module boundary: `context/` depends on `models/` and `utils/`, not `services/`.
2. Template method pattern: base class handles compaction, header, pipeline orchestration. Subclasses override only `format_step()`.
3. Three extractors named by what they extract: `MetadataExtractor`, `SummaryExtractor`, `DetailExtractor`.
4. Shared metadata block across all extractors (session info, step counts, tool summary).
5. Leverage compaction summaries as pre-compressed context at the summary level.
6. Batcher loses `get_settings()` dependency; `max_batch_tokens` becomes a required parameter.

## Module Structure

```
src/vibelens/context/
  __init__.py       Public API exports
  base.py           ContextExtractor ABC + _IndexTracker
  extractors.py     MetadataExtractor, SummaryExtractor, DetailExtractor
  params.py         ContextParams frozen dataclass + 4 presets
  batcher.py        build_batches(contexts, max_batch_tokens)
  formatter.py      Shared step formatting helpers
```

Dependency direction: `models/` -> `context/` -> `services/`

- `context/` depends on: `models/trajectories`, `models/context`, `utils/`, `llm/tokenizer` (batcher only)
- `context/` does NOT depend on: `services/`, `deps.py`, `config/`

## Base Extractor

```python
# context/base.py

class ContextExtractor(ABC):
    """Base context extractor using template method pattern.

    Handles: main trajectory detection, compaction agent detection,
    compaction interleaving, metadata header, step iteration.

    Subclasses override: format_step() to control per-step detail level.
    """

    def __init__(self, params: ContextParams):
        self.params = params

    def extract(
        self,
        trajectory_group: list[Trajectory],
        session_index: int | None = None,
    ) -> SessionContext:
        """Template method: extract compressed context from a trajectory group."""
        main = self._find_main_trajectory(trajectory_group)
        compaction_agents = self._find_compaction_agents(trajectory_group)
        tracker = _IndexTracker()

        context_text = self._extract_steps(main, compaction_agents, tracker)
        header = build_metadata_block(main, session_index)
        full_text = f"{header}\n\n{context_text}"

        return SessionContext(
            session_id=main.session_id,
            project_path=main.project_path,
            context_text=full_text,
            trajectory_group=trajectory_group,
            prev_trajectory_ref_id=(
                main.prev_trajectory_ref.session_id
                if main.prev_trajectory_ref
                else None
            ),
            next_trajectory_ref_id=(
                main.next_trajectory_ref.session_id
                if main.next_trajectory_ref
                else None
            ),
            timestamp=main.timestamp,
            session_index=session_index,
            step_index2id=tracker.index_to_real_id,
        )

    @abstractmethod
    def format_step(self, step: Step, tracker: _IndexTracker) -> str:
        """Format a single step. Subclasses control detail level."""
        ...

    # Protected pipeline methods (inherited by all subclasses):
    def _find_main_trajectory(self, trajectory_group) -> Trajectory: ...
    def _find_compaction_agents(self, trajectory_group) -> list[Trajectory]: ...
    def _extract_steps(self, main, compaction_agents, tracker) -> str:
        """Iterates steps, interleaving compaction summaries if present."""
        ...
```

Key design decisions:
- `extract()` is the public entry point (explicit over `__call__`)
- `format_step()` is the single abstract method (narrow override surface)
- `_IndexTracker` is internal to the base, passed to `format_step()` for step index assignment
- Compaction detection uses `extra["is_compaction_agent"]` flag set by parsers
- Truncation (ContextParams) is separate from extraction structure: each subclass provides a default preset but accepts an override. This separates *what* to extract (subclass identity) from *how much* to truncate (configurable params)

## Subclass Extractors

### Shared Metadata Block

All extractors emit this header (built by `formatter.build_metadata_block`):

```
=== SESSION: {session_id} (index=N) ===
PROJECT: ~/path/to/project
TIMESTAMP: 2026-04-10T14:30:00
STEPS: 45 (user=12, agent=33)
TOOLS: Edit(8), Read(5), Bash(4), Grep(3)
```

### MetadataExtractor

Purpose: maximum compression for large session sets (1000+ sessions, ~1B tokens raw).

Extracts: metadata block + first user prompt (truncated).

```python
class MetadataExtractor(ContextExtractor):
    def __init__(self, params: ContextParams = PRESET_RECOMMENDATION):
        super().__init__(params=params)
```

```
=== SESSION: abc123 (index=0) ===
PROJECT: ~/Projects/VibeLens
STEPS: 45 (user=12, agent=33)
TOOLS: Edit(8), Read(5), Bash(4), Grep(3)

FIRST PROMPT: Refactor the authentication module to use JWT tokens instead of...
```

Compaction handling: ignored. At this compression level, even compaction summaries are too detailed.

Default preset: `PRESET_RECOMMENDATION` (user_prompt_max_chars=500, agent_message_max_chars=0). Override with custom `ContextParams` for different truncation limits.

Token cost per session: ~100-200 tokens.

Used by: recommendation engine (standard path).

### SummaryExtractor

Purpose: balanced compression for pattern discovery across 30 sessions (~10M tokens raw).

Extracts: metadata block + first user prompt + final compaction summary.

```python
class SummaryExtractor(ContextExtractor):
    def __init__(self, params: ContextParams = PRESET_MEDIUM):
        super().__init__(params=params)
```

The final compaction summary is a pre-compressed representation of the session's history, already generated by the agent itself. This leverages compaction as a natural TL;DR.

With compaction agents:
```
=== SESSION: abc123 (index=0) ===
PROJECT: ~/Projects/VibeLens
STEPS: 45 (user=12, agent=33)
TOOLS: Edit(8), Read(5), Bash(4), Grep(3)

FIRST PROMPT: Refactor the authentication module to use JWT...

--- COMPACTION SUMMARY (latest) ---
The session involved refactoring auth from session-based to JWT. Key changes:
- Added jwt_handler.py with token generation and validation
- Modified middleware.py to check Authorization headers
- Updated 12 test files for the new auth flow...
```

Without compaction (shorter sessions): metadata + all user prompts (truncated). Since no compaction exists, user prompts are the best compressed thread of intent.

Default preset: `PRESET_MEDIUM` (user_prompt_max_chars=1500, agent_message_max_chars=500). Override with custom `ContextParams` for different truncation limits.

Token cost per session: ~500-2000 tokens.

Used by: skill creation proposals, skill evolution proposals.

### DetailExtractor

Purpose: full detail for deep analysis of smaller session subsets (5-10 sessions).

Extracts: metadata block + all user prompts + agent messages + tool calls with args + error observations + optional non-error observations + all compaction summaries interleaved chronologically.

```python
class DetailExtractor(ContextExtractor):
    def __init__(self, params: ContextParams = PRESET_DETAIL):
        super().__init__(params=params)
```

This is the current `extract_session_context` behavior with `PRESET_DETAIL`, plus the new metadata header.

Default preset: `PRESET_DETAIL` (user_prompt_max_chars=2000, include_non_error_obs=True). Override with custom `ContextParams` for different truncation limits.

Token cost per session: ~5000-50000 tokens.

Used by: friction analysis, skill deep-create, skill deep-edit.

### Scale Summary

| Extractor | Tokens/session | Compaction strategy | Scenario |
|---|---|---|---|
| Metadata | ~100-200 | Ignored | 1000+ sessions (1B raw) |
| Summary | ~500-2000 | Final summary as TL;DR | 30 sessions (10M raw) |
| Detail | ~5000-50000 | All interleaved chronologically | 5-10 sessions |

## Formatter (Shared Helpers)

```python
# context/formatter.py

TOOL_ARG_KEYS: dict[str, list[str]]  # tool name -> relevant arg keys
_PATH_ARG_KEYS: set[str]             # arg keys that are file paths

def build_metadata_block(main: Trajectory, session_index: int | None) -> str:
    """Build shared metadata header: session ID, project, timestamps, step counts, tool summary."""

def format_user_prompt(message: str, params: ContextParams) -> str:
    """Truncate long user prompts (head + tail with marker)."""

def format_agent_message(message: str, params: ContextParams) -> str:
    """Truncate long agent text messages."""

def summarize_tool_args(function_name: str, arguments: object, params: ContextParams) -> str:
    """Summarize tool call arguments based on tool-specific rules."""

def shorten_path(path_str: str, params: ContextParams) -> str:
    """Shorten file path: ~ prefix + last-N-segment trimming."""
```

All pure functions with no state or I/O.

## Batcher Changes

`context/batcher.py` moves from `services/session_batcher.py`.

Signature change:
```python
def build_batches(
    session_contexts: list[SessionContext],
    max_batch_tokens: int,              # was: int | None with get_settings() fallback
) -> list[SessionContextBatch]:
```

`max_batch_tokens` is now required. Callers pass it explicitly (typically from `settings.max_batch_tokens`). This removes the `deps.get_settings()` import from the context layer.

All internal logic (oversized splitting, chain grouping, chain budget enforcement, affinity packing) stays unchanged.

## extract_all_contexts (stays in services/)

`services/inference_shared.py` (renamed from `analysis_shared.py`) keeps `extract_all_contexts` since it bridges storage and extraction (I/O concern).

Signature change:
```python
def extract_all_contexts(
    session_ids: list[str],
    session_token: str | None,
    extractor: ContextExtractor,        # was: params: ContextParams = PRESET_DETAIL
) -> SessionContextBatch:
```

Internally calls `extractor.extract(trajectory_group, session_index=...)` instead of `extract_session_context(trajectory_group, params=..., session_index=...)`.

## Call Site Migration

| Current | New |
|---|---|
| `extract_all_contexts(sids, token, PRESET_DETAIL)` | `extract_all_contexts(sids, token, DetailExtractor())` |
| `extract_all_contexts(sids, token, PRESET_MEDIUM)` | `extract_all_contexts(sids, token, SummaryExtractor())` |
| `extract_all_contexts(sids, token, PRESET_RECOMMENDATION)` | `extract_all_contexts(sids, token, MetadataExtractor())` |
| `build_batches(contexts)` | `build_batches(contexts, max_batch_tokens=settings.max_batch_tokens)` |
| `from vibelens.services.context_params import ...` | `from vibelens.context import ...` |
| `from vibelens.services.context_extraction import ...` | `from vibelens.context import ...` |
| `from vibelens.services.session_batcher import ...` | `from vibelens.context import ...` |

## Files Deleted

- `src/vibelens/services/context_extraction.py` -> `context/base.py` + `context/extractors.py` + `context/formatter.py`
- `src/vibelens/services/context_params.py` -> `context/params.py`
- `src/vibelens/services/session_batcher.py` -> `context/batcher.py`

## Files Modified

- `services/analysis_shared.py` -- rename to `services/inference_shared.py`, update imports, change signature
- `services/friction/analysis.py` -- use `DetailExtractor()`
- `services/skill/creation.py` -- use `SummaryExtractor()` and `DetailExtractor()`
- `services/skill/evolution.py` -- use `SummaryExtractor()` and `DetailExtractor()`
- `services/recommendation/engine.py` -- use `MetadataExtractor()`
- `tests/services/test_context_params.py` -- update imports
- `tests/services/test_context_extraction.py` -- update imports, test new extractors
- `tests/services/test_session_batcher.py` -- update imports

## Testing

- Unit tests for each extractor: verify output format matches expected structure
- Unit tests for metadata block: verify step counts, tool summary accuracy
- Unit tests for SummaryExtractor compaction path: verify final compaction summary is used
- Unit tests for SummaryExtractor no-compaction fallback: verify all user prompts included
- Existing batcher tests updated for required `max_batch_tokens` parameter
- Integration: verify friction, skill, and recommendation pipelines produce equivalent results

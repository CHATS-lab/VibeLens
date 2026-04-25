# ATIF Data Models

Pydantic domain models implementing the Agent Trajectory Interchange Format (ATIF) v1.6 -- the unified data schema for all agent session data.

## Purpose

VibeLens normalizes conversation histories from multiple coding agent CLIs (Claude Code, Codex, Gemini, OpenClaw, Dataclaw) into a single data format. The ATIF model hierarchy provides this common structure: every parser outputs `Trajectory` objects, and every downstream service (dashboard, friction analysis, skill analysis, export) consumes them.

The models live in `src/vibelens/models/trajectories/` with one file per model. All models use Pydantic `BaseModel` with type validation. Fields marked **(ext)** are VibeLens extensions beyond the ATIF spec.

Reference: [ATIF Specification (Harbor)](https://github.com/cfahlgren1/atif)

## Model Hierarchy

```
Trajectory                          <- Root container: one agent session
+-- agent: Agent                    <- Agent system metadata
+-- steps: list[Step]               <- Ordered interaction sequence
|   +-- tool_calls: list[ToolCall]  <- Tool invocations
|   +-- observation: Observation    <- Tool execution results
|   |   +-- results: list[ObservationResult]
|   +-- metrics: Metrics            <- Per-step token usage
+-- final_metrics: FinalMetrics     <- Session-level aggregate metrics
+-- parent_trajectory_ref: TrajectoryRef
+-- continued_trajectory_ref: TrajectoryRef
+-- parent_session_ref: TrajectoryRef
```

## Key Files

| File | Model | Role |
|------|-------|------|
| `trajectory.py` | `Trajectory` | Root container for a complete session |
| `agent.py` | `Agent` | Agent system config (name, version, model) |
| `step.py` | `Step` | Single interaction turn (user/agent/system) |
| `tool_call.py` | `ToolCall` | One tool invocation record |
| `observation.py` | `Observation` | Container for tool execution results |
| `observation_result.py` | `ObservationResult` | Single tool output |
| `content.py` | `ContentPart`, `Base64Source`, `ImageSource` | Multimodal content blocks |
| `metrics.py` | `Metrics` | Per-step token usage |
| `final_metrics.py` | `FinalMetrics` | Session-level aggregates |
| `trajectory_ref.py` | `TrajectoryRef` | Cross-trajectory reference |

All under `src/vibelens/models/trajectories/`.

## Core Models

### Trajectory

Root container for one agent session.

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `ATIF_VERSION` | `"ATIF-v1.6"` |
| `session_id` | `str` | Unique session identifier (UUID) |
| `project_path` | `str | None` | Working directory path **(ext)** |
| `first_message` | `str | None` | Truncated first user message preview **(ext)** |
| `agent` | `Agent` | Agent system configuration |
| `final_metrics` | `FinalMetrics | None` | Session-level aggregate metrics |
| `parent_trajectory_ref` | `TrajectoryRef | None` | Previous session in continuation chain **(ext)** |
| `continued_trajectory_ref` | `TrajectoryRef | None` | Next session in continuation chain |
| `parent_session_ref` | `TrajectoryRef | None` | Parent session for sub-agents **(ext)** |
| `timestamp` | `datetime | None` | Session start time, derived from first step **(ext)** |
| `steps` | `list[Step]` | Ordered interaction steps (min 1) |
| `extra` | `dict | None` | Custom metadata |

**Validators:** `validate_unique_step_ids` (blocking -- raises on duplicate step IDs), `validate_tool_observation_balance` (warning only), `validate_unique_tool_call_ids` (warning only).

### Step

One interaction turn. Richer than a chat message -- an agent step can include text, reasoning, tool calls, and tool results in a single object.

| Field | Type | Description |
|-------|------|-------------|
| `step_id` | `str` | Step identifier (UUID string) |
| `timestamp` | `datetime | None` | Step creation time |
| `source` | `StepSource` | `"user"`, `"agent"`, or `"system"` |
| `model_name` | `str | None` | LLM model used (agent steps only) |
| `message` | `str | list[ContentPart]` | Conversation text or multimodal content |
| `reasoning_content` | `str | None` | Internal reasoning (Extended Thinking) |
| `tool_calls` | `list[ToolCall]` | Tool invocations in this step |
| `observation` | `Observation | None` | Tool execution results |
| `metrics` | `Metrics | None` | Token usage for this step |
| `is_copied_context` | `bool | None` | Copied from previous session (v1.5) |

### ToolCall

| Field | Type | Description |
|-------|------|-------------|
| `tool_call_id` | `str` | Unique ID, paired with `ObservationResult.source_call_id` |
| `function_name` | `str` | Tool name (e.g., `"Bash"`, `"Read"`, `"Edit"`) |
| `arguments` | `dict | str | None` | Tool parameters |

### Metrics (Per-Step)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `prompt_tokens` | `int` | `0` | Input tokens (includes cached) |
| `completion_tokens` | `int` | `0` | Generated tokens |
| `cached_tokens` | `int` | `0` | Cache-hit portion of prompt_tokens |
| `cache_creation_tokens` | `int` | `0` | Tokens written to cache **(ext)** |
| `cost_usd` | `float | None` | `None` | API call cost |

Integer fields default to `0` (not `None`) so aggregation can sum directly without null guards.

### FinalMetrics (Session-Level)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `total_prompt_tokens` | `int | None` | `None` | Sum of input tokens |
| `total_completion_tokens` | `int | None` | `None` | Sum of generated tokens |
| `total_cost_usd` | `float | None` | `None` | Total session cost |
| `total_steps` | `int | None` | `None` | Step count |
| `tool_call_count` | `int` | `0` | Total tool invocations **(ext)** |
| `duration` | `int` | `0` | Wall-clock seconds **(ext)** |
| `total_cache_write` | `int` | `0` | Cache write tokens **(ext)** |
| `total_cache_read` | `int` | `0` | Cache read tokens **(ext)** |

Uses `None` for aggregated fields (meaning "data unavailable") vs. `0` (meaning "confirmed zero").

### TrajectoryRef

Lightweight cross-trajectory reference used for continuation chains and sub-agent relationships.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `str` | Referenced session ID |
| `trajectory_path` | `str | None` | File path of referenced trajectory |
| `step_id` | `str | None` | Step that triggered sub-agent |
| `tool_call_id` | `str | None` | Tool call that created sub-agent |

## Trajectory References

```
Session A             Session B             Session C
+----------+         +----------+         +----------+
| steps... |--last-->| steps... |--last-->| steps... |
|          |<-cont---|          |<-cont---|          |
+----------+         +----------+         +----------+
                           |
                     parent |
                           v
                     +----------+
                     | Sub-agent|
                     +----------+
```

- **`last_trajectory_ref`**: Points backward to the previous session in a continuation chain.
- **`continued_trajectory_ref`**: Points forward to the next session.
- **`parent_session_ref`**: Links a sub-agent to its parent session.

## Enums

Defined in `src/vibelens/models/enums.py`:

| Enum | Values |
|------|--------|
| `StepSource` | `"system"`, `"user"`, `"agent"` |
| `ContentType` | `"text"`, `"image"`, `"pdf"` |
| `AgentType` | `"claude_code"`, `"codex"`, `"gemini"` |
| `AppMode` | `"self"`, `"demo"` |

## Error Content Convention

ATIF `ObservationResult` has no `is_error` field. VibeLens marks errors with a `"[ERROR] "` prefix on `content`. Helpers `is_error_content()` and `mark_error_content()` in `ingest/parsers/base.py` handle detection and marking.

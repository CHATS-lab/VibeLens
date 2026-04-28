# ATIF Trajectory Models

The Pydantic schema VibeLens uses for every agent session, regardless of which agent produced it.

## Motivation

VibeLens normalises sessions from a couple of dozen different agent CLIs (Claude, Codex, Gemini, OpenClaw, Cursor, Hermes, Kiro, Kilo, OpenCode, CodeBuddy, Copilot, Dataclaw, …). Each agent invents its own log format and changes it across versions. Without a common shape every downstream service — dashboard stats, friction analysis, skill analysis, search, donation packaging — would need per-agent code paths.

The Agent Trajectory Interchange Format (ATIF) is that common shape. Parsers translate the agent's native format into ATIF; everything downstream consumes ATIF. The models live in `src/vibelens/models/trajectories/`, one file per model, and stamp `schema_version = "ATIF-v1.6"` on every new trajectory.

Reference: [ATIF specification (Harbor)](https://github.com/cfahlgren1/atif). Fields tagged **(VibeLens)** below are extensions beyond the upstream spec.

## Hierarchy

```
Trajectory                    one agent session, the root container
├── agent: Agent              what produced the session (name, version, model)
├── steps: list[Step]         ordered turns
│   ├── tool_calls            tool invocations issued in this turn
│   ├── observation           tool results delivered back to the agent
│   │   └── results[]
│   └── metrics               per-step token / cost
├── final_metrics             session-level aggregates
├── prev_trajectory_ref       (VibeLens) backward link in a continuation chain
├── next_trajectory_ref       forward link
└── parent_trajectory_ref     (VibeLens) parent that spawned this sub-agent
```

## What each model is for

- **`Trajectory`** — root container. Carries the session identity (`session_id`), `created_at` / `updated_at` (derived from step timestamps when missing), `project_path`, the truncated `first_message` preview, the `steps` list, and the three trajectory refs described below. It runs three model-level validators on construction:
  - **blocking:** duplicate `step_id`s — raises. Cross-references depend on uniqueness, so we'd rather fail loudly than store garbage.
  - **warning:** unbalanced tool calls vs. observation results.
  - **warning:** duplicate `tool_call_id`s.

  It also rejects `session_id`s that contain path separators or null bytes — the id becomes a filename in `DiskTrajectoryStore`, so a malicious upload could otherwise write outside the storage root.

- **`Step`** — one turn. Richer than a chat message: a single step can hold text, reasoning, tool calls, and the observations they produce. `source` is `user` / `agent` / `system`.

- **`ToolCall` / `Observation` / `ObservationResult`** — paired by `tool_call_id` ↔ `source_call_id`. `ObservationResult.is_error` (VibeLens) is set by parsers from each agent's native error signal (`claude tool_result.is_error`, `openclaw msg.isError`, `gemini status="error"`, …). Sub-agent trajectories are linked back via `subagent_trajectory_ref` on the result.

- **`Metrics` (per step)** — `prompt_tokens`, `completion_tokens`, `cached_tokens`, `cache_creation_tokens` (VibeLens), `cost_usd`. Integer fields default to `0` so aggregation can sum directly without null guards.

- **`FinalMetrics` (per trajectory)** — session-level aggregates plus `tool_call_count`, `duration`, cache totals (VibeLens). Aggregated fields default to `None` ("data unavailable") rather than `0` ("confirmed zero") to keep that distinction visible.

- **`Agent`** — agent system metadata: name, version, model.

- **`ContentPart` / `Base64Source` / `ImageSource`** — multimodal message blocks (text, image, pdf).

- **`TrajectoryRef`** — lightweight cross-trajectory pointer carrying `session_id`, optional `trajectory_path`, and (for sub-agents) the `step_id` and `tool_call_id` that triggered the link.

## Trajectory references

Three refs on `Trajectory` carry the inter-session topology:

```
session A             session B             session C
+----------+ next →   +----------+ next →   +----------+
|  steps   |          |  steps   |          |  steps   |
+----------+ ← prev   +----------+ ← prev   +----------+
                            │
                            │ parent_trajectory_ref (set on the sub-agent)
                            ▼
                      +----------+
                      | sub-agent|
                      +----------+
```

- `prev_trajectory_ref` — the session this one continues from. Set on continuations.
- `next_trajectory_ref` — the session that continues from this one.
- `parent_trajectory_ref` — only on sub-agents; points back to the parent and includes the spawning `step_id` / `tool_call_id`.

## Enums

In `models/enums.py`:

- **`AgentType`** — every agent VibeLens knows about. A handful (`AIDER`, the *claw family) have no parser and exist only for the LLM-backend or extensions layer. New parsers add a new `AgentType` value.
- **`StepSource`** — `system` / `user` / `agent`.
- **`ContentType`** — `text` / `image` / `pdf`.
- **`AppMode`** — `self` / `demo` / `test`.
- **`AgentExtensionType`** — `skill`, `plugin`, `subagent`, `command`, `hook`, `mcp_server`, `repo`.
- **`SessionPhase`** — semantic phase tags used by phase detection.

## Errors on observations

ATIF upstream has no `is_error` flag on `ObservationResult`. VibeLens adds one (the `(VibeLens)` field above). Each parser maps its agent's native error signal into this bool; downstream code never has to grep for `[ERROR]` prefixes or do per-agent checks.

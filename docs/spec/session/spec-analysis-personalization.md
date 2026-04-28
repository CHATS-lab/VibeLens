# Personalization

LLM-powered analyses that turn agent-session evidence into installable extensions. Three top-level modes — recommend existing extensions, create new skills, evolve installed skills — each with its own service, store, and API surface.

## Motivation

VibeLens already shows the user *what* they did with their agent. Personalization is the layer that asks *what would have helped them do it better*: from sessions, infer recurring workflows, then either point at existing extensions that match those workflows, generate new skill definitions, or amend the skills the user has already installed.

Each mode has different cost, latency, and UX expectations, so they're built as three sibling services rather than one polymorphic pipeline:

- **Recommendation** is a retrieval problem against a large catalogue. The fast path uses the same field-weighted BM25 engine that powers extension browse (see [`spec-extension-search.md`](../extension/spec-extension-search.md)); the LLM is used only to rank a small candidate set and produce rationale.
- **Creation** is a generative problem. Cost and user trust matter, so it's a two-step pipeline (cheap proposals → user confirms → deep generation per accepted proposal).
- **Evolution** edits content the user has already installed. The model has to know *which* skill is being edited and ground every edit in a real conflict observed in a session, otherwise it'll cheerfully drift the skill away from what the user actually does.

All three share the same trajectory-compression layer (`services/context`), the same job-tracker (`services/job_tracker`), and the same persistence shape (per-analysis JSON file + JSONL index).

## Architecture

```
sessions selected by user
        │
        ▼
context extraction + batching         (shared with friction)
        │
        ├──────────────┐──────────────┐
        ▼              ▼              ▼
   recommendation   creation        evolution
        │              │              │
        ▼              ▼              ▼
  catalogue BM25   propose → user → create   discover → diagnose → prescribe
        │              │              │
        ▼              ▼              ▼
   ranked items    SKILL.md           per-skill edits
        │              │              │
        └──────────────┴──────────────┘
                       ▼
              JobTracker + per-mode store
```

Every `POST` returns immediately with a `job_id`; the actual work runs as a background `asyncio.Task` under the shared job tracker. The frontend polls.

## Modules

| Path | Role |
|---|---|
| `services/recommendation/engine.py` | L2 (LLM profile) + L3 (BM25 retrieval) + L4 (rationale) pipeline. |
| `services/creation/creation.py` | Two-step pipeline: proposals → deep generation. |
| `services/evolution/evolution.py` | Three-phase: discover-active → diagnose-conflicts → prescribe-edits. |
| `services/personalization/store.py` | Shared persistence backend (per-analysis JSON, append-only index, in-memory TTL cache). |
| `services/personalization/shared.py` | Cross-mode helpers (digest framing, profile loading). |
| `services/job_tracker.py` | Background job lifecycle, polling, cancellation. |
| `services/analysis_store.py` | Generic analysis store contract reused across friction + personalization modes. |
| `models/{recommendation,creation,evolution}/...` | Domain models per mode. |
| `api/recommendation.py`, `api/creation.py`, `api/evolution.py` | HTTP surface (one router per mode). |
| `llm/prompts/...` | Prompt templates per mode. |

## API surface

Each mode mounts under `/api/<mode>/`. Within each, the contract is identical:

| Method | Path | Purpose |
|---|---|---|
| `POST /api/<mode>` | start an analysis (returns `job_id`) |
| `POST /api/<mode>/estimate` | pre-flight token / cost estimate |
| `GET /api/<mode>/jobs/{job_id}` | poll job status |
| `POST /api/<mode>/jobs/{job_id}/cancel` | cancel a running job |
| `GET /api/<mode>/history` | list persisted analyses |
| `GET /api/<mode>/{analysis_id}` | load full result |
| `DELETE /api/<mode>/{analysis_id}` | delete an analysis |

Friction analysis follows the same shape under `/api/analysis/friction/...` (see [`spec-analysis-friction.md`](spec-analysis-friction.md)).

## Skill format

Skills target a common, install-anywhere markdown format:

```markdown
---
description: One-line trigger description.
tags: [tag1, tag2]
allowed_tools: [Read, Edit, Bash, Grep, Glob, Write]
---

# Skill name

Step-by-step instructions the agent follows when triggered.
```

Install paths vary by agent (`~/.claude/skills/`, `~/.codex/skills/`, etc.); the install pipeline lives in `services/extensions/platforms.py`.

## Mode 1 — Recommendation

Goal: surface existing extensions (skills, plugins, sub-agents, …) that match the user's recurring workflows.

The engine is layered:

- **L1: signals.** Per-session step signals (tool frequency, error patterns, user topic summaries) are aggregated into a compact corpus the LLM can reason about.
- **L2: profile.** One LLM call produces a `UserProfile` with weighted `search_keywords` describing the user's working style.
- **L3: retrieval.** `rank_catalog(query=ExtensionQuery(profile=...), sort=PERSONALIZED, top_k=...)` returns the top candidates from the shared catalogue index. Same engine that powers the explore tab — browse-quality ≡ recommend-quality.
- **L4: rationale.** A second LLM call ranks and explains the top candidates, producing per-item rationale.

Output is a `RankedRecommendationItem` list with score breakdown, rationale, and the underlying `AgentExtensionItem`.

## Mode 2 — Creation

Goal: when no existing extension covers a recurring workflow, generate a new skill.

Two steps, on purpose:

1. **Proposals** — cheap LLM call returning short `(name, description, rationale)` triples. Batched when the session set exceeds the context budget, with a synthesis pass to merge.
2. **Deep creation** — for each proposal the user accepts, one focused LLM call produces the full SKILL.md (frontmatter + body). One call per accepted skill.

The two-step shape lets the user filter at the cheap stage; deep generation only runs on what they want.

## Mode 3 — Evolution

Goal: improve skills the user has already installed.

Three phases:

1. **Discover** — which installed skills appear to have been active in the analysed sessions (by name match, by tool overlap, by description match).
2. **Diagnose** — for each candidate skill, find conflicts between observed user behaviour and the skill's current instructions: skipped step, added step, wrong tool, bad trigger, outdated instruction.
3. **Prescribe** — emit granular edits per conflict. Edit kinds are `add_instruction`, `remove_instruction`, `replace_instruction`, `update_description`, `add_tool`, `remove_tool`.

Every edit is grounded in a `StepRef` so the user can see the exact session evidence behind it.

## Persistence

All three modes use the same on-disk shape:

```
{personalization_dir}/{mode}/
├── index.jsonl              append-only metadata, one entry per analysis
└── {analysis_id}.json       full result blob
```

An in-memory TTL cache fronts each store; entries are keyed by a hash of the sorted session-id list so the same analysis run twice replays from cache. The shared friction store (`services/friction/store.py`) follows the same shape under `{friction_dir}/`.

## Job lifecycle

```
submit_job ──▶ RUNNING
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
   COMPLETED  FAILED  CANCELLED
        │        │        │
        └────────┴────────┘
                 ▼
       cleanup_stale (after grace period)
```

All endpoints follow the same pattern: in mock mode (demo, test) the job completes immediately with canned output; in real mode the background task drives the LLM pipeline. The job tracker handles cancellation: a `cancel` request sets a flag the pipeline checks between phases, so the run terminates cleanly without partial writes.

## Cost estimation

Each mode's `/estimate` endpoint runs the same loading and batching pipeline without LLM calls and reports an input-token / output-token / cost range. Used by the frontend to show the user what they're about to spend.

## Demo / test mode

Mock results carry real step IDs from the user's sessions so the UI exercises the same rendering paths it would for real results. Mock mode is selected by absence of an inference backend — there's no separate flag.

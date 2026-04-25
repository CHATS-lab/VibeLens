# Skill Personalization

LLM-powered analysis that turns trajectory evidence into skill recommendations. Three modes: retrieve existing skills, create new ones, and evolve installed skills.

## Purpose

Skill personalization detects recurring workflow patterns in agent sessions and takes three actions:

1. **Retrieve** -- recommend existing skills from a catalog that match the user's workflows.
2. **Create** -- generate new SKILL.md definitions when no existing skill covers a pattern.
3. **Evolve** -- improve installed skills when the user's behavior diverges from skill instructions.

All analysis runs asynchronously as background tasks. Results are persisted and browsable via a history sidebar.

## Architecture

```
POST /skills/analysis
         |
         v
  Load sessions -> build_step_signals() -> digest for LLM
         |
         v
  +------+------+------+
  |      |      |      |
  v      v      v      v
Retrieve  Create   Evolve  Proposals
  |      |      |      |
  v      v      v      v
  LLM inference (1 or batched)
         |
         v
  SkillAnalysisResult (persisted to SkillStore)
```

## Key Files

### Backend

| File | Role |
|------|------|
| `services/skill/retrieval.py` | Skill retrieval + shared infrastructure (loading, parsing, cache) |
| `services/skill/creation.py` | Skill creation pipeline |
| `services/skill/evolution.py` | Skill evolution analysis |
| `services/skill/shared.py` | Shared utilities across skill modes |
| `services/skill/download.py` | Skill download/install |
| `services/skill/importer.py` | Skill import from files |
| `services/skill/store.py` | `SkillStore`: save/load/list/delete |
| `services/skill/mock.py` | Mock results for demo/test mode |
| `services/analysis_shared.py` | Shared analysis utilities |
| `services/job_tracker.py` | Background job lifecycle management |
| `models/skill/` | Domain models (results, patterns, retrieval, creation, evolution) |
| `schemas/skills.py` | Request/response schemas |
| `api/skill_analysis.py` | Skill analysis endpoints |
| `llm/prompts/skill_retrieval.py` | Retrieval prompt templates |
| `llm/prompts/skill_creation.py` | Creation prompt templates |
| `llm/prompts/skill_evolution.py` | Evolution prompt templates |

### Frontend

| File | Role |
|------|------|
| `components/skills/skills-panel.tsx` | Main skill analysis UI (tabs, polling, results) |
| `components/skills/skills-history.tsx` | History sidebar |

## Skill Format

Skills target a common format installable across coding agent CLIs:

```markdown
---
description: One-line trigger description
tags: [tag1, tag2]
allowed_tools: [Read, Edit, Bash, Grep, Glob, Write]
---

# Skill Name

Step-by-step instructions the agent follows when triggered.
```

Install locations: Claude Code (`~/.claude/commands/`), Codex (`~/.codex/skills/`).

## Shared Concepts

### Session Digest

All modes share the same trajectory compression: raw trajectories -> step signals via `build_step_signals()` -> compact text digest optimized for LLM context. The digest includes per-session tool frequency counts and user topic summaries.

### Installed Skills

The central skill store at `~/.vibelens/skills/` provides the inventory of skills the user already has. All modes use this for dedup (retrieval/creation) or as edit targets (evolution).

### Background Job Execution

All POST endpoints return immediately with a `job_id`. The shared `JobTracker` wraps coroutines in `asyncio.Task` instances. Frontend polls at 3s intervals. Users can cancel running jobs.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/skills/analysis` | Start skill analysis (retrieval/creation/evolution) |
| `POST` | `/skills/analysis/proposals` | Generate creation proposals |
| `POST` | `/skills/analysis/create` | Deep create from approved proposal |
| `GET` | `/skills/analysis/jobs/{job_id}` | Poll job status |
| `POST` | `/skills/analysis/jobs/{job_id}/cancel` | Cancel running job |
| `GET` | `/skills/analysis/history` | List past analyses |
| `GET` | `/skills/analysis/{analysis_id}` | Load full result |
| `DELETE` | `/skills/analysis/{analysis_id}` | Delete result |

## Mode 1: Skill Retrieval

Recommend existing skills from a catalog matching the user's recurring workflows.

**Scaling tiers:**
- Tier 1 (current): All candidates fit in LLM context. Pre-filter via keyword scoring when catalog exceeds 200 candidates. Source: `featured-skills.json` (~300 skills).
- Tier 2 (planned): BM25/TF-IDF search index for thousands of skills.
- Tier 3 (future): Embedding search + LLM re-ranking for marketplace scale.

**Decision rule:** Recommend when a workflow pattern repeats, a candidate skill matches, and no installed skill covers it.

**Output:** `WorkflowPattern[]` + `SkillRecommendation[]` with confidence scores.

## Mode 2: Skill Creation

Two-step pipeline to manage cost and user control:

**Step 1: Proposals** -- Lightweight analysis producing short proposals (name + description + rationale). Cheap enough to run frequently. Batched when sessions exceed context window, with synthesis merge pass.

**Step 2: Deep Creation** -- For each approved proposal, a focused LLM call generates full SKILL.md content. One LLM call per skill.

**Decision rule:** Propose when a workflow pattern repeats, has stable steps, and no existing skill covers it.

## Mode 3: Skill Evolution

Three-phase analysis of installed skills:

1. **Discover** -- which installed skills were active during analyzed sessions
2. **Diagnose** -- conflicts between user behavior and skill instructions
3. **Prescribe** -- granular edits resolving each conflict

**Conflict types:** skipped step, added step, wrong tool, bad trigger, outdated instruction.

**Edit kinds:** `add_instruction`, `remove_instruction`, `replace_instruction`, `update_description`, `add_tool`, `remove_tool`.

**Decision rule:** Evolve when a skill is close but insufficient, and fixing is simpler than creating a new one.

## Data Models

### SkillAnalysisResult

| Field | Type | Description |
|-------|------|-------------|
| `analysis_id` | `str | None` | Set on persistence |
| `mode` | `SkillMode` | retrieval / creation / evolution |
| `session_ids` | `list[str]` | Sessions analyzed |
| `workflow_patterns` | `list[WorkflowPattern]` | Detected recurring patterns |
| `recommendations` | `list[SkillRecommendation]` | Retrieval matches |
| `generated_skills` | `list[SkillCreation]` | Created skills |
| `evolution_suggestions` | `list[SkillEvolutionSuggestion]` | Per-skill edit plans |
| `summary` | `str` | Narrative overview |
| `user_profile` | `str` | Working style description |
| `model` | `str` | Model identifier |
| `cost_usd` | `float | None` | Inference cost |

### WorkflowPattern

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Short name (e.g., "Search-Read-Edit Cycle") |
| `description` | `str` | What the pattern does |
| `pain_point` | `str` | Why automation helps |
| `example_refs` | `list[StepRef]` | Real step IDs from trajectories |

## Persistence

`SkillStore` uses disk-based storage (same pattern as FrictionStore):

```
{skill_dir}/
+-- index.jsonl             <- Append-only metadata
+-- {analysis_id}.json      <- Full SkillAnalysisResult per analysis
```

In-memory cache with 1-hour TTL.

## Job Lifecycle

```
submit_job() -> RUNNING
                  |
          +-------+-------+
          |       |       |
     COMPLETED  FAILED  CANCELLED
          |       |       |
     cleanup_stale (removed after 1h)
```

All analysis endpoints follow the same pattern: mock mode returns completed immediately, real mode dispatches background task.

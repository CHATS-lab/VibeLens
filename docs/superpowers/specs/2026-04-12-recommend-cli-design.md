# Recommend CLI, Lightweight Extraction, and GEMINI Merge — Design Spec

## Goal

Three tightly coupled changes to make the recommendation pipeline usable from the CLI on real-world session data (576+ sessions, 1.3 GB):

1. **GEMINI/GEMINI_CLI merge** — collapse redundant enum values
2. **Lightweight context extraction** — compaction-first strategy for 10M+ token session data
3. **`vibelens recommend` CLI command** — runs pipeline, opens web UI with interactive results
4. **Frontend recommendation view** — interactive report with install actions and GitHub links

## 1. GEMINI/GEMINI_CLI Enum Merge

### Problem

`AgentType` has both `GEMINI` and `GEMINI_CLI`. Only `GEMINI` is used by parsers and backends. `GEMINI_CLI` exists only in `SkillSourceType` and frontend badge constants. The distinction is unnecessary.

### Changes

**Backend:**
- `models/enums.py`: Remove `GEMINI_CLI = "gemini_cli"` from `AgentType`
- `models/skill/source.py`: Remove `GEMINI_CLI = AgentType.GEMINI_CLI` from `SkillSourceType`
- `storage/skill/agent.py`: Change `SkillSourceType.GEMINI_CLI` key to `SkillSourceType.GEMINI` in `AGENT_SKILL_REGISTRY`. The path stays `~/.gemini/skills/`
- `llm/backends/gemini_cli.py`: No changes needed (already uses `BackendType.GEMINI`)
- `config/llm_config.py`: Add `"gemini_cli": "gemini"` to `LEGACY_BACKEND_ALIASES` for backward compat

**Frontend:**
- `skill-constants.ts`: Remove `gemini_cli` entries from `SOURCE_COLORS`, `SOURCE_LABELS`, `SOURCE_DESCRIPTIONS`, `ALL_SYNC_TARGETS`

**Tests:**
- Update `test_enum_renames.py` to assert `GEMINI_CLI` no longer exists in `AgentType` or `SkillSourceType`

## 2. Lightweight Context Extraction (Compaction-First)

### Problem

The current `extract_all_contexts()` loads every session JSONL file (1.3 GB across 576 sessions), fully parses each, then formats all steps. Even PRESET_RECOMMENDATION's aggressive truncation can't fit 576 sessions into the 100K token L2 budget. The I/O and parsing alone takes minutes.

### Approach: Compaction Summaries + Metadata Fallback

81% of sessions (469/576) have compaction agent files (`agent-acompact-*.jsonl`). These contain LLM-generated summaries of the session's work — exactly what L2 needs for profile generation. For the remaining 19%, use cached session metadata.

### New Components

**New function: `extract_lightweight_digest()`** in `services/recommendation/extraction.py`

```
Input:  list of session metadata dicts (from store.list_metadata())
Output: (digest_text: str, session_count: int, signal_count: int)
```

Steps:
1. Group sessions by whether they have compaction agents
2. For sessions WITH compaction: read compaction JSONL files directly (skip main trajectory), extract summary text, truncate to 300 chars each
3. For sessions WITHOUT compaction: format metadata as signal line: `"Project: {path} | Tools: {count} | Duration: {dur} | Model: {model}"`
4. Concatenate all signals into a single digest, targeting 30-50K tokens for 576 sessions

**Finding compaction files without loading full session:**

The Claude Code file layout is deterministic:
- Main session: `{projects_dir}/{encoded-path}/{uuid}.jsonl`
- Compaction agents: `{projects_dir}/{encoded-path}/{uuid}/subagents/agent-acompact-*.jsonl`

From the index, we have `(filepath, parser)` for each session. For Claude Code sessions, derive the compaction path:
```python
compaction_dir = filepath.parent / filepath.stem / "subagents"
compaction_files = sorted(compaction_dir.glob("agent-acompact-*.jsonl"))
```

**Reading compaction files directly:**

Compaction JSONL files are small (~50KB). Parse them with the Claude Code parser to get a Trajectory, then extract the AGENT step's message content (the summary). This avoids loading the main session file entirely.

**Output format per session:**

With compaction:
```
--- SESSION {session_id} ---
Project: VibeLens
Compaction summary: [truncated summary text, max 300 chars]
```

Without compaction (metadata only):
```
--- SESSION {session_id} ---
Project: VibeLens | Tools: 45 | Duration: 35min | Model: claude-sonnet-4-20250514
```

### Engine Changes

**New function `_extract_lightweight_digest()`** in `engine.py` calls `extract_lightweight_digest()`:
- Called by `analyze_recommendation()` instead of `extract_all_contexts()`
- Takes no session_ids argument (uses ALL sessions from local store)
- Returns `(digest_text, session_ids, signal_count)` where `digest_text` is ready for L2

**`analyze_recommendation()` signature change:**
- Current: `analyze_recommendation(session_ids, session_token)` — expects explicit IDs
- New: When `session_ids` is empty or None, use all local sessions via lightweight extraction
- Backward compatible: explicit session_ids still work (for web UI use case with selected sessions)

### Performance Target

| Metric | Current (extract_all_contexts) | New (lightweight) |
|--------|-------------------------------|-------------------|
| I/O | 1.3 GB (all sessions) | ~25 MB (compaction files only) |
| Parse time | Minutes | Seconds |
| Output tokens | Exceeds budget | 30-50K tokens |

## 3. `vibelens recommend` CLI Command

### Interface

```
vibelens recommend [--top-n 15] [--config path/to/config.yaml] [--no-open]
```

Options:
- `--top-n`: Maximum recommendations to show (default 15, matches SCORING_TOP_K)
- `--config`: Path to YAML config file (for LLM backend settings)
- `--no-open`: Skip launching browser (just run pipeline and save)

### Flow

1. Load settings and validate LLM backend is configured
2. Get all session metadata from `LocalTrajectoryStore`
3. Extract lightweight digest (compaction summaries + metadata)
4. Print progress at each L1-L4 stage to stderr via `typer.echo()`
5. Run L2 profile → L3 retrieval+scoring → L4 rationale
6. Save result to `RecommendationStore`
7. Unless `--no-open`: start VibeLens server and open browser to `http://{host}:{port}?recommendation={analysis_id}`

### Terminal Output

```
VibeLens v0.10.0

Loading sessions... 576 found (469 with summaries)
Extracting signals... done (32,450 tokens)
Generating profile... done
  Domains: web-dev, api-development
  Languages: python, typescript
  Frameworks: fastapi, react
Retrieving candidates... 30 retrieved, 15 scored
Generating rationales... done

Saved: rec-20260412-abc123 (2 LLM calls, $0.04, 38s)
Opening http://localhost:5555?recommendation=rec-20260412-abc123
```

### Error Handling

- No LLM backend: `"Error: No LLM backend configured. Run 'vibelens serve' and configure in Settings."` → exit 1
- No sessions found: `"No sessions found. VibeLens looks in ~/.claude/, ~/.codex/, ~/.gemini/, ~/.openclaw/"` → exit 1
- No catalog: `"No catalog available. Place catalog.json in ~/.vibelens/catalog/ or ~/.vibelens/data/"` → exit 1
- LLM call fails: Print error, exit 1

### Async Handling

The engine's `analyze_recommendation()` is `async`. The CLI command runs it via:
```python
import asyncio
result = asyncio.run(analyze_recommendation(...))
```

## 4. Frontend Recommendation View

### Trigger

The app reads `?recommendation={analysis_id}` from the URL on load (same pattern as existing `?session=`, `?share=`). When present, the app enters recommendation view mode.

### Data Fetching

Fetches `GET /recommendation/{analysis_id}` → returns `RecommendationResult` with profile, recommendations array, and metadata.

### Layout

Full-page view (replaces normal session list + session view):

**Header bar:**
- Title: `result.title` (e.g., "Top 15 recommendations for your workflow")
- Summary: `result.summary` (e.g., "Based on web-dev, api-development sessions...")
- Profile chips: domains, languages, frameworks as colored pills
- Metadata line: "{len(session_ids)} sessions analyzed | {duration}s | {model} | ${cost}"
- "Back to sessions" button to return to normal view

**Recommendation cards** (scrollable list):
- Type badge: colored pill using existing skill badge colors (cyan for skill, violet for subagent, teal for command, amber for hook, blue for repo)
- Name: bold, large
- Description: 1-2 sentences
- Rationale: the personalized L4 output, displayed in a distinct callout style
- Score bar: horizontal bar showing composite score (0-1)
- Confidence: percentage next to score
- Action buttons:
  - "View on GitHub" → opens `source_url` in new tab
  - "Install" → for file-based types (skill, subagent, command, hook): triggers existing `install-target-dialog` with `install_content`; for repos: shows `install_command` in a copyable code block
- Quality indicator: small star rating or quality badge from `quality_score`

### New Files

- `frontend/src/components/recommendations/recommendation-view.tsx` — main view component (~150 lines)
- `frontend/src/components/recommendations/recommendation-card.tsx` — individual card (~100 lines)
- `frontend/src/components/recommendations/recommendation-constants.ts` — type colors, labels

### App Integration

In `app.tsx`:
- New state: `const [recommendationId] = useState<string | null>(() => params.get("recommendation"))`
- When `recommendationId` is set, render `<RecommendationView>` instead of the normal browse/analyze layout
- The "Back to sessions" button clears `recommendationId` and removes the URL param

### API Types

Add TypeScript interfaces in `frontend/src/types.ts` matching the Python models:
```typescript
interface RecommendationResult {
  analysis_id: string;
  title: string;
  summary: string;
  user_profile: UserProfile;
  recommendations: CatalogRecommendation[];
  model: string;
  created_at: string;
  duration_seconds: number;
  metrics: { cost_usd: number };
  catalog_version: string;
}
```

## Testing Strategy

### Backend Tests

- `test_gemini_merge.py`: Verify `GEMINI_CLI` removed from AgentType and SkillSourceType, `GEMINI` still works
- `test_lightweight_extraction.py`: Test compaction file discovery, summary extraction, metadata fallback, digest formatting. Use real sessions from `~/.claude/` for integration testing.
- `test_recommend_cli.py`: Test CLI command invocation (at minimum: `--help` works, missing backend shows error)
- Run existing recommendation engine tests to verify backward compat

### Frontend Tests

- Manual: open `http://localhost:5555?recommendation=mock-recommendation-001` in demo mode
- Verify cards render, GitHub links work, install dialog triggers

### Integration Test

- Run `vibelens recommend --no-open` against real sessions in `~/.claude/`
- Verify output format, result saved to store, no crashes
- Measure token count and timing

## Scope Boundaries

**In scope:**
- GEMINI/GEMINI_CLI enum merge
- Lightweight extraction function
- CLI recommend command
- Frontend recommendation view

**Out of scope (future):**
- Catalog crawler/builder
- Catalog auto-update
- Recommendation history browsing in web UI (just the single result view for now)
- Embedding-based or hybrid retrieval

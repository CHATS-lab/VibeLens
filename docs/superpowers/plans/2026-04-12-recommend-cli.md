# Recommend CLI, Lightweight Extraction, and GEMINI Merge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the recommendation pipeline usable from the CLI on real-world session data (576+ sessions, 1.3 GB) by adding lightweight extraction, a `vibelens recommend` command, a frontend recommendation view, and merging the GEMINI/GEMINI_CLI enum split.

**Architecture:** Four independent changes wired together: (1) GEMINI_CLI enum removal simplifies the agent type model, (2) a new compaction-first extraction module bypasses full session parsing for CLI-scale data, (3) a `vibelens recommend` CLI command orchestrates the pipeline with backend auto-discovery, and (4) a frontend recommendation view renders interactive results with install actions.

**Tech Stack:** Python 3.10+, Typer CLI, FastAPI, React + TypeScript + Tailwind, Pydantic, asyncio

**Spec:** `docs/superpowers/specs/2026-04-12-recommend-cli-design.md`

---

## File Structure

### Files to Create

| File | Responsibility |
|------|---------------|
| `src/vibelens/services/recommendation/extraction.py` | Lightweight digest extraction from compaction files + diversity sampling |
| `frontend/src/components/recommendations/recommendation-view.tsx` | Full-page recommendation view (header + card list) |
| `frontend/src/components/recommendations/recommendation-card.tsx` | Individual recommendation card with score, install, GitHub link |
| `frontend/src/components/recommendations/recommendation-constants.ts` | Type colors, labels, and badge config |
| `tests/services/recommendation/test_extraction.py` | Tests for lightweight extraction and sampling |
| `tests/test_gemini_merge.py` | Tests asserting GEMINI_CLI is removed |
| `tests/test_recommend_cli.py` | Tests for CLI recommend command |

### Files to Modify

| File | Change |
|------|--------|
| `src/vibelens/models/enums.py` | Remove `GEMINI_CLI` from `AgentType` |
| `src/vibelens/models/skill/source.py` | Remove `GEMINI_CLI` from `SkillSourceType` |
| `src/vibelens/storage/skill/agent.py` | Change `GEMINI_CLI` key to `GEMINI` in `AGENT_SKILL_REGISTRY` |
| `src/vibelens/config/llm_config.py` | Add `"gemini_cli": "gemini"` to `LEGACY_BACKEND_ALIASES` |
| `src/vibelens/services/recommendation/engine.py` | Add lightweight extraction path when `session_ids` is empty |
| `src/vibelens/services/recommendation/__init__.py` | Re-export `extract_lightweight_digest` |
| `src/vibelens/cli.py` | Add `recommend` command and `discover_and_select_backend()` |
| `frontend/src/components/skills/skill-constants.ts` | Remove `gemini_cli` entries |
| `frontend/src/app.tsx` | Add `?recommendation=` URL param and recommendation view routing |
| `frontend/src/types.ts` | Add `RecommendationResult` and related interfaces |
| `tests/models/test_enum_renames.py` | Add assertion that `GEMINI_CLI` no longer exists |

---

## Task 1: GEMINI_CLI Enum Merge — Tests

**Files:**
- Create: `tests/test_gemini_merge.py`
- Modify: `tests/models/test_enum_renames.py:12-15`

- [ ] **Step 1: Write failing tests for GEMINI_CLI removal**

Create `tests/test_gemini_merge.py`:

```python
"""Tests for GEMINI/GEMINI_CLI merge."""
from vibelens.models.enums import AgentType
from vibelens.models.skill.source import SkillSourceType
from vibelens.storage.skill.agent import AGENT_SKILL_REGISTRY


def test_gemini_cli_removed_from_agent_type():
    """GEMINI_CLI no longer exists in AgentType."""
    assert not hasattr(AgentType, "GEMINI_CLI")
    assert AgentType.GEMINI == "gemini"


def test_gemini_cli_removed_from_skill_source_type():
    """GEMINI_CLI no longer exists in SkillSourceType."""
    assert not hasattr(SkillSourceType, "GEMINI_CLI")
    assert SkillSourceType.GEMINI == "gemini"


def test_agent_skill_registry_uses_gemini():
    """AGENT_SKILL_REGISTRY uses GEMINI key, not GEMINI_CLI."""
    assert SkillSourceType.GEMINI in AGENT_SKILL_REGISTRY
    gemini_path = AGENT_SKILL_REGISTRY[SkillSourceType.GEMINI]
    assert "/.gemini/skills" in str(gemini_path)


def test_legacy_alias_maps_gemini_cli():
    """Legacy 'gemini_cli' backend alias maps to 'gemini'."""
    from vibelens.config.llm_config import LEGACY_BACKEND_ALIASES

    assert LEGACY_BACKEND_ALIASES["gemini_cli"] == "gemini"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gemini_merge.py -v`
Expected: FAIL — `GEMINI_CLI` still exists in `AgentType` and `SkillSourceType`

- [ ] **Step 3: Update test_enum_renames.py**

Add to `tests/models/test_enum_renames.py` after the existing `test_agent_type_kimi_renamed` function:

```python
def test_agent_type_gemini_cli_removed():
    """GEMINI_CLI merged into GEMINI."""
    assert AgentType.GEMINI == "gemini"
    assert not hasattr(AgentType, "GEMINI_CLI")
```

- [ ] **Step 4: Commit test files**

```bash
git add tests/test_gemini_merge.py tests/models/test_enum_renames.py
git commit -m "test: add failing tests for GEMINI_CLI removal"
```

---

## Task 2: GEMINI_CLI Enum Merge — Implementation

**Files:**
- Modify: `src/vibelens/models/enums.py:20`
- Modify: `src/vibelens/models/skill/source.py:27`
- Modify: `src/vibelens/storage/skill/agent.py:25`
- Modify: `src/vibelens/config/llm_config.py:63-75`
- Modify: `frontend/src/components/skills/skill-constants.ts`

- [ ] **Step 1: Remove GEMINI_CLI from AgentType**

In `src/vibelens/models/enums.py`, delete the line:

```python
    GEMINI_CLI = "gemini_cli"
```

The enum should go from `GEMINI = "gemini"` directly to `KIMI = "kimi"`.

- [ ] **Step 2: Remove GEMINI_CLI from SkillSourceType**

In `src/vibelens/models/skill/source.py`, delete the line:

```python
    GEMINI_CLI = AgentType.GEMINI_CLI
```

- [ ] **Step 3: Change AGENT_SKILL_REGISTRY key**

In `src/vibelens/storage/skill/agent.py`, change:

```python
    SkillSourceType.GEMINI_CLI: Path.home() / ".gemini" / "skills",
```

to:

```python
    SkillSourceType.GEMINI: Path.home() / ".gemini" / "skills",
```

- [ ] **Step 4: Add legacy alias for backward compat**

In `src/vibelens/config/llm_config.py`, add `"gemini_cli": "gemini"` to `LEGACY_BACKEND_ALIASES`:

```python
LEGACY_BACKEND_ALIASES: dict[str, str] = {
    "anthropic-api": "litellm",
    "openai-api": "litellm",
    "claude-cli": "claude_code",
    "codex-cli": "codex",
    "gemini-cli": "gemini",
    "gemini_cli": "gemini",
    "cursor-cli": "cursor",
    "kimi-cli": "kimi",
    "openclaw-cli": "openclaw",
    "opencode-cli": "opencode",
    "aider-cli": "aider",
    "amp-cli": "amp",
}
```

- [ ] **Step 5: Remove gemini_cli from frontend skill-constants.ts**

In `frontend/src/components/skills/skill-constants.ts`:

Remove from `SOURCE_COLORS`:
```typescript
  gemini_cli: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-700/30",
```

Remove from `SOURCE_LABELS`:
```typescript
  gemini_cli: "gemini_cli",
```

Remove from `SOURCE_DESCRIPTIONS`:
```typescript
  gemini_cli: "Installed in ~/.gemini/skills/",
```

Remove from `ALL_SYNC_TARGETS`:
```typescript
  { key: "gemini_cli", label: "gemini_cli" },
```

- [ ] **Step 6: Run merge tests**

Run: `pytest tests/test_gemini_merge.py tests/models/test_enum_renames.py -v`
Expected: ALL PASS

- [ ] **Step 7: Run full test suite to check for breakage**

Run: `pytest tests/ -v --timeout=30`
Expected: ALL PASS (no code references `AgentType.GEMINI_CLI` except what we removed)

- [ ] **Step 8: Commit**

```bash
git add src/vibelens/models/enums.py src/vibelens/models/skill/source.py src/vibelens/storage/skill/agent.py src/vibelens/config/llm_config.py frontend/src/components/skills/skill-constants.ts
git commit -m "refactor: merge GEMINI_CLI into GEMINI across backend and frontend"
```

---

## Task 3: Lightweight Extraction — Tests

**Files:**
- Create: `tests/services/recommendation/test_extraction.py`

- [ ] **Step 1: Write failing tests for extract_lightweight_digest**

Create `tests/services/recommendation/test_extraction.py`:

```python
"""Tests for lightweight compaction-based extraction."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from vibelens.services.recommendation.extraction import (
    extract_lightweight_digest,
    _sample_sessions,
)


def test_extract_lightweight_digest_with_compaction(tmp_path):
    """Sessions with compaction agents produce summary-based signals."""
    # Create a fake compaction JSONL file
    session_dir = tmp_path / "projects" / "test" / "abc123" / "subagents"
    session_dir.mkdir(parents=True)
    compaction_file = session_dir / "agent-acompact-001.jsonl"
    # Write a minimal JSONL with an assistant message (the summary)
    import json

    lines = [
        json.dumps({
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Implemented auth system with JWT tokens and bcrypt hashing."}],
            },
        }),
    ]
    compaction_file.write_text("\n".join(lines))

    metadata = [
        {
            "session_id": "abc123",
            "project_path": "/home/user/myproject",
            "filepath": str(tmp_path / "projects" / "test" / "abc123.jsonl"),
            "agent_type": "claude_code",
            "model": "claude-sonnet-4-20250514",
            "total_tool_calls": 25,
            "duration_seconds": 600,
        },
    ]

    digest, session_count, signal_count = extract_lightweight_digest(metadata)

    assert session_count == 1
    assert signal_count == 1
    assert "abc123" in digest
    assert "auth system" in digest.lower() or "JWT" in digest


def test_extract_lightweight_digest_metadata_fallback(tmp_path):
    """Sessions without compaction use metadata-only signal."""
    metadata = [
        {
            "session_id": "def456",
            "project_path": "/home/user/other",
            "filepath": str(tmp_path / "nonexistent" / "def456.jsonl"),
            "agent_type": "codex",
            "model": "gpt-4o",
            "total_tool_calls": 10,
            "duration_seconds": 300,
        },
    ]

    digest, session_count, signal_count = extract_lightweight_digest(metadata)

    assert session_count == 1
    assert signal_count == 1
    assert "other" in digest
    assert "Tools: 10" in digest


def test_extract_lightweight_digest_empty():
    """Empty metadata list produces empty digest."""
    digest, session_count, signal_count = extract_lightweight_digest([])

    assert session_count == 0
    assert signal_count == 0
    assert digest == ""


def test_sample_sessions_under_budget():
    """Sessions under budget are returned unchanged."""
    sessions = [
        ("s1", "Short signal", "/project-a", "2026-01-01"),
        ("s2", "Another signal", "/project-b", "2026-01-02"),
    ]
    result = _sample_sessions(sessions, token_budget=80_000)
    assert len(result) == 2


def test_sample_sessions_over_budget():
    """Sampling reduces sessions when over budget."""
    # Create many sessions with large signals
    sessions = [
        (f"s{i}", "x" * 2000, f"/project-{i % 3}", f"2026-01-{i:02d}")
        for i in range(1, 101)
    ]
    result = _sample_sessions(sessions, token_budget=5_000)
    assert len(result) < 100
    # All three projects should still be represented
    project_ids = {sid.split("-")[-1] for sid, _ in result}
    print(f"Sampled {len(result)}/100 sessions")


def test_sample_sessions_diverse_projects():
    """Sampling prefers recent sessions and covers all projects."""
    sessions = []
    for proj in range(5):
        for i in range(20):
            sessions.append(
                (f"p{proj}-s{i}", f"Signal for project {proj}", f"/project-{proj}", f"2026-01-{i+1:02d}")
            )
    result = _sample_sessions(sessions, token_budget=3_000)
    # Should have sessions from multiple projects
    projects_seen = set()
    for sid, _ in result:
        proj_id = sid.split("-")[0]
        projects_seen.add(proj_id)
    assert len(projects_seen) >= 3, f"Only {len(projects_seen)} projects represented"
    print(f"Sampled {len(result)}/100 sessions across {len(projects_seen)} projects")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/recommendation/test_extraction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vibelens.services.recommendation.extraction'`

- [ ] **Step 3: Commit**

```bash
git add tests/services/recommendation/test_extraction.py
git commit -m "test: add failing tests for lightweight extraction and sampling"
```

---

## Task 4: Lightweight Extraction — Implementation

**Files:**
- Create: `src/vibelens/services/recommendation/extraction.py`
- Modify: `src/vibelens/services/recommendation/__init__.py`

- [ ] **Step 1: Create extraction.py**

Create `src/vibelens/services/recommendation/extraction.py`:

```python
"""Lightweight context extraction using compaction summaries.

Reads compaction agent JSONL files (~50KB each) instead of full session
files (~2.3MB each) to produce a digest suitable for the L2 profile
generation step. Falls back to session metadata for sessions without
compaction agents.
"""

import json
from pathlib import Path

from vibelens.llm.tokenizer import count_tokens
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Max characters per compaction summary
SUMMARY_MAX_CHARS = 300
# Default token budget for the digest (leaves room for system prompt overhead)
DIGEST_TOKEN_BUDGET = 80_000
# Max sessions per project in diversity sampling
MAX_PER_PROJECT = 3


def extract_lightweight_digest(
    metadata_list: list[dict],
) -> tuple[str, int, int]:
    """Extract a lightweight digest from session metadata and compaction files.

    For sessions with compaction agents: reads the compaction JSONL directly,
    extracts the summary text, and truncates to SUMMARY_MAX_CHARS.
    For sessions without: formats metadata as a signal line.

    Args:
        metadata_list: List of session metadata dicts from store.list_metadata().

    Returns:
        Tuple of (digest_text, session_count, signal_count).
    """
    if not metadata_list:
        return "", 0, 0

    signals: list[tuple[str, str, str, str]] = []

    for meta in metadata_list:
        session_id = meta.get("session_id", "unknown")
        project_path = meta.get("project_path", "unknown")
        filepath = meta.get("filepath", "")
        timestamp = meta.get("timestamp", meta.get("created_at", ""))

        compaction_text = _read_compaction_summary(filepath)
        if compaction_text:
            signal = _format_compaction_signal(session_id, project_path, compaction_text)
        else:
            signal = _format_metadata_signal(session_id, meta)

        signals.append((session_id, signal, project_path, str(timestamp)))

    sampled = _sample_sessions(signals, token_budget=DIGEST_TOKEN_BUDGET)
    digest = "\n\n".join(signal_text for _, signal_text in sampled)

    total_sessions = len(metadata_list)
    signal_count = len(sampled)
    if signal_count < total_sessions:
        logger.info(
            "Sampled %d/%d sessions (%d tokens)",
            signal_count,
            total_sessions,
            count_tokens(digest),
        )

    return digest, total_sessions, signal_count


def _read_compaction_summary(filepath: str) -> str | None:
    """Read the most recent compaction summary for a session.

    Claude Code layout: {uuid}/subagents/agent-acompact-*.jsonl
    Derives compaction path from the main session filepath.

    Args:
        filepath: Path to the main session JSONL file.

    Returns:
        Summary text from the compaction agent, or None if unavailable.
    """
    if not filepath:
        return None

    session_path = Path(filepath)
    compaction_dir = session_path.parent / session_path.stem / "subagents"
    if not compaction_dir.is_dir():
        return None

    compaction_files = sorted(compaction_dir.glob("agent-acompact-*.jsonl"))
    if not compaction_files:
        return None

    # Read the most recent compaction file (last in sorted order)
    latest = compaction_files[-1]
    return _extract_summary_from_jsonl(latest)


def _extract_summary_from_jsonl(jsonl_path: Path) -> str | None:
    """Extract the assistant's summary text from a compaction JSONL file.

    Scans for the first message with role=assistant and extracts
    the text content, which is the compaction summary.

    Args:
        jsonl_path: Path to the compaction agent JSONL file.

    Returns:
        Summary text truncated to SUMMARY_MAX_CHARS, or None.
    """
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                message = entry.get("message", entry)
                if message.get("role") != "assistant":
                    continue

                content = message.get("content", "")
                if isinstance(content, list):
                    text_parts = [
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    text = " ".join(text_parts)
                elif isinstance(content, str):
                    text = content
                else:
                    continue

                text = text.strip()
                if text:
                    return text[:SUMMARY_MAX_CHARS]
    except OSError as exc:
        logger.debug("Failed to read compaction file %s: %s", jsonl_path, exc)

    return None


def _format_compaction_signal(session_id: str, project_path: str, summary: str) -> str:
    """Format a session signal from a compaction summary.

    Args:
        session_id: Session identifier.
        project_path: Project directory path.
        summary: Compaction summary text.

    Returns:
        Formatted signal string.
    """
    project_name = Path(project_path).name if project_path else "unknown"
    return f"--- SESSION {session_id} ---\nProject: {project_name}\nCompaction summary: {summary}"


def _format_metadata_signal(session_id: str, meta: dict) -> str:
    """Format a session signal from metadata only (no compaction available).

    Args:
        session_id: Session identifier.
        meta: Session metadata dict.

    Returns:
        Formatted signal string.
    """
    project_name = Path(meta.get("project_path", "unknown")).name
    tool_count = meta.get("total_tool_calls", 0)
    duration = meta.get("duration_seconds", 0)
    model = meta.get("model", "unknown")
    dur_min = round(duration / 60) if duration else 0
    return (
        f"--- SESSION {session_id} ---\n"
        f"Project: {project_name} | Tools: {tool_count} | Duration: {dur_min}min | Model: {model}"
    )


def _sample_sessions(
    sessions: list[tuple[str, str, str, str]],
    token_budget: int = DIGEST_TOKEN_BUDGET,
) -> list[tuple[str, str]]:
    """Sample a diverse, representative subset of sessions to fit within token budget.

    Uses project-stratified sampling: groups by project, selects up to
    MAX_PER_PROJECT most recent sessions per project, then trims by
    project activity until under budget.

    Args:
        sessions: List of (session_id, signal_text, project_path, timestamp) tuples.
        token_budget: Maximum tokens for the combined digest.

    Returns:
        List of (session_id, signal_text) tuples fitting within budget.
    """
    if not sessions:
        return []

    # Check if everything fits without sampling
    combined = "\n\n".join(signal for _, signal, _, _ in sessions)
    if count_tokens(combined) <= token_budget:
        return [(sid, signal) for sid, signal, _, _ in sessions]

    # Group by project
    project_groups: dict[str, list[tuple[str, str, str]]] = {}
    for sid, signal, project, timestamp in sessions:
        project_groups.setdefault(project, []).append((sid, signal, timestamp))

    # Within each project, sort by timestamp (newest first), keep top MAX_PER_PROJECT
    selected: list[tuple[str, str, str]] = []
    for project, group in project_groups.items():
        group.sort(key=lambda x: x[2], reverse=True)
        selected.extend(group[:MAX_PER_PROJECT])

    # Check if stratified selection fits
    combined = "\n\n".join(signal for _, signal, _ in selected)
    if count_tokens(combined) <= token_budget:
        return [(sid, signal) for sid, signal, _ in selected]

    # Still over budget: rank projects by session count (most active first),
    # drop least-active projects until under budget
    project_by_count = sorted(project_groups.keys(), key=lambda p: len(project_groups[p]), reverse=True)
    result: list[tuple[str, str]] = []
    running_text = ""
    for project in project_by_count:
        group = project_groups[project]
        group.sort(key=lambda x: x[2], reverse=True)
        for sid, signal, _ in group[:MAX_PER_PROJECT]:
            candidate = running_text + "\n\n" + signal if running_text else signal
            if count_tokens(candidate) > token_budget:
                return result
            running_text = candidate
            result.append((sid, signal))

    return result
```

- [ ] **Step 2: Update __init__.py**

In `src/vibelens/services/recommendation/__init__.py`, add the new export:

```python
from vibelens.services.recommendation.engine import analyze_recommendation, estimate_recommendation
from vibelens.services.recommendation.extraction import extract_lightweight_digest

__all__ = ["analyze_recommendation", "estimate_recommendation", "extract_lightweight_digest"]
```

- [ ] **Step 3: Run extraction tests**

Run: `pytest tests/services/recommendation/test_extraction.py -v -s`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/vibelens/services/recommendation/extraction.py src/vibelens/services/recommendation/__init__.py
git commit -m "feat: add lightweight compaction-based extraction with diversity sampling"
```

---

## Task 5: Engine — Lightweight Extraction Path

**Files:**
- Modify: `src/vibelens/services/recommendation/engine.py:117-180`

- [ ] **Step 1: Write test for engine lightweight path**

Add to `tests/services/recommendation/test_engine.py`:

```python
def test_engine_exports_lightweight_path():
    """Engine accepts empty session_ids for lightweight extraction."""
    from vibelens.services.recommendation.engine import _run_pipeline

    # Verify the function signature accepts empty session_ids
    import inspect

    sig = inspect.signature(_run_pipeline)
    params = list(sig.parameters.keys())
    assert "session_ids" in params


def test_analyze_recommendation_signature():
    """analyze_recommendation accepts optional session_ids."""
    import inspect

    from vibelens.services.recommendation.engine import analyze_recommendation

    sig = inspect.signature(analyze_recommendation)
    session_ids_param = sig.parameters["session_ids"]
    # Should have a default (None or empty list)
    assert session_ids_param.default is not inspect.Parameter.empty
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/services/recommendation/test_engine.py::test_analyze_recommendation_signature -v`
Expected: FAIL — `session_ids` has no default value currently

- [ ] **Step 3: Update analyze_recommendation signature and _run_pipeline**

In `src/vibelens/services/recommendation/engine.py`:

Update the import block to add:

```python
from vibelens.services.recommendation.extraction import extract_lightweight_digest
from vibelens.services.session.store_resolver import list_all_metadata
```

Update `analyze_recommendation` signature (line 117):

```python
async def analyze_recommendation(
    session_ids: list[str] | None = None, session_token: str | None = None
) -> RecommendationResult:
```

Update `_run_pipeline` signature (line 157):

```python
async def _run_pipeline(
    session_ids: list[str] | None, session_token: str | None, analysis_id: str
) -> RecommendationResult:
```

In `_run_pipeline`, replace the L1 block (lines 174-179) with:

```python
    # L1: Context extraction
    if session_ids:
        # Standard path: web UI with explicit session selection
        context_set = extract_all_contexts(
            session_ids=session_ids, session_token=session_token, params=PRESET_RECOMMENDATION
        )
        if not context_set.contexts:
            raise ValueError(f"No sessions could be loaded from: {session_ids}")
        loaded_session_ids = context_set.session_ids
        skipped_session_ids = context_set.skipped_session_ids
        digest = format_batch_digest(context_set)
    else:
        # Lightweight path: CLI with all local sessions
        all_metadata = list_all_metadata(session_token)
        if not all_metadata:
            raise ValueError("No sessions found in local stores.")
        digest, total_count, signal_count = extract_lightweight_digest(all_metadata)
        loaded_session_ids = [m.get("session_id", "") for m in all_metadata]
        skipped_session_ids = []
        logger.info(
            "Lightweight extraction: %d sessions, %d signals",
            total_count,
            signal_count,
        )
```

Update the rest of `_run_pipeline` to use `loaded_session_ids` and `skipped_session_ids` instead of `context_set.session_ids` and `context_set.skipped_session_ids`. Specifically, replace references to `context_set.session_ids` with `loaded_session_ids` and `context_set.skipped_session_ids` with `skipped_session_ids` in:
- The `_build_empty_result` call (around line 185)
- The `_generate_profile` call (around line 203)
- The final `RecommendationResult` construction (around line 233)

Update the cache key function to handle None:

```python
def _recommendation_cache_key(session_ids: list[str] | None) -> str:
    """Generate a cache key from sorted session IDs."""
    if not session_ids:
        return "recommendation:all-local"
    sorted_ids = ",".join(sorted(session_ids))
    return f"recommendation:{hashlib.sha256(sorted_ids.encode()).hexdigest()[:16]}"
```

- [ ] **Step 4: Run engine tests**

Run: `pytest tests/services/recommendation/test_engine.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibelens/services/recommendation/engine.py tests/services/recommendation/test_engine.py
git commit -m "feat: add lightweight extraction path to engine for CLI use"
```

---

## Task 6: CLI Backend Auto-Discovery

**Files:**
- Modify: `src/vibelens/cli.py`

- [ ] **Step 1: Write test for discover_and_select_backend**

Create `tests/test_recommend_cli.py`:

```python
"""Tests for the vibelens recommend CLI command."""
import shutil

from typer.testing import CliRunner

from vibelens.cli import app, discover_and_select_backend

runner = CliRunner()


def test_recommend_help():
    """vibelens recommend --help works."""
    result = runner.invoke(app, ["recommend", "--help"])
    assert result.exit_code == 0
    assert "--top-n" in result.output
    assert "--no-open" in result.output


def test_discover_finds_available_backends(monkeypatch):
    """discover_and_select_backend finds CLIs in PATH."""
    # Mock shutil.which to simulate 'gemini' being available
    original_which = shutil.which

    def mock_which(name):
        if name == "gemini":
            return "/usr/local/bin/gemini"
        return None

    monkeypatch.setattr(shutil, "which", mock_which)

    from vibelens.llm.backends import _CLI_BACKEND_REGISTRY

    backends = []
    for backend_type, (module_path, class_name) in _CLI_BACKEND_REGISTRY.items():
        # Lazy-import to get cli_executable
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        instance = cls()
        if shutil.which(instance.cli_executable):
            backends.append((backend_type, instance))

    assert len(backends) >= 1
    print(f"Found {len(backends)} available backends")
```

- [ ] **Step 2: Run to verify test infrastructure works**

Run: `pytest tests/test_recommend_cli.py::test_recommend_help -v`
Expected: FAIL — `recommend` command doesn't exist yet

- [ ] **Step 3: Add discover_and_select_backend and recommend command to cli.py**

In `src/vibelens/cli.py`, add imports at the top:

```python
import asyncio
import importlib
import shutil

import typer
import uvicorn

from vibelens import __version__
from vibelens.config import load_settings
from vibelens.config.llm_config import LLMConfig
from vibelens.llm.pricing import lookup_pricing
from vibelens.models.llm.inference import BackendType
```

Remove the old `import threading` and `import webbrowser` (keep them but they'll coexist — actually keep `threading` and `webbrowser`, just add the new imports).

Add after the existing `build_catalog` command:

```python
def discover_and_select_backend() -> LLMConfig | None:
    """Scan system for available CLI backends and let user pick one.

    Checks each registered CLI backend's executable via shutil.which().
    Presents an interactive numbered list with default models and pricing.

    Returns:
        LLMConfig for the selected backend, or None if user cancels or none found.
    """
    from vibelens.llm.backends import _CLI_BACKEND_REGISTRY

    available: list[tuple[BackendType, str, str, str]] = []

    for backend_type, (module_path, class_name) in _CLI_BACKEND_REGISTRY.items():
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        instance = cls()
        if shutil.which(instance.cli_executable) is None:
            continue
        default_model = instance.default_model or "default"
        pricing = lookup_pricing(default_model)
        if pricing:
            est_input = 50_000 * pricing.input_per_mtok / 1_000_000
            est_output = 8_000 * pricing.output_per_mtok / 1_000_000
            cost_str = f"~${est_input + est_output:.2f}/run"
        else:
            cost_str = "free" if "gemini" in default_model.lower() else "unknown"
        available.append((backend_type, instance.cli_executable, default_model, cost_str))

    if not available:
        return None

    typer.echo("\nNo LLM backend configured. Found available backends:\n")
    for idx, (bt, exe, model, cost) in enumerate(available, 1):
        typer.echo(f"  {idx}. {bt.value:<14} ({exe:<10}) → {model:<25} {cost}")
    typer.echo()

    choice = typer.prompt(f"Pick a backend [1-{len(available)}]", type=int)
    if choice < 1 or choice > len(available):
        typer.echo("Invalid choice.")
        return None

    selected_bt, _, selected_model, _ = available[choice - 1]
    typer.echo(f"\nUsing {selected_bt.value} with {selected_model}")

    return LLMConfig(backend=selected_bt, model=selected_model)


@app.command()
def recommend(
    top_n: int = typer.Option(15, "--top-n", help="Maximum recommendations to show"),
    config: Path | None = typer.Option(None, help="Path to YAML config file"),  # noqa: B008
    no_open: bool = typer.Option(False, "--no-open", help="Skip launching browser"),
) -> None:
    """Run the recommendation pipeline on all local sessions."""
    from vibelens.deps import get_llm_config, get_settings, set_llm_config
    from vibelens.services.recommendation.engine import SCORING_TOP_K, analyze_recommendation

    typer.echo(f"VibeLens v{__version__}\n")

    settings = load_settings(config_path=config)

    # Check if backend is configured; if not, run auto-discovery
    llm_config = get_llm_config()
    if llm_config.backend == BackendType.DISABLED:
        discovered = discover_and_select_backend()
        if discovered is None:
            typer.echo(
                "No LLM backend available. Install a supported agent CLI "
                "(claude, gemini, codex, etc.) or configure an API key."
            )
            raise typer.Exit(code=1)
        set_llm_config(discovered)
        typer.echo(f"Saved to {get_settings().settings_path or '~/.vibelens/settings.json'}\n")

    # Run pipeline
    typer.echo("Loading sessions...", nl=False)
    from vibelens.services.session.store_resolver import list_all_metadata

    all_metadata = list_all_metadata(session_token=None)
    if not all_metadata:
        typer.echo(
            "\nNo sessions found. VibeLens looks in ~/.claude/, ~/.codex/, ~/.gemini/, ~/.openclaw/"
        )
        raise typer.Exit(code=1)

    compaction_count = sum(
        1 for m in all_metadata if _has_compaction_files(m.get("filepath", ""))
    )
    typer.echo(f" {len(all_metadata)} found ({compaction_count} with summaries)")

    typer.echo("Running recommendation pipeline...")
    try:
        result = asyncio.run(analyze_recommendation(session_ids=None, session_token=None))
    except Exception as exc:
        typer.echo(f"\nError: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"  Profile: {', '.join(result.user_profile.domains[:3])}")
    typer.echo(f"  Languages: {', '.join(result.user_profile.languages[:3])}")
    typer.echo(f"  Recommendations: {len(result.recommendations)}")

    cost_str = f"${result.metrics.cost_usd:.2f}" if result.metrics.cost_usd else "n/a"
    typer.echo(
        f"\nSaved: {result.analysis_id} "
        f"({result.duration_seconds}s, {cost_str})"
    )

    if not no_open:
        bind_host = settings.host
        bind_port = settings.port
        url = f"http://{bind_host}:{bind_port}?recommendation={result.analysis_id}"
        typer.echo(f"Opening {url}")

        timer = threading.Timer(
            BROWSER_OPEN_DELAY_SECONDS, _open_browser, args=[url]
        )
        timer.daemon = True
        timer.start()

        uvicorn.run(
            "vibelens.app:create_app",
            factory=True,
            host=bind_host,
            port=bind_port,
            reload=False,
        )


def _has_compaction_files(filepath: str) -> bool:
    """Check if a session has compaction agent files without loading it."""
    if not filepath:
        return False
    session_path = Path(filepath)
    compaction_dir = session_path.parent / session_path.stem / "subagents"
    if not compaction_dir.is_dir():
        return False
    return any(compaction_dir.glob("agent-acompact-*.jsonl"))
```

- [ ] **Step 4: Run CLI tests**

Run: `pytest tests/test_recommend_cli.py -v -s`
Expected: ALL PASS

- [ ] **Step 5: Lint check**

Run: `ruff check src/vibelens/cli.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/vibelens/cli.py tests/test_recommend_cli.py
git commit -m "feat: add vibelens recommend CLI with backend auto-discovery"
```

---

## Task 7: Frontend — TypeScript Types

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Add recommendation interfaces to types.ts**

Add at the end of `frontend/src/types.ts`:

```typescript
/** Recommendation pipeline result from the backend. */
export interface RecommendationResult {
  analysis_id: string;
  title: string;
  summary: string;
  user_profile: UserProfile;
  recommendations: CatalogRecommendation[];
  session_ids: string[];
  skipped_session_ids: string[];
  model: string;
  created_at: string;
  duration_seconds: number | null;
  metrics: { cost_usd: number | null };
  catalog_version: string;
}

export interface UserProfile {
  domains: string[];
  languages: string[];
  frameworks: string[];
  agent_platforms: string[];
  bottlenecks: string[];
  workflow_style: string;
  search_keywords: string[];
}

export interface CatalogRecommendation {
  item_id: string;
  item_type: string;
  user_label: string;
  name: string;
  description: string;
  rationale: string;
  confidence: number;
  quality_score: number;
  score: number;
  install_method: string | null;
  install_command: string | null;
  has_content: boolean;
  source_url: string | null;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat: add RecommendationResult TypeScript interfaces"
```

---

## Task 8: Frontend — Recommendation Constants

**Files:**
- Create: `frontend/src/components/recommendations/recommendation-constants.ts`

- [ ] **Step 1: Create recommendation constants**

Create `frontend/src/components/recommendations/recommendation-constants.ts`:

```typescript
/** Color classes for recommendation item type badges. */
export const ITEM_TYPE_COLORS: Record<string, string> = {
  skill: "bg-cyan-100 text-cyan-800 border-cyan-300 dark:bg-cyan-900/30 dark:text-cyan-400 dark:border-cyan-700/30",
  subagent: "bg-violet-100 text-violet-800 border-violet-300 dark:bg-violet-900/30 dark:text-violet-400 dark:border-violet-700/30",
  command: "bg-teal-100 text-teal-800 border-teal-300 dark:bg-teal-900/30 dark:text-teal-400 dark:border-teal-700/30",
  hook: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-700/30",
  repo: "bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-700/30",
};

/** Human-readable labels for item types. */
export const ITEM_TYPE_LABELS: Record<string, string> = {
  skill: "Skill",
  subagent: "Sub-agent",
  command: "Command",
  hook: "Hook",
  repo: "Repository",
};

/** Score bar color based on score value. */
export function scoreColor(score: number): string {
  if (score >= 0.7) return "bg-emerald-500 dark:bg-emerald-400";
  if (score >= 0.4) return "bg-amber-500 dark:bg-amber-400";
  return "bg-zinc-400 dark:bg-zinc-500";
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/recommendations/recommendation-constants.ts
git commit -m "feat: add recommendation type constants and color config"
```

---

## Task 9: Frontend — Recommendation Card Component

**Files:**
- Create: `frontend/src/components/recommendations/recommendation-card.tsx`

- [ ] **Step 1: Create recommendation card**

Create `frontend/src/components/recommendations/recommendation-card.tsx`:

```tsx
import { ExternalLink, Download } from "lucide-react";
import type { CatalogRecommendation } from "../../types";
import { ITEM_TYPE_COLORS, ITEM_TYPE_LABELS, scoreColor } from "./recommendation-constants";

interface RecommendationCardProps {
  recommendation: CatalogRecommendation;
  rank: number;
  onInstall: (rec: CatalogRecommendation) => void;
}

export function RecommendationCard({ recommendation: rec, rank, onInstall }: RecommendationCardProps) {
  const typeColor = ITEM_TYPE_COLORS[rec.item_type] ?? ITEM_TYPE_COLORS.skill;
  const typeLabel = ITEM_TYPE_LABELS[rec.item_type] ?? rec.user_label;
  const barColor = scoreColor(rec.score);
  const barWidth = `${Math.round(rec.score * 100)}%`;

  return (
    <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800/50 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-zinc-400 dark:text-zinc-500 w-6 shrink-0">
            #{rank}
          </span>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${typeColor}`}>
            {typeLabel}
          </span>
          <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100 truncate">
            {rec.name}
          </h3>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {rec.source_url && (
            <a
              href={rec.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
              title="View on GitHub"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
          {(rec.has_content || rec.install_command) && (
            <button
              onClick={() => onInstall(rec)}
              className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
              title="Install"
            >
              <Download className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-zinc-600 dark:text-zinc-300">{rec.description}</p>

      {/* Rationale callout */}
      <div className="rounded-md bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 px-3 py-2">
        <p className="text-sm text-zinc-700 dark:text-zinc-300 italic">{rec.rationale}</p>
      </div>

      {/* Score bar + confidence */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-1.5 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
          <div className={`h-full rounded-full ${barColor}`} style={{ width: barWidth }} />
        </div>
        <span className="text-xs text-zinc-500 dark:text-zinc-400 tabular-nums shrink-0">
          {Math.round(rec.confidence * 100)}% match
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/recommendations/recommendation-card.tsx
git commit -m "feat: add recommendation card component with score bar and actions"
```

---

## Task 10: Frontend — Recommendation View Component

**Files:**
- Create: `frontend/src/components/recommendations/recommendation-view.tsx`

- [ ] **Step 1: Create recommendation view**

Create `frontend/src/components/recommendations/recommendation-view.tsx`:

```tsx
import { ArrowLeft, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { CatalogRecommendation, RecommendationResult } from "../../types";
import { useAppContext } from "../../app";
import { RecommendationCard } from "./recommendation-card";

interface RecommendationViewProps {
  analysisId: string;
  onBack: () => void;
}

export function RecommendationView({ analysisId, onBack }: RecommendationViewProps) {
  const { fetchWithToken } = useAppContext();
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchWithToken(`/recommendation/${analysisId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load recommendation: ${res.status}`);
        return res.json();
      })
      .then((data) => setResult(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [analysisId, fetchWithToken]);

  const handleInstall = useCallback((rec: CatalogRecommendation) => {
    if (rec.install_command) {
      navigator.clipboard.writeText(rec.install_command);
    }
    // TODO: integrate with install-target-dialog for file-based installs
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-zinc-400" />
      </div>
    );
  }

  if (error || !result) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">{error ?? "No result found"}</p>
        <button onClick={onBack} className="text-sm text-cyan-600 dark:text-cyan-400 hover:underline">
          Back to sessions
        </button>
      </div>
    );
  }

  const costStr = result.metrics?.cost_usd != null ? `$${result.metrics.cost_usd.toFixed(2)}` : "";
  const durationStr = result.duration_seconds != null ? `${result.duration_seconds}s` : "";
  const metaParts = [
    `${result.session_ids.length} sessions analyzed`,
    durationStr,
    result.model,
    costStr,
  ].filter(Boolean);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="border-b border-zinc-200 dark:border-zinc-700 px-6 py-4 space-y-2 shrink-0">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to sessions
        </button>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">{result.title}</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-300">{result.summary}</p>

        {/* Profile pills */}
        <div className="flex flex-wrap gap-1.5">
          {result.user_profile.domains.map((d) => (
            <span key={d} className="px-2 py-0.5 text-xs rounded-full bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400">
              {d}
            </span>
          ))}
          {result.user_profile.languages.map((l) => (
            <span key={l} className="px-2 py-0.5 text-xs rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
              {l}
            </span>
          ))}
          {result.user_profile.frameworks.map((f) => (
            <span key={f} className="px-2 py-0.5 text-xs rounded-full bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400">
              {f}
            </span>
          ))}
        </div>

        <p className="text-xs text-zinc-400 dark:text-zinc-500">{metaParts.join(" · ")}</p>
      </div>

      {/* Card list */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {result.recommendations.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400 text-center py-8">
            No recommendations found.
          </p>
        ) : (
          result.recommendations.map((rec, idx) => (
            <RecommendationCard
              key={rec.item_id}
              recommendation={rec}
              rank={idx + 1}
              onInstall={handleInstall}
            />
          ))
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/recommendations/recommendation-view.tsx
git commit -m "feat: add recommendation view with header, profile pills, and card list"
```

---

## Task 11: Frontend — App Integration

**Files:**
- Modify: `frontend/src/app.tsx`

- [ ] **Step 1: Add recommendation URL param and state**

In `frontend/src/app.tsx`, add state for recommendation ID after the `shareToken` state (around line 92):

```typescript
  const [recommendationId, setRecommendationId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("recommendation") || null;
  });
```

- [ ] **Step 2: Add import for RecommendationView**

Add at the top with other component imports:

```typescript
import { RecommendationView } from "./components/recommendations/recommendation-view";
```

- [ ] **Step 3: Add recommendation view routing**

In the main render, add a condition that renders `RecommendationView` when `recommendationId` is set. Find where the `shareToken` renders `SharedSessionView` (there's likely a pattern like `if (shareToken) return <SharedSessionView .../>`) and add a similar block after it:

```typescript
  if (recommendationId) {
    return (
      <AppContext.Provider value={contextValue}>
        <RecommendationView
          analysisId={recommendationId}
          onBack={() => {
            setRecommendationId(null);
            const url = new URL(window.location.href);
            url.searchParams.delete("recommendation");
            window.history.replaceState({}, "", url.toString());
          }}
        />
      </AppContext.Provider>
    );
  }
```

- [ ] **Step 4: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds with zero errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app.tsx
git commit -m "feat: add recommendation URL param routing to app"
```

---

## Task 12: Full Integration Test

**Files:** No new files — testing existing code together.

- [ ] **Step 1: Run all Python tests**

Run: `pytest tests/ -v --timeout=30`
Expected: ALL PASS

- [ ] **Step 2: Run ruff linter**

Run: `ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit any fixes**

If any tests or lint issues surfaced, fix and commit:

```bash
git add -A
git commit -m "fix: resolve integration issues from recommend CLI implementation"
```

---

## Task 13: Manual CLI Test with Real Sessions

**Files:** No changes — validation only.

- [ ] **Step 1: Test CLI help**

Run: `vibelens recommend --help`
Expected: Shows `--top-n`, `--config`, `--no-open` options

- [ ] **Step 2: Test with --no-open**

Run: `vibelens recommend --no-open`
Expected: Pipeline runs against real sessions in `~/.claude/`, prints progress, saves result. Verify:
- Session count matches expected (~576)
- Compaction summary count is ~80% of sessions
- Pipeline completes in under 60 seconds
- Result ID is printed

- [ ] **Step 3: Verify saved result loads**

Run: `python -c "from vibelens.deps import get_recommendation_store; store = get_recommendation_store(); print([m.analysis_id for m in store.list_metadata()])"`
Expected: The result from step 2 appears in the list

- [ ] **Step 4: Document findings**

Note any issues with extraction, token counts, or timing. If the digest exceeds 80K tokens, the sampling should engage automatically.

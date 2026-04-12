# Recommendation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the recommendation pipeline (L1-L4 engine) with prompts refactoring, AgentType/BackendType rename to official names, new API endpoints, CLI commands, and config fields.

**Architecture:** 4-layer recommendation engine — L1 context extraction (no LLM), L2 profile generation (1 LLM call), L3 TF-IDF retrieval + scoring (no LLM), L4 rationale generation (1 LLM call). Plus prompts refactoring (rename skill_* → domain-specific), AgentType/BackendType official naming, catalog loader, and recommendation API routes.

**Tech Stack:** Python 3.10+, Pydantic, FastAPI, Jinja2, scikit-learn (TF-IDF), Typer CLI

**Spec reference:** `docs/spec/spec-personalization-pipeline.md` — Migration phases B (items 11-15), C (items 16-19, 23), D (items 24-30).

---

### Task 1: Refactor prompts/ — rename files and split templates

Rename `skill_creation.py` → `creation.py`, `skill_evolution.py` → `evolution.py`. Delete `skill_retrieval.py`. Split `templates/skill/` into `templates/creation/` and `templates/evolution/`. Create empty `templates/recommendation/` directory. Update all imports.

**Files:**
- Rename: `src/vibelens/prompts/skill_creation.py` → `src/vibelens/prompts/creation.py`
- Rename: `src/vibelens/prompts/skill_evolution.py` → `src/vibelens/prompts/evolution.py`
- Delete: `src/vibelens/prompts/skill_retrieval.py`
- Move: `src/vibelens/prompts/templates/skill/creation_*.j2` → `src/vibelens/prompts/templates/creation/`
- Move: `src/vibelens/prompts/templates/skill/evolution_*.j2` → `src/vibelens/prompts/templates/evolution/`
- Delete: `src/vibelens/prompts/templates/skill/retrieval_*.j2`
- Delete: `src/vibelens/prompts/templates/skill/` (empty after moves)
- Create: `src/vibelens/prompts/templates/recommendation/` (empty dir, populated in Task 6)
- Modify: `src/vibelens/prompts/__init__.py`
- Modify: `src/vibelens/services/skill/retrieval.py` (remove retrieval prompt import — file will be deleted in Plan 3)
- Modify: `src/vibelens/services/skill/creation.py` (update import path)
- Modify: `src/vibelens/services/skill/evolution.py` (update import path)
- Test: `tests/prompts/test_prompts_refactor.py`

- [ ] **Step 1: Write test for renamed prompts**

```python
# tests/prompts/test_prompts_refactor.py
"""Tests for the prompts/ refactoring — renamed files and split templates."""
from pathlib import Path


def test_creation_prompts_importable():
    """creation.py exports all three creation prompts."""
    from vibelens.prompts.creation import (
        SKILL_CREATION_GENERATE_PROMPT,
        SKILL_CREATION_PROPOSAL_PROMPT,
        SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT,
    )
    assert SKILL_CREATION_PROPOSAL_PROMPT.task_id == "skill_creation_proposal"
    assert SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT.task_id == "skill_creation_proposal_synthesis"
    assert SKILL_CREATION_GENERATE_PROMPT.task_id == "skill_creation_generate"


def test_evolution_prompts_importable():
    """evolution.py exports all three evolution prompts."""
    from vibelens.prompts.evolution import (
        SKILL_EVOLUTION_EDIT_PROMPT,
        SKILL_EVOLUTION_PROPOSAL_PROMPT,
        SKILL_EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT,
    )
    assert SKILL_EVOLUTION_PROPOSAL_PROMPT.task_id == "skill_evolution_proposal"
    assert SKILL_EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT.task_id == "skill_evolution_proposal_synthesis"
    assert SKILL_EVOLUTION_EDIT_PROMPT.task_id == "skill_evolution_edit"


def test_old_skill_retrieval_removed():
    """skill_retrieval.py should no longer exist."""
    import importlib
    try:
        importlib.import_module("vibelens.prompts.skill_retrieval")
        assert False, "skill_retrieval.py should have been deleted"
    except ModuleNotFoundError:
        pass


def test_creation_templates_in_creation_dir():
    """Creation templates live under templates/creation/."""
    from vibelens.models.llm.prompts import TEMPLATES_DIR
    creation_dir = TEMPLATES_DIR / "creation"
    assert creation_dir.is_dir()
    expected = [
        "creation_proposal_system.j2",
        "creation_proposal_user.j2",
        "creation_proposal_synthesis_system.j2",
        "creation_proposal_synthesis_user.j2",
        "creation_system.j2",
        "creation_user.j2",
    ]
    for name in expected:
        assert (creation_dir / name).is_file(), f"Missing {name}"


def test_evolution_templates_in_evolution_dir():
    """Evolution templates live under templates/evolution/."""
    from vibelens.models.llm.prompts import TEMPLATES_DIR
    evolution_dir = TEMPLATES_DIR / "evolution"
    assert evolution_dir.is_dir()
    expected = [
        "evolution_proposal_system.j2",
        "evolution_proposal_user.j2",
        "evolution_proposal_synthesis_system.j2",
        "evolution_proposal_synthesis_user.j2",
        "evolution_system.j2",
        "evolution_user.j2",
    ]
    for name in expected:
        assert (evolution_dir / name).is_file(), f"Missing {name}"


def test_old_skill_template_dir_removed():
    """templates/skill/ should no longer exist."""
    from vibelens.models.llm.prompts import TEMPLATES_DIR
    assert not (TEMPLATES_DIR / "skill").exists()


def test_recommendation_template_dir_exists():
    """templates/recommendation/ directory exists (populated later)."""
    from vibelens.models.llm.prompts import TEMPLATES_DIR
    assert (TEMPLATES_DIR / "recommendation").is_dir()


def test_prompt_registry_updated():
    """PROMPT_REGISTRY references only creation and evolution prompts (no retrieval)."""
    from vibelens.prompts import PROMPT_REGISTRY
    assert "skill_retrieval" not in PROMPT_REGISTRY
    assert "skill_evolution_proposal" in PROMPT_REGISTRY
    # Friction still registered
    assert "friction_analysis" in PROMPT_REGISTRY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/prompts/test_prompts_refactor.py -v`
Expected: FAIL — old files still exist, templates not moved yet.

- [ ] **Step 3: Move creation templates**

Move all `creation_*` templates from `templates/skill/` to `templates/creation/`:

```bash
mkdir -p src/vibelens/prompts/templates/creation
mv src/vibelens/prompts/templates/skill/creation_proposal_system.j2 src/vibelens/prompts/templates/creation/
mv src/vibelens/prompts/templates/skill/creation_proposal_user.j2 src/vibelens/prompts/templates/creation/
mv src/vibelens/prompts/templates/skill/creation_proposal_synthesis_system.j2 src/vibelens/prompts/templates/creation/
mv src/vibelens/prompts/templates/skill/creation_proposal_synthesis_user.j2 src/vibelens/prompts/templates/creation/
mv src/vibelens/prompts/templates/skill/creation_system.j2 src/vibelens/prompts/templates/creation/
mv src/vibelens/prompts/templates/skill/creation_user.j2 src/vibelens/prompts/templates/creation/
```

- [ ] **Step 4: Move evolution templates**

```bash
mkdir -p src/vibelens/prompts/templates/evolution
mv src/vibelens/prompts/templates/skill/evolution_proposal_system.j2 src/vibelens/prompts/templates/evolution/
mv src/vibelens/prompts/templates/skill/evolution_proposal_user.j2 src/vibelens/prompts/templates/evolution/
mv src/vibelens/prompts/templates/skill/evolution_proposal_synthesis_system.j2 src/vibelens/prompts/templates/evolution/
mv src/vibelens/prompts/templates/skill/evolution_proposal_synthesis_user.j2 src/vibelens/prompts/templates/evolution/
mv src/vibelens/prompts/templates/skill/evolution_system.j2 src/vibelens/prompts/templates/evolution/
mv src/vibelens/prompts/templates/skill/evolution_user.j2 src/vibelens/prompts/templates/evolution/
```

- [ ] **Step 5: Delete retrieval templates and skill/ directory**

```bash
rm src/vibelens/prompts/templates/skill/retrieval_system.j2
rm src/vibelens/prompts/templates/skill/retrieval_user.j2
rm src/vibelens/prompts/templates/skill/retrieval_synthesis_system.j2
rm src/vibelens/prompts/templates/skill/retrieval_synthesis_user.j2
rmdir src/vibelens/prompts/templates/skill
mkdir -p src/vibelens/prompts/templates/recommendation
```

- [ ] **Step 6: Rename prompt Python files and update template paths**

Rename `skill_creation.py` → `creation.py`. Update `load_template()` paths from `"skill/creation_*"` to `"creation/creation_*"`.

```python
# src/vibelens/prompts/creation.py  (renamed from skill_creation.py)
"""Prompts for element creation: proposals, synthesis, and generation.

Two-step pipeline:
1. Proposals: detect patterns and generate lightweight creation proposals
2. Generation: generate full element file for each approved proposal
"""

from vibelens.models.llm.prompts import AnalysisPrompt, load_template
from vibelens.models.skill import SkillCreation, SkillCreationProposalOutput

# Per-batch proposal: detects patterns and proposes new skills
SKILL_CREATION_PROPOSAL_PROMPT = AnalysisPrompt(
    task_id="skill_creation_proposal",
    system_template=load_template("creation/creation_proposal_system.j2"),
    user_template=load_template("creation/creation_proposal_user.j2"),
    output_model=SkillCreationProposalOutput,
)
# Post-batch synthesis: merges and deduplicates proposals across batches
SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT = AnalysisPrompt(
    task_id="skill_creation_proposal_synthesis",
    system_template=load_template("creation/creation_proposal_synthesis_system.j2"),
    user_template=load_template("creation/creation_proposal_synthesis_user.j2"),
    output_model=SkillCreationProposalOutput,
)
# Generation step: produces full SKILL.md for each approved proposal
SKILL_CREATION_GENERATE_PROMPT = AnalysisPrompt(
    task_id="skill_creation_generate",
    system_template=load_template("creation/creation_system.j2"),
    user_template=load_template("creation/creation_user.j2"),
    output_model=SkillCreation,
    exclude_fields={"SkillCreation": frozenset({"addressed_patterns"})},
)
```

Rename `skill_evolution.py` → `evolution.py`. Update `load_template()` paths from `"skill/evolution_*"` to `"evolution/evolution_*"`.

```python
# src/vibelens/prompts/evolution.py  (renamed from skill_evolution.py)
"""Prompts for element evolution: proposals, synthesis, and editing.

Two-step pipeline:
1. Proposals: detect patterns and propose improvements to existing elements
2. Editing: generate granular edits for each approved proposal
"""

from vibelens.models.llm.prompts import AnalysisPrompt, load_template
from vibelens.models.skill import SkillEvolution, SkillEvolutionProposalOutput

# Per-batch proposal: detects patterns and proposes improvements
SKILL_EVOLUTION_PROPOSAL_PROMPT = AnalysisPrompt(
    task_id="skill_evolution_proposal",
    system_template=load_template("evolution/evolution_proposal_system.j2"),
    user_template=load_template("evolution/evolution_proposal_user.j2"),
    output_model=SkillEvolutionProposalOutput,
)
# Post-batch synthesis: merges and deduplicates evolution proposals across batches
SKILL_EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT = AnalysisPrompt(
    task_id="skill_evolution_proposal_synthesis",
    system_template=load_template("evolution/evolution_proposal_synthesis_system.j2"),
    user_template=load_template("evolution/evolution_proposal_synthesis_user.j2"),
    output_model=SkillEvolutionProposalOutput,
)
# Edit step: generates granular old_string/new_string edits for each proposal
SKILL_EVOLUTION_EDIT_PROMPT = AnalysisPrompt(
    task_id="skill_evolution_edit",
    system_template=load_template("evolution/evolution_system.j2"),
    user_template=load_template("evolution/evolution_user.j2"),
    output_model=SkillEvolution,
    exclude_fields={"SkillEvolution": frozenset({"description", "addressed_patterns"})},
)
```

Delete `skill_retrieval.py`:

```bash
rm src/vibelens/prompts/skill_retrieval.py
rm src/vibelens/prompts/skill_creation.py
rm src/vibelens/prompts/skill_evolution.py
```

- [ ] **Step 7: Update prompts/__init__.py**

Remove retrieval from PROMPT_REGISTRY. Update imports to new file names.

```python
# src/vibelens/prompts/__init__.py
"""Analysis prompt registry.

Central lookup for all available AnalysisPrompt instances.
"""

from vibelens.models.llm.prompts import AnalysisPrompt
from vibelens.prompts.friction_analysis import FRICTION_ANALYSIS_PROMPT
from vibelens.prompts.evolution import SKILL_EVOLUTION_PROPOSAL_PROMPT

PROMPT_REGISTRY: dict[str, AnalysisPrompt] = {
    FRICTION_ANALYSIS_PROMPT.task_id: FRICTION_ANALYSIS_PROMPT,
    SKILL_EVOLUTION_PROPOSAL_PROMPT.task_id: SKILL_EVOLUTION_PROPOSAL_PROMPT,
}


def get_prompt(task_id: str) -> AnalysisPrompt | None:
    """Look up a registered analysis prompt by task ID.

    Args:
        task_id: Unique prompt identifier (e.g. 'friction_analysis').

    Returns:
        AnalysisPrompt instance, or None if not found.
    """
    return PROMPT_REGISTRY.get(task_id)
```

- [ ] **Step 8: Update service imports**

In `services/skill/creation.py`, change:
```python
# OLD
from vibelens.prompts.skill_creation import (...)
# NEW
from vibelens.prompts.creation import (...)
```

In `services/skill/evolution.py`, change:
```python
# OLD
from vibelens.prompts.skill_evolution import (...)
# NEW
from vibelens.prompts.evolution import (...)
```

In `services/skill/retrieval.py`, comment out or remove the retrieval prompt import and add a `# TODO: delete this file in Plan 3` comment at top. The retrieval.py service still needs to exist until Plan 3 replaces it, but the prompt imports will break. For now, make `analyze_skill_retrieval` raise `NotImplementedError("Retrieval replaced by recommendation pipeline")` and remove the prompt import.

- [ ] **Step 9: Run tests to verify**

Run: `pytest tests/prompts/test_prompts_refactor.py -v`
Expected: ALL PASS

Run: `pytest tests/ -v --timeout=300`
Expected: All 344+ tests pass (services/skill/retrieval tests may need adjusting if they exist).

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: rename prompts files, split templates/skill/ into creation/ and evolution/"
```

---

### Task 2: Rename AgentType and BackendType to official product names

Rename enum values to use official product names consistently. Both enums represent agent CLIs; the naming should be consistent and match official product branding.

**Renames for AgentType:**

| Old Value | New Member Name | New String Value | Official Name |
|-----------|----------------|-----------------|---------------|
| `CLAUDE_CODE = "claude_code"` | `CLAUDE_CODE = "claude_code"` | (unchanged) | Claude Code |
| `CLAUDE_CODE_WEB = "claude_code_web"` | `CLAUDE_CODE_WEB = "claude_code_web"` | (unchanged) | Claude Code Web |
| `CODEX = "codex"` | `CODEX = "codex"` | (unchanged) | Codex CLI |
| `GEMINI = "gemini"` | `GEMINI = "gemini"` | (unchanged) | Gemini CLI (legacy alias) |
| `GEMINI_CLI = "gemini_cli"` | `GEMINI_CLI = "gemini_cli"` | (unchanged) | Gemini CLI |
| `CURSOR = "cursor"` | `CURSOR = "cursor"` | (unchanged) | Cursor |
| `COPILOT = "copilot"` | `COPILOT = "copilot"` | (unchanged) | GitHub Copilot |
| `KIMI_CLI = "kimi_cli"` | `KIMI = "kimi"` | `"kimi"` | Kimi |
| `OPENCODE = "opencode"` | `OPENCODE = "opencode"` | (unchanged) | OpenCode |
| `OPENCLAW = "openclaw"` | `OPENCLAW = "openclaw"` | (unchanged) | OpenClaw |
| `OPENHANDS = "openhands"` | `OPENHANDS = "openhands"` | (unchanged) | OpenHands |
| `QWEN_CODE = "qwen_code"` | `QWEN_CODE = "qwen_code"` | (unchanged) | Qwen Coder |
| `ANTIGRAVITY = "antigravity"` | `ANTIGRAVITY = "antigravity"` | (unchanged) | Antigravity |
| `DATACLAW = "dataclaw"` | `DATACLAW = "dataclaw"` | (unchanged) | Dataclaw |
| `PARSED = "parsed"` | `PARSED = "parsed"` | (unchanged) | (generic) |
| (new) | `AIDER = "aider"` | `"aider"` | Aider |
| (new) | `AMP = "amp"` | `"amp"` | Amp |

**Renames for BackendType:**

| Old Value | New Member Name | New String Value |
|-----------|----------------|-----------------|
| `LITELLM = "litellm"` | (unchanged) | (unchanged) |
| `CLAUDE_CLI = "claude-cli"` | `CLAUDE_CODE = "claude_code"` | `"claude_code"` |
| `CODEX_CLI = "codex-cli"` | `CODEX = "codex"` | `"codex"` |
| `GEMINI_CLI = "gemini-cli"` | `GEMINI = "gemini"` | `"gemini"` |
| `CURSOR_CLI = "cursor-cli"` | `CURSOR = "cursor"` | `"cursor"` |
| `KIMI_CLI = "kimi-cli"` | `KIMI = "kimi"` | `"kimi"` |
| `OPENCLAW_CLI = "openclaw-cli"` | `OPENCLAW = "openclaw"` | `"openclaw"` |
| `OPENCODE_CLI = "opencode-cli"` | `OPENCODE = "opencode"` | `"opencode"` |
| `AIDER_CLI = "aider-cli"` | `AIDER = "aider"` | `"aider"` |
| `AMP_CLI = "amp-cli"` | `AMP = "amp"` | `"amp"` |
| `MOCK = "mock"` | (unchanged) | (unchanged) |
| `DISABLED = "disabled"` | (unchanged) | (unchanged) |

This makes BackendType member names match AgentType member names (minus LITELLM, MOCK, DISABLED) and aligns string values to use underscores instead of hyphens.

**Files:**
- Modify: `src/vibelens/models/enums.py` (AgentType)
- Modify: `src/vibelens/models/llm/inference.py` (BackendType)
- Modify: all files referencing `BackendType.CLAUDE_CLI`, `BackendType.CODEX_CLI`, etc.
- Modify: all files referencing `AgentType.KIMI_CLI`
- Modify: `src/vibelens/llm/backends/__init__.py` (backend registry)
- Modify: all backend files (`claude_cli.py` → update `backend_id`)
- Modify: `src/vibelens/models/skill/source.py` (SkillSourceType.KIMI_CLI → KIMI)
- Modify: config files referencing old string values
- Modify: frontend components displaying agent type labels
- Test: `tests/models/test_enum_renames.py`

- [ ] **Step 1: Write test for renamed enums**

```python
# tests/models/test_enum_renames.py
"""Tests for AgentType and BackendType official name renames."""
from vibelens.models.enums import AgentType
from vibelens.models.llm.inference import BackendType


def test_agent_type_has_aider_and_amp():
    """AgentType includes Aider and Amp (previously backend-only)."""
    assert AgentType.AIDER == "aider"
    assert AgentType.AMP == "amp"


def test_agent_type_kimi_renamed():
    """KIMI_CLI renamed to KIMI."""
    assert AgentType.KIMI == "kimi"
    assert not hasattr(AgentType, "KIMI_CLI")


def test_backend_type_uses_underscores():
    """BackendType string values use underscores, not hyphens."""
    assert BackendType.CLAUDE_CODE == "claude_code"
    assert BackendType.CODEX == "codex"
    assert BackendType.GEMINI == "gemini"
    assert BackendType.CURSOR == "cursor"
    assert BackendType.KIMI == "kimi"
    assert BackendType.OPENCLAW == "openclaw"
    assert BackendType.OPENCODE == "opencode"
    assert BackendType.AIDER == "aider"
    assert BackendType.AMP == "amp"


def test_backend_type_no_cli_suffix():
    """Old *_CLI members no longer exist."""
    assert not hasattr(BackendType, "CLAUDE_CLI")
    assert not hasattr(BackendType, "CODEX_CLI")
    assert not hasattr(BackendType, "GEMINI_CLI")


def test_backend_and_agent_names_overlap():
    """Every CLI backend has a matching AgentType member (name alignment)."""
    cli_backends = {
        bt for bt in BackendType
        if bt not in (BackendType.LITELLM, BackendType.MOCK, BackendType.DISABLED)
    }
    for bt in cli_backends:
        assert hasattr(AgentType, bt.name), f"AgentType missing {bt.name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_enum_renames.py -v`
Expected: FAIL — old names still in place.

- [ ] **Step 3: Update AgentType in enums.py**

In `src/vibelens/models/enums.py`:
- Rename `KIMI_CLI = "kimi_cli"` to `KIMI = "kimi"`
- Add `AIDER = "aider"` and `AMP = "amp"`
- Reorder alphabetically

```python
class AgentType(StrEnum):
    """Known agent CLI types.

    Includes both trajectory-parsed agents and scan-only agents
    that VibeLens discovers installed skills from.
    """

    AIDER = "aider"
    AMP = "amp"
    ANTIGRAVITY = "antigravity"
    CLAUDE_CODE = "claude_code"
    CLAUDE_CODE_WEB = "claude_code_web"
    CODEX = "codex"
    COPILOT = "copilot"
    CURSOR = "cursor"
    DATACLAW = "dataclaw"
    GEMINI = "gemini"
    GEMINI_CLI = "gemini_cli"
    KIMI = "kimi"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    OPENHANDS = "openhands"
    PARSED = "parsed"
    QWEN_CODE = "qwen_code"
```

- [ ] **Step 4: Update BackendType in inference.py**

In `src/vibelens/models/llm/inference.py`:

```python
class BackendType(StrEnum):
    """Inference backend type identifier."""

    LITELLM = "litellm"
    AIDER = "aider"
    AMP = "amp"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR = "cursor"
    GEMINI = "gemini"
    KIMI = "kimi"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    MOCK = "mock"
    DISABLED = "disabled"
```

- [ ] **Step 5: Update backend registry and all BackendType references**

Search all files for `BackendType.CLAUDE_CLI`, `BackendType.CODEX_CLI`, etc. and update to new names. Key files:

- `src/vibelens/llm/backends/__init__.py` — `_CLI_BACKEND_REGISTRY` keys
- Each backend file (`claude_cli.py`, `codex_cli.py`, etc.) — `backend_id` property return value
- `src/vibelens/config/llm_config.py` — backend type references
- `src/vibelens/llm/backends/cursor_cli.py`, `gemini_cli.py`, `kimi_cli.py`, `openclaw_cli.py`, `opencode_cli.py`, `aider_cli.py`, `amp_cli.py`

For each backend file, update the `backend_id` property to return the new BackendType value.

- [ ] **Step 6: Update AgentType references**

Search all files for `AgentType.KIMI_CLI` and update to `AgentType.KIMI`. Search for string `"kimi_cli"` in config files and update to `"kimi"`.

Update `src/vibelens/models/skill/source.py`: rename `SkillSourceType.KIMI_CLI` → `SkillSourceType.KIMI` with value `"kimi"`.

Update `src/vibelens/storage/skill/agent.py`: `AGENT_SKILL_REGISTRY` key from `SkillSourceType.KIMI_CLI` to `SkillSourceType.KIMI`.

Update any parser fingerprinting that returns `AgentType.KIMI_CLI`.

**IMPORTANT:** For persisted data, the old string values (`"claude-cli"`, `"codex-cli"`, `"kimi_cli"`) may exist in stored JSON files (`~/.vibelens/skill_analyses/`, `~/.vibelens/friction/`). These files use BackendType string values. Add a backward-compat migration note but do NOT add runtime migration code — existing analyses will simply fail to load (acceptable for dev, we'll handle data migration in Plan E).

- [ ] **Step 7: Update frontend agent type labels**

Search frontend for `kimi_cli` references and update to `kimi`. Check agent label maps in frontend components.

- [ ] **Step 8: Run tests**

Run: `pytest tests/models/test_enum_renames.py -v`
Expected: ALL PASS

Run: `pytest tests/ -v --timeout=300`
Expected: All tests pass. Some tests that hardcode old string values (e.g. `"claude-cli"`) will need updating.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: rename AgentType and BackendType to official product names"
```

---

### Task 3: Add PRESET_RECOMMENDATION context params

Add the recommendation-tier context extraction preset per spec.

**Files:**
- Modify: `src/vibelens/services/context_params.py`
- Test: `tests/services/test_context_params.py`

- [ ] **Step 1: Write test**

```python
# tests/services/test_context_params.py
"""Tests for context parameter presets."""
from vibelens.services.context_params import (
    PRESET_CONCISE,
    PRESET_RECOMMENDATION,
)


def test_preset_recommendation_exists():
    """PRESET_RECOMMENDATION is importable and has correct values."""
    assert PRESET_RECOMMENDATION.user_prompt_max_chars == 500
    assert PRESET_RECOMMENDATION.agent_message_max_chars == 0
    assert PRESET_RECOMMENDATION.bash_command_max_chars == 0
    assert PRESET_RECOMMENDATION.tool_arg_max_chars == 0
    assert PRESET_RECOMMENDATION.include_non_error_obs is False
    assert PRESET_RECOMMENDATION.observation_max_chars == 0
    assert PRESET_RECOMMENDATION.shorten_home_prefix is True
    assert PRESET_RECOMMENDATION.path_max_segments == 2


def test_preset_recommendation_more_aggressive_than_concise():
    """PRESET_RECOMMENDATION is more aggressive compression than PRESET_CONCISE."""
    assert PRESET_RECOMMENDATION.user_prompt_max_chars < PRESET_CONCISE.user_prompt_max_chars
    assert PRESET_RECOMMENDATION.agent_message_max_chars < PRESET_CONCISE.agent_message_max_chars
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_context_params.py -v`
Expected: FAIL — PRESET_RECOMMENDATION not defined.

- [ ] **Step 3: Add PRESET_RECOMMENDATION**

Append to `src/vibelens/services/context_params.py`:

```python
# Maximum compression for recommendation profile generation
PRESET_RECOMMENDATION = ContextParams(
    user_prompt_max_chars=500,
    user_prompt_head_chars=400,
    user_prompt_tail_chars=100,
    bash_command_max_chars=0,
    tool_arg_max_chars=0,
    error_truncate_chars=200,
    include_non_error_obs=False,
    observation_max_chars=0,
    agent_message_max_chars=0,
    agent_message_head_chars=0,
    agent_message_tail_chars=0,
    shorten_home_prefix=True,
    path_max_segments=2,
)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/services/test_context_params.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibelens/services/context_params.py tests/services/test_context_params.py
git commit -m "feat: add PRESET_RECOMMENDATION context params for recommendation pipeline"
```

---

### Task 4: Add catalog config settings

Add `catalog_update_url`, `catalog_auto_update`, `catalog_check_interval_hours`, and `recommendation_dir` fields to Settings.

**Files:**
- Modify: `src/vibelens/config/settings.py`
- Test: `tests/config/test_catalog_settings.py`

- [ ] **Step 1: Write test**

```python
# tests/config/test_catalog_settings.py
"""Tests for catalog configuration fields."""
from vibelens.config.settings import Settings


def test_catalog_defaults():
    """Settings has catalog fields with correct defaults."""
    s = Settings()
    assert s.catalog_auto_update is True
    assert s.catalog_check_interval_hours == 24
    assert "github" in s.catalog_update_url.lower() or s.catalog_update_url == ""
    assert s.recommendation_dir.name == "recommendations"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/config/test_catalog_settings.py -v`
Expected: FAIL

- [ ] **Step 3: Add fields to Settings**

In `src/vibelens/config/settings.py`, add after the `skill_analysis_dir` field:

```python
    # Recommendation persistence
    recommendation_dir: Path = Field(
        default=Path.home() / ".vibelens" / "recommendations",
        description="Directory for persisted recommendation results.",
    )

    # Catalog updates
    catalog_update_url: str = Field(
        default="",
        description="URL to fetch catalog.json updates from (GitHub Release asset).",
    )
    catalog_auto_update: bool = Field(
        default=True,
        description="Check for catalog updates on startup.",
    )
    catalog_check_interval_hours: int = Field(
        default=24,
        description="Minimum hours between catalog update checks.",
    )
```

Add `self.recommendation_dir = self.recommendation_dir.expanduser()` to `expand_paths`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/config/test_catalog_settings.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibelens/config/settings.py tests/config/test_catalog_settings.py
git commit -m "feat: add catalog and recommendation config settings"
```

---

### Task 5: Create services/recommendation/catalog.py — catalog loader

Runtime catalog loader: loads `catalog.json` from bundled path or `~/.vibelens/catalog/`, picks newer version, supports background update checks.

**Files:**
- Create: `src/vibelens/services/recommendation/__init__.py`
- Create: `src/vibelens/services/recommendation/catalog.py`
- Test: `tests/services/recommendation/test_catalog.py`

- [ ] **Step 1: Write test**

```python
# tests/services/recommendation/__init__.py
# (empty)
```

```python
# tests/services/recommendation/test_catalog.py
"""Tests for the recommendation catalog loader."""
import json
import tempfile
from pathlib import Path

from vibelens.models.recommendation.catalog import CatalogItem, ItemType
from vibelens.services.recommendation.catalog import (
    CatalogSnapshot,
    load_catalog_from_path,
)


def _build_test_catalog(item_count: int = 3) -> dict:
    """Build a minimal catalog dict for testing."""
    items = []
    for i in range(item_count):
        items.append({
            "item_id": f"test-org/test-repo-{i}",
            "item_type": "skill",
            "name": f"test-skill-{i}",
            "description": f"Test skill {i} description",
            "tags": ["test", "skill"],
            "category": "testing",
            "platforms": ["claude-code"],
            "quality_score": 75.0,
            "popularity": 0.5,
            "updated_at": "2026-04-01T00:00:00Z",
            "source_url": f"https://github.com/test-org/test-repo-{i}",
            "repo_full_name": f"test-org/test-repo-{i}",
            "install_method": "skill_file",
        })
    return {
        "schema_version": 1,
        "version": "2026-04-10",
        "built_at": "2026-04-10T08:30:00Z",
        "item_count": item_count,
        "items": items,
    }


def test_load_catalog_from_path():
    """load_catalog_from_path parses catalog.json into CatalogSnapshot."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_build_test_catalog(5), f)
        path = Path(f.name)

    snapshot = load_catalog_from_path(path)
    assert snapshot is not None
    assert snapshot.version == "2026-04-10"
    assert len(snapshot.items) == 5
    assert all(isinstance(item, CatalogItem) for item in snapshot.items)
    print(f"Loaded {len(snapshot.items)} items, version={snapshot.version}")
    path.unlink()


def test_load_catalog_missing_file():
    """load_catalog_from_path returns None for missing file."""
    snapshot = load_catalog_from_path(Path("/nonexistent/catalog.json"))
    assert snapshot is None


def test_load_catalog_invalid_json():
    """load_catalog_from_path returns None for corrupt JSON."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not json")
        path = Path(f.name)

    snapshot = load_catalog_from_path(path)
    assert snapshot is None
    path.unlink()


def test_catalog_snapshot_item_lookup():
    """CatalogSnapshot supports item lookup by ID."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_build_test_catalog(3), f)
        path = Path(f.name)

    snapshot = load_catalog_from_path(path)
    item = snapshot.get_item("test-org/test-repo-1")
    assert item is not None
    assert item.name == "test-skill-1"
    assert snapshot.get_item("nonexistent") is None
    path.unlink()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/recommendation/test_catalog.py -v`
Expected: FAIL

- [ ] **Step 3: Create services/recommendation/ package**

```python
# src/vibelens/services/recommendation/__init__.py
"""Recommendation pipeline — L1-L4 engine for personalized tool recommendations."""
```

```python
# src/vibelens/services/recommendation/catalog.py
"""Runtime catalog loader and manager.

Loads catalog.json from the bundled path or user cache, picks the newer
version, and supports background update checks.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Bundled catalog shipped with VibeLens releases
BUNDLED_CATALOG_PATH = Path(__file__).resolve().parents[4] / "catalog.json"
# User-cached catalog downloaded from update URL
USER_CATALOG_DIR = Path.home() / ".vibelens" / "catalog"


class CatalogSnapshot(BaseModel):
    """In-memory snapshot of the loaded catalog."""

    version: str = Field(description="Catalog version date string (e.g. 2026-04-10).")
    schema_version: int = Field(default=1, description="Catalog schema version.")
    items: list[CatalogItem] = Field(default_factory=list, description="All catalog items.")
    _index: dict[str, CatalogItem] = {}

    def model_post_init(self, __context: object) -> None:
        """Build item lookup index after loading."""
        self._index = {item.item_id: item for item in self.items}

    def get_item(self, item_id: str) -> CatalogItem | None:
        """Look up a catalog item by ID.

        Args:
            item_id: Unique item identifier.

        Returns:
            CatalogItem or None if not found.
        """
        return self._index.get(item_id)


def load_catalog_from_path(path: Path) -> CatalogSnapshot | None:
    """Load and parse a catalog.json file.

    Args:
        path: Path to catalog.json.

    Returns:
        CatalogSnapshot or None if file missing/corrupt.
    """
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        items = [CatalogItem.model_validate(item) for item in data.get("items", [])]
        return CatalogSnapshot(
            version=data.get("version", "unknown"),
            schema_version=data.get("schema_version", 1),
            items=items,
        )
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.warning("Failed to load catalog from %s: %s", path, exc)
        return None


def load_catalog() -> CatalogSnapshot | None:
    """Load the best available catalog (user cache > bundled).

    Checks both the user-cached catalog and the bundled catalog,
    returning whichever has the newer version date.

    Returns:
        CatalogSnapshot or None if no catalog available.
    """
    user_path = USER_CATALOG_DIR / "catalog.json"
    user_catalog = load_catalog_from_path(user_path)
    bundled_catalog = load_catalog_from_path(BUNDLED_CATALOG_PATH)

    if user_catalog and bundled_catalog:
        if user_catalog.version >= bundled_catalog.version:
            logger.info("Using user-cached catalog v%s (%d items)", user_catalog.version, len(user_catalog.items))
            return user_catalog
        logger.info("Using bundled catalog v%s (%d items)", bundled_catalog.version, len(bundled_catalog.items))
        return bundled_catalog

    result = user_catalog or bundled_catalog
    if result:
        logger.info("Loaded catalog v%s (%d items)", result.version, len(result.items))
    else:
        logger.warning("No catalog available (checked %s and %s)", user_path, BUNDLED_CATALOG_PATH)
    return result
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/services/recommendation/test_catalog.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibelens/services/recommendation/ tests/services/recommendation/
git commit -m "feat: add recommendation catalog loader"
```

---

### Task 6: Create recommendation prompts and templates

Create `prompts/recommendation.py` with L2 (profile generation) and L4 (rationale) prompt definitions. Create Jinja2 templates in `templates/recommendation/`.

**Files:**
- Create: `src/vibelens/prompts/recommendation.py`
- Create: `src/vibelens/prompts/templates/recommendation/profile_system.j2`
- Create: `src/vibelens/prompts/templates/recommendation/profile_user.j2`
- Create: `src/vibelens/prompts/templates/recommendation/rationale_system.j2`
- Create: `src/vibelens/prompts/templates/recommendation/rationale_user.j2`
- Modify: `src/vibelens/prompts/__init__.py` (add to PROMPT_REGISTRY)
- Test: `tests/prompts/test_recommendation_prompts.py`

- [ ] **Step 1: Write test**

```python
# tests/prompts/test_recommendation_prompts.py
"""Tests for recommendation prompt definitions."""
from vibelens.prompts.recommendation import (
    RECOMMENDATION_PROFILE_PROMPT,
    RECOMMENDATION_RATIONALE_PROMPT,
)


def test_profile_prompt_renders():
    """L2 profile prompt renders system and user templates."""
    system = RECOMMENDATION_PROFILE_PROMPT.render_system(
        output_schema="{}", backend_rules=""
    )
    assert "profile" in system.lower() or "workflow" in system.lower()
    print(f"Profile system prompt: {len(system)} chars")

    user = RECOMMENDATION_PROFILE_PROMPT.render_user(
        session_count=5,
        session_digest="User asked about Python testing...",
    )
    assert "5" in user
    print(f"Profile user prompt: {len(user)} chars")


def test_rationale_prompt_renders():
    """L4 rationale prompt renders system and user templates."""
    system = RECOMMENDATION_RATIONALE_PROMPT.render_system(
        output_schema="{}", backend_rules=""
    )
    assert "rationale" in system.lower() or "recommend" in system.lower()

    user = RECOMMENDATION_RATIONALE_PROMPT.render_user(
        user_profile={"domains": ["web-dev"], "languages": ["python"]},
        candidates=[{"name": "test-runner", "description": "Runs tests"}],
    )
    assert "test-runner" in user
    print(f"Rationale user prompt: {len(user)} chars")


def test_profile_prompt_task_id():
    """Profile prompt has correct task_id."""
    assert RECOMMENDATION_PROFILE_PROMPT.task_id == "recommendation_profile"


def test_rationale_prompt_task_id():
    """Rationale prompt has correct task_id."""
    assert RECOMMENDATION_RATIONALE_PROMPT.task_id == "recommendation_rationale"


def test_recommendation_prompts_in_registry():
    """Recommendation prompts are registered in PROMPT_REGISTRY."""
    from vibelens.prompts import PROMPT_REGISTRY
    assert "recommendation_profile" in PROMPT_REGISTRY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/prompts/test_recommendation_prompts.py -v`
Expected: FAIL

- [ ] **Step 3: Create recommendation templates**

```jinja2
{# src/vibelens/prompts/templates/recommendation/profile_system.j2 #}
You are a workflow analyst. You analyze coding agent session transcripts and extract a structured user profile summarizing what the user works on, how they work, and what tools would help them.

## Your Task

Given compressed session transcripts, produce a JSON user profile with:
- **domains**: What areas they work in (e.g. "web-dev", "data-pipeline", "devops")
- **languages**: Programming languages used
- **frameworks**: Frameworks and tools observed
- **agent_platforms**: Which coding agents they use (e.g. "claude-code", "codex")
- **bottlenecks**: Recurring friction points or pain areas
- **workflow_style**: One sentence describing how they work
- **search_keywords**: 20-30 keywords designed to match a catalog of AI coding tools. Translate observed patterns into tool-search-friendly terms.

## Writing Rules

- All text must be plain language, understandable by non-technical users.
- `search_keywords` should bridge the semantic gap: translate noisy session patterns (e.g. "keeps fixing import errors") into catalog-friendly terms (e.g. "auto-import", "import-management", "dependency-resolver").
- Include both specific terms (framework names, tool names) and general capability terms ("testing", "documentation", "refactoring").

## Output Schema

Return ONLY valid JSON matching this schema:

{{ output_schema }}
{{ backend_rules }}
```

```jinja2
{# src/vibelens/prompts/templates/recommendation/profile_user.j2 #}
Analyze {{ session_count }} coding agent session{{ "s" if session_count != 1 else "" }} and produce a user profile.

{{ session_digest }}

Produce the user profile JSON with domains, languages, frameworks, agent_platforms, bottlenecks, workflow_style, and search_keywords (20-30 catalog-friendly terms).
```

```jinja2
{# src/vibelens/prompts/templates/recommendation/rationale_system.j2 #}
You are a recommendation writer. Given a user profile and a list of candidate tools, write a short personalized rationale for each tool explaining why it would help this specific user.

## Rationale Format

For each candidate, write:
- `rationale`: One sentence (max 15 words), then 1-2 bullets starting with "\n- " (max 10 words each).
- `confidence`: 0.0-1.0 match strength.

## Writing Rules

- Plain language, no jargon. Written for non-technical users.
- Each rationale must be personalized — reference specific aspects of the user's workflow.
- Do NOT pad confidence scores. Only high confidence (0.8+) for strong matches.

## Output Schema

Return ONLY valid JSON matching this schema:

{{ output_schema }}
{{ backend_rules }}
```

```jinja2
{# src/vibelens/prompts/templates/recommendation/rationale_user.j2 #}
## User Profile

{{ user_profile | tojson(indent=2) }}

## Candidates

For each candidate below, write a personalized rationale explaining why it matches this user's workflow.

{% for candidate in candidates %}
- **{{ candidate.name }}**: {{ candidate.description }}
{% endfor %}

Produce the rationale JSON array with item_id, rationale, and confidence for each candidate.
```

- [ ] **Step 4: Create recommendation.py prompt definitions**

```python
# src/vibelens/prompts/recommendation.py
"""Prompts for the recommendation pipeline: profile generation and rationale.

Two LLM calls:
1. L2 Profile: Extract structured user profile from session transcripts
2. L4 Rationale: Generate personalized rationale for top-scoring candidates
"""

from vibelens.models.llm.prompts import AnalysisPrompt, load_template
from vibelens.models.recommendation.profile import UserProfile
from vibelens.models.recommendation.results import RationaleOutput

# L2: Profile generation from session transcripts
RECOMMENDATION_PROFILE_PROMPT = AnalysisPrompt(
    task_id="recommendation_profile",
    system_template=load_template("recommendation/profile_system.j2"),
    user_template=load_template("recommendation/profile_user.j2"),
    output_model=UserProfile,
)

# L4: Rationale generation for top candidates
RECOMMENDATION_RATIONALE_PROMPT = AnalysisPrompt(
    task_id="recommendation_rationale",
    system_template=load_template("recommendation/rationale_system.j2"),
    user_template=load_template("recommendation/rationale_user.j2"),
    output_model=RationaleOutput,
)
```

This requires adding `RationaleOutput` to `models/recommendation/results.py`:

```python
# Add to src/vibelens/models/recommendation/results.py

class RationaleItem(BaseModel):
    """LLM-generated rationale for a single candidate."""

    item_id: str = Field(description="CatalogItem reference.")
    rationale: str = Field(
        description=(
            "Personalized explanation: one sentence (max 15 words), "
            "then 1-2 bullets starting with '\\n- ' (max 10 words each)."
        )
    )
    confidence: float = Field(description="Match confidence from 0.0 to 1.0.")


class RationaleOutput(BaseModel):
    """LLM output for L4 rationale generation."""

    rationales: list[RationaleItem] = Field(
        description="Per-candidate personalized rationales."
    )
```

- [ ] **Step 5: Update prompts/__init__.py**

Add `RECOMMENDATION_PROFILE_PROMPT` to `PROMPT_REGISTRY`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/prompts/test_recommendation_prompts.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add recommendation prompts and templates for L2 profile and L4 rationale"
```

---

### Task 7: Create services/recommendation/retrieval.py — TF-IDF retrieval backend

Implement the `RetrievalBackend` ABC and `KeywordRetrieval` (TF-IDF) default backend per spec.

**Files:**
- Create: `src/vibelens/services/recommendation/retrieval.py`
- Test: `tests/services/recommendation/test_retrieval.py`

- [ ] **Step 1: Write test**

```python
# tests/services/recommendation/test_retrieval.py
"""Tests for TF-IDF keyword retrieval backend."""
from vibelens.models.recommendation.catalog import CatalogItem, ItemType
from vibelens.services.recommendation.retrieval import KeywordRetrieval


def _make_item(name: str, description: str, tags: list[str] | None = None) -> CatalogItem:
    """Build a minimal CatalogItem for testing."""
    return CatalogItem(
        item_id=f"test/{name}",
        item_type=ItemType.SKILL,
        name=name,
        description=description,
        tags=tags or [],
        category="testing",
        platforms=["claude-code"],
        quality_score=75.0,
        popularity=0.5,
        updated_at="2026-04-01T00:00:00Z",
        source_url=f"https://github.com/test/{name}",
        repo_full_name=f"test/{name}",
        install_method="skill_file",
    )


def test_keyword_retrieval_basic():
    """KeywordRetrieval finds items matching query keywords."""
    items = [
        _make_item("test-runner", "Runs pytest and reports results", ["testing", "pytest"]),
        _make_item("docker-deploy", "Deploy containers to production", ["docker", "deploy"]),
        _make_item("code-review", "Automated code review", ["review", "quality"]),
    ]
    backend = KeywordRetrieval()
    backend.build_index(items)

    results = backend.search("pytest testing runner", top_k=2)
    assert len(results) > 0
    names = [item.name for item, _ in results]
    assert "test-runner" in names
    print(f"Search results: {[(item.name, round(score, 3)) for item, score in results]}")


def test_keyword_retrieval_empty_query():
    """Empty query returns empty results."""
    backend = KeywordRetrieval()
    backend.build_index([_make_item("test", "A test skill")])
    results = backend.search("", top_k=5)
    assert len(results) == 0


def test_keyword_retrieval_top_k():
    """Results respect top_k limit."""
    items = [_make_item(f"skill-{i}", f"Description {i}") for i in range(20)]
    backend = KeywordRetrieval()
    backend.build_index(items)
    results = backend.search("description skill", top_k=5)
    assert len(results) <= 5


def test_keyword_retrieval_scores_normalized():
    """Scores are between 0.0 and 1.0."""
    items = [
        _make_item("exact-match", "python testing automation pytest"),
        _make_item("partial", "some other tool"),
    ]
    backend = KeywordRetrieval()
    backend.build_index(items)
    results = backend.search("python testing pytest", top_k=10)
    for _, score in results:
        assert 0.0 <= score <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/recommendation/test_retrieval.py -v`
Expected: FAIL

- [ ] **Step 3: Implement retrieval backend**

```python
# src/vibelens/services/recommendation/retrieval.py
"""Retrieval backends for the recommendation pipeline.

Provides pluggable search over the catalog. Default is KeywordRetrieval
(TF-IDF cosine similarity, zero external dependencies).
"""

from abc import ABC, abstractmethod

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class RetrievalBackend(ABC):
    """Abstract retrieval backend for catalog search."""

    @abstractmethod
    def build_index(self, items: list[CatalogItem]) -> None:
        """Build search index from catalog items.

        Args:
            items: Full catalog item list.
        """

    @abstractmethod
    def search(self, query: str, top_k: int) -> list[tuple[CatalogItem, float]]:
        """Search the catalog for items matching query.

        Args:
            query: Search query string (e.g. joined search_keywords).
            top_k: Maximum number of results to return.

        Returns:
            List of (CatalogItem, relevance_score) tuples, sorted by score descending.
        """


class KeywordRetrieval(RetrievalBackend):
    """TF-IDF cosine similarity retrieval.

    Pre-computes TF-IDF vectors from item name + description + tags.
    Query is vectorized and compared via cosine similarity.
    Zero external dependencies beyond scikit-learn.
    """

    def __init__(self) -> None:
        self._vectorizer = TfidfVectorizer(stop_words="english", max_features=10_000)
        self._items: list[CatalogItem] = []
        self._tfidf_matrix = None

    def build_index(self, items: list[CatalogItem]) -> None:
        """Build TF-IDF index from catalog items.

        Args:
            items: Catalog items to index.
        """
        self._items = items
        if not items:
            self._tfidf_matrix = None
            return

        documents = [
            f"{item.name} {item.description} {' '.join(item.tags)}"
            for item in items
        ]
        self._tfidf_matrix = self._vectorizer.fit_transform(documents)
        logger.info("Built TF-IDF index: %d items, %d features", len(items), self._tfidf_matrix.shape[1])

    def search(self, query: str, top_k: int) -> list[tuple[CatalogItem, float]]:
        """Search catalog using TF-IDF cosine similarity.

        Args:
            query: Space-separated search keywords.
            top_k: Maximum results to return.

        Returns:
            Ranked (CatalogItem, score) pairs.
        """
        if not query.strip() or self._tfidf_matrix is None:
            return []

        query_vec = self._vectorizer.transform([query])
        similarities = cosine_similarity(query_vec, self._tfidf_matrix).flatten()

        top_indices = similarities.argsort()[::-1][:top_k]
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.0:
                results.append((self._items[idx], score))
        return results
```

- [ ] **Step 4: Add scikit-learn dependency if not already present**

Check `pyproject.toml` for scikit-learn. If missing:

```bash
# Add to pyproject.toml dependencies
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/services/recommendation/test_retrieval.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/vibelens/services/recommendation/retrieval.py tests/services/recommendation/test_retrieval.py
git commit -m "feat: add TF-IDF keyword retrieval backend for recommendation pipeline"
```

---

### Task 8: Create services/recommendation/scoring.py — multi-signal scoring

Implement the configurable scoring pipeline with 5 signals per spec.

**Files:**
- Create: `src/vibelens/services/recommendation/scoring.py`
- Test: `tests/services/recommendation/test_scoring.py`

- [ ] **Step 1: Write test**

```python
# tests/services/recommendation/test_scoring.py
"""Tests for the multi-signal recommendation scoring pipeline."""
from vibelens.models.recommendation.catalog import CatalogItem, ItemType
from vibelens.models.recommendation.profile import UserProfile
from vibelens.services.recommendation.scoring import score_candidates


def _make_item(name: str, quality: float = 50.0, platforms: list[str] | None = None) -> CatalogItem:
    return CatalogItem(
        item_id=f"test/{name}",
        item_type=ItemType.SKILL,
        name=name,
        description=f"A {name} tool",
        tags=[],
        category="testing",
        platforms=platforms or ["claude-code"],
        quality_score=quality,
        popularity=0.5,
        updated_at="2026-04-01T00:00:00Z",
        source_url=f"https://github.com/test/{name}",
        repo_full_name=f"test/{name}",
        install_method="skill_file",
    )


def _make_profile() -> UserProfile:
    return UserProfile(
        domains=["web-dev"],
        languages=["python"],
        frameworks=["fastapi"],
        agent_platforms=["claude-code"],
        bottlenecks=["slow tests"],
        workflow_style="iterative debugger",
        search_keywords=["testing", "fastapi"],
    )


def test_score_candidates_returns_sorted():
    """score_candidates returns results sorted by score descending."""
    candidates = [
        (_make_item("low-quality", quality=10.0), 0.3),
        (_make_item("high-quality", quality=90.0), 0.8),
        (_make_item("mid-quality", quality=50.0), 0.5),
    ]
    profile = _make_profile()
    results = score_candidates(candidates, profile, top_k=3)
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
    print(f"Scores: {[(item.name, round(s, 3)) for item, s in results]}")


def test_platform_match_boosts_score():
    """Items matching user's agent platform score higher."""
    matched = _make_item("matched", platforms=["claude-code"])
    unmatched = _make_item("unmatched", platforms=["cursor"])
    candidates = [(matched, 0.5), (unmatched, 0.5)]
    profile = _make_profile()
    results = score_candidates(candidates, profile, top_k=2)
    matched_score = next(s for item, s in results if item.name == "matched")
    unmatched_score = next(s for item, s in results if item.name == "unmatched")
    assert matched_score > unmatched_score


def test_top_k_limit():
    """score_candidates respects top_k."""
    candidates = [(_make_item(f"item-{i}"), 0.5) for i in range(20)]
    results = score_candidates(candidates, _make_profile(), top_k=5)
    assert len(results) <= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/recommendation/test_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: Implement scoring pipeline**

```python
# src/vibelens/services/recommendation/scoring.py
"""Multi-signal weighted scoring for recommendation candidates.

Combines retrieval relevance, quality, platform match, popularity,
and composability into a final score per candidate.
"""

from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.models.recommendation.profile import UserProfile

# Signal weights from spec
WEIGHT_RELEVANCE = 0.40
WEIGHT_QUALITY = 0.25
WEIGHT_PLATFORM_MATCH = 0.20
WEIGHT_POPULARITY = 0.10
WEIGHT_COMPOSABILITY = 0.05

# Maximum quality score from catalog
MAX_QUALITY_SCORE = 100.0


def _score_quality(item: CatalogItem) -> float:
    """Normalize quality score to 0.0-1.0 range.

    Args:
        item: Catalog item with quality_score (0-100).

    Returns:
        Normalized quality score.
    """
    return min(item.quality_score / MAX_QUALITY_SCORE, 1.0)


def _score_platform_match(item: CatalogItem, profile: UserProfile) -> float:
    """Binary platform match: 1.0 if any user platform matches, else 0.0.

    Args:
        item: Catalog item with platforms list.
        profile: User profile with agent_platforms.

    Returns:
        1.0 or 0.0.
    """
    user_platforms = set(profile.agent_platforms)
    item_platforms = set(item.platforms)
    return 1.0 if user_platforms & item_platforms else 0.0


def _score_popularity(item: CatalogItem) -> float:
    """Return pre-normalized popularity score.

    Args:
        item: Catalog item with popularity (0.0-1.0).

    Returns:
        Popularity score.
    """
    return min(max(item.popularity, 0.0), 1.0)


def score_candidates(
    candidates: list[tuple[CatalogItem, float]],
    profile: UserProfile,
    top_k: int = 15,
) -> list[tuple[CatalogItem, float]]:
    """Score and rank retrieval candidates using weighted signals.

    Args:
        candidates: (CatalogItem, relevance_score) pairs from retrieval.
        profile: User profile for platform matching.
        top_k: Number of top results to return.

    Returns:
        Top-k (CatalogItem, composite_score) pairs sorted by score descending.
    """
    scored: list[tuple[CatalogItem, float]] = []

    for item, relevance in candidates:
        composite = (
            WEIGHT_RELEVANCE * relevance
            + WEIGHT_QUALITY * _score_quality(item)
            + WEIGHT_PLATFORM_MATCH * _score_platform_match(item, profile)
            + WEIGHT_POPULARITY * _score_popularity(item)
            + WEIGHT_COMPOSABILITY * 0.0  # Composability uses pre-computed pairs (future)
        )
        scored.append((item, composite))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/services/recommendation/test_scoring.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibelens/services/recommendation/scoring.py tests/services/recommendation/test_scoring.py
git commit -m "feat: add multi-signal weighted scoring for recommendation pipeline"
```

---

### Task 9: Create services/recommendation/engine.py — L1-L4 orchestrator

Implement the main recommendation engine that orchestrates all 4 layers.

**Files:**
- Create: `src/vibelens/services/recommendation/engine.py`
- Modify: `src/vibelens/services/recommendation/__init__.py` (export entry points)
- Test: `tests/services/recommendation/test_engine.py`

- [ ] **Step 1: Write test**

```python
# tests/services/recommendation/test_engine.py
"""Tests for the recommendation engine orchestrator."""
from vibelens.services.recommendation.engine import (
    RECOMMENDATION_OUTPUT_TOKENS,
    RECOMMENDATION_TIMEOUT_SECONDS,
    RETRIEVAL_TOP_K,
    SCORING_TOP_K,
)


def test_engine_constants():
    """Engine constants are defined with expected values."""
    assert RETRIEVAL_TOP_K == 30
    assert SCORING_TOP_K == 15
    assert RECOMMENDATION_OUTPUT_TOKENS > 0
    assert RECOMMENDATION_TIMEOUT_SECONDS > 0


def test_engine_importable():
    """Engine entry points are importable."""
    from vibelens.services.recommendation.engine import (
        analyze_recommendation,
        estimate_recommendation,
    )
    assert callable(analyze_recommendation)
    assert callable(estimate_recommendation)
```

Note: Full integration tests require a mock LLM backend and catalog. The engine's `analyze_recommendation` function will be tested via mock in a later step or as part of the API test.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/recommendation/test_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement engine**

```python
# src/vibelens/services/recommendation/engine.py
"""Recommendation engine — L1 through L4 orchestration.

L1: Context extraction (no LLM, 5-10s)
L2: LLM profile generation (1 call, 15-25s)
L3: TF-IDF retrieval + scoring (no LLM, <1s)
L4: LLM rationale generation (1 call, 15-25s)
"""

import time
from datetime import datetime, timezone

from vibelens.deps import get_settings
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.models.recommendation.profile import UserProfile
from vibelens.models.recommendation.results import (
    CatalogRecommendation,
    RationaleOutput,
    RecommendationResult,
)
from vibelens.models.trajectories.metrics import Metrics
from vibelens.prompts.recommendation import (
    RECOMMENDATION_PROFILE_PROMPT,
    RECOMMENDATION_RATIONALE_PROMPT,
)
from vibelens.services.analysis_shared import (
    build_system_kwargs,
    extract_all_contexts,
    format_batch_digest,
    require_backend,
    save_analysis_log,
    truncate_digest_to_fit,
)
from vibelens.services.analysis_store import generate_analysis_id
from vibelens.services.context_params import PRESET_RECOMMENDATION
from vibelens.services.recommendation.catalog import CatalogSnapshot, load_catalog
from vibelens.services.recommendation.retrieval import KeywordRetrieval
from vibelens.services.recommendation.scoring import score_candidates
from vibelens.services.skill.shared import parse_llm_output
from vibelens.utils.log import clear_analysis_id, get_logger, set_analysis_id

logger = get_logger(__name__)

# Retrieval returns top-30 candidates
RETRIEVAL_TOP_K = 30
# Scoring returns top-15 for rationale generation
SCORING_TOP_K = 15
# LLM output token budgets
RECOMMENDATION_OUTPUT_TOKENS = 4096
# Timeout per LLM call (seconds)
RECOMMENDATION_TIMEOUT_SECONDS = 120
# Log directory
RECOMMENDATION_LOG_DIR_NAME = "recommendation"


def estimate_recommendation(
    session_ids: list[str], session_token: str | None = None
) -> CostEstimate:
    """Pre-flight cost estimate for recommendation analysis.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        CostEstimate with projected cost range.
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, params=PRESET_RECOMMENDATION
    )
    if not context_set:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    digest = format_batch_digest(context_set)
    system_prompt = RECOMMENDATION_PROFILE_PROMPT.render_system(
        **build_system_kwargs(RECOMMENDATION_PROFILE_PROMPT, backend)
    )
    input_tokens = count_tokens(system_prompt) + count_tokens(digest)

    return estimate_analysis_cost(
        batch_token_counts=[input_tokens],
        system_prompt=system_prompt,
        model=backend.model,
        max_output_tokens=RECOMMENDATION_OUTPUT_TOKENS,
        synthesis_output_tokens=RECOMMENDATION_OUTPUT_TOKENS,
        synthesis_threshold=999,  # No synthesis for recommendation
    )


async def analyze_recommendation(
    session_ids: list[str], session_token: str | None = None
) -> RecommendationResult:
    """Run the full L1-L4 recommendation pipeline.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        RecommendationResult with ranked recommendations.
    """
    start_time = time.monotonic()
    analysis_id = generate_analysis_id()
    set_analysis_id(analysis_id)
    total_cost = 0.0

    try:
        backend = require_backend()

        # --- L1: Context Extraction ---
        logger.info("L1: Extracting context from %d sessions", len(session_ids))
        context_set = extract_all_contexts(
            session_ids=session_ids, session_token=session_token, params=PRESET_RECOMMENDATION
        )
        if not context_set:
            raise ValueError(f"No sessions could be loaded from: {session_ids}")

        digest = format_batch_digest(context_set)
        logger.info("L1 complete: %d chars of context", len(digest))

        # --- L2: Profile Generation ---
        logger.info("L2: Generating user profile via LLM")
        profile, profile_cost = await _generate_profile(backend, digest, len(context_set.session_ids))
        total_cost += profile_cost
        logger.info("L2 complete: %d keywords, cost=$%.4f", len(profile.search_keywords), profile_cost)

        # --- L3: Retrieval + Scoring ---
        logger.info("L3: Retrieving and scoring candidates")
        catalog = load_catalog()
        if not catalog or not catalog.items:
            logger.warning("No catalog available, returning empty recommendations")
            return _build_empty_result(
                analysis_id, session_ids, context_set.skipped_session_ids,
                profile, backend, total_cost, start_time, catalog,
            )

        retrieval_backend = KeywordRetrieval()
        retrieval_backend.build_index(catalog.items)
        query = " ".join(profile.search_keywords)
        raw_candidates = retrieval_backend.search(query, top_k=RETRIEVAL_TOP_K)
        scored = score_candidates(raw_candidates, profile, top_k=SCORING_TOP_K)
        logger.info("L3 complete: %d candidates scored", len(scored))

        if not scored:
            return _build_empty_result(
                analysis_id, session_ids, context_set.skipped_session_ids,
                profile, backend, total_cost, start_time, catalog,
            )

        # --- L4: Rationale Generation ---
        logger.info("L4: Generating rationales for %d candidates", len(scored))
        rationale_output, rationale_cost = await _generate_rationales(
            backend, profile, scored
        )
        total_cost += rationale_cost
        logger.info("L4 complete: %d rationales, cost=$%.4f", len(rationale_output.rationales), rationale_cost)

        # --- Build Result ---
        recommendations = _merge_scores_and_rationales(scored, rationale_output, catalog)
        duration = round(time.monotonic() - start_time, 2)

        result = RecommendationResult(
            analysis_id=analysis_id,
            session_ids=context_set.session_ids,
            skipped_session_ids=context_set.skipped_session_ids,
            title=f"Found {len(recommendations)} tools for your workflow",
            summary=f"Based on your {', '.join(profile.domains[:3])} work with {', '.join(profile.languages[:3])}.",
            user_profile=profile,
            recommendations=recommendations,
            backend_id=backend.backend_id,
            model=backend.model,
            created_at=datetime.now(timezone.utc).isoformat(),
            metrics=Metrics(cost_usd=total_cost if total_cost > 0 else None),
            duration_seconds=duration,
            catalog_version=catalog.version,
        )
        return result

    finally:
        clear_analysis_id()


async def _generate_profile(
    backend: InferenceBackend,
    digest: str,
    session_count: int,
) -> tuple[UserProfile, float]:
    """L2: Generate user profile from session context via LLM.

    Args:
        backend: Configured inference backend.
        digest: Compressed session context text.
        session_count: Number of sessions analyzed.

    Returns:
        Tuple of (UserProfile, cost_usd).
    """
    prompt = RECOMMENDATION_PROFILE_PROMPT
    system_kwargs = build_system_kwargs(prompt, backend)
    system_prompt = prompt.render_system(**system_kwargs)

    non_digest = prompt.render_user(session_count=session_count, session_digest="")
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest)

    user_prompt = prompt.render_user(session_count=session_count, session_digest=digest)

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=RECOMMENDATION_OUTPUT_TOKENS,
        timeout=RECOMMENDATION_TIMEOUT_SECONDS,
        json_schema=prompt.output_json_schema(),
    )

    result = await backend.generate(request)
    profile = parse_llm_output(result.text, UserProfile, "profile generation")
    return profile, result.cost_usd or 0.0


async def _generate_rationales(
    backend: InferenceBackend,
    profile: UserProfile,
    scored: list[tuple[CatalogItem, float]],
) -> tuple[RationaleOutput, float]:
    """L4: Generate personalized rationales for top candidates.

    Args:
        backend: Configured inference backend.
        profile: User profile from L2.
        scored: Top-k (CatalogItem, score) pairs from L3.

    Returns:
        Tuple of (RationaleOutput, cost_usd).
    """
    prompt = RECOMMENDATION_RATIONALE_PROMPT
    system_kwargs = build_system_kwargs(prompt, backend)
    system_prompt = prompt.render_system(**system_kwargs)

    candidates_data = [
        {"item_id": item.item_id, "name": item.name, "description": item.description}
        for item, _ in scored
    ]
    user_prompt = prompt.render_user(
        user_profile=profile.model_dump(),
        candidates=candidates_data,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=RECOMMENDATION_OUTPUT_TOKENS,
        timeout=RECOMMENDATION_TIMEOUT_SECONDS,
        json_schema=prompt.output_json_schema(),
    )

    result = await backend.generate(request)
    rationale_output = parse_llm_output(result.text, RationaleOutput, "rationale generation")
    return rationale_output, result.cost_usd or 0.0


def _merge_scores_and_rationales(
    scored: list[tuple[CatalogItem, float]],
    rationale_output: RationaleOutput,
    catalog: CatalogSnapshot,
) -> list[CatalogRecommendation]:
    """Merge scoring results with LLM rationales into final recommendations.

    Args:
        scored: (CatalogItem, composite_score) pairs.
        rationale_output: LLM-generated rationales.
        catalog: Loaded catalog snapshot.

    Returns:
        Ranked list of CatalogRecommendation.
    """
    from vibelens.models.recommendation.catalog import ITEM_TYPE_LABELS

    rationale_map = {r.item_id: r for r in rationale_output.rationales}

    recommendations = []
    for item, composite_score in scored:
        rationale_item = rationale_map.get(item.item_id)
        recommendations.append(CatalogRecommendation(
            item_id=item.item_id,
            item_type=item.item_type,
            user_label=ITEM_TYPE_LABELS.get(item.item_type, "Tool"),
            name=item.name,
            description=item.description,
            rationale=rationale_item.rationale if rationale_item else "",
            confidence=rationale_item.confidence if rationale_item else 0.5,
            quality_score=item.quality_score,
            score=composite_score,
            install_method=item.install_method,
            install_command=item.install_command,
            has_content=item.install_content is not None,
            source_url=item.source_url,
        ))
    return recommendations


def _build_empty_result(
    analysis_id: str,
    session_ids: list[str],
    skipped_session_ids: list[str],
    profile: UserProfile,
    backend: InferenceBackend,
    total_cost: float,
    start_time: float,
    catalog: CatalogSnapshot | None,
) -> RecommendationResult:
    """Build an empty recommendation result when no matches found.

    Args:
        analysis_id: Unique analysis ID.
        session_ids: Sessions that were analyzed.
        skipped_session_ids: Sessions that failed to load.
        profile: User profile from L2.
        backend: Inference backend used.
        total_cost: Total cost incurred so far.
        start_time: monotonic start time.
        catalog: Catalog snapshot (may be None).

    Returns:
        RecommendationResult with empty recommendations.
    """
    return RecommendationResult(
        analysis_id=analysis_id,
        session_ids=session_ids,
        skipped_session_ids=skipped_session_ids,
        title="No strong matches found",
        summary="Try Create Custom to build something specific for your workflow.",
        user_profile=profile,
        recommendations=[],
        backend_id=backend.backend_id,
        model=backend.model,
        created_at=datetime.now(timezone.utc).isoformat(),
        metrics=Metrics(cost_usd=total_cost if total_cost > 0 else None),
        duration_seconds=round(time.monotonic() - start_time, 2),
        catalog_version=catalog.version if catalog else "none",
    )
```

- [ ] **Step 4: Update services/recommendation/__init__.py**

```python
# src/vibelens/services/recommendation/__init__.py
"""Recommendation pipeline — L1-L4 engine for personalized tool recommendations."""

from vibelens.services.recommendation.engine import (
    analyze_recommendation,
    estimate_recommendation,
)

__all__ = ["analyze_recommendation", "estimate_recommendation"]
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/services/recommendation/test_engine.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/vibelens/services/recommendation/engine.py src/vibelens/services/recommendation/__init__.py tests/services/recommendation/test_engine.py
git commit -m "feat: add L1-L4 recommendation engine orchestrator"
```

---

### Task 10: Create services/recommendation/store.py and mock.py

Recommendation persistence (AnalysisStore subclass) and demo mock data.

**Files:**
- Create: `src/vibelens/services/recommendation/store.py`
- Create: `src/vibelens/services/recommendation/mock.py`
- Modify: `src/vibelens/deps.py` (add `get_recommendation_store()`)
- Test: `tests/services/recommendation/test_store.py`

- [ ] **Step 1: Write test**

```python
# tests/services/recommendation/test_store.py
"""Tests for recommendation store and mock data."""
import tempfile
from pathlib import Path

from vibelens.services.recommendation.store import RecommendationStore
from vibelens.services.recommendation.mock import build_mock_recommendation_result


def test_recommendation_store_save_and_load():
    """RecommendationStore saves and loads results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = RecommendationStore(Path(tmpdir))
        result = build_mock_recommendation_result(["session-1", "session-2"])
        store.save(result, "test-analysis-001")
        loaded = store.load("test-analysis-001")
        assert loaded is not None
        assert loaded.analysis_id == "test-analysis-001"
        assert len(loaded.recommendations) > 0
        print(f"Saved and loaded {len(loaded.recommendations)} recommendations")


def test_recommendation_store_list():
    """RecommendationStore lists analyses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = RecommendationStore(Path(tmpdir))
        result = build_mock_recommendation_result(["s1"])
        store.save(result, "test-001")
        analyses = store.list_analyses()
        assert len(analyses) == 1
        assert analyses[0].analysis_id == "test-001"


def test_mock_recommendation_result():
    """build_mock_recommendation_result produces valid result."""
    result = build_mock_recommendation_result(["s1", "s2", "s3"])
    assert len(result.recommendations) > 0
    assert result.user_profile is not None
    assert len(result.user_profile.search_keywords) > 0
    print(f"Mock: {len(result.recommendations)} recs, {len(result.user_profile.domains)} domains")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/recommendation/test_store.py -v`
Expected: FAIL

- [ ] **Step 3: Implement store**

```python
# src/vibelens/services/recommendation/store.py
"""Recommendation analysis persistence."""

from vibelens.models.recommendation.results import RecommendationResult
from vibelens.services.analysis_store import AnalysisStore

# Lightweight metadata for listing
from pydantic import BaseModel, Field


class RecommendationMeta(BaseModel):
    """Lightweight metadata for a persisted recommendation analysis."""

    analysis_id: str = Field(description="Unique analysis ID.")
    title: str = Field(default="", description="Main finding.")
    session_ids: list[str] = Field(description="Sessions analyzed.")
    created_at: str = Field(description="ISO timestamp.")
    model: str = Field(description="Model used.")
    cost_usd: float | None = Field(default=None, description="Inference cost.")
    duration_seconds: float | None = Field(default=None, description="Wall-clock duration.")
    recommendation_count: int = Field(default=0, description="Number of recommendations.")
    is_example: bool = Field(default=False, description="Bundled example flag.")


class RecommendationStore(AnalysisStore[RecommendationResult, RecommendationMeta]):
    """Disk-backed store for recommendation analysis results."""

    def _build_meta(self, result: RecommendationResult, analysis_id: str) -> RecommendationMeta:
        """Build lightweight metadata from a full result.

        Args:
            result: Full recommendation result.
            analysis_id: Unique analysis ID.

        Returns:
            RecommendationMeta for indexing.
        """
        return RecommendationMeta(
            analysis_id=analysis_id,
            title=result.title,
            session_ids=result.session_ids,
            created_at=result.created_at,
            model=result.model,
            cost_usd=result.metrics.cost_usd if result.metrics else None,
            duration_seconds=result.duration_seconds,
            recommendation_count=len(result.recommendations),
            is_example=result.is_example,
        )
```

- [ ] **Step 4: Implement mock**

```python
# src/vibelens/services/recommendation/mock.py
"""Mock recommendation data for demo and test modes."""

from datetime import datetime, timezone

from vibelens.models.llm.inference import BackendType
from vibelens.models.recommendation.catalog import ITEM_TYPE_LABELS, ItemType
from vibelens.models.recommendation.profile import UserProfile
from vibelens.models.recommendation.results import CatalogRecommendation, RecommendationResult
from vibelens.models.trajectories.metrics import Metrics


def build_mock_recommendation_result(session_ids: list[str]) -> RecommendationResult:
    """Build a realistic mock recommendation result for demo/test mode.

    Args:
        session_ids: Session IDs to include in the result.

    Returns:
        RecommendationResult with sample recommendations.
    """
    profile = UserProfile(
        domains=["web-dev", "api-development"],
        languages=["python", "typescript"],
        frameworks=["fastapi", "react", "docker"],
        agent_platforms=["claude-code"],
        bottlenecks=["repeated test failures", "slow CI feedback"],
        workflow_style="iterative debugger, prefers small commits",
        search_keywords=[
            "testing", "pytest", "fastapi", "react", "docker",
            "code-review", "refactoring", "debugging", "linting",
            "type-checking", "documentation", "ci-cd", "deployment",
        ],
    )

    recommendations = [
        CatalogRecommendation(
            item_id="anthropics/skills/test-runner",
            item_type=ItemType.SKILL,
            user_label=ITEM_TYPE_LABELS[ItemType.SKILL],
            name="test-runner",
            description="Automatically runs tests after code changes and reports results.",
            rationale="Catches test failures early in your workflow.\n- Runs after every edit\n- Shows only failing tests",
            confidence=0.92,
            quality_score=85.0,
            score=0.88,
            install_method="skill_file",
            install_command=None,
            has_content=True,
            source_url="https://github.com/anthropics/skills/tree/main/skills/test-runner",
        ),
        CatalogRecommendation(
            item_id="anthropics/skills/code-review",
            item_type=ItemType.SKILL,
            user_label=ITEM_TYPE_LABELS[ItemType.SKILL],
            name="code-review",
            description="Reviews code changes for bugs, style issues, and best practices.",
            rationale="Catches issues before they reach your tests.\n- Reviews diffs automatically\n- Suggests improvements inline",
            confidence=0.85,
            quality_score=80.0,
            score=0.82,
            install_method="skill_file",
            install_command=None,
            has_content=True,
            source_url="https://github.com/anthropics/skills/tree/main/skills/code-review",
        ),
        CatalogRecommendation(
            item_id="modelcontextprotocol/servers/postgres",
            item_type=ItemType.REPO,
            user_label=ITEM_TYPE_LABELS[ItemType.REPO],
            name="postgres-mcp",
            description="MCP server for PostgreSQL database access and querying.",
            rationale="Lets your agent query your database directly.\n- No manual SQL copying\n- Schema-aware queries",
            confidence=0.78,
            quality_score=90.0,
            score=0.76,
            install_method="mcp_config",
            install_command=None,
            has_content=False,
            source_url="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
        ),
    ]

    return RecommendationResult(
        analysis_id="mock-recommendation-001",
        session_ids=session_ids,
        skipped_session_ids=[],
        title=f"Found {len(recommendations)} tools for your workflow",
        summary="Based on your web-dev and API work with Python and TypeScript.",
        user_profile=profile,
        recommendations=recommendations,
        backend_id=BackendType.MOCK,
        model="mock-model",
        created_at=datetime.now(timezone.utc).isoformat(),
        metrics=Metrics(cost_usd=0.05),
        duration_seconds=2.5,
        catalog_version="2026-04-10",
        is_example=True,
    )
```

- [ ] **Step 5: Add get_recommendation_store() to deps.py**

In `src/vibelens/deps.py`, add:

```python
def get_recommendation_store():
    """Return cached RecommendationStore singleton."""
    from vibelens.services.recommendation.store import RecommendationStore

    return _get_or_create(
        "recommendation_store", lambda: RecommendationStore(get_settings().recommendation_dir)
    )
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/services/recommendation/test_store.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add recommendation store, mock data, and deps singleton"
```

---

### Task 11: Create schemas/recommendation.py and api/recommendation.py

API endpoints for recommendation: analyze, estimate, load, history, delete, install, catalog status.

**Files:**
- Create: `src/vibelens/schemas/recommendation.py`
- Create: `src/vibelens/api/recommendation.py`
- Modify: `src/vibelens/api/__init__.py` (add recommendation_router)
- Test: `tests/api/test_recommendation_api.py`

- [ ] **Step 1: Write test**

```python
# tests/api/test_recommendation_api.py
"""Tests for recommendation API endpoints."""


def test_recommendation_schemas_importable():
    """Recommendation schemas are importable."""
    from vibelens.schemas.recommendation import (
        RecommendationAnalyzeRequest,
        RecommendationInstallRequest,
    )
    req = RecommendationAnalyzeRequest(session_ids=["s1", "s2"])
    assert len(req.session_ids) == 2

    install = RecommendationInstallRequest(
        selected_item_ids=["test-runner"],
        target_agent="claude-code",
    )
    assert install.target_agent == "claude-code"


def test_recommendation_router_importable():
    """Recommendation API router is importable."""
    from vibelens.api.recommendation import router
    routes = [r.path for r in router.routes]
    assert "/analyze" in routes or any("/analyze" in r for r in routes)
    print(f"Recommendation routes: {routes}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_recommendation_api.py -v`
Expected: FAIL

- [ ] **Step 3: Create schemas/recommendation.py**

```python
# src/vibelens/schemas/recommendation.py
"""Recommendation API request/response schemas."""

from pydantic import BaseModel, Field


class RecommendationAnalyzeRequest(BaseModel):
    """Request body for starting a recommendation analysis."""

    session_ids: list[str] = Field(description="Session IDs to analyze for recommendations.")


class RecommendationInstallRequest(BaseModel):
    """Request body for generating an installation plan."""

    selected_item_ids: list[str] = Field(description="CatalogItem IDs to install.")
    target_agent: str = Field(
        default="claude-code",
        description="Target agent platform for installation instructions.",
    )


class CatalogStatusResponse(BaseModel):
    """Response for catalog status check."""

    version: str = Field(description="Catalog version date.")
    item_count: int = Field(description="Number of items in the catalog.")
    schema_version: int = Field(description="Catalog schema version.")
```

- [ ] **Step 4: Create api/recommendation.py**

```python
# src/vibelens/api/recommendation.py
"""Recommendation API endpoints."""

import asyncio
import secrets

from fastapi import APIRouter, Header, HTTPException

from vibelens.deps import get_recommendation_store, is_demo_mode, is_test_mode
from vibelens.models.recommendation.results import RecommendationResult
from vibelens.schemas.analysis import AnalysisJobResponse, AnalysisJobStatus
from vibelens.schemas.cost_estimate import CostEstimateResponse
from vibelens.schemas.recommendation import (
    CatalogStatusResponse,
    RecommendationAnalyzeRequest,
)
from vibelens.services.job_tracker import (
    cancel_job,
    get_job,
    mark_completed,
    mark_failed,
    submit_job,
)
from vibelens.services.recommendation import analyze_recommendation, estimate_recommendation
from vibelens.services.recommendation.catalog import load_catalog
from vibelens.services.recommendation.mock import build_mock_recommendation_result
from vibelens.services.recommendation.store import RecommendationMeta
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/recommendation", tags=["recommendation"])


async def _run_recommendation(
    job_id: str,
    session_ids: list[str],
    token: str | None,
) -> None:
    """Background wrapper for recommendation analysis."""
    try:
        result = await analyze_recommendation(session_ids, session_token=token)
        store = get_recommendation_store()
        store.save(result, result.analysis_id or "")
        mark_completed(job_id, result.analysis_id or "")
    except asyncio.CancelledError:
        logger.info("Recommendation job %s was cancelled", job_id)
        raise
    except Exception as exc:
        mark_failed(job_id, f"{type(exc).__name__}: {exc}")
        logger.exception("Recommendation job %s failed", job_id)


@router.post("/analyze")
async def recommendation_analyze(
    body: RecommendationAnalyzeRequest,
    x_session_token: str | None = Header(None),
) -> AnalysisJobResponse:
    """Start a recommendation analysis (background job).

    Args:
        body: Request with session IDs.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        Job ID and initial status.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    if is_test_mode() or is_demo_mode():
        result = build_mock_recommendation_result(body.session_ids)
        store = get_recommendation_store()
        store.save(result, result.analysis_id or "mock")
        return AnalysisJobResponse(
            job_id="mock", status="completed", analysis_id=result.analysis_id
        )

    job_id = secrets.token_urlsafe(12)
    try:
        submit_job(job_id, _run_recommendation(job_id, body.session_ids, x_session_token))
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return AnalysisJobResponse(job_id=job_id, status="running")


@router.post("/estimate")
async def recommendation_estimate(
    body: RecommendationAnalyzeRequest,
    x_session_token: str | None = Header(None),
) -> CostEstimateResponse:
    """Pre-flight cost estimate for recommendation analysis.

    Args:
        body: Request with session IDs.
        x_session_token: Browser tab token for upload scoping.

    Returns:
        Cost estimate.
    """
    if not body.session_ids:
        raise HTTPException(status_code=400, detail="session_ids must not be empty")

    try:
        est = estimate_recommendation(body.session_ids, session_token=x_session_token)
    except ValueError as exc:
        status = 503 if "inference backend" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return CostEstimateResponse(
        model=est.model,
        batch_count=est.batch_count,
        total_input_tokens=est.total_input_tokens,
        total_output_tokens_budget=est.total_output_tokens_budget,
        cost_min_usd=est.cost_min_usd,
        cost_max_usd=est.cost_max_usd,
        pricing_found=est.pricing_found,
        formatted_cost=est.formatted_cost,
    )


@router.get("/jobs/{job_id}")
async def recommendation_job_status(job_id: str) -> AnalysisJobStatus:
    """Poll recommendation job status.

    Args:
        job_id: Job identifier.

    Returns:
        Current job status.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return AnalysisJobStatus(
        job_id=job.job_id,
        status=job.status.value,
        analysis_id=job.analysis_id,
        error_message=job.error_message,
    )


@router.post("/jobs/{job_id}/cancel")
async def recommendation_job_cancel(job_id: str) -> AnalysisJobStatus:
    """Cancel a running recommendation job.

    Args:
        job_id: Job identifier.

    Returns:
        Updated job status.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    cancel_job(job_id)
    return AnalysisJobStatus(
        job_id=job.job_id,
        status=job.status.value,
        analysis_id=job.analysis_id,
        error_message=job.error_message,
    )


@router.get("/history")
async def recommendation_history() -> list[RecommendationMeta]:
    """List all persisted recommendation analyses, newest first."""
    return get_recommendation_store().list_analyses()


@router.get("/{analysis_id}")
async def recommendation_load(analysis_id: str) -> RecommendationResult:
    """Load a persisted recommendation result.

    Args:
        analysis_id: Unique analysis identifier.

    Returns:
        Full RecommendationResult.
    """
    result = get_recommendation_store().load(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Recommendation {analysis_id} not found")
    return result


@router.delete("/{analysis_id}")
async def recommendation_delete(analysis_id: str) -> dict[str, bool]:
    """Delete a persisted recommendation result.

    Args:
        analysis_id: Unique analysis identifier.

    Returns:
        Success status.
    """
    deleted = get_recommendation_store().delete(analysis_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Recommendation {analysis_id} not found")
    return {"deleted": True}


@router.get("/catalog/status")
async def catalog_status() -> CatalogStatusResponse:
    """Get current catalog version and item count."""
    catalog = load_catalog()
    if not catalog:
        return CatalogStatusResponse(version="none", item_count=0, schema_version=0)
    return CatalogStatusResponse(
        version=catalog.version,
        item_count=len(catalog.items),
        schema_version=catalog.schema_version,
    )
```

- [ ] **Step 5: Add recommendation_router to api/__init__.py**

In `src/vibelens/api/__init__.py`, add:

```python
from vibelens.api.recommendation import router as recommendation_router
```

And in `build_router()`:

```python
router.include_router(recommendation_router)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/api/test_recommendation_api.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add recommendation API endpoints, schemas, and router"
```

---

### Task 12: Add CLI commands for catalog management

Add `build-catalog` and `update-catalog` commands to the Typer CLI.

**Files:**
- Modify: `src/vibelens/cli.py`
- Test: `tests/cli/test_catalog_cli.py`

- [ ] **Step 1: Write test**

```python
# tests/cli/test_catalog_cli.py
"""Tests for catalog CLI commands."""
from typer.testing import CliRunner
from vibelens.cli import app

runner = CliRunner()


def test_update_catalog_check_command():
    """update-catalog --check runs without error (may warn about missing URL)."""
    result = runner.invoke(app, ["update-catalog", "--check"])
    # Should not crash even without config
    assert result.exit_code in (0, 1)
    print(f"Output: {result.stdout}")


def test_build_catalog_requires_token():
    """build-catalog without --github-token fails with helpful message."""
    result = runner.invoke(app, ["build-catalog"])
    assert result.exit_code != 0 or "token" in result.stdout.lower() or "token" in (result.stderr or "").lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_catalog_cli.py -v`
Expected: FAIL — commands don't exist yet.

- [ ] **Step 3: Add CLI commands**

In `src/vibelens/cli.py`, add after the `version` command:

```python
@app.command()
def update_catalog(
    check: bool = typer.Option(False, "--check", help="Check version without downloading"),
) -> None:
    """Download the latest catalog from the update URL."""
    from vibelens.config import load_settings
    settings = load_settings()
    if not settings.catalog_update_url:
        typer.echo("No catalog_update_url configured. Set it in your vibelens.yaml or environment.")
        raise typer.Exit(code=1)

    if check:
        typer.echo(f"Catalog update URL: {settings.catalog_update_url}")
        typer.echo("Version check not yet implemented (requires catalog loader).")
        raise typer.Exit()

    typer.echo("Catalog download not yet implemented (requires HTTP client).")
    raise typer.Exit(code=1)


@app.command()
def build_catalog(
    github_token: str = typer.Option("", "--github-token", help="GitHub personal access token"),
    output: str = typer.Option("catalog.json", "--output", help="Output file path"),
) -> None:
    """Build catalog.json by crawling GitHub (requires --github-token)."""
    if not github_token:
        typer.echo("Error: --github-token is required for catalog builds.")
        typer.echo("Usage: vibelens build-catalog --github-token $GITHUB_TOKEN")
        raise typer.Exit(code=1)

    typer.echo(f"Catalog build not yet implemented (planned for crawler subpackage).")
    typer.echo(f"Would output to: {output}")
    raise typer.Exit(code=1)
```

Note: The actual HTTP download and GitHub crawling will be implemented in a future plan (crawler subpackage). These commands establish the CLI interface now.

- [ ] **Step 4: Run tests**

Run: `pytest tests/cli/test_catalog_cli.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibelens/cli.py tests/cli/test_catalog_cli.py
git commit -m "feat: add build-catalog and update-catalog CLI commands"
```

---

### Task 13: Run full test suite and verify alignment

Run the full test suite, verify all 344+ tests still pass, and check that the implementation matches the spec migration path.

**Files:**
- No new files. Verification only.

- [ ] **Step 1: Run ruff**

```bash
ruff check src/ tests/
```

Expected: Clean (0 errors). Fix any linting issues found.

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v --timeout=300
```

Expected: All tests pass (344+ existing + ~30 new tests from this plan).

- [ ] **Step 3: Verify spec alignment**

Check off completed migration path items:

**Phase B (Prompts):**
- [x] Item 10: Move `llm/prompts/` to `src/vibelens/prompts/` — Done in Plan 1
- [x] Item 11: Rename `skill_creation.py` → `creation.py`, `skill_evolution.py` → `evolution.py` — Task 1
- [x] Item 12: Delete `skill_retrieval.py`, create `recommendation.py` — Tasks 1, 6
- [x] Item 13: Split `templates/skill/` → `templates/creation/` and `templates/evolution/` — Task 1
- [x] Item 14: Create `templates/recommendation/` — Task 6
- [x] Item 15: Update `PROMPT_REGISTRY` and all imports — Tasks 1, 6

**Phase C (Services) — Plan 2 items:**
- [x] Item 16: Create `services/shared.py` — Deferred; `services/skill/shared.py` still used. Cross-pipeline extraction happens in Plans 3/4 when `services/skill/` is dissolved.
- [x] Item 17: Create `services/recommendation/` package — Tasks 5, 7, 8, 9, 10
- [ ] Item 18: Create `services/recommendation/crawler/` — Deferred to a dedicated crawler plan (heavy GitHub API work, separate concern)
- [ ] Item 19: Move `services/skill/download.py` and `importer.py` to `services/recommendation/` — Deferred to Plan 3 (when services/skill/ is dissolved)
- [x] Item 23: Add `PRESET_RECOMMENDATION` — Task 3

**Phase D (API + CLI + Config):**
- [x] Item 24: Add catalog config fields to settings — Task 4
- [x] Item 25: Create `api/recommendation.py` — Task 11
- [ ] Item 26: Split `api/skill_analysis.py` → `api/creation.py` and `api/evolution.py` — Plan 3/4
- [x] Item 27: Add recommendation_router to `api/__init__.py` — Task 11
- [x] Item 28: Create `schemas/recommendation.py` — Task 11
- [x] Item 29: Add `get_recommendation_store()` to `deps.py` — Task 10
- [x] Item 30: Add CLI commands — Task 12

**Deferred to later plans:**
- Items 18-19: Crawler and download/importer move — separate crawler plan
- Items 20-22: services/creation/, services/evolution/, delete services/skill/ — Plans 3 and 4
- Item 26: Split api/skill_analysis.py — Plans 3 and 4
- Items 31-34: Data migration, frontend — Phase E plan
- POST `/recommendation/{analysis_id}/install` endpoint — requires `services/recommendation/installer.py` (generates agent-executable markdown from selected items). Separate task after core pipeline works.
- `services/shared.py` extraction from `services/skill/shared.py` — Plans 3/4 when services/skill/ dissolves

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: post-plan-2 cleanup and test fixes"
```

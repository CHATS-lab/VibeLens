"""Mock skill analysis data for demo/test mode.

Builds a realistic SkillAnalysisResult with workflow patterns and
recommendations, using real step IDs from loaded trajectories.
"""

from datetime import UTC, datetime

from vibelens.deps import get_central_skill_store, get_store
from vibelens.models.analysis.skills import (
    SkillAnalysisResult,
    SkillCreation,
    SkillEvolutionSuggestion,
    SkillMode,
    SkillRecommendation,
    WorkflowPattern,
)
from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.inference import BackendType


def build_mock_skill_result(session_ids: list[str], mode: SkillMode) -> SkillAnalysisResult:
    """Build a mock SkillAnalysisResult for demo/test mode.

    Args:
        session_ids: Session IDs from the request.
        mode: Analysis mode (retrieval, creation, or evolution).

    Returns:
        Mock SkillAnalysisResult with sample patterns and mode-specific output.
    """
    step_pool = _collect_step_ids(session_ids)
    loaded_ids = list(step_pool.keys())
    skipped = [sid for sid in session_ids if sid not in step_pool]

    patterns = _build_mock_patterns(step_pool)

    recommendations: list[SkillRecommendation] = []
    generated_skills: list[SkillCreation] = []
    evolution_suggestions: list[SkillEvolutionSuggestion] = []

    if mode == SkillMode.RETRIEVAL:
        recommendations = _build_mock_recommendations()
    elif mode == SkillMode.CREATION:
        generated_skills = _build_mock_creations()
    elif mode == SkillMode.EVOLUTION:
        evolution_suggestions = _build_mock_evolutions()

    return SkillAnalysisResult(
        mode=mode,
        workflow_patterns=patterns,
        recommendations=recommendations,
        generated_skills=generated_skills,
        evolution_suggestions=evolution_suggestions,
        summary=(
            f"Analyzed {len(loaded_ids)} sessions and detected {len(patterns)} "
            f"recurring workflow patterns. The most frequent pattern involves "
            f"search-then-read-then-edit sequences that could be automated with skills."
        ),
        user_profile=(
            "Developer focused on Python/TypeScript full-stack projects. "
            "Frequently uses Grep → Read → Edit → Bash workflows for code modifications. "
            "Prefers iterative development with test-driven verification."
        ),
        session_ids=loaded_ids,
        sessions_skipped=skipped,
        backend_id=BackendType.MOCK,
        model="mock/test-model",
        cost_usd=0.035,
        created_at=datetime.now(UTC).isoformat(),
    )


def _collect_step_ids(session_ids: list[str]) -> dict[str, list[str]]:
    """Load trajectories and collect step IDs per session."""
    store = get_store()
    pool: dict[str, list[str]] = {}
    for sid in session_ids:
        trajectories = store.load(sid)
        if not trajectories:
            continue
        step_ids = [step.step_id for traj in trajectories for step in traj.steps]
        if step_ids:
            pool[sid] = step_ids
    return pool


def _build_mock_patterns(pool: dict[str, list[str]]) -> list[WorkflowPattern]:
    """Build mock workflow patterns from real step IDs."""
    if not pool:
        return []

    sids = list(pool.keys())
    refs: list[StepRef] = []
    for sid in sids[:3]:
        steps = pool[sid]
        if steps:
            refs.append(StepRef(session_id=sid, start_step_id=steps[0]))

    return [
        WorkflowPattern(
            description=(
                "Search-read-edit cycle: Grep for pattern, read matching file, then edit it."
            ),
            pain_point=(
                "Manual three-step workflow repeated across sessions. Could be a single skill."
            ),
            example_refs=refs[:2],
        ),
        WorkflowPattern(
            description="Test-fix loop: Run tests, read failure, apply fix, re-run tests.",
            pain_point=(
                "Repetitive cycle consumes context. "
                "A skill could automate the read-fix-verify loop."
            ),
            example_refs=refs[:1],
        ),
        WorkflowPattern(
            description=(
                "New file scaffolding: Create file with boilerplate, add imports, run linter."
            ),
            pain_point=(
                "Boilerplate structure is identical across files. A skill could generate it."
            ),
            example_refs=refs[1:3] if len(refs) > 1 else refs,
        ),
    ]


def _build_mock_recommendations() -> list[SkillRecommendation]:
    """Build mock skill recommendations."""
    return [
        SkillRecommendation(
            skill_name="smart-refactor",
            match_reason=(
                "Automates the search-read-edit pattern with intelligent code refactoring."
            ),
            confidence=0.85,
        ),
        SkillRecommendation(
            skill_name="test-driven-fix",
            match_reason="Automates the test-fix-verify loop with structured error analysis.",
            confidence=0.72,
        ),
    ]


def _build_mock_creations() -> list[SkillCreation]:
    """Build mock skill creations."""
    return [
        SkillCreation(
            name="project-scaffold",
            description="Generate project file scaffolding with standard boilerplate and imports.",
            skill_md_content=(
                "---\n"
                "description: Generate project file scaffolding with standard boilerplate.\n"
                "allowed-tools: Write, Edit, Bash\n"
                "---\n\n"
                "# Project Scaffold\n\n"
                "When creating a new file in the project:\n"
                "1. Use the project's standard template structure\n"
                "2. Include required imports based on file location\n"
                "3. Add module docstring following Google style\n"
                "4. Run the linter after creation\n"
            ),
            rationale="Detected repeated file creation with identical boilerplate structure.",
        ),
    ]


def _build_mock_evolutions() -> list[SkillEvolutionSuggestion]:
    """Build mock evolution suggestions using installed skills."""
    skill_store = get_central_skill_store()
    skills = skill_store.get_cached()

    if not skills:
        return []

    first_skill = skills[0]
    return [
        SkillEvolutionSuggestion(
            skill_name=first_skill.name,
            edits=[],
            rationale=(
                f"Skill '{first_skill.name}' could benefit from additional "
                f"instructions based on observed usage patterns."
            ),
        ),
    ]

"""Mock skill analysis data for demo/test mode.

Builds a realistic SkillAnalysisResult with workflow patterns and
recommendations, using real step IDs from loaded trajectories.
"""

from datetime import UTC, datetime

from vibelens.deps import get_central_skill_store
from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.inference import BackendType
from vibelens.models.skill.skills import (
    SkillAnalysisResult,
    SkillCreation,
    SkillEdit,
    SkillEditKind,
    SkillEvolutionSuggestion,
    SkillMode,
    SkillRecommendation,
    WorkflowPattern,
)
from vibelens.services.session.store_resolver import load_from_stores


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
            f"search-then-read-then-edit sequences that could be automated with skills. "
            f"Several test-driven development loops and file scaffolding patterns were also "
            f"identified as strong candidates for skill automation."
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


MAX_MOCK_SESSIONS = 5


def _collect_step_ids(session_ids: list[str]) -> dict[str, list[str]]:
    """Load trajectories and collect step IDs per session.

    Only loads up to MAX_MOCK_SESSIONS to avoid slow I/O in mock mode.
    All remaining session_ids are reported as loaded (with no step refs).
    """
    pool: dict[str, list[str]] = {}
    for sid in session_ids[:MAX_MOCK_SESSIONS]:
        trajectories = load_from_stores(sid)
        if not trajectories:
            continue
        step_ids = [step.step_id for traj in trajectories for step in traj.steps]
        if step_ids:
            pool[sid] = step_ids
    # Mark remaining sessions as "loaded" without step data
    for sid in session_ids[MAX_MOCK_SESSIONS:]:
        if sid not in pool:
            pool[sid] = []
    return pool


def _build_mock_patterns(pool: dict[str, list[str]]) -> list[WorkflowPattern]:
    """Build mock workflow patterns with varying frequencies for edge-case coverage."""
    if not pool:
        return []

    sids = list(pool.keys())

    # Build a large pool of step refs across sessions
    all_refs: list[StepRef] = []
    for sid in sids[:5]:
        steps = pool[sid]
        for step_id in steps[:3]:
            all_refs.append(StepRef(session_id=sid, start_step_id=step_id))

    return [
        WorkflowPattern(
            title="Search-Read-Edit Cycle",
            description=(
                "Grep for a pattern, read the matching file, then edit it. "
                "This three-step sequence appears whenever code modifications are needed."
            ),
            pain_point=(
                "Manual three-step workflow repeated across sessions. "
                "Could be a single skill that searches, reads context, and applies edits."
            ),
            example_refs=all_refs[:6],
        ),
        WorkflowPattern(
            title="Test-Fix Loop",
            description=(
                "Run tests, read failure output, apply fix, re-run tests. "
                "Iterative debugging cycle until all tests pass."
            ),
            pain_point=(
                "Repetitive cycle consumes context window and developer attention. "
                "A skill could automate the read-fix-verify loop."
            ),
            example_refs=all_refs[:3],
        ),
        WorkflowPattern(
            title="New File Scaffolding",
            description=(
                "Create file with boilerplate structure, add standard imports, "
                "then run the linter. Identical scaffolding repeated for every new module."
            ),
            pain_point=(
                "Boilerplate structure is identical across files. "
                "A skill could generate the full scaffold in one step."
            ),
            example_refs=all_refs[1:3] if len(all_refs) > 1 else all_refs[:1],
        ),
        WorkflowPattern(
            title="Dependency Upgrade Workflow",
            description=(
                "Check outdated packages, read changelogs, update version constraints, "
                "run tests, and fix any breaking changes. Multi-step process per dependency."
            ),
            pain_point=(
                "Each dependency upgrade requires 4-5 manual steps. "
                "Batching multiple upgrades amplifies the effort."
            ),
            example_refs=all_refs[:1],
        ),
        WorkflowPattern(
            title="Config-Driven Feature Toggle",
            description=(
                "Read config files, add feature flags, update environment templates, "
                "and modify conditional logic in multiple source files."
            ),
            pain_point=(
                "Feature toggles touch config, env templates, and source code. "
                "Easy to miss one location, causing inconsistencies."
            ),
            example_refs=all_refs[2:6] if len(all_refs) > 2 else all_refs,
        ),
    ]


def _build_mock_recommendations() -> list[SkillRecommendation]:
    """Build mock skill recommendations with varying confidence levels."""
    return [
        SkillRecommendation(
            skill_name="smart-refactor",
            match_reason=(
                "Automates the search-read-edit pattern with intelligent code refactoring. "
                "Matches your most frequent workflow pattern with high confidence."
            ),
            confidence=0.92,
        ),
        SkillRecommendation(
            skill_name="test-driven-fix",
            match_reason=(
                "Automates the test-fix-verify loop with structured error analysis. "
                "Reads test output, identifies root cause, and applies targeted fixes."
            ),
            confidence=0.78,
        ),
        SkillRecommendation(
            skill_name="project-scaffold",
            match_reason=(
                "Generates standard project file scaffolding with imports and docstrings. "
                "Partially matches your file creation patterns."
            ),
            confidence=0.61,
        ),
        SkillRecommendation(
            skill_name="dep-updater",
            match_reason=(
                "Automates dependency version bumps with changelog analysis. "
                "Low match — your upgrade pattern is infrequent."
            ),
            confidence=0.35,
        ),
    ]


def _build_mock_creations() -> list[SkillCreation]:
    """Build mock skill creations covering different complexity levels."""
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
            rationale=(
                "Detected repeated file creation with identical boilerplate structure "
                "across 3 sessions. Automating this saves ~2 minutes per new file."
            ),
        ),
        SkillCreation(
            name="search-and-replace",
            description="Intelligent multi-file search and replace with preview and rollback.",
            skill_md_content=(
                "---\n"
                "description: Intelligent multi-file search and replace "
                "with context-aware matching.\n"
                "allowed-tools: Grep, Read, Edit, Bash\n"
                "---\n\n"
                "# Search and Replace\n\n"
                "When the user asks to rename or replace across files:\n"
                "1. Use Grep to find all occurrences with context\n"
                "2. Show a preview of proposed changes\n"
                "3. Apply changes file-by-file with Edit tool\n"
                "4. Run linter and tests to verify no breakage\n"
                "5. Summarize changes made\n"
            ),
            rationale=(
                "Your search-read-edit cycle is the most frequent pattern. "
                "This skill packages it into a single, repeatable workflow."
            ),
        ),
        SkillCreation(
            name="test-fix-loop",
            description="Automated test-driven debugging: run, diagnose, fix, verify.",
            skill_md_content=(
                "---\n"
                "description: Automated test-driven debugging loop.\n"
                "allowed-tools: Bash, Read, Edit, Grep\n"
                "---\n\n"
                "# Test-Fix Loop\n\n"
                "When tests fail:\n"
                "1. Parse the test output to identify failing tests\n"
                "2. Read the relevant source files for context\n"
                "3. Diagnose the root cause\n"
                "4. Apply the minimal fix\n"
                "5. Re-run only the affected tests\n"
                "6. If still failing, repeat from step 2 (max 3 iterations)\n"
            ),
            rationale=(
                "Test-fix loops consumed significant context in 2 sessions. "
                "Automating the diagnosis step alone would save ~40% of iterations."
            ),
        ),
    ]


def _build_mock_evolutions() -> list[SkillEvolutionSuggestion]:
    """Build mock evolution suggestions using installed skills."""
    skill_store = get_central_skill_store()
    skills = skill_store.get_cached()

    suggestions: list[SkillEvolutionSuggestion] = []

    if skills:
        first_skill = skills[0]
        suggestions.append(
            SkillEvolutionSuggestion(
                skill_name=first_skill.name,
                edits=[
                    SkillEdit(
                        kind=SkillEditKind.ADD_INSTRUCTION,
                        target="end of skill body",
                        replacement=(
                            "5. Run `ruff check` after every edit to catch lint errors early."
                        ),
                        rationale="User frequently runs linter manually after edits.",
                    ),
                    SkillEdit(
                        kind=SkillEditKind.UPDATE_DESCRIPTION,
                        target="skill description",
                        replacement=(
                            f"{first_skill.name} with automatic linting and error checking"
                        ),
                        rationale="Updated trigger description to reflect new capabilities.",
                    ),
                    SkillEdit(
                        kind=SkillEditKind.ADD_TOOL,
                        target="allowed-tools",
                        replacement="Grep",
                        rationale="Skill could benefit from Grep for searching related files.",
                    ),
                ],
                rationale=(
                    f"Skill '{first_skill.name}' could benefit from additional "
                    f"instructions based on observed usage patterns. "
                    f"Adding linting and search capabilities would align it with your workflow."
                ),
            )
        )

    if len(skills) > 1:
        second_skill = skills[1]
        suggestions.append(
            SkillEvolutionSuggestion(
                skill_name=second_skill.name,
                edits=[
                    SkillEdit(
                        kind=SkillEditKind.REMOVE_INSTRUCTION,
                        target="Step 3: Manual verification",
                        replacement=None,
                        rationale="This step is redundant — automated tests already cover it.",
                    ),
                    SkillEdit(
                        kind=SkillEditKind.REPLACE_INSTRUCTION,
                        target="Step 2: Read all files in directory",
                        replacement="Step 2: Read only modified files (use `git diff --name-only`)",
                        rationale="Reading all files wastes context. Focus on changed files only.",
                    ),
                ],
                rationale=(
                    f"Skill '{second_skill.name}' has redundant steps and reads too many files. "
                    f"Streamlining it would reduce context usage by ~30%."
                ),
            )
        )

    # Add a suggestion even if no skills installed
    if not suggestions:
        suggestions.append(
            SkillEvolutionSuggestion(
                skill_name="example-skill",
                edits=[
                    SkillEdit(
                        kind=SkillEditKind.ADD_INSTRUCTION,
                        target="end of skill body",
                        replacement="Always verify changes with the linter before completing.",
                        rationale="Consistent linting reduces review cycles.",
                    ),
                ],
                rationale=(
                    "No installed skills found. This is an example suggestion showing "
                    "how evolution analysis would improve your skills."
                ),
            )
        )

    return suggestions

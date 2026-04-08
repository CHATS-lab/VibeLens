"""Mock skill analysis data for demo/test mode.

Builds realistic SkillAnalysisResult instances using real step IDs
from loaded trajectories.
"""

from datetime import UTC, datetime

from vibelens.deps import get_central_skill_store
from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.llm.inference import BackendType
from vibelens.models.skill import (
    SkillAnalysisResult,
    SkillCreation,
    SkillEdit,
    SkillEvolution,
    SkillMode,
    SkillRecommendation,
    WorkflowPattern,
)
from vibelens.models.trajectories.metrics import Metrics
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
    creations: list[SkillCreation] = []
    evolutions: list[SkillEvolution] = []

    if mode == SkillMode.RETRIEVAL:
        recommendations = _build_mock_recommendations()
    elif mode == SkillMode.CREATION:
        creations = _build_mock_creations()
    elif mode == SkillMode.EVOLUTION:
        evolutions = _build_mock_evolutions()

    return SkillAnalysisResult(
        mode=mode,
        title="You Search, Read, and Edit Files in Repetitive Cycles That Could Be Automated",
        workflow_patterns=patterns,
        recommendations=recommendations,
        creations=creations,
        evolutions=evolutions,
        session_ids=loaded_ids,
        skipped_session_ids=skipped,
        backend_id=BackendType.MOCK,
        model="mock/test-model",
        metrics=Metrics(cost_usd=0.035),
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
            example_refs=all_refs[:6],
        ),
        WorkflowPattern(
            title="Test-Fix Loop",
            description=(
                "Run tests, read failure output, apply fix, re-run tests. "
                "Iterative debugging cycle until all tests pass."
            ),
            example_refs=all_refs[:3],
        ),
        WorkflowPattern(
            title="New File Scaffolding",
            description=(
                "Create file with boilerplate structure, add standard imports, "
                "then run the linter. Identical scaffolding repeated for every new module."
            ),
            example_refs=all_refs[1:3] if len(all_refs) > 1 else all_refs[:1],
        ),
        WorkflowPattern(
            title="Dependency Upgrade Workflow",
            description=(
                "Check outdated packages, read changelogs, update version constraints, "
                "run tests, and fix any breaking changes. Multi-step process per dependency."
            ),
            example_refs=all_refs[:1],
        ),
        WorkflowPattern(
            title="Config-Driven Feature Toggle",
            description=(
                "Read config files, add feature flags, update environment templates, "
                "and modify conditional logic in multiple source files."
            ),
            example_refs=all_refs[2:6] if len(all_refs) > 2 else all_refs,
        ),
    ]


def _build_mock_recommendations() -> list[SkillRecommendation]:
    """Build mock skill recommendations with varying confidence levels."""
    return [
        SkillRecommendation(
            skill_name="smart-refactor",
            description=(
                "Intelligently refactor code by searching, reading,"
                " and editing files in one coordinated step."
            ),
            rationale=(
                "Strong match for your most frequent workflow.\n"
                "- Automates the search-read-edit pattern with intelligent refactoring\n"
                "- Eliminates 3-step manual sequence per code change"
            ),
            addressed_patterns=["Search-Read-Edit Cycle"],
            confidence=0.92,
        ),
        SkillRecommendation(
            skill_name="test-driven-fix",
            description=(
                "Diagnose test failures and apply targeted fixes"
                " by reading test output and identifying root causes."
            ),
            rationale=(
                "Directly addresses your test-fix loops.\n"
                "- Reads test output and identifies root cause automatically\n"
                "- Applies targeted fixes without manual diagnosis steps"
            ),
            addressed_patterns=["Test-Fix Loop"],
            confidence=0.78,
        ),
        SkillRecommendation(
            skill_name="project-scaffold",
            description=(
                "Generate standard project file structure"
                " with imports, docstrings, and boilerplate."
            ),
            rationale=(
                "Partial match for file creation patterns.\n"
                "- Generates standard scaffolding with imports and docstrings"
            ),
            addressed_patterns=["New File Scaffolding"],
            confidence=0.61,
        ),
        SkillRecommendation(
            skill_name="dep-updater",
            description=(
                "Automate dependency version upgrades"
                " with changelog analysis and compatibility checks."
            ),
            rationale=(
                "Low match due to infrequent upgrade pattern.\n"
                "- Automates dependency version bumps with changelog analysis"
            ),
            addressed_patterns=["Dependency Upgrade Workflow"],
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
                "Repeated boilerplate detected across 3 sessions.\n"
                "- Identical file structure created manually each time\n"
                "- Automating saves ~2 minutes per new file"
            ),
            tools_used=[],
            addressed_patterns=["New File Scaffolding"],
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
                "Most frequent pattern in your sessions.\n"
                "- Packages search-read-edit into a single repeatable workflow"
            ),
            tools_used=[],
            addressed_patterns=["Search-Read-Edit Cycle"],
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
                "Test-fix loops consumed significant context in 2 sessions.\n"
                "- Automating the diagnosis step saves ~40% of iterations"
            ),
            tools_used=[],
            addressed_patterns=["Test-Fix Loop"],
        ),
    ]


def _build_mock_evolutions() -> list[SkillEvolution]:
    """Build mock evolution suggestions using installed skills."""
    skill_store = get_central_skill_store()
    skills = skill_store.get_cached()

    evolutions: list[SkillEvolution] = []

    if skills:
        first_skill = skills[0]
        evolutions.append(
            SkillEvolution(
                skill_name=first_skill.name,
                description=first_skill.description or first_skill.name,
                edits=[
                    SkillEdit(
                        old_string="",
                        new_string="5. Run `ruff check` after every edit to catch lint errors.",
                    ),
                    SkillEdit(
                        old_string=first_skill.description or first_skill.name,
                        new_string=f"{first_skill.name} with automatic linting and error checking",
                    ),
                    SkillEdit(
                        old_string="allowed_tools: [Read, Edit]",
                        new_string="allowed_tools: [Read, Edit, Grep]",
                    ),
                ],
                rationale=(
                    f"Skill '{first_skill.name}' needs alignment with observed usage.\n"
                    "- Adding linting catches errors earlier in the workflow\n"
                    "- Search capabilities match your grep-first patterns"
                ),
                addressed_patterns=["Search-Read-Edit Cycle", "Test-Fix Loop"],
            )
        )

    if len(skills) > 1:
        second_skill = skills[1]
        evolutions.append(
            SkillEvolution(
                skill_name=second_skill.name,
                description=second_skill.description or second_skill.name,
                edits=[
                    SkillEdit(
                        old_string="Step 3: Manual verification\n",
                        new_string="",
                    ),
                    SkillEdit(
                        old_string="Step 2: Read all files in directory",
                        new_string="Step 2: Read only modified files (use `git diff --name-only`)",
                    ),
                ],
                rationale=(
                    f"Skill '{second_skill.name}' wastes context on redundant steps.\n"
                    "- Removing manual verification step saves a full turn\n"
                    "- Reading only modified files reduces context usage by ~30%"
                ),
                addressed_patterns=["New File Scaffolding"],
            )
        )

    if not evolutions:
        evolutions.append(
            SkillEvolution(
                skill_name="example-skill",
                description="Example skill for demonstrating evolution analysis.",
                edits=[
                    SkillEdit(
                        old_string="",
                        new_string="Always verify changes with the linter before completing.",
                    ),
                ],
                rationale=(
                    "No installed skills found.\n"
                    "- This is an example showing how evolution analysis works"
                ),
                addressed_patterns=["Config-Driven Feature Toggle"],
            )
        )

    return evolutions

"""Mock creation analysis data for demo/test mode.

Builds realistic CreationAnalysisResult instances using real step IDs
from loaded trajectories.
"""

from datetime import datetime, timezone

from vibelens.models.creation import CreationAnalysisResult, ElementCreation
from vibelens.models.llm.inference import BackendType
from vibelens.models.session.patterns import WorkflowPattern
from vibelens.models.step_ref import StepRef
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.session.store_resolver import load_from_stores

# Cap session loading in mock mode to avoid slow I/O
MAX_MOCK_SESSIONS = 5


def build_mock_creation_result(session_ids: list[str]) -> CreationAnalysisResult:
    """Build a mock CreationAnalysisResult for demo/test mode.

    Args:
        session_ids: Session IDs from the request.

    Returns:
        Mock CreationAnalysisResult with sample patterns and creations.
    """
    step_pool = _collect_step_ids(session_ids)
    loaded_ids = list(step_pool.keys())
    skipped = [sid for sid in session_ids if sid not in step_pool]

    patterns = _build_mock_patterns(step_pool)
    creations = _build_mock_creations()

    return CreationAnalysisResult(
        title="You Repeat File Scaffolding and Multi-File Search Patterns Every Session",
        workflow_patterns=patterns,
        creations=creations,
        session_ids=loaded_ids,
        skipped_session_ids=skipped,
        backend_id=BackendType.MOCK,
        model="mock/test-model",
        metrics=Metrics(cost_usd=0.035),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


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
    """Build mock workflow patterns with step refs from loaded sessions."""
    if not pool:
        return []

    sids = list(pool.keys())

    all_refs: list[StepRef] = []
    for sid in sids[:5]:
        steps = pool[sid]
        for step_id in steps[:3]:
            all_refs.append(StepRef(session_id=sid, start_step_id=step_id))

    return [
        WorkflowPattern(
            title="New File Scaffolding",
            description=(
                "Create file with boilerplate structure, add standard imports, "
                "then run the linter. Identical scaffolding repeated for every new module."
            ),
            example_refs=all_refs[:6],
        ),
        WorkflowPattern(
            title="Search-Read-Edit Cycle",
            description=(
                "Grep for a pattern, read the matching file, then edit it. "
                "This three-step sequence appears whenever code modifications are needed."
            ),
            example_refs=all_refs[:3],
        ),
    ]


def _build_mock_creations() -> list[ElementCreation]:
    """Build mock element creations covering common workflow patterns."""
    return [
        ElementCreation(
            name="project-scaffold",
            description=(
                "Generate project file scaffolding with standard boilerplate and imports. "
                "Activate when creating a new module or file."
            ),
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
            tools_used=["Write", "Edit", "Bash"],
            addressed_patterns=["New File Scaffolding"],
            confidence=0.88,
        ),
        ElementCreation(
            name="search-and-replace",
            description=(
                "Intelligent multi-file search and replace with context-aware matching. "
                "Activate when renaming or replacing patterns across the codebase."
            ),
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
            tools_used=["Grep", "Read", "Edit", "Bash"],
            addressed_patterns=["Search-Read-Edit Cycle"],
            confidence=0.92,
        ),
    ]

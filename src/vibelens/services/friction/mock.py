"""Mock friction analysis data for demo/test mode.

Builds realistic FrictionAnalysisResult with user-centric friction types
covering all severity levels, spread across available sessions.
"""

from datetime import UTC, datetime

from vibelens.models.analysis.friction import (
    FrictionAnalysisResult,
    FrictionCost,
    FrictionType,
    Mitigation,
)
from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.llm.inference import BackendType
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.session.store_resolver import load_from_stores


def build_mock_friction_result(session_ids: list[str]) -> FrictionAnalysisResult:
    """Build a realistic mock FrictionAnalysisResult for demo/test mode.

    Loads real trajectories from the store to extract actual step IDs,
    ensuring jump-to-step navigation works end-to-end.

    Args:
        session_ids: Session IDs from the request.

    Returns:
        Mock FrictionAnalysisResult with sample friction types and mitigations.
    """
    step_id_pool = _collect_step_ids(session_ids)
    friction_types = _build_mock_types(step_id_pool)
    skipped = [sid for sid in session_ids if sid not in step_id_pool]

    return FrictionAnalysisResult(
        title="Agent Often Changed More Than Requested and Misread Your Requirements",
        mitigations=[
            Mitigation(
                title="Confirm requirements before coding",
                action=(
                    "Before starting implementation, restate the user's"
                    " requirement and wait for confirmation."
                ),
                rationale=(
                    "Prevents wasted effort from misunderstood intent.\n"
                    "- Catches scope mismatches before any code is written\n"
                    "- Reduces correction cycles by 60-80%"
                ),
                confidence=0.9,
                addressed_friction_types=["misunderstood-intent", "scope-violation"],
            ),
            Mitigation(
                title="Limit changes to requested scope",
                action=(
                    "Only change what was explicitly requested."
                    " Never refactor adjacent code."
                ),
                rationale=(
                    "Scope creep caused most high-severity friction.\n"
                    "- Unrequested refactors broke existing tests\n"
                    "- User had to revert changes multiple times"
                ),
                confidence=0.85,
                addressed_friction_types=["scope-violation"],
            ),
            Mitigation(
                title="Read full test context first",
                action=(
                    "When a test fails, read the full test file including"
                    " fixtures before attempting a fix."
                ),
                rationale=(
                    "Repeated failures stemmed from partial context.\n"
                    "- Agent fixed wrong assertions three times\n"
                    "- Full fixture reading prevents blind guessing"
                ),
                confidence=0.7,
                addressed_friction_types=["repeated-failure", "quality-rejection"],
            ),
        ],
        friction_types=friction_types,
        session_ids=list(step_id_pool.keys()),
        skipped_session_ids=skipped,
        batch_count=1,
        backend_id=BackendType.MOCK,
        model="mock/test-model",
        metrics=Metrics(cost_usd=0.042),
        created_at=datetime.now(UTC).isoformat(),
    )


def _collect_step_ids(session_ids: list[str]) -> dict[str, list[str]]:
    """Load trajectories and collect agent step IDs per session.

    Args:
        session_ids: Requested session IDs.

    Returns:
        Mapping of session_id to list of step_ids (agent steps only).
    """
    pool: dict[str, list[str]] = {}
    for sid in session_ids:
        trajectories = load_from_stores(sid)
        if not trajectories:
            continue
        step_ids = [
            step.step_id for traj in trajectories for step in traj.steps if step.source == "agent"
        ]
        if step_ids:
            pool[sid] = step_ids
    return pool


def _pick_steps(
    pool: dict[str, list[str]], session_idx: int, start: int, count: int
) -> tuple[str, list[str]]:
    """Pick consecutive step IDs from the pool for a mock example ref."""
    sids = list(pool.keys())
    sid = sids[session_idx % len(sids)]
    steps = pool[sid]
    actual_start = min(start, max(len(steps) - count, 0))
    return sid, steps[actual_start : actual_start + count]


def _build_mock_types(pool: dict[str, list[str]]) -> list[FrictionType]:
    """Build mock friction types with user-centric categories."""
    if not pool:
        return []

    n = len(pool)

    sid_1, steps_1 = _pick_steps(pool, 0, 1, 3)
    sid_2, steps_2 = _pick_steps(pool, 1 % n, 2, 2)
    sid_3, steps_3 = _pick_steps(pool, 2 % n, 4, 4)
    sid_4, steps_4 = _pick_steps(pool, 3 % n, 0, 1)
    sid_5, steps_5 = _pick_steps(pool, 4 % n, 6, 3)

    return [
        FrictionType(
            type_name="scope-violation",
            description=(
                "User wanted CSS alignment fix but agent refactored the entire"
                " component, breaking existing tests."
            ),
            severity=5,
            example_refs=[
                StepRef(
                    session_id=sid_3,
                    start_step_id=steps_3[0],
                    end_step_id=steps_3[-1] if len(steps_3) > 1 else None,
                ),
            ],
            friction_cost=FrictionCost(
                affected_steps=4, affected_tokens=18000, affected_time_seconds=120
            ),
        ),
        FrictionType(
            type_name="misunderstood-intent",
            description=(
                "User asked for incremental JWT migration but agent"
                " rewrote the entire auth module from scratch."
            ),
            severity=4,
            example_refs=[
                StepRef(
                    session_id=sid_1,
                    start_step_id=steps_1[0],
                    end_step_id=steps_1[-1] if len(steps_1) > 1 else None,
                ),
            ],
            friction_cost=FrictionCost(
                affected_steps=3, affected_tokens=12000, affected_time_seconds=90
            ),
        ),
        FrictionType(
            type_name="quality-rejection",
            description=(
                "User wanted simple Pydantic validators but agent"
                " added overly complex custom validation logic."
            ),
            severity=3,
            example_refs=[
                StepRef(
                    session_id=sid_2,
                    start_step_id=steps_2[0],
                    end_step_id=steps_2[-1] if len(steps_2) > 1 else None,
                ),
            ],
            friction_cost=FrictionCost(
                affected_steps=2, affected_tokens=6500, affected_time_seconds=45
            ),
        ),
        FrictionType(
            type_name="repeated-failure",
            description=(
                "User pointed out fixture issue but agent fixed"
                " the wrong assertion three times before understanding."
            ),
            severity=3,
            example_refs=[
                StepRef(
                    session_id=sid_5,
                    start_step_id=steps_5[0],
                    end_step_id=steps_5[-1] if len(steps_5) > 1 else None,
                ),
            ],
            friction_cost=FrictionCost(
                affected_steps=3, affected_tokens=9500, affected_time_seconds=60
            ),
        ),
        FrictionType(
            type_name="abandoned-task",
            description="User gave up on generating TypeScript types from the OpenAPI spec.",
            severity=2,
            example_refs=[
                StepRef(session_id=sid_4, start_step_id=steps_4[0]),
            ],
            friction_cost=FrictionCost(
                affected_steps=1, affected_tokens=2000, affected_time_seconds=15
            ),
        ),
    ]

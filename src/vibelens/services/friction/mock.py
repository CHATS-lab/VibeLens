"""Mock friction analysis data for demo/test mode.

Builds realistic FrictionAnalysisResult with user-centric friction events
covering all severity levels, spread across available sessions.
"""

from datetime import UTC, datetime

from vibelens.models.analysis.friction import (
    FrictionAnalysisResult,
    FrictionCost,
    FrictionEvent,
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
        Mock FrictionAnalysisResult with sample events and mitigations.
    """
    step_id_pool = _collect_step_ids(session_ids)
    events = _build_mock_events(step_id_pool)
    skipped = [sid for sid in session_ids if sid not in step_id_pool]
    session_count = len(step_id_pool)

    return FrictionAnalysisResult(
        title="Scope Violations and Misunderstood Intent",
        user_profile=(
            "Full-stack developer working on auth, API, and frontend components. "
            "Prefers incremental changes over rewrites."
        ),
        summary=(
            f"Analysis of {session_count} session{'s' if session_count != 1 else ''} "
            f"found {len(events)} friction events where users expressed dissatisfaction. "
            "Most friction stemmed from the agent misunderstanding user intent and "
            "producing code that didn't match requirements."
        ),
        mitigations=[
            Mitigation(
                action=(
                    "Before starting implementation, restate the user's"
                    " requirement and wait for confirmation."
                ),
                confidence=0.9,
            ),
            Mitigation(
                action=(
                    "Only change what was explicitly requested."
                    " Never refactor adjacent code."
                ),
                confidence=0.85,
            ),
            Mitigation(
                action=(
                    "When a test fails, read the full test file including"
                    " fixtures before attempting a fix."
                ),
                confidence=0.7,
            ),
        ],
        friction_events=events,
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
    """Pick consecutive step IDs from the pool for a mock event."""
    sids = list(pool.keys())
    sid = sids[session_idx % len(sids)]
    steps = pool[sid]
    actual_start = min(start, max(len(steps) - count, 0))
    return sid, steps[actual_start : actual_start + count]


def _build_mock_events(pool: dict[str, list[str]]) -> list[FrictionEvent]:
    """Build mock friction events with user-centric friction types."""
    if not pool:
        return []

    n = len(pool)

    sid_1, steps_1 = _pick_steps(pool, 0, 1, 3)
    sid_2, steps_2 = _pick_steps(pool, 1 % n, 2, 2)
    sid_3, steps_3 = _pick_steps(pool, 2 % n, 4, 4)
    sid_4, steps_4 = _pick_steps(pool, 3 % n, 0, 1)
    sid_5, steps_5 = _pick_steps(pool, 4 % n, 6, 3)

    return [
        FrictionEvent(
            friction_type="scope-violation",
            span_ref=StepRef(
                session_id=sid_3,
                start_step_id=steps_3[0],
                end_step_id=steps_3[-1] if len(steps_3) > 1 else None,
            ),
            severity=5,
            user_intention="Fix the login button CSS alignment",
            description=(
                "Agent fixed CSS but also refactored the entire"
                " component, breaking existing tests."
            ),
            friction_cost=FrictionCost(
                affected_steps=4, affected_tokens=18000, affected_time_seconds=120
            ),
        ),
        FrictionEvent(
            friction_type="misunderstood-intent",
            span_ref=StepRef(
                session_id=sid_1,
                start_step_id=steps_1[0],
                end_step_id=steps_1[-1] if len(steps_1) > 1 else None,
            ),
            severity=4,
            user_intention="Refactor auth module to use JWT tokens instead of session cookies",
            description=(
                "Agent rewrote the entire auth module from scratch"
                " instead of migrating incrementally."
            ),
            friction_cost=FrictionCost(
                affected_steps=3, affected_tokens=12000, affected_time_seconds=90
            ),
        ),
        FrictionEvent(
            friction_type="quality-rejection",
            span_ref=StepRef(
                session_id=sid_2,
                start_step_id=steps_2[0],
                end_step_id=steps_2[-1] if len(steps_2) > 1 else None,
            ),
            severity=3,
            user_intention="Add input validation to the API endpoint",
            description=(
                "Agent added overly complex validation when user"
                " wanted simple Pydantic validators."
            ),
            friction_cost=FrictionCost(
                affected_steps=2, affected_tokens=6500, affected_time_seconds=45
            ),
        ),
        FrictionEvent(
            friction_type="repeated-failure",
            span_ref=StepRef(
                session_id=sid_5,
                start_step_id=steps_5[0],
                end_step_id=steps_5[-1] if len(steps_5) > 1 else None,
            ),
            severity=3,
            user_intention="Run the test suite and fix the failing test",
            description=(
                "Agent fixed the wrong assertion three times before"
                " user pointed out the fixture issue."
            ),
            friction_cost=FrictionCost(
                affected_steps=3, affected_tokens=9500, affected_time_seconds=60
            ),
        ),
        FrictionEvent(
            friction_type="abandoned-task",
            span_ref=StepRef(
                session_id=sid_4,
                start_step_id=steps_4[0],
            ),
            severity=2,
            user_intention="Generate TypeScript types from the OpenAPI spec",
            description="",
            friction_cost=FrictionCost(
                affected_steps=1, affected_tokens=2000, affected_time_seconds=15
            ),
        ),
    ]

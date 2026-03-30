"""Mock friction analysis data for demo/test mode.

Builds realistic FrictionAnalysisResult with user-centric friction events
covering all severity levels, spread across available sessions.
"""

from collections import defaultdict
from datetime import UTC, datetime

from vibelens.models.analysis.friction import (
    FrictionAnalysisResult,
    FrictionCost,
    FrictionEvent,
    Mitigation,
    TypeSummary,
)
from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.inference import BackendType
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
    type_summary = _build_mock_type_summary(events)
    skipped = [sid for sid in session_ids if sid not in step_id_pool]
    session_count = len(step_id_pool)

    return FrictionAnalysisResult(
        events=events,
        summary=(
            f"Analysis of {session_count} session{'s' if session_count != 1 else ''} "
            f"found {len(events)} friction events where users expressed dissatisfaction. "
            "Most friction stemmed from the agent misunderstanding user intent and "
            "producing code that didn't match requirements. The highest-impact issue "
            "was repeated scope violations despite clear user instructions."
        ),
        top_mitigation=Mitigation(
            action_type="update_claude_md",
            target="Task Execution",
            content=(
                "Before starting implementation, restate the user's requirement "
                "in your own words and wait for confirmation."
            ),
        ),
        type_summary=type_summary,
        session_ids=list(step_id_pool.keys()),
        sessions_skipped=skipped,
        batch_count=1,
        backend_id=BackendType.MOCK,
        model="mock/test-model",
        cost_usd=0.042,
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
            friction_type="misunderstood-intent",
            span_ref=StepRef(
                session_id=sid_1,
                start_step_id=steps_1[0],
                end_step_id=steps_1[-1] if len(steps_1) > 1 else None,
            ),
            severity=4,
            user_intention="Refactor the auth module to use JWT tokens instead of session cookies",
            friction_detail=(
                "Agent rewrote the entire auth module from scratch instead of "
                "migrating the existing session-based code to JWT."
            ),
            claude_helpfulness=3,
            mitigations=[
                Mitigation(
                    action_type="update_claude_md",
                    target="Refactoring",
                    content=(
                        "When asked to refactor, modify existing code incrementally. "
                        "Never rewrite entire modules unless explicitly asked."
                    ),
                ),
            ],
            estimated_cost=FrictionCost(
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
            friction_detail=(
                "Agent added overly complex validation with custom error classes "
                "when user wanted simple Pydantic field validators."
            ),
            claude_helpfulness=4,
            mitigations=[
                Mitigation(
                    action_type="update_claude_md",
                    target="Coding Conventions",
                    content=(
                        "Use Pydantic field validators for API input "
                        "validation. No custom error classes."
                    ),
                ),
            ],
            estimated_cost=FrictionCost(
                affected_steps=2, affected_tokens=6500, affected_time_seconds=45
            ),
        ),
        FrictionEvent(
            friction_type="scope-violation",
            span_ref=StepRef(
                session_id=sid_3,
                start_step_id=steps_3[0],
                end_step_id=steps_3[-1] if len(steps_3) > 1 else None,
            ),
            severity=5,
            user_intention="Fix the login button CSS alignment",
            friction_detail=(
                "Agent fixed the CSS but also refactored the entire component "
                "to use a new design system, breaking existing tests."
            ),
            claude_helpfulness=2,
            mitigations=[
                Mitigation(
                    action_type="update_claude_md",
                    target="Task Execution",
                    content=(
                        "Only change what was explicitly requested. Never refactor adjacent code."
                    ),
                ),
                Mitigation(
                    action_type="write_test",
                    target="tests/test_login.py",
                    content="Add visual regression test for login button alignment.",
                ),
            ],
            estimated_cost=FrictionCost(
                affected_steps=4, affected_tokens=18000, affected_time_seconds=120
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
            friction_detail="",
            claude_helpfulness=4,
            mitigations=[],
            estimated_cost=FrictionCost(
                affected_steps=1, affected_tokens=2000, affected_time_seconds=15
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
            friction_detail=(
                "Agent fixed the wrong assertion three times before user "
                "pointed out the actual issue was in the fixture setup."
            ),
            claude_helpfulness=3,
            mitigations=[
                Mitigation(
                    action_type="update_claude_md",
                    target="Debugging",
                    content=(
                        "When a test fails, read the full test file including fixtures "
                        "before attempting a fix."
                    ),
                ),
            ],
            estimated_cost=FrictionCost(
                affected_steps=3, affected_tokens=9500, affected_time_seconds=60
            ),
        ),
    ]


def _build_mock_type_summary(events: list[FrictionEvent]) -> list[TypeSummary]:
    """Build type summary dynamically from mock events."""
    type_groups: dict[str, list[FrictionEvent]] = defaultdict(list)
    for event in events:
        type_groups[event.friction_type].append(event)

    summaries = []
    for friction_type, group in type_groups.items():
        total_steps = sum(e.estimated_cost.affected_steps for e in group)
        total_time = sum(e.estimated_cost.affected_time_seconds or 0 for e in group)
        total_tokens = sum(e.estimated_cost.affected_tokens or 0 for e in group)
        affected = len({e.span_ref.session_id for e in group})
        avg_sev = sum(e.severity for e in group) / len(group)

        summaries.append(
            TypeSummary(
                friction_type=friction_type,
                count=len(group),
                affected_sessions=affected,
                total_estimated_cost=FrictionCost(
                    affected_steps=total_steps,
                    affected_time_seconds=total_time if total_time > 0 else None,
                    affected_tokens=total_tokens if total_tokens > 0 else None,
                ),
                avg_severity=round(avg_sev, 1),
            )
        )

    summaries.sort(key=lambda s: s.avg_severity, reverse=True)
    return summaries

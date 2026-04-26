"""Tests for score-and-rank session sampling."""

from datetime import datetime, timedelta, timezone

from vibelens.context import sample_contexts
from vibelens.models.context import SessionContext, SessionContextBatch
from vibelens.models.trajectories.agent import Agent
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.trajectory import Trajectory

_TEST_AGENT = Agent(name="test-agent")


def _make_context(
    session_id: str,
    project_path: str,
    timestamp: datetime,
    step_count: int = 50,
    text_chars: int = 500,
) -> SessionContext:
    """Build a SessionContext with a trajectory for scoring."""
    steps = [
        Step(step_id=f"{session_id}-step-{i}", source="agent", message=f"step {i}")
        for i in range(step_count)
    ]
    traj = Trajectory(
        session_id=session_id,
        project_path=project_path,
        created_at=timestamp,
        agent=_TEST_AGENT,
        steps=steps,
    )
    return SessionContext(
        session_id=session_id,
        project_path=project_path,
        created_at=timestamp,
        context_text="x" * text_chars,
        trajectory_group=[traj],
    )


def test_all_fit_within_budget():
    """When everything fits, all sessions are returned."""
    now = datetime.now(timezone.utc)
    contexts = [
        _make_context(f"s{i}", "/proj-a", now - timedelta(days=i), text_chars=100) for i in range(5)
    ]
    batch = SessionContextBatch(contexts=contexts, session_ids=[c.session_id for c in contexts])

    result = sample_contexts(batch, token_budget=100_000)

    assert len(result.contexts) == 5
    print(f"All {len(result.contexts)} sessions fit within budget")


def test_sampling_reduces_when_over_budget():
    """Sampling drops sessions when combined text exceeds budget."""
    now = datetime.now(timezone.utc)
    # Each context ~2000 chars = 500 tokens. 100 sessions = ~50k tokens.
    contexts = [
        _make_context(f"s{i}", f"/proj-{i % 5}", now - timedelta(days=i), text_chars=2000)
        for i in range(100)
    ]
    batch = SessionContextBatch(contexts=contexts, session_ids=[c.session_id for c in contexts])

    result = sample_contexts(batch, token_budget=5_000)

    assert len(result.contexts) < 100
    assert len(result.contexts) > 0
    print(f"Sampled {len(result.contexts)}/100 sessions for 5k token budget")


def test_recency_preferred():
    """More recent sessions should be preferred over older ones."""
    now = datetime.now(timezone.utc)
    old = _make_context("old", "/proj", now - timedelta(days=90), text_chars=2000)
    new = _make_context("new", "/proj", now - timedelta(days=1), text_chars=2000)
    # Only room for 1 session
    batch = SessionContextBatch(contexts=[old, new], session_ids=["old", "new"])

    result = sample_contexts(batch, token_budget=600)

    assert len(result.contexts) == 1
    assert result.contexts[0].session_id == "new"
    print(f"Selected: {result.contexts[0].session_id} (recent preferred)")


def test_project_diversity():
    """Sessions from underrepresented projects get a diversity boost."""
    now = datetime.now(timezone.utc)
    # 9 sessions from proj-A, 1 from proj-B — all same age and step count
    contexts = [
        _make_context(f"a{i}", "/proj-a", now - timedelta(hours=i), text_chars=500)
        for i in range(9)
    ]
    contexts.append(_make_context("b0", "/proj-b", now - timedelta(hours=5), text_chars=500))
    batch = SessionContextBatch(contexts=contexts, session_ids=[c.session_id for c in contexts])

    # Budget for ~5 sessions
    result = sample_contexts(batch, token_budget=800)

    selected_projects = {c.project_path for c in result.contexts}
    assert "/proj-b" in selected_projects, "Underrepresented project should be included"
    print(f"Selected {len(result.contexts)} sessions from projects: {selected_projects}")


def test_reindexing_after_sampling():
    """Sampled sessions get re-indexed sequentially."""
    now = datetime.now(timezone.utc)
    contexts = [
        _make_context(f"s{i}", f"/proj-{i}", now - timedelta(days=i), text_chars=200)
        for i in range(10)
    ]
    for i, ctx in enumerate(contexts):
        ctx.session_index = i
    batch = SessionContextBatch(contexts=contexts, session_ids=[c.session_id for c in contexts])

    result = sample_contexts(batch, token_budget=2_000)

    indices = [c.session_index for c in result.contexts]
    assert indices == list(range(len(result.contexts)))
    print(f"Re-indexed: {indices}")


def test_empty_batch():
    """Empty batch returns empty batch."""
    batch = SessionContextBatch(contexts=[], session_ids=[])

    result = sample_contexts(batch, token_budget=100_000)

    assert len(result.contexts) == 0


def test_min_steps_filter_drops_small_sessions():
    """Sessions below default min_steps (10) are moved to skipped_session_ids."""
    now = datetime.now(timezone.utc)
    big = _make_context("big", "/proj-a", now - timedelta(days=1), step_count=50)
    small = _make_context("small", "/proj-b", now - timedelta(days=1), step_count=3)
    batch = SessionContextBatch(contexts=[big, small], session_ids=["big", "small"])

    result = sample_contexts(batch, token_budget=100_000)

    selected_ids = [ctx.session_id for ctx in result.contexts]
    assert selected_ids == ["big"]
    assert "small" in result.skipped_session_ids
    print(f"Filtered small session: selected={selected_ids}, skipped={result.skipped_session_ids}")


def test_min_steps_threshold_inclusive():
    """A session with exactly min_steps survives; one below is filtered."""
    now = datetime.now(timezone.utc)
    at_threshold = _make_context("at10", "/proj", now - timedelta(days=1), step_count=10)
    below = _make_context("at9", "/proj", now - timedelta(days=1), step_count=9)
    batch = SessionContextBatch(contexts=[at_threshold, below], session_ids=["at10", "at9"])

    result = sample_contexts(batch, token_budget=100_000)

    assert [ctx.session_id for ctx in result.contexts] == ["at10"]
    assert result.skipped_session_ids == ["at9"]
    print(
        f"Threshold=10: survivors={[c.session_id for c in result.contexts]}, "
        f"skipped={result.skipped_session_ids}"
    )


def test_custom_min_steps_parameter():
    """A caller-supplied min_steps overrides the default."""
    now = datetime.now(timezone.utc)
    contexts = [
        _make_context(f"s{i}", "/proj", now - timedelta(days=i), step_count=7) for i in range(3)
    ]
    batch = SessionContextBatch(contexts=contexts, session_ids=[c.session_id for c in contexts])

    # With default 10 all would be filtered; with min_steps=5 all survive.
    result = sample_contexts(batch, token_budget=100_000, min_steps=5)

    assert len(result.contexts) == 3
    assert not any(sid in result.skipped_session_ids for sid in ["s0", "s1", "s2"])
    print(f"Custom min_steps=5 kept {len(result.contexts)} sessions with 7 steps each")


def test_all_small_sessions_returns_empty_batch():
    """When every session is below min_steps, contexts is empty but the call does not raise."""
    now = datetime.now(timezone.utc)
    contexts = [
        _make_context(f"s{i}", "/proj", now - timedelta(days=i), step_count=2) for i in range(4)
    ]
    batch = SessionContextBatch(contexts=contexts, session_ids=[c.session_id for c in contexts])

    result = sample_contexts(batch, token_budget=100_000)

    assert result.contexts == []
    assert result.session_ids == []
    assert set(result.skipped_session_ids) == {"s0", "s1", "s2", "s3"}
    print(f"All-small input returned empty contexts; skipped={result.skipped_session_ids}")

"""Tests for per-step cost enrichment during ingest.

Ensures ``_compute_final_metrics`` populates ``step.metrics.cost_usd``
when a step has token metrics but no pre-computed cost, using the
shared pricing table.
"""

from datetime import datetime, timezone

from vibelens.ingest.parsers.base import _compute_final_metrics
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Metrics, Step


def _agent_step(
    step_id: str, prompt: int, completion: int, cached: int = 0, cache_write: int = 0
) -> Step:
    """Build an agent step with token metrics and no pre-computed cost."""
    return Step(
        step_id=step_id,
        timestamp=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc),
        source=StepSource.AGENT,
        model_name="claude-opus-4-7",
        message="ok",
        metrics=Metrics(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=cached,
            cache_creation_tokens=cache_write,
            cost_usd=None,  # explicit: parsers leave this empty for Claude/Hermes/Codex
        ),
    )


def test_enriches_step_cost_for_claude_style_step():
    """An agent step with token metrics gets cost_usd filled in-place."""
    step = _agent_step("s1", prompt=1000, completion=500)
    _compute_final_metrics([step], session_model="claude-opus-4-7")

    print(f"step.metrics.cost_usd after enrichment: {step.metrics.cost_usd}")
    assert step.metrics.cost_usd is not None
    assert step.metrics.cost_usd > 0


def test_final_metrics_total_cost_equals_sum_of_step_costs():
    """``total_cost_usd`` is the sum of the now-populated per-step costs."""
    steps = [
        _agent_step("s1", prompt=2000, completion=400),
        _agent_step("s2", prompt=3000, completion=600),
        _agent_step("s3", prompt=1500, completion=200, cached=500),
    ]
    fm = _compute_final_metrics(steps, session_model="claude-opus-4-7")

    step_sum = sum(s.metrics.cost_usd for s in steps if s.metrics.cost_usd)
    print(f"fm.total_cost_usd={fm.total_cost_usd} step_sum={step_sum}")
    assert fm.total_cost_usd is not None
    assert abs(fm.total_cost_usd - step_sum) < 1e-9


def test_no_model_leaves_cost_as_none():
    """If the step has neither step.model_name nor session_model, no cost."""
    step = Step(
        step_id="s1",
        timestamp=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc),
        source=StepSource.AGENT,
        message="ok",
        metrics=Metrics(prompt_tokens=1000, completion_tokens=500, cost_usd=None),
    )
    fm = _compute_final_metrics([step], session_model=None)

    print(f"cost when no model: {step.metrics.cost_usd}, final: {fm.total_cost_usd}")
    assert step.metrics.cost_usd is None
    assert fm.total_cost_usd is None


def test_unknown_model_leaves_cost_as_none():
    """A model missing from the pricing table doesn't crash; leaves None."""
    step = Step(
        step_id="s1",
        timestamp=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc),
        source=StepSource.AGENT,
        model_name="some-unreleased-model-9000",
        message="ok",
        metrics=Metrics(prompt_tokens=1000, completion_tokens=500, cost_usd=None),
    )
    fm = _compute_final_metrics([step], session_model=None)

    print(f"cost for unknown model: {step.metrics.cost_usd}")
    assert step.metrics.cost_usd is None
    assert fm.total_cost_usd is None


def test_preserves_precomputed_cost():
    """When the parser wrote cost_usd (e.g. openclaw), we don't overwrite it."""
    step = Step(
        step_id="s1",
        timestamp=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc),
        source=StepSource.AGENT,
        model_name="claude-opus-4-7",
        message="ok",
        metrics=Metrics(
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=42.0,  # parser pre-populated
        ),
    )
    fm = _compute_final_metrics([step], session_model="claude-opus-4-7")

    print(f"preserved cost: {step.metrics.cost_usd}")
    assert step.metrics.cost_usd == 42.0
    assert fm.total_cost_usd == 42.0


def test_user_and_system_steps_never_get_cost():
    """Steps without metrics stay without cost; no accidental enrichment."""
    user = Step(
        step_id="u1",
        timestamp=datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc),
        source=StepSource.USER,
        message="hi",
    )
    agent = _agent_step("s1", prompt=500, completion=100)
    fm = _compute_final_metrics([user, agent], session_model="claude-opus-4-7")

    assert user.metrics is None, "user step should have no metrics block"
    assert agent.metrics.cost_usd is not None
    assert fm.total_cost_usd is not None


def _agent_step_at(step_id: str, ts: datetime, prompt: int, completion: int) -> Step:
    return Step(
        step_id=step_id,
        timestamp=ts,
        source=StepSource.AGENT,
        model_name="claude-opus-4-7",
        message="ok",
        metrics=Metrics(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=0,
            cache_creation_tokens=0,
            cost_usd=None,
        ),
    )


def test_daily_breakdown_single_day():
    """All steps on the same local day → one breakdown bucket."""
    base = datetime(2026, 4, 22, 10, 0, tzinfo=timezone.utc)
    steps = [
        _agent_step_at("s1", base, prompt=1000, completion=200),
        _agent_step_at("s2", base, prompt=500, completion=100),
    ]
    fm = _compute_final_metrics(steps, session_model="claude-opus-4-7")

    print(f"daily_breakdown: {fm.daily_breakdown}")
    assert fm.daily_breakdown is not None
    assert len(fm.daily_breakdown) == 1
    bucket = next(iter(fm.daily_breakdown.values()))
    assert bucket.messages == 2
    assert bucket.tokens == 1800
    assert abs(bucket.cost_usd - fm.total_cost_usd) < 1e-9


def test_daily_breakdown_cross_day_splits_by_step_timestamp():
    """Steps on two local days → two buckets whose sums match session totals."""
    # Pick two timestamps 24h apart at noon UTC — guaranteed to fall on
    # different local days in any timezone.
    day_a = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)
    day_b = datetime(2026, 4, 23, 12, 0, tzinfo=timezone.utc)
    steps = [
        _agent_step_at("s1", day_a, prompt=1000, completion=200),
        _agent_step_at("s2", day_b, prompt=2000, completion=400),
    ]
    fm = _compute_final_metrics(steps, session_model="claude-opus-4-7")

    breakdown = fm.daily_breakdown
    print(f"cross-day breakdown keys: {sorted(breakdown)}")
    assert breakdown is not None
    assert len(breakdown) == 2

    total_messages = sum(b.messages for b in breakdown.values())
    total_tokens = sum(b.tokens for b in breakdown.values())
    total_cost = sum(b.cost_usd for b in breakdown.values())
    assert total_messages == 2
    assert total_tokens == 3600
    assert abs(total_cost - fm.total_cost_usd) < 1e-9


def test_daily_breakdown_none_when_no_step_timestamps():
    """No usable timestamps → ``daily_breakdown`` is omitted (None)."""
    step = Step(
        step_id="s1",
        timestamp=None,
        source=StepSource.AGENT,
        model_name="claude-opus-4-7",
        message="ok",
        metrics=Metrics(
            prompt_tokens=1000, completion_tokens=200, cached_tokens=0, cache_creation_tokens=0,
        ),
    )
    fm = _compute_final_metrics([step], session_model="claude-opus-4-7")
    print(f"daily_breakdown when no ts: {fm.daily_breakdown}")
    assert fm.daily_breakdown is None


def test_daily_breakdown_key_is_local_day_dst_aware():
    """The day key is the timestamp's local-day, resolved per-instant
    so winter (EST) and summer (EDT) timestamps land on the correct
    local date regardless of when the ingest process started.
    """
    # Use two UTC instants that each resolve to a local evening in their
    # own season. If the code used a fixed-offset tz (cached at process
    # start) it would mis-attribute one of them by one calendar day.
    winter = datetime(2026, 1, 5, 3, 30, tzinfo=timezone.utc)  # 22:30 EST Jan 4
    summer = datetime(2026, 7, 5, 2, 30, tzinfo=timezone.utc)  # 22:30 EDT Jul 4

    fm_w = _compute_final_metrics(
        [_agent_step_at("sw", winter, prompt=100, completion=50)],
        session_model="claude-opus-4-7",
    )
    fm_s = _compute_final_metrics(
        [_agent_step_at("ss", summer, prompt=100, completion=50)],
        session_model="claude-opus-4-7",
    )

    expected_w = winter.astimezone().strftime("%Y-%m-%d")
    expected_s = summer.astimezone().strftime("%Y-%m-%d")
    actual_w = next(iter(fm_w.daily_breakdown))
    actual_s = next(iter(fm_s.daily_breakdown))
    print(f"winter: expected {expected_w} got {actual_w}")
    print(f"summer: expected {expected_s} got {actual_s}")

    assert actual_w == expected_w
    assert actual_s == expected_s

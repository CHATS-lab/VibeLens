"""Regression tests locking the ``messages == len(steps)`` contract at ingest.

These tests guard the boundary between ingest and dashboard: ingest writes
``final_metrics.total_steps`` and ``final_metrics.daily_breakdown.messages``,
and the dashboard's fast path (``compute_dashboard_stats_from_metadata``)
reads these. If ingest's writer ever filters SYSTEM steps again — the
historical bug class that produced fast=156k vs slow=57k drift — these
tests will fail.
"""

from datetime import datetime, timezone

from vibelens.ingest.parsers.helpers import compute_final_metrics
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Step


def test_total_steps_equals_len_steps_regardless_of_source():
    """``compute_final_metrics`` writes ``total_steps == len(steps)`` for any
    mix of USER, AGENT, and SYSTEM steps.
    """
    ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    steps = [
        Step(step_id="sys-1", source=StepSource.SYSTEM, message="<reminder>", timestamp=ts),
        Step(step_id="u-1", source=StepSource.USER, message="hi", timestamp=ts),
        Step(step_id="a-1", source=StepSource.AGENT, message="hello", timestamp=ts),
        Step(step_id="sys-2", source=StepSource.SYSTEM, message="<reminder>", timestamp=ts),
    ]
    fm = compute_final_metrics(steps, session_model="claude-opus-4-7")
    assert fm.total_steps == 4


def test_daily_breakdown_messages_sums_to_total_steps():
    """``sum(daily_breakdown.messages) == total_steps``. The dashboard fast
    path re-pins ``messages`` to this sum, so a divergence here would show
    up as a discrepancy between top-line and daily bars on the UI.
    """
    ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    steps = [
        Step(step_id="sys-1", source=StepSource.SYSTEM, message="<reminder>", timestamp=ts),
        Step(step_id="u-1", source=StepSource.USER, message="hi", timestamp=ts),
        Step(step_id="a-1", source=StepSource.AGENT, message="hello", timestamp=ts),
        Step(step_id="sys-2", source=StepSource.SYSTEM, message="<reminder>", timestamp=ts),
    ]
    fm = compute_final_metrics(steps, session_model="claude-opus-4-7")
    daily_sum = sum(b.messages for b in fm.daily_breakdown.values())
    assert daily_sum == fm.total_steps == 4


def test_steps_without_timestamp_count_via_fallback_day():
    """A SYSTEM step injected by the parser without a per-step timestamp
    (e.g. ``<command-name>`` markers reclassified after the fact) must
    still count toward ``daily_breakdown.messages`` via the fallback day,
    so the invariant ``sum(daily.messages) == total_steps`` holds.
    """
    ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    steps = [
        Step(step_id="u-1", source=StepSource.USER, message="hi", timestamp=ts),
        Step(step_id="a-1", source=StepSource.AGENT, message="hello", timestamp=ts),
        Step(step_id="sys-1", source=StepSource.SYSTEM, message="<reminder>"),
    ]
    fm = compute_final_metrics(steps, session_model=None)
    assert fm.total_steps == 3
    daily_sum = sum(b.messages for b in fm.daily_breakdown.values())
    assert daily_sum == 3


def test_no_timestamps_anywhere_yields_no_breakdown():
    """If no step has any timestamp, the breakdown stays None and we accept
    that ``sum(daily.messages)`` is undefined. ``total_steps`` still equals
    ``len(steps)`` so the dashboard fallback (uses ``total_steps`` directly)
    still gets the right answer.
    """
    steps = [
        Step(step_id="u-1", source=StepSource.USER, message="hi"),
        Step(step_id="a-1", source=StepSource.AGENT, message="hello"),
    ]
    fm = compute_final_metrics(steps, session_model=None)
    assert fm.total_steps == 2
    assert fm.daily_breakdown is None


def test_cross_day_steps_split_by_local_day():
    """Steps that genuinely cross a local day boundary should split the
    ``daily_breakdown`` into two days, with the per-day messages summing
    back to ``len(steps)``.
    """
    day1 = datetime(2026, 4, 10, 23, 30, tzinfo=timezone.utc)
    day2 = datetime(2026, 4, 11, 0, 30, tzinfo=timezone.utc)
    steps = [
        Step(step_id="u-1", source=StepSource.USER, message="late", timestamp=day1),
        Step(step_id="a-1", source=StepSource.AGENT, message="ok", timestamp=day1),
        Step(step_id="u-2", source=StepSource.USER, message="early", timestamp=day2),
        Step(step_id="a-2", source=StepSource.AGENT, message="ok", timestamp=day2),
    ]
    fm = compute_final_metrics(steps, session_model=None)
    assert fm.total_steps == 4
    daily_sum = sum(b.messages for b in fm.daily_breakdown.values())
    assert daily_sum == 4

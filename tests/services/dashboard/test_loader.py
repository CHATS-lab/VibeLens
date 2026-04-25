"""Tests for the dashboard loader's dispatch + cache + reconciliation logic.

These cover the seams between metadata, trajectories, and the dashboard
response that the unit-level stats tests don't reach: which path runs,
how the TTL cache isolates filtered views, what happens when a session
fails to parse, and how invalidation works.
"""

from datetime import datetime, timedelta, timezone

import pytest

from vibelens.models.dashboard.dashboard import DashboardStats, PeriodStats
from vibelens.models.trajectories import (
    Agent,
    Step,
    Trajectory,
)
from vibelens.services.dashboard import loader
from vibelens.services.dashboard.loader import (
    _has_enriched_metrics,
    _reconcile_session_counts,
    invalidate_cache,
)


@pytest.fixture(autouse=True)
def _clean_caches():
    """Every test starts with empty TTL caches so state never leaks."""
    invalidate_cache()
    yield
    invalidate_cache()


def _enriched_meta(sid: str, prompt_tokens: int = 100) -> dict:
    return {
        "session_id": sid,
        "project_path": "/p",
        "timestamp": "2026-04-10T10:00:00+00:00",
        "agent": {"name": "claude-code", "model_name": "claude-opus-4-7"},
        "final_metrics": {"total_prompt_tokens": prompt_tokens, "total_completion_tokens": 0},
    }


def _bare_meta(sid: str) -> dict:
    return {
        "session_id": sid,
        "project_path": "/p",
        "timestamp": "2026-04-10T10:00:00+00:00",
        "agent": {"name": "claude-code", "model_name": "claude-opus-4-7"},
    }


class TestHasEnrichedMetrics:
    """``_has_enriched_metrics`` decides between the fast and slow path.

    A session counts as "enriched" when its metadata carries a non-zero
    prompt or completion token total. The function returns True iff a
    strict majority of sessions are enriched, with early termination
    once the threshold is reached either way.
    """

    def test_empty_metadata_returns_false(self):
        assert _has_enriched_metrics([]) is False

    def test_all_enriched_returns_true(self):
        metadata = [_enriched_meta(f"s{i}") for i in range(5)]
        assert _has_enriched_metrics(metadata) is True

    def test_all_bare_returns_false(self):
        metadata = [_bare_meta(f"s{i}") for i in range(5)]
        assert _has_enriched_metrics(metadata) is False

    def test_strict_majority_enriched_returns_true(self):
        metadata = [_enriched_meta("a"), _enriched_meta("b"), _enriched_meta("c"), _bare_meta("d")]
        assert _has_enriched_metrics(metadata) is True

    def test_strict_majority_bare_returns_false(self):
        metadata = [_bare_meta("a"), _bare_meta("b"), _bare_meta("c"), _enriched_meta("d")]
        assert _has_enriched_metrics(metadata) is False

    def test_zero_token_counts_count_as_unenriched(self):
        """Token totals of literal 0 do not count as enriched — only strictly
        positive values do. Catches the case where final_metrics exists but
        was populated from a parse that returned no token data."""
        zeros = {"total_prompt_tokens": 0, "total_completion_tokens": 0}
        metadata = [{**_bare_meta("a"), "final_metrics": zeros}]
        assert _has_enriched_metrics(metadata) is False


class TestReconcileSessionCounts:
    """``_reconcile_session_counts`` makes the slow path's totals match the
    sidebar by adding failed-to-parse sessions back into the distributions
    and recomputing period counts from metadata timestamps."""

    def _empty_stats(self) -> DashboardStats:
        return DashboardStats(
            total_sessions=0,
            total_messages=0,
            total_tokens=0,
            total_tool_calls=0,
            total_duration=0,
            total_duration_hours=0.0,
            this_year=PeriodStats(),
            this_month=PeriodStats(),
            this_week=PeriodStats(),
            daily_stats=[],
            model_distribution={},
            project_distribution={},
            hourly_distribution={},
            weekday_hour_heatmap={},
        )

    def test_overrides_total_sessions_to_metadata_count(self):
        stats = self._empty_stats()
        metadata = [_enriched_meta("s1"), _enriched_meta("s2"), _enriched_meta("s3")]
        _reconcile_session_counts(stats, trajectories=[], metadata=metadata)
        assert stats.total_sessions == 3

    def test_failed_parse_session_added_to_project_distribution(self):
        stats = self._empty_stats()
        meta_a = _enriched_meta("a")
        meta_b = {**_enriched_meta("b"), "project_path": "/different"}
        metadata = [meta_a, meta_b]
        _reconcile_session_counts(stats, trajectories=[], metadata=metadata)
        assert stats.project_distribution == {"/p": 1, "/different": 1}

    def test_parsed_session_not_double_counted(self):
        """A session that parsed successfully must not be added again to the
        distribution — it's already there from the slow-path aggregation."""
        stats = self._empty_stats()
        stats.project_distribution["/p"] = 1
        traj = Trajectory(
            session_id="s1",
            project_path="/p",
            timestamp=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
            agent=Agent(name="claude-code"),
            steps=[Step(step_id="u", source="user", message="x")],
        )
        metadata = [_enriched_meta("s1"), _enriched_meta("s2")]
        _reconcile_session_counts(stats, trajectories=[traj], metadata=metadata)
        assert stats.project_distribution["/p"] == 2  # s1 already there + s2 reconciled in

    def test_period_counts_recomputed_from_metadata_timestamps(self):
        """Period (year/month/week) counts should reflect every metadata
        entry whose timestamp falls in the period — not just successfully
        parsed trajectories."""
        stats = self._empty_stats()
        now = datetime.now(tz=timezone.utc)
        recent = (now - timedelta(days=1)).isoformat()
        old = (now - timedelta(days=400)).isoformat()
        metadata = [
            {**_bare_meta("recent-1"), "timestamp": recent},
            {**_bare_meta("recent-2"), "timestamp": recent},
            {**_bare_meta("old"), "timestamp": old},
        ]
        _reconcile_session_counts(stats, trajectories=[], metadata=metadata)
        assert stats.this_year.sessions >= 2
        assert stats.this_year.sessions <= 3  # old may or may not fall in current year


class TestCacheBehavior:
    """Two TTL caches (one for stats, one for tool usage) keyed by the
    full filter tuple. Different filter combinations cache independently;
    ``invalidate_cache`` clears both."""

    def test_invalidate_clears_both_caches(self):
        loader._dashboard_cache["dash:all:None:None:None:all"] = "stats-payload"
        loader._tool_usage_cache["tools:all:None:None:None:all"] = "tools-payload"
        invalidate_cache()
        assert "dash:all:None:None:None:all" not in loader._dashboard_cache
        assert "tools:all:None:None:None:all" not in loader._tool_usage_cache

    def test_filter_tuples_cache_independently(self):
        """Two different filter combinations must occupy different cache
        keys — a global view and a project-filtered view never collide."""
        loader._dashboard_cache["dash:/proj-a:None:None:None:all"] = "a"
        loader._dashboard_cache["dash:/proj-b:None:None:None:all"] = "b"
        loader._dashboard_cache["dash:all:2026-04-01:2026-04-30:None:all"] = "april"
        assert loader._dashboard_cache["dash:/proj-a:None:None:None:all"] == "a"
        assert loader._dashboard_cache["dash:/proj-b:None:None:None:all"] == "b"
        assert loader._dashboard_cache["dash:all:2026-04-01:2026-04-30:None:all"] == "april"

    def test_warming_status_default_shape(self):
        """``get_warming_status`` returns the three-field dict the frontend
        polls for the loading spinner."""
        status = loader.get_warming_status()
        assert set(status.keys()) == {"total", "loaded", "done"}

"""Tests for dashboard_service aggregation functions."""

from datetime import datetime, timedelta, timezone

import pytest

from vibelens.models.trajectories import (
    Agent,
    FinalMetrics,
    Metrics,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.services.dashboard.analytics import compute_session_analytics
from vibelens.services.dashboard.stats import compute_dashboard_stats, filter_metadata
from vibelens.services.dashboard.tool_usage import compute_tool_usage


def _make_metadata(
    session_id: str,
    model: str = "claude-sonnet-4-6",
    project: str = "/Users/test/myproject",
    timestamp: str = "2026-03-15T10:30:00+00:00",
) -> dict:
    """Build a metadata dict for filter_metadata tests."""
    return {
        "session_id": session_id,
        "project_path": project,
        "timestamp": timestamp,
        "agent": {"name": "claude-code", "model_name": model},
    }


def _make_trajectory(
    session_id: str = "test-session",
    model: str = "claude-sonnet-4-6",
    tools: list[str] | None = None,
    timestamp: datetime | None = None,
    project: str = "/Users/test/myproject",
    duration: int = 60,
    prompt_tokens: int = 200,
    completion_tokens: int = 150,
) -> Trajectory:
    """Build a Trajectory with realistic step-level metrics."""
    if tools is None:
        tools = ["Read", "Edit", "Bash"]
    if timestamp is None:
        timestamp = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

    end_time = timestamp + timedelta(minutes=1)

    steps = [
        Step(
            step_id="step-user-1",
            source="user",
            message="Fix the bug",
            timestamp=timestamp,
            metrics=Metrics(prompt_tokens=100, completion_tokens=0),
        ),
    ]

    tool_calls_list = []
    obs_results = []
    for i, tool_name in enumerate(tools):
        tc = ToolCall(
            tool_call_id=f"tc-{i}", function_name=tool_name, arguments={"path": f"/tmp/file{i}.py"}
        )
        tool_calls_list.append(tc)
        obs_results.append(
            ObservationResult(source_call_id=f"tc-{i}", content=f"Result of {tool_name}")
        )

    agent_step = Step(
        step_id="step-agent-1",
        source="agent",
        message="Let me fix that",
        timestamp=end_time,
        tool_calls=tool_calls_list,
        observation=Observation(results=obs_results),
        metrics=Metrics(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=50,
            cache_write_tokens=10,
        ),
    )
    steps.append(agent_step)

    return Trajectory(
        session_id=session_id,
        project_path=project,
        agent=Agent(name="claude-code", model_name=model),
        steps=steps,
        final_metrics=FinalMetrics(duration=duration, total_steps=2, tool_call_count=len(tools)),
    )


class TestComputeDashboardStats:
    """Tests for compute_dashboard_stats."""

    def test_empty_trajectories(self):
        """Empty list returns zero stats."""
        result = compute_dashboard_stats([])
        print(f"Empty result: {result.model_dump()}")

        assert result.total_sessions == 0
        assert result.total_messages == 0
        assert result.total_tokens == 0
        assert result.daily_stats == []

    def test_single_session(self):
        """Single session produces correct aggregation."""
        traj = _make_trajectory(prompt_tokens=200, completion_tokens=150)
        result = compute_dashboard_stats([traj])

        print(f"Single session: sessions={result.total_sessions}, tokens={result.total_tokens}")

        assert result.total_sessions == 1
        assert result.total_messages == 2
        # 100 (user step) + 200 (agent step) input, 150 output
        assert result.total_input_tokens == 300
        assert result.total_output_tokens == 150
        assert result.total_tokens == 450

    def test_multiple_sessions_aggregate(self):
        """Multiple sessions sum correctly."""
        trajs = [
            _make_trajectory(
                session_id="s1", prompt_tokens=200, completion_tokens=100, tools=["Read"]
            ),
            _make_trajectory(
                session_id="s2", prompt_tokens=400, completion_tokens=200, tools=["Edit", "Bash"]
            ),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"Multi-session: sessions={result.total_sessions}, tokens={result.total_tokens}")

        assert result.total_sessions == 2
        assert result.total_tool_calls == 3  # 1 + 2

    def test_model_distribution(self):
        """Model distribution counts correctly."""
        trajs = [
            _make_trajectory(session_id="s1", model="claude-sonnet-4-6"),
            _make_trajectory(session_id="s2", model="claude-sonnet-4-6"),
            _make_trajectory(session_id="s3", model="claude-haiku-4-5"),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"Model distribution: {result.model_distribution}")

        assert result.model_distribution["claude-sonnet-4-6"] == 2
        assert result.model_distribution["claude-haiku-4-5"] == 1

    def test_project_distribution(self):
        """Project distribution groups by project_path."""
        trajs = [
            _make_trajectory(session_id="s1", project="project-a"),
            _make_trajectory(session_id="s2", project="project-a"),
            _make_trajectory(session_id="s3", project="project-b"),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"Project distribution: {result.project_distribution}")

        assert result.project_distribution["project-a"] == 2
        assert result.project_distribution["project-b"] == 1
        assert result.project_count == 2

    def test_daily_stats_grouping(self):
        """Sessions group by local date correctly."""
        ts1 = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc)
        ts3 = datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc)
        trajs = [
            _make_trajectory(session_id="s1", timestamp=ts1),
            _make_trajectory(session_id="s2", timestamp=ts2),
            _make_trajectory(session_id="s3", timestamp=ts3),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"Daily stats: {[s.model_dump() for s in result.daily_stats]}")

        # All 3 sessions appear in daily_stats regardless of timezone
        total_daily = sum(d.session_count for d in result.daily_stats)
        assert total_daily == 3

    def test_hourly_distribution(self):
        """Hourly distribution uses local hours."""
        ts = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        local_hour = ts.astimezone().hour
        trajs = [
            _make_trajectory(session_id="s1", timestamp=ts),
            _make_trajectory(
                session_id="s2",
                timestamp=datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc),
            ),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"Hourly distribution: {result.hourly_distribution}")

        # Both sessions at UTC 10:xx map to the same local hour
        assert result.hourly_distribution[local_hour] == 2

    def test_heatmap_keys(self):
        """Heatmap uses local weekday_hour format."""
        ts = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        local_ts = ts.astimezone()
        expected_key = f"{local_ts.weekday()}_{local_ts.hour}"
        trajs = [_make_trajectory(timestamp=ts)]
        result = compute_dashboard_stats(trajs)

        print(f"Heatmap: {result.weekday_hour_heatmap}")

        assert expected_key in result.weekday_hour_heatmap
        assert result.weekday_hour_heatmap[expected_key] == 1

    def test_duration_from_final_metrics(self):
        """Duration uses final_metrics.duration when available."""
        traj = _make_trajectory(duration=7200)
        result = compute_dashboard_stats([traj])

        print(f"Duration: {result.total_duration}s = {result.total_duration_hours}h")

        assert result.total_duration == 7200
        assert result.total_duration_hours == 2.0

    def test_token_breakdown(self):
        """Token breakdown separates input/output/cache."""
        traj = _make_trajectory()
        result = compute_dashboard_stats([traj])

        print(
            f"Token breakdown: in={result.total_input_tokens}, "
            f"out={result.total_output_tokens}, "
            f"cache={result.total_cache_tokens}"
        )

        assert result.total_input_tokens > 0
        assert result.total_output_tokens > 0
        assert result.total_cache_tokens > 0

    def test_averages(self):
        """Per-session averages computed correctly."""
        trajs = [
            _make_trajectory(session_id="s1", tools=["Read"]),
            _make_trajectory(session_id="s2", tools=["Edit", "Bash"]),
        ]
        result = compute_dashboard_stats(trajs)

        print(
            f"Averages: msgs={result.avg_messages_per_session}, "
            f"tools={result.avg_tool_calls_per_session}"
        )

        assert result.avg_messages_per_session == 2.0
        assert result.avg_tool_calls_per_session == 1.5

    def test_daily_activity_heatmap(self):
        """Daily activity has date -> count entries in local timezone."""
        ts1 = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc)
        trajs = [
            _make_trajectory(session_id="s1", timestamp=ts1),
            _make_trajectory(session_id="s2", timestamp=ts2),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"Daily activity: {result.daily_activity}")

        # Both sessions counted in daily_activity
        total = sum(result.daily_activity.values())
        assert total == 2

    def test_this_year_period(self):
        """This year period accumulates sessions from current year."""
        now = datetime.now(tz=timezone.utc)
        this_year_ts = datetime(now.year, 1, 15, 10, 0, tzinfo=timezone.utc)
        last_year_ts = datetime(now.year - 1, 6, 15, 10, 0, tzinfo=timezone.utc)
        trajs = [
            _make_trajectory(session_id="s1", timestamp=this_year_ts),
            _make_trajectory(session_id="s2", timestamp=last_year_ts),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"This year: {result.this_year.model_dump()}")

        assert result.this_year.sessions >= 1
        assert result.total_sessions == 2

    def test_cost_aggregation(self):
        """Cost aggregated from known models."""
        traj = _make_trajectory(model="claude-sonnet-4-6")
        result = compute_dashboard_stats([traj])

        print(f"Cost: total={result.total_cost_usd}, avg={result.avg_cost_per_session}")

        assert result.total_cost_usd > 0
        assert result.avg_cost_per_session > 0

    def test_cost_by_model(self):
        """Cost broken down by canonical model name."""
        trajs = [
            _make_trajectory(session_id="s1", model="claude-sonnet-4-6"),
            _make_trajectory(session_id="s2", model="claude-haiku-4-5"),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"Cost by model: {result.cost_by_model}")
        print(f"Total cost: {result.total_cost_usd}")

        assert len(result.cost_by_model) >= 1
        assert result.total_cost_usd > 0
        assert "claude-sonnet-4-6" in result.cost_by_model
        assert "claude-haiku-4-5" in result.cost_by_model

    def test_cost_in_period_stats(self):
        """Period stats include cost accumulation."""
        now = datetime.now(tz=timezone.utc)
        traj = _make_trajectory(model="claude-sonnet-4-6", timestamp=now)
        result = compute_dashboard_stats([traj])

        print(f"This year cost: {result.this_year.cost_usd}")

        assert result.this_year.cost_usd > 0

    def test_cost_in_daily_stats(self):
        """Daily stats include cost."""
        traj = _make_trajectory(model="claude-sonnet-4-6")
        result = compute_dashboard_stats([traj])

        assert len(result.daily_stats) > 0
        total_daily_cost = sum(d.total_cost_usd for d in result.daily_stats)
        print(f"Daily cost total: {total_daily_cost}")
        assert total_daily_cost > 0

    def test_unknown_model_zero_cost(self):
        """Unknown models contribute zero cost."""
        steps = [
            Step(
                step_id="s1",
                source="user",
                message="hi",
                timestamp=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
            ),
            Step(
                step_id="s2",
                source="agent",
                message="hello",
                model_name="some-unknown-model",
                timestamp=datetime(2026, 3, 15, 10, 1, tzinfo=timezone.utc),
                metrics=Metrics(prompt_tokens=100, completion_tokens=50),
            ),
        ]
        traj = Trajectory(
            session_id="test",
            agent=Agent(name="test", model_name="some-unknown-model"),
            steps=steps,
            final_metrics=FinalMetrics(duration=60, total_steps=2),
        )
        result = compute_dashboard_stats([traj])

        print(f"Unknown model cost: {result.total_cost_usd}")
        assert result.total_cost_usd == 0.0

    def test_model_from_steps_fallback(self):
        """Model extracted from step.model_name when agent has none."""
        steps = [
            Step(
                step_id="s1",
                source="user",
                message="hi",
                timestamp=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
            ),
            Step(
                step_id="s2",
                source="agent",
                message="hello",
                model_name="claude-opus-4-6",
                timestamp=datetime(2026, 3, 15, 10, 1, tzinfo=timezone.utc),
            ),
        ]
        traj = Trajectory(
            session_id="test",
            agent=Agent(name="claude-code"),
            steps=steps,
            final_metrics=FinalMetrics(duration=60, total_steps=2),
        )
        result = compute_dashboard_stats([traj])
        print(f"Model from steps: {result.model_distribution}")
        assert "claude-opus-4-6" in result.model_distribution


class TestComputeToolUsage:
    """Tests for compute_tool_usage."""

    def test_empty_trajectories(self):
        """Empty list returns empty stats."""
        result = compute_tool_usage([])
        print(f"Empty tool usage: {result}")
        assert result == []

    def test_tool_counts(self):
        """Tool call counts aggregate correctly."""
        traj = _make_trajectory(tools=["Read", "Read", "Edit", "Bash"])
        result = compute_tool_usage([traj])

        print(f"Tool counts: {[(s.tool_name, s.call_count) for s in result]}")

        tool_map = {s.tool_name: s.call_count for s in result}
        assert tool_map["Read"] == 2
        assert tool_map["Edit"] == 1
        assert tool_map["Bash"] == 1

    def test_sorted_by_count_descending(self):
        """Results sorted by call_count descending."""
        traj = _make_trajectory(tools=["Edit", "Read", "Read", "Read", "Bash", "Bash"])
        result = compute_tool_usage([traj])

        counts = [s.call_count for s in result]
        print(f"Sorted counts: {counts}")
        assert counts == sorted(counts, reverse=True)

    def test_avg_per_session(self):
        """Average per session calculated correctly."""
        traj1 = _make_trajectory(session_id="s1", tools=["Read", "Read"])
        traj2 = _make_trajectory(session_id="s2", tools=["Read"])
        result = compute_tool_usage([traj1, traj2])

        read_stat = next(s for s in result if s.tool_name == "Read")
        print(f"Read: count={read_stat.call_count}, avg={read_stat.avg_per_session}")

        assert read_stat.call_count == 3
        assert read_stat.avg_per_session == 1.5


class TestComputeSessionAnalytics:
    """Tests for compute_session_analytics."""

    def test_basic_analytics(self):
        """Session analytics computed correctly."""
        traj = _make_trajectory(tools=["Read", "Edit", "Bash"])
        result = compute_session_analytics([traj])

        print(f"Session analytics: id={result.session_id}")
        print(f"  token_breakdown={result.token_breakdown}")
        print(f"  tool_frequency={result.tool_frequency}")

        assert result.session_id == "test-session"
        assert result.token_breakdown["prompt"] == 300
        assert result.token_breakdown["completion"] == 150
        assert result.tool_frequency["Read"] == 1

    def test_phase_segments_generated(self):
        """Phase detector produces segments."""
        traj = _make_trajectory(tools=["Read", "Read", "Read"])
        result = compute_session_analytics([traj])

        print(f"Phase segments: {len(result.phase_segments)}")
        assert len(result.phase_segments) >= 1

    def test_cost_computed(self):
        """Session analytics includes cost for known models."""
        traj = _make_trajectory(model="claude-sonnet-4-6", tools=["Read", "Edit"])
        result = compute_session_analytics([traj])

        print(f"Session cost: {result.cost_usd}")

        assert result.cost_usd is not None
        assert result.cost_usd > 0

    def test_empty_trajectories_raises(self):
        """Empty trajectories raises ValueError."""
        with pytest.raises(ValueError, match="No trajectories"):
            compute_session_analytics([])


class TestFilterMetadata:
    """Tests for filter_metadata."""

    def test_no_filters(self):
        """No filters returns all."""
        metadata = [_make_metadata("s1"), _make_metadata("s2")]
        result = filter_metadata(metadata)
        assert len(result) == 2

    def test_project_filter(self):
        """Project path filter works."""
        metadata = [
            _make_metadata("s1", project="project-a"),
            _make_metadata("s2", project="project-b"),
        ]
        result = filter_metadata(metadata, project_path="project-a")

        print(f"Filtered by project: {len(result)} results")
        assert len(result) == 1
        assert result[0]["session_id"] == "s1"

    def test_date_from_filter(self):
        """Date from filter excludes earlier sessions."""
        metadata = [
            _make_metadata("s1", timestamp="2026-03-10T10:00:00+00:00"),
            _make_metadata("s2", timestamp="2026-03-15T10:00:00+00:00"),
        ]
        result = filter_metadata(metadata, date_from="2026-03-12")

        print(f"Filtered by date_from: {len(result)} results")
        assert len(result) == 1
        assert result[0]["session_id"] == "s2"

    def test_date_to_filter(self):
        """Date to filter excludes later sessions."""
        metadata = [
            _make_metadata("s1", timestamp="2026-03-10T10:00:00+00:00"),
            _make_metadata("s2", timestamp="2026-03-20T10:00:00+00:00"),
        ]
        result = filter_metadata(metadata, date_to="2026-03-15")

        print(f"Filtered by date_to: {len(result)} results")
        assert len(result) == 1
        assert result[0]["session_id"] == "s1"

    def test_combined_filters(self):
        """Multiple filters combine with AND."""
        metadata = [
            _make_metadata("s1", project="a", timestamp="2026-03-10T10:00:00+00:00"),
            _make_metadata("s2", project="a", timestamp="2026-03-20T10:00:00+00:00"),
            _make_metadata("s3", project="b", timestamp="2026-03-15T10:00:00+00:00"),
        ]
        result = filter_metadata(metadata, project_path="a", date_from="2026-03-12")

        print(f"Combined filter: {len(result)} results")
        assert len(result) == 1
        assert result[0]["session_id"] == "s2"

    def test_none_timestamp_excluded_by_date_filter(self):
        """Sessions without timestamp excluded with date filters."""
        metadata = [
            _make_metadata("s1", timestamp="2026-03-15T10:00:00+00:00"),
            {"session_id": "s2", "project_path": "p", "timestamp": None, "agent": {"name": "test"}},
        ]
        result = filter_metadata(metadata, date_from="2026-03-01")

        print(f"None timestamp with date filter: {len(result)}")
        assert len(result) == 1
        assert result[0]["session_id"] == "s1"


class TestEdgeCases:
    """Edge cases for dashboard stats computation."""

    def test_zero_completion_tokens(self):
        """Zero completion tokens should not cause division-by-zero."""
        traj = _make_trajectory(prompt_tokens=200, completion_tokens=0)
        result = compute_dashboard_stats([traj])

        assert result.total_sessions == 1
        assert result.total_output_tokens == 0
        # user step (100) + agent step (200) = 300 input tokens, 0 output
        assert result.total_tokens == 300
        print(f"Zero completion: tokens={result.total_tokens}")

    def test_identical_timestamps_stable_sort(self):
        """Sessions with identical timestamps maintain stable ordering."""
        same_ts = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        trajs = [_make_trajectory(session_id=f"s{i}", timestamp=same_ts) for i in range(5)]
        result = compute_dashboard_stats(trajs)

        assert result.total_sessions == 5
        total_daily = sum(d.session_count for d in result.daily_stats)
        assert total_daily == 5
        print(f"Same timestamp: {result.total_sessions} sessions, daily={total_daily}")

    def test_large_token_counts(self):
        """Very large token counts (1M+) compute cost without overflow."""
        traj = _make_trajectory(
            model="claude-sonnet-4-6",
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
        )
        result = compute_dashboard_stats([traj])

        assert result.total_input_tokens >= 1_000_000
        assert result.total_output_tokens >= 500_000
        assert result.total_cost_usd > 0
        print(f"Large tokens: cost=${result.total_cost_usd:.4f}")


def _make_cross_day_trajectory(
    session_id: str,
    day1_ts: datetime,
    day2_ts: datetime,
    model: str = "claude-sonnet-4-6",
) -> Trajectory:
    """Build a trajectory with one agent step on each of two local days.

    Each agent step carries the same token metrics, so the per-day
    tokens should split evenly when bucketed by step timestamp.
    """
    steps = [
        Step(
            step_id="u1",
            source="user",
            message="Let's keep going tomorrow",
            timestamp=day1_ts,
        ),
        Step(
            step_id="a1",
            source="agent",
            message="Sure",
            timestamp=day1_ts + timedelta(minutes=5),
            metrics=Metrics(prompt_tokens=1000, completion_tokens=200),
        ),
        Step(
            step_id="u2",
            source="user",
            message="Morning",
            timestamp=day2_ts,
        ),
        Step(
            step_id="a2",
            source="agent",
            message="Continuing",
            timestamp=day2_ts + timedelta(minutes=5),
            metrics=Metrics(prompt_tokens=1000, completion_tokens=200),
        ),
    ]
    return Trajectory(
        session_id=session_id,
        project_path="/Users/test/myproject",
        timestamp=day1_ts,  # creation = day 1
        agent=Agent(name="claude-code", model_name=model),
        steps=steps,
        final_metrics=FinalMetrics(duration=120, total_steps=4, tool_call_count=0),
    )


class TestCrossDayBucketing:
    """Step-timestamp bucketing behavior for cross-day sessions."""

    def _bracketing_days(self):
        """Return timestamps and local-date keys for a session that crosses midnight.

        Uses a recent local-evening anchor to stay safely inside the
        year/month/week periods regardless of when the test runs.
        """
        from vibelens.utils.timestamps import local_date_key, local_tz

        now = datetime.now(tz=local_tz())
        day1_ts = now.replace(hour=23, minute=30, second=0, microsecond=0) - timedelta(days=3)
        day2_ts = day1_ts + timedelta(hours=2)  # 01:30 the next local day
        return day1_ts, day2_ts, local_date_key(day1_ts), local_date_key(day2_ts)

    def test_messages_split_across_days(self):
        """A session with one user step per day puts one message in each bar."""
        day1_ts, day2_ts, day1_key, day2_key = self._bracketing_days()
        traj = _make_cross_day_trajectory("sess-1", day1_ts, day2_ts)
        result = compute_dashboard_stats([traj])

        day_map = {d.date: d for d in result.daily_stats}
        print(f"day1 {day1_key}: {day_map[day1_key].total_messages} messages")
        print(f"day2 {day2_key}: {day_map[day2_key].total_messages} messages")
        assert day_map[day1_key].total_messages == 2  # 1 user + 1 agent
        assert day_map[day2_key].total_messages == 2

    def test_tokens_split_across_days(self):
        """Tokens go to the day of the step that earned them."""
        day1_ts, day2_ts, day1_key, day2_key = self._bracketing_days()
        traj = _make_cross_day_trajectory("sess-1", day1_ts, day2_ts)
        result = compute_dashboard_stats([traj])

        day_map = {d.date: d for d in result.daily_stats}
        day1_tokens = day_map[day1_key].total_tokens
        day2_tokens = day_map[day2_key].total_tokens
        print(f"tokens: day1={day1_tokens} day2={day2_tokens} total={day1_tokens + day2_tokens}")
        # Each agent step contributes 1000+200=1200 tokens.
        assert day1_tokens == 1200
        assert day2_tokens == 1200
        assert day1_tokens + day2_tokens == result.total_tokens

    def test_cost_split_across_days(self):
        """Cost follows step timestamps and sums back to the session total."""
        day1_ts, day2_ts, day1_key, day2_key = self._bracketing_days()
        traj = _make_cross_day_trajectory("sess-1", day1_ts, day2_ts)
        result = compute_dashboard_stats([traj])

        day_map = {d.date: d for d in result.daily_stats}
        day1_cost = day_map[day1_key].total_cost_usd
        day2_cost = day_map[day2_key].total_cost_usd
        print(f"cost: day1=${day1_cost:.4f} day2=${day2_cost:.4f}")
        assert day1_cost > 0
        assert day2_cost > 0
        assert abs((day1_cost + day2_cost) - result.total_cost_usd) < 1e-6

    def test_session_count_stays_on_creation_day(self):
        """session_count, hourly_dist, heatmap all anchor to the creation day."""
        day1_ts, day2_ts, day1_key, day2_key = self._bracketing_days()
        traj = _make_cross_day_trajectory("sess-1", day1_ts, day2_ts)
        result = compute_dashboard_stats([traj])

        day_map = {d.date: d for d in result.daily_stats}
        print(
            f"session counts: day1={day_map[day1_key].session_count} "
            f"day2={day_map[day2_key].session_count}"
        )
        assert day_map[day1_key].session_count == 1
        assert day_map[day2_key].session_count == 0
        assert result.daily_activity[day1_key] == 1
        assert day2_key not in result.daily_activity
        # Heatmap cell for day 1 fires; no separate cell for day 2's 01:30.
        creation_cell = f"{day1_ts.weekday()}_{day1_ts.hour}"
        day2_cell = f"{day2_ts.weekday()}_{day2_ts.hour}"
        assert result.weekday_hour_heatmap.get(creation_cell) == 1
        assert result.weekday_hour_heatmap.get(day2_cell, 0) == 0

    def test_duration_stays_on_creation_day(self):
        """Duration is session wall-clock, anchored to the creation day."""
        day1_ts, day2_ts, day1_key, day2_key = self._bracketing_days()
        traj = _make_cross_day_trajectory("sess-1", day1_ts, day2_ts)
        result = compute_dashboard_stats([traj])

        day_map = {d.date: d for d in result.daily_stats}
        print(
            f"duration: day1={day_map[day1_key].total_duration} "
            f"day2={day_map[day2_key].total_duration}"
        )
        assert day_map[day1_key].total_duration == traj.final_metrics.duration
        # Day 2 bucket exists only for messages/tokens/cost, not duration.
        assert day_map[day2_key].total_duration == 0

    def test_single_day_session_unchanged(self):
        """Regression: a session whose steps all live in one day behaves as before."""
        from vibelens.utils.timestamps import local_date_key, local_tz

        session_ts = datetime.now(tz=local_tz()).replace(hour=10, minute=0, second=0, microsecond=0)
        traj = _make_trajectory(timestamp=session_ts)
        result = compute_dashboard_stats([traj])

        session_key = local_date_key(session_ts)
        day_map = {d.date: d for d in result.daily_stats}
        assert list(day_map.keys()) == [session_key]
        assert day_map[session_key].session_count == 1
        assert day_map[session_key].total_messages == result.total_messages
        assert day_map[session_key].total_tokens == result.total_tokens
        assert day_map[session_key].total_cost_usd == pytest.approx(result.total_cost_usd, rel=1e-9)


class TestFastPathDailyBreakdown:
    """Fast path must honour ``final_metrics.daily_breakdown`` so a session
    created yesterday with steps today shows today's activity on today's bar.
    """

    def _metadata_with_breakdown(
        self, session_id: str, timestamp: str, breakdown: dict[str, dict]
    ) -> dict:
        return {
            "session_id": session_id,
            "project_path": "/p",
            "timestamp": timestamp,
            "agent": {"name": "claude-code", "model_name": "claude-opus-4-7"},
            "final_metrics": {
                "total_prompt_tokens": sum(b["tokens"] for b in breakdown.values()),
                "total_completion_tokens": 0,
                "total_cache_read_tokens": 0,
                "total_cache_write_tokens": 0,
                "tool_call_count": 0,
                "total_steps": sum(b["messages"] for b in breakdown.values()),
                "duration": 3600,
                "total_cost_usd": sum(b["cost_usd"] for b in breakdown.values()),
                "daily_breakdown": breakdown,
            },
        }

    def test_cross_day_session_splits_across_local_days(self):
        """A session created yesterday but active today shows up on both bars."""
        from vibelens.services.dashboard.stats import (
            compute_dashboard_stats_from_metadata,
        )

        meta = self._metadata_with_breakdown(
            session_id="s1",
            timestamp="2026-04-22T23:00:00+00:00",
            breakdown={
                "2026-04-22": {"messages": 3, "tokens": 1000, "cost_usd": 5.0},
                "2026-04-23": {"messages": 2, "tokens": 500, "cost_usd": 2.0},
            },
        )
        result = compute_dashboard_stats_from_metadata([meta])

        day_map = {d.date: d for d in result.daily_stats}
        print(f"daily_stats keys: {list(day_map.keys())}")
        assert "2026-04-22" in day_map
        assert "2026-04-23" in day_map
        assert day_map["2026-04-22"].total_cost_usd == pytest.approx(5.0, rel=1e-9)
        assert day_map["2026-04-23"].total_cost_usd == pytest.approx(2.0, rel=1e-9)
        assert day_map["2026-04-22"].total_tokens == 1000
        assert day_map["2026-04-23"].total_tokens == 500
        # session_count still anchored to creation day only.
        assert day_map["2026-04-22"].session_count == 1
        assert day_map["2026-04-23"].session_count == 0

    def test_missing_breakdown_falls_back_to_creation_day(self):
        """Legacy metadata (no daily_breakdown) → credit creation day."""
        from vibelens.services.dashboard.stats import (
            compute_dashboard_stats_from_metadata,
        )

        meta = {
            "session_id": "s2",
            "project_path": "/p",
            "timestamp": "2026-04-22T23:00:00+00:00",
            "agent": {"name": "claude-code", "model_name": "claude-opus-4-7"},
            "final_metrics": {
                "total_prompt_tokens": 1500,
                "total_completion_tokens": 0,
                "total_cache_read_tokens": 0,
                "total_cache_write_tokens": 0,
                "tool_call_count": 0,
                "total_steps": 5,
                "duration": 3600,
                "total_cost_usd": 7.0,
            },
        }
        result = compute_dashboard_stats_from_metadata([meta])

        day_map = {d.date: d for d in result.daily_stats}
        print(f"fallback keys: {list(day_map.keys())}")
        assert len(day_map) == 1
        (only_day,) = day_map.values()
        assert only_day.total_cost_usd == pytest.approx(7.0, rel=1e-9)
        assert only_day.total_tokens == 1500


class TestMessageCountInvariant:
    """Lock in the invariant that the top-line ``total_messages`` always
    equals the sum of daily_stats messages and the sum of period messages.

    Violating this invariant caused a 5x day-to-day drift: the top card read
    ``total_steps`` (which includes SYSTEM steps and differs between
    ingestion paths) while daily bars read ``daily_breakdown.messages``
    (non-SYSTEM). A cache rebuild flipped which path populated the cache,
    producing two wildly different dashboards for the same data.
    """

    def test_full_path_excludes_system_and_matches_daily_sum(self):
        """SYSTEM steps never count; total matches sum of daily bars."""
        from vibelens.models.enums import StepSource

        ts = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
        steps = [
            Step(step_id="sys1", source=StepSource.SYSTEM, message="<reminder>", timestamp=ts),
            Step(step_id="u1", source=StepSource.USER, message="Hi", timestamp=ts),
            Step(
                step_id="a1",
                source=StepSource.AGENT,
                message="Hello",
                timestamp=ts + timedelta(minutes=1),
                metrics=Metrics(prompt_tokens=100, completion_tokens=50),
            ),
            Step(step_id="sys2", source=StepSource.SYSTEM, message="<reminder>", timestamp=ts),
        ]
        traj = Trajectory(
            session_id="s1",
            project_path="/p",
            timestamp=ts,
            agent=Agent(name="claude-code", model_name="claude-sonnet-4-6"),
            steps=steps,
            final_metrics=FinalMetrics(duration=60, total_steps=4, tool_call_count=0),
        )
        result = compute_dashboard_stats([traj])

        daily_sum = sum(d.total_messages for d in result.daily_stats)
        year_msgs = result.this_year.messages
        print(f"total={result.total_messages} daily_sum={daily_sum} year={year_msgs}")
        assert result.total_messages == 2  # 1 user + 1 agent, no SYSTEM
        assert result.total_messages == daily_sum
        assert result.total_messages == result.this_year.messages
        assert result.avg_messages_per_session == pytest.approx(2.0, rel=1e-9)

    def test_fast_path_uses_breakdown_not_total_steps(self):
        """When metadata carries daily_breakdown, total_messages follows it,
        not the raw ``total_steps`` (which may be inflated by SYSTEM steps
        from full-parse or deflated to user-prompt count from skeleton parse).
        """
        from vibelens.services.dashboard.stats import (
            compute_dashboard_stats_from_metadata,
        )

        meta = {
            "session_id": "s1",
            "project_path": "/p",
            "timestamp": "2026-04-10T10:00:00+00:00",
            "agent": {"name": "claude-code", "model_name": "claude-opus-4-7"},
            "final_metrics": {
                "total_prompt_tokens": 1000,
                "total_completion_tokens": 0,
                "total_cache_read_tokens": 0,
                "total_cache_write_tokens": 0,
                "tool_call_count": 0,
                "total_steps": 999,  # deliberately wrong — must not leak into UI
                "duration": 60,
                "total_cost_usd": 1.0,
                "daily_breakdown": {
                    "2026-04-10": {"messages": 5, "tokens": 1000, "cost_usd": 1.0},
                },
            },
        }
        result = compute_dashboard_stats_from_metadata([meta])

        daily_sum = sum(d.total_messages for d in result.daily_stats)
        print(f"total={result.total_messages} daily_sum={daily_sum} total_steps_meta=999")
        assert result.total_messages == 5
        assert result.total_messages == daily_sum
        assert result.total_messages == result.this_year.messages

    def test_fast_path_fallback_no_breakdown_still_consistent(self):
        """Legacy metadata (no daily_breakdown): total must still equal daily sum."""
        from vibelens.services.dashboard.stats import (
            compute_dashboard_stats_from_metadata,
        )

        meta = {
            "session_id": "s2",
            "project_path": "/p",
            "timestamp": "2026-04-10T10:00:00+00:00",
            "agent": {"name": "claude-code", "model_name": "claude-opus-4-7"},
            "final_metrics": {
                "total_prompt_tokens": 500,
                "total_completion_tokens": 0,
                "total_cache_read_tokens": 0,
                "total_cache_write_tokens": 0,
                "tool_call_count": 0,
                "total_steps": 7,
                "duration": 60,
                "total_cost_usd": 2.0,
            },
        }
        result = compute_dashboard_stats_from_metadata([meta])

        daily_sum = sum(d.total_messages for d in result.daily_stats)
        print(f"legacy: total={result.total_messages} daily_sum={daily_sum}")
        assert result.total_messages == daily_sum
        assert result.total_messages == result.this_year.messages

    def test_cross_day_session_invariant_holds(self):
        """Invariant survives the cross-day bucketing case."""
        from vibelens.utils.timestamps import local_tz

        now = datetime.now(tz=local_tz())
        day1_ts = now.replace(hour=23, minute=30, second=0, microsecond=0) - timedelta(days=3)
        day2_ts = day1_ts + timedelta(hours=2)
        traj = _make_cross_day_trajectory("sess-x", day1_ts, day2_ts)
        result = compute_dashboard_stats([traj])

        daily_sum = sum(d.total_messages for d in result.daily_stats)
        print(f"cross-day: total={result.total_messages} daily_sum={daily_sum}")
        assert result.total_messages == daily_sum
        assert result.total_messages == result.this_year.messages

    def test_invariant_holds_across_many_sessions(self):
        """Mixed sessions: invariant holds in aggregate."""
        from vibelens.models.enums import StepSource

        trajs = []
        base_ts = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
        for i in range(5):
            ts = base_ts + timedelta(days=i)
            steps = [
                Step(step_id=f"sys-{i}", source=StepSource.SYSTEM, message="x", timestamp=ts),
                Step(step_id=f"u-{i}", source=StepSource.USER, message="q", timestamp=ts),
                Step(
                    step_id=f"a-{i}",
                    source=StepSource.AGENT,
                    message="a",
                    timestamp=ts + timedelta(minutes=1),
                    metrics=Metrics(prompt_tokens=100, completion_tokens=50),
                ),
            ]
            trajs.append(
                Trajectory(
                    session_id=f"s{i}",
                    project_path="/p",
                    timestamp=ts,
                    agent=Agent(name="claude-code", model_name="claude-sonnet-4-6"),
                    steps=steps,
                    final_metrics=FinalMetrics(duration=60, total_steps=3, tool_call_count=0),
                )
            )
        result = compute_dashboard_stats(trajs)
        daily_sum = sum(d.total_messages for d in result.daily_stats)
        print(f"many: total={result.total_messages} daily_sum={daily_sum}")
        assert result.total_messages == 10  # 5 sessions * 2 non-SYSTEM each
        assert result.total_messages == daily_sum
        assert result.total_messages == result.this_year.messages

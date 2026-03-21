"""Tests for dashboard_service aggregation functions."""

from datetime import UTC, datetime

import pytest

from vibelens.analysis.dashboard_service import (
    compute_dashboard_stats,
    compute_session_analytics,
    compute_tool_usage,
    filter_metadata,
)
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
        timestamp = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)

    end_time = datetime(
        timestamp.year,
        timestamp.month,
        timestamp.day,
        timestamp.hour,
        timestamp.minute + 1,
        tzinfo=UTC,
    )

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
            tool_call_id=f"tc-{i}",
            function_name=tool_name,
            arguments={"path": f"/tmp/file{i}.py"},
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
            cached_tokens=50,
            cache_creation_tokens=10,
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
        ts1 = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
        ts2 = datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
        ts3 = datetime(2026, 3, 16, 9, 0, tzinfo=UTC)
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
        ts = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
        local_hour = ts.astimezone().hour
        trajs = [
            _make_trajectory(session_id="s1", timestamp=ts),
            _make_trajectory(
                session_id="s2",
                timestamp=datetime(2026, 3, 15, 10, 30, tzinfo=UTC),
            ),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"Hourly distribution: {result.hourly_distribution}")

        # Both sessions at UTC 10:xx map to the same local hour
        assert result.hourly_distribution[local_hour] == 2

    def test_heatmap_keys(self):
        """Heatmap uses local weekday_hour format."""
        ts = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
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
        ts1 = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
        ts2 = datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
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
        now = datetime.now(tz=UTC)
        this_year_ts = datetime(now.year, 1, 15, 10, 0, tzinfo=UTC)
        last_year_ts = datetime(now.year - 1, 6, 15, 10, 0, tzinfo=UTC)
        trajs = [
            _make_trajectory(session_id="s1", timestamp=this_year_ts),
            _make_trajectory(session_id="s2", timestamp=last_year_ts),
        ]
        result = compute_dashboard_stats(trajs)

        print(f"This year: {result.this_year.model_dump()}")

        assert result.this_year.sessions >= 1
        assert result.total_sessions == 2

    def test_model_from_steps_fallback(self):
        """Model extracted from step.model_name when agent has none."""
        steps = [
            Step(
                step_id="s1",
                source="user",
                message="hi",
                timestamp=datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
            ),
            Step(
                step_id="s2",
                source="agent",
                message="hello",
                model_name="claude-opus-4-6",
                timestamp=datetime(2026, 3, 15, 10, 1, tzinfo=UTC),
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

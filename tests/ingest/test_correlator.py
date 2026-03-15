"""Tests for vibelens.ingest.correlator — cross-agent session correlation."""

from datetime import UTC, datetime, timedelta

from vibelens.ingest.correlator import (
    CorrelatedGroup,
    CorrelatedSession,
    _find_overlapping,
    correlate_sessions,
)
from vibelens.models.session import DataSourceType, SessionSummary

_DEFAULT_TIMESTAMP = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)


def _make_summary(
    session_id: str,
    project_name: str = "my-project",
    timestamp: datetime | None = _DEFAULT_TIMESTAMP,
    duration: int = 600,
    source_type: DataSourceType = DataSourceType.LOCAL,
) -> SessionSummary:
    """Build a minimal SessionSummary for correlation tests."""
    return SessionSummary(
        session_id=session_id,
        project_name=project_name,
        timestamp=timestamp,
        duration=duration,
        source_type=source_type,
    )


class TestCorrelateSessionsBasic:
    """Tests for correlate_sessions grouping and filtering."""

    def test_two_overlapping_sessions(self):
        """Two sessions on the same project with overlapping time windows."""
        s1 = _make_summary("s1", timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC), duration=600)
        s2 = _make_summary("s2", timestamp=datetime(2025, 1, 15, 10, 5, tzinfo=UTC), duration=600)

        groups = correlate_sessions([s1, s2])
        print(f"  groups: {len(groups)}")
        for g in groups:
            print(f"    project={g.project_path}, overlap={g.time_overlap_seconds}s")
            for cs in g.sessions:
                print(f"      {cs.source_type}:{cs.session_id}")
        assert len(groups) == 1
        assert len(groups[0].sessions) == 2
        assert groups[0].time_overlap_seconds > 0

    def test_no_overlap(self):
        """Two sessions on the same project with non-overlapping time windows."""
        s1 = _make_summary("s1", timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC), duration=60)
        s2 = _make_summary("s2", timestamp=datetime(2025, 1, 15, 12, 0, tzinfo=UTC), duration=60)

        groups = correlate_sessions([s1, s2])
        assert groups == []

    def test_different_projects_not_grouped(self):
        """Overlapping sessions on different projects are not correlated."""
        s1 = _make_summary("s1", project_name="project-a")
        s2 = _make_summary("s2", project_name="project-b")

        groups = correlate_sessions([s1, s2])
        assert groups == []

    def test_single_session_no_group(self):
        """A project with only one session does not form a group."""
        s1 = _make_summary("s1")
        groups = correlate_sessions([s1])
        assert groups == []

    def test_empty_input(self):
        """Empty input returns no groups."""
        assert correlate_sessions([]) == []

    def test_sessions_without_timestamps_skipped(self):
        """Sessions with None timestamps are excluded from correlation."""
        s1 = SessionSummary(
            session_id="s1", project_name="my-project",
            timestamp=None, duration=600,
        )
        s2 = SessionSummary(
            session_id="s2", project_name="my-project",
            timestamp=None, duration=600,
        )
        groups = correlate_sessions([s1, s2])
        assert groups == []

    def test_sessions_without_project_name_skipped(self):
        """Sessions with empty project_name are excluded."""
        s1 = _make_summary("s1", project_name="")
        s2 = _make_summary("s2", project_name="")
        groups = correlate_sessions([s1, s2])
        assert groups == []


class TestCorrelateSessionsAdvanced:
    """Advanced correlation scenarios with multiple sources."""

    def test_three_sessions_all_overlapping(self):
        """Three sessions all overlapping form a single group."""
        base = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        s1 = _make_summary("s1", timestamp=base, duration=3600)
        s2 = _make_summary("s2", timestamp=base + timedelta(minutes=10), duration=3600)
        s3 = _make_summary("s3", timestamp=base + timedelta(minutes=20), duration=3600)

        groups = correlate_sessions([s1, s2, s3])
        assert len(groups) == 1
        assert len(groups[0].sessions) == 3

    def test_mixed_sources(self):
        """Sessions from different sources are grouped by project."""
        base = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        s1 = _make_summary("s1", timestamp=base, duration=3600, source_type=DataSourceType.LOCAL)
        s2 = _make_summary(
            "s2",
            timestamp=base + timedelta(minutes=5),
            duration=3600,
            source_type=DataSourceType.HUGGINGFACE,
        )

        groups = correlate_sessions([s1, s2])
        assert len(groups) == 1
        source_types = {cs.source_type for cs in groups[0].sessions}
        print(f"  source_types: {source_types}")
        assert "local" in source_types
        assert "huggingface" in source_types

    def test_two_projects_independent_groups(self):
        """Overlapping sessions on two different projects form two groups."""
        base = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        sa1 = _make_summary("sa1", project_name="alpha", timestamp=base, duration=3600)
        offset = base + timedelta(minutes=5)
        sa2 = _make_summary(
            "sa2", project_name="alpha", timestamp=offset, duration=3600,
        )
        sb1 = _make_summary("sb1", project_name="beta", timestamp=base, duration=3600)
        sb2 = _make_summary(
            "sb2", project_name="beta", timestamp=offset, duration=3600,
        )

        groups = correlate_sessions([sa1, sa2, sb1, sb2])
        assert len(groups) == 2
        project_paths = {g.project_path for g in groups}
        assert project_paths == {"alpha", "beta"}

    def test_overlap_seconds_calculation(self):
        """Overlap duration is calculated correctly."""
        base = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        # s1: 10:00 - 10:10 (600s)
        # s2: 10:05 - 10:15 (600s)
        # Overlap: 10:05 - 10:10 = 300s
        s1 = _make_summary("s1", timestamp=base, duration=600)
        s2 = _make_summary("s2", timestamp=base + timedelta(minutes=5), duration=600)

        groups = correlate_sessions([s1, s2])
        assert len(groups) == 1
        print(f"  overlap: {groups[0].time_overlap_seconds}s")
        assert groups[0].time_overlap_seconds == 300

    def test_zero_duration_uses_minimum_interval(self):
        """Sessions with zero duration use minimum 1-second interval."""
        base = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        s1 = _make_summary("s1", timestamp=base, duration=0)
        s2 = _make_summary("s2", timestamp=base, duration=0)

        groups = correlate_sessions([s1, s2])
        assert len(groups) == 1
        assert groups[0].time_overlap_seconds >= 1


class TestFindOverlapping:
    """Tests for _find_overlapping internal helper."""

    def test_returns_none_for_no_overlap(self):
        """Returns None when sessions do not overlap."""
        s1 = _make_summary("s1", timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC), duration=60)
        s2 = _make_summary("s2", timestamp=datetime(2025, 1, 15, 12, 0, tzinfo=UTC), duration=60)
        result = _find_overlapping([s1, s2])
        assert result is None

    def test_returns_group_for_overlap(self):
        """Returns CorrelatedGroup when sessions overlap."""
        base = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        s1 = _make_summary("s1", timestamp=base, duration=600)
        s2 = _make_summary("s2", timestamp=base + timedelta(minutes=5), duration=600)
        result = _find_overlapping([s1, s2])
        assert result is not None
        assert isinstance(result, CorrelatedGroup)
        assert result.project_path == "my-project"

    def test_no_duplicate_sessions_in_group(self):
        """Session IDs are deduplicated in the overlapping group."""
        base = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        s1 = _make_summary("s1", timestamp=base, duration=3600)
        s2 = _make_summary("s2", timestamp=base + timedelta(minutes=5), duration=3600)
        s3 = _make_summary("s3", timestamp=base + timedelta(minutes=10), duration=3600)

        result = _find_overlapping([s1, s2, s3])
        assert result is not None
        session_ids = [cs.session_id for cs in result.sessions]
        assert len(session_ids) == len(set(session_ids))

    def test_sessions_without_timestamps_excluded(self):
        """Sessions with None timestamps are skipped."""
        s1 = SessionSummary(
            session_id="s1", project_name="my-project",
            timestamp=None, duration=600,
        )
        s2 = _make_summary(
            "s2", timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            duration=600,
        )
        result = _find_overlapping([s1, s2])
        assert result is None


class TestCorrelatedModels:
    """Tests for Pydantic model serialization and fields."""

    def test_correlated_session_defaults(self):
        cs = CorrelatedSession(source_type="local", session_id="s1")
        assert cs.is_main is True

    def test_correlated_session_sub_agent(self):
        cs = CorrelatedSession(source_type="local", session_id="s1", is_main=False)
        assert cs.is_main is False

    def test_correlated_group_serialization(self):
        group = CorrelatedGroup(
            project_path="my-project",
            sessions=[CorrelatedSession(source_type="local", session_id="s1")],
            time_overlap_seconds=300,
        )
        data = group.model_dump()
        assert data["project_path"] == "my-project"
        assert len(data["sessions"]) == 1
        assert data["time_overlap_seconds"] == 300

    def test_correlated_group_json_roundtrip(self):
        group = CorrelatedGroup(
            project_path="test",
            sessions=[
                CorrelatedSession(source_type="local", session_id="s1"),
                CorrelatedSession(source_type="huggingface", session_id="s2", is_main=False),
            ],
            time_overlap_seconds=600,
        )
        json_str = group.model_dump_json()
        restored = CorrelatedGroup.model_validate_json(json_str)
        assert restored.project_path == "test"
        assert len(restored.sessions) == 2
        assert restored.sessions[1].is_main is False

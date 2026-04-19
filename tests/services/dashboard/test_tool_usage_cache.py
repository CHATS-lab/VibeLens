"""Tests for the persisted per-session tool-usage cache."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vibelens.models.dashboard.dashboard import SessionToolUsage
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Step, Trajectory
from vibelens.models.trajectories.agent import Agent
from vibelens.models.trajectories.observation import Observation
from vibelens.models.trajectories.observation_result import ObservationResult
from vibelens.models.trajectories.tool_call import ToolCall
from vibelens.services.dashboard import loader, tool_usage_cache
from vibelens.services.dashboard.tool_usage import (
    aggregate_tool_usage,
    compute_per_session_tool_usage,
    compute_tool_usage,
)


def _make_traj(session_id: str, tool_calls: list[tuple[str, bool]]) -> Trajectory:
    """Build a minimal trajectory with one step containing the given tool calls.

    Args:
        session_id: Session id.
        tool_calls: List of (function_name, is_error) tuples.
    """
    calls = [
        ToolCall(tool_call_id=f"c-{i}", function_name=fn, function_arguments="{}")
        for i, (fn, _) in enumerate(tool_calls)
    ]
    results = [
        ObservationResult(
            source_call_id=f"c-{i}",
            content=("ERROR: boom" if is_err else "ok"),
        )
        for i, (_, is_err) in enumerate(tool_calls)
    ]
    step = Step(
        step_id="s-0",
        source=StepSource.AGENT,
        message="",
        timestamp=datetime(2026, 4, 18, tzinfo=timezone.utc),
        tool_calls=calls,
        observation=Observation(results=results) if results else None,
    )
    return Trajectory(
        session_id=session_id,
        first_message="x",
        agent=Agent(name="test-agent"),
        steps=[step],
    )


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch) -> Path:
    """Redirect the tool-usage cache to a tmp path per test."""
    path = tmp_path / "tool_usage.json"
    monkeypatch.setattr(tool_usage_cache, "DEFAULT_CACHE_PATH", path)
    return path


def test_aggregator_matches_legacy_compute():
    """aggregate_tool_usage(per-session entries) == compute_tool_usage(trajectories)."""
    trajs = [
        _make_traj("a", [("Bash", False), ("Bash", True), ("Read", False)]),
        _make_traj("b", [("Bash", False), ("Edit", False)]),
    ]
    legacy = {s.tool_name: s for s in compute_tool_usage(trajs)}
    entries = {t.session_id: compute_per_session_tool_usage(t, content_mtime_ns=0) for t in trajs}
    aggregated = {s.tool_name: s for s in aggregate_tool_usage(entries)}
    assert legacy == aggregated


def test_aggregator_skips_no_trajectory_entries():
    """no_trajectory entries are excluded from the session_count denominator."""
    trajs = [_make_traj("a", [("Bash", False), ("Bash", False)])]
    entries = {t.session_id: compute_per_session_tool_usage(t, content_mtime_ns=0) for t in trajs}
    entries["b"] = SessionToolUsage(content_mtime_ns=999, no_trajectory=True)
    stats = aggregate_tool_usage(entries)
    bash = next(s for s in stats if s.tool_name == "Bash")
    # 2 calls / 1 valid session = 2.0
    assert bash.avg_per_session == 2.0


def test_load_save_roundtrip(isolated_cache):
    entries = {
        "a": SessionToolUsage(
            content_mtime_ns=12345,
            tool_counts={"Bash": 3},
            error_counts={"Bash": 1},
        ),
        "b": SessionToolUsage(content_mtime_ns=42, no_trajectory=True),
    }
    tool_usage_cache.save_cache(entries)
    loaded = tool_usage_cache.load_cache()
    assert loaded["a"].tool_counts == {"Bash": 3}
    assert loaded["a"].error_counts == {"Bash": 1}
    assert loaded["b"].no_trajectory is True


def test_load_missing_returns_empty(isolated_cache):
    assert tool_usage_cache.load_cache() == {}


def test_load_corrupt_returns_empty(isolated_cache):
    isolated_cache.write_text("{not json", encoding="utf-8")
    assert tool_usage_cache.load_cache() == {}


def test_load_version_mismatch_returns_empty(isolated_cache):
    payload = {"version": 999, "entries": {}}
    isolated_cache.write_text(json.dumps(payload), encoding="utf-8")
    assert tool_usage_cache.load_cache() == {}


def test_warm_cache_uses_persisted_entries_for_unchanged(
    isolated_cache, tmp_path, monkeypatch
):
    """Pre-populate cache for a session whose mtime matches; loader should not reload it."""
    fake_session_file = tmp_path / "fake.jsonl"
    fake_session_file.write_text("dummy")
    mtime = fake_session_file.stat().st_mtime_ns

    entries = {
        "session-cached": SessionToolUsage(
            content_mtime_ns=mtime,
            tool_counts={"Read": 5},
            error_counts={},
        )
    }
    tool_usage_cache.save_cache(entries)

    # Patch the dashboard loader's metadata source to return our session,
    # and assert _load_one_session is NOT called for it.
    monkeypatch.setattr(
        loader,
        "list_all_metadata",
        lambda session_token: [
            {"session_id": "session-cached", "filepath": str(fake_session_file)}
        ],
    )
    monkeypatch.setattr(loader, "filter_metadata", lambda md, *args, **kwargs: md)
    monkeypatch.setattr(loader, "_has_enriched_metrics", lambda md: True)
    monkeypatch.setattr(
        loader,
        "compute_dashboard_stats_from_metadata",
        lambda md: {"sessions": len(md)},
    )

    load_calls: list[str] = []

    def boom(meta, sid, _token):
        load_calls.append(sid)
        return None

    monkeypatch.setattr(loader, "_load_one_session", boom)

    loader.warm_cache()

    assert load_calls == [], "Session with matching mtime should not be reloaded"
    # Aggregated stat reflects the cached counts.
    cached_stat = loader._tool_usage_cache["tools:all:None:None:None:all"]
    read_stat = next((s for s in cached_stat if s.tool_name == "Read"), None)
    assert read_stat is not None
    assert read_stat.call_count == 5


def test_warm_cache_recomputes_on_mtime_change(
    isolated_cache, tmp_path, monkeypatch
):
    """Stale mtime triggers reload; new SessionToolUsage replaces the old."""
    fake_file = tmp_path / "session.jsonl"
    fake_file.write_text("dummy")
    current_mtime = fake_file.stat().st_mtime_ns

    entries = {
        "session-stale": SessionToolUsage(
            content_mtime_ns=current_mtime - 1,  # stale
            tool_counts={"Bash": 1},
            error_counts={},
        )
    }
    tool_usage_cache.save_cache(entries)

    monkeypatch.setattr(
        loader,
        "list_all_metadata",
        lambda session_token: [
            {"session_id": "session-stale", "filepath": str(fake_file)}
        ],
    )
    monkeypatch.setattr(loader, "filter_metadata", lambda md, *args, **kwargs: md)
    monkeypatch.setattr(loader, "_has_enriched_metrics", lambda md: True)
    monkeypatch.setattr(loader, "compute_dashboard_stats_from_metadata", lambda md: {})

    fresh_traj = _make_traj("session-stale", [("Bash", False), ("Bash", False)])
    monkeypatch.setattr(
        loader, "_load_one_session", lambda meta, sid, _token: fresh_traj
    )

    loader.warm_cache()

    reloaded = tool_usage_cache.load_cache()["session-stale"]
    assert reloaded.tool_counts == {"Bash": 2}
    assert reloaded.content_mtime_ns == current_mtime


def test_warm_cache_drops_removed_sessions(
    isolated_cache, tmp_path, monkeypatch
):
    """A cached entry whose session is no longer in metadata gets purged."""
    entries = {
        "session-gone": SessionToolUsage(
            content_mtime_ns=42, tool_counts={"Bash": 1}, error_counts={}
        )
    }
    tool_usage_cache.save_cache(entries)

    monkeypatch.setattr(loader, "list_all_metadata", lambda session_token: [])
    monkeypatch.setattr(loader, "filter_metadata", lambda md, *args, **kwargs: md)
    monkeypatch.setattr(loader, "_has_enriched_metrics", lambda md: True)
    monkeypatch.setattr(loader, "compute_dashboard_stats_from_metadata", lambda md: {})

    loader.warm_cache()

    final = tool_usage_cache.load_cache()
    assert "session-gone" not in final


def test_warm_cache_marks_no_trajectory_when_load_returns_none(
    isolated_cache, tmp_path, monkeypatch
):
    """Sessions that fail to load get cached as no_trajectory=True so future warms skip them."""
    fake_file = tmp_path / "bad.jsonl"
    fake_file.write_text("dummy")
    mtime = fake_file.stat().st_mtime_ns

    monkeypatch.setattr(
        loader,
        "list_all_metadata",
        lambda session_token: [
            {"session_id": "session-bad", "filepath": str(fake_file)}
        ],
    )
    monkeypatch.setattr(loader, "filter_metadata", lambda md, *args, **kwargs: md)
    monkeypatch.setattr(loader, "_has_enriched_metrics", lambda md: True)
    monkeypatch.setattr(loader, "compute_dashboard_stats_from_metadata", lambda md: {})
    monkeypatch.setattr(loader, "_load_one_session", lambda meta, sid, _token: None)

    loader.warm_cache()

    cached = tool_usage_cache.load_cache()
    assert cached["session-bad"].no_trajectory is True
    assert cached["session-bad"].content_mtime_ns == mtime

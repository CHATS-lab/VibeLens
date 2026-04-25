"""Tests for the partial-rebuild path in LocalTrajectoryStore.

The partial path lets startup re-parse only changed/new/removed files
instead of rebuilding the entire index. These tests cover the partition
logic and the dropped_paths memo that prevents retrying empty files.
"""

import json
from pathlib import Path

import pytest

from vibelens.ingest import index_cache
from vibelens.models.enums import AgentType
from vibelens.storage.trajectory.local import LocalTrajectoryStore, _partition_files


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch) -> Path:
    """Redirect index_cache.DEFAULT_CACHE_PATH to a tmp file per test."""
    cache_file = tmp_path / "session_index.json"
    monkeypatch.setattr(index_cache, "DEFAULT_CACHE_PATH", cache_file)
    return cache_file


@pytest.fixture
def claude_data_dirs(tmp_path) -> dict[AgentType, Path]:
    """Build a minimal claude data dir with two valid session files + history.jsonl."""
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects" / "-Users-Test-Project"
    projects_dir.mkdir(parents=True)

    history_file = claude_dir / "history.jsonl"
    history_entries = [
        {
            "display": "First message",
            "pastedContents": {},
            "timestamp": 1707734674932,
            "project": "/Users/Test/Project",
            "sessionId": "session-A",
        },
        {
            "display": "Second message",
            "pastedContents": {},
            "timestamp": 1707734680000,
            "project": "/Users/Test/Project",
            "sessionId": "session-B",
        },
    ]
    with history_file.open("w") as f:
        for e in history_entries:
            f.write(json.dumps(e) + "\n")

    for sid in ("session-A", "session-B"):
        session_file = projects_dir / f"{sid}.jsonl"
        with session_file.open("w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": f"u-{sid}",
                        "sessionId": sid,
                        "timestamp": 1707734674932,
                        "message": {"role": "user", "content": f"prompt for {sid}"},
                    }
                )
                + "\n"
            )

    return {AgentType.CLAUDE: claude_dir}


def _read_cache(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_warm_restart_unchanged_takes_fast_path(
    isolated_cache, claude_data_dirs, caplog
):
    """When no file mtimes change between two starts, the fast cache-hit path runs."""
    store1 = LocalTrajectoryStore(data_dirs=claude_data_dirs)
    store1.list_metadata()  # warm
    assert isolated_cache.exists()

    caplog.clear()
    store2 = LocalTrajectoryStore(data_dirs=claude_data_dirs)
    store2.list_metadata()  # should hit fast path
    messages = [r.getMessage() for r in caplog.records]
    assert any("Loaded 2 sessions from index cache" in m for m in messages)
    # Fast-path log line lacks the "(N unchanged...)" suffix.
    assert not any("unchanged," in m for m in messages)


def test_one_changed_file_runs_partial_rebuild(
    isolated_cache, claude_data_dirs, caplog
):
    """Touching one session file triggers the partial path; the other survives from cache."""
    store1 = LocalTrajectoryStore(data_dirs=claude_data_dirs)
    store1.list_metadata()

    # Touch session-A's file to bump its mtime.
    session_a = (
        claude_data_dirs[AgentType.CLAUDE]
        / "projects"
        / "-Users-Test-Project"
        / "session-A.jsonl"
    )
    text = session_a.read_text()
    session_a.write_text(text + "\n")

    caplog.clear()
    store2 = LocalTrajectoryStore(data_dirs=claude_data_dirs)
    store2.list_metadata()
    messages = [r.getMessage() for r in caplog.records]
    partial_lines = [m for m in messages if "1 unchanged" in m and "1 re-parsed" in m]
    assert partial_lines, f"expected partial-rebuild log, got: {messages}"
    assert "session-A" in store2._metadata_cache
    assert "session-B" in store2._metadata_cache


def test_dropped_path_not_retried_on_warm_restart(isolated_cache, tmp_path, caplog):
    """A file that yields no parseable trajectory is recorded in dropped_paths
    and skipped on the next startup as long as its mtime is unchanged."""
    # Build a claude dir where session-bad.jsonl has only a snapshot entry
    # (no user/assistant messages → first_message empty → dropped).
    claude_dir = tmp_path / ".claude"
    projects = claude_dir / "projects" / "-Users-Test-Project"
    projects.mkdir(parents=True)
    bad_file = projects / "session-bad.jsonl"
    bad_file.write_text(
        json.dumps(
            {
                "type": "file-history-snapshot",
                "messageId": "snap-1",
                "snapshot": {"messageId": "snap-1", "trackedFileBackups": {}},
            }
        )
        + "\n"
    )

    data_dirs = {AgentType.CLAUDE: claude_dir}
    store1 = LocalTrajectoryStore(data_dirs=data_dirs)
    store1.list_metadata()

    cache = _read_cache(isolated_cache)
    assert str(bad_file) in cache["dropped_paths"], (
        f"dropped_paths should contain bad file, got {cache['dropped_paths']}"
    )

    # Second startup: file mtime unchanged → bad file not retried.
    caplog.clear()
    store2 = LocalTrajectoryStore(data_dirs=data_dirs)
    store2.list_metadata()
    # No "session-bad" should appear in metadata_cache.
    assert "session-bad" not in store2._metadata_cache
    # The cache should still record the dropped path.
    cache2 = _read_cache(isolated_cache)
    assert str(bad_file) in cache2["dropped_paths"]


def test_partition_files_classifies_correctly(tmp_path):
    """_partition_files separates unchanged / changed / new / removed correctly."""
    file_a = tmp_path / "a.jsonl"
    file_a.write_text("a")
    file_b = tmp_path / "b.jsonl"
    file_b.write_text("b")

    file_index = {
        "a": (file_a, object()),
        "b": (file_b, object()),
    }

    # cached stat records a's old mtime + a third file 'c' that no longer exists.
    a_st = file_a.stat()
    cached_stats = {
        str(file_a): [a_st.st_mtime_ns - 1, a_st.st_size],  # different mtime → changed
        str(tmp_path / "c.jsonl"): [999_999, 0],  # gone → removed
    }
    dropped_paths: dict[str, list[int]] = {}

    partition, fresh_dropped, current_stats = _partition_files(
        file_index, cached_stats, dropped_paths
    )

    assert "a" in partition.changed
    assert "b" in partition.new
    assert partition.unchanged == {}
    assert str(tmp_path / "c.jsonl") in partition.removed_paths
    assert fresh_dropped == {}
    # current_stats should cover every live file we actually statted.
    assert str(file_a) in current_stats
    assert str(file_b) in current_stats


def test_partition_files_size_change_marks_changed(tmp_path):
    """In-place rewrite that preserves mtime is caught by the size component."""
    f = tmp_path / "rewritten.jsonl"
    f.write_text("hello")
    st = f.stat()

    file_index = {"r": (f, object())}
    cached_stats = {str(f): [st.st_mtime_ns, st.st_size + 1]}  # size differs only

    partition, _, _ = _partition_files(file_index, cached_stats, {})

    assert "r" in partition.changed


def test_partition_files_skips_dropped_with_unchanged_mtime(tmp_path):
    """Files in dropped_paths with matching stat tuples are excluded from all sets."""
    bad = tmp_path / "bad.jsonl"
    bad.write_text("x")
    st = bad.stat()
    bad_stat = [st.st_mtime_ns, st.st_size]

    file_index = {"bad": (bad, object())}
    cached_stats: dict[str, list[int]] = {}
    dropped_paths = {str(bad): bad_stat}

    partition, fresh_dropped, _ = _partition_files(file_index, cached_stats, dropped_paths)

    assert partition.new == {}
    assert partition.unchanged == {}
    assert partition.changed == {}
    assert fresh_dropped == {str(bad): bad_stat}


def _write_claude_session(projects_dir: Path, sid: str, text: str = "prompt") -> Path:
    """Write a minimal valid Claude session file and return its path."""
    session_file = projects_dir / f"{sid}.jsonl"
    session_file.write_text(
        json.dumps(
            {
                "type": "user",
                "uuid": f"u-{sid}",
                "sessionId": sid,
                "timestamp": 1707734674932,
                "message": {"role": "user", "content": text},
            }
        )
        + "\n"
    )
    return session_file


def test_long_lived_store_detects_new_session_without_explicit_refresh(
    isolated_cache, claude_data_dirs, caplog
):
    """A session created after first list_metadata() must appear on next call
    without any explicit invalidate_index() — this is the bug the fix solves."""
    store = LocalTrajectoryStore(data_dirs=claude_data_dirs)
    initial = {m["session_id"] for m in store.list_metadata()}
    assert initial == {"session-A", "session-B"}

    # Simulate: app was started earlier; user creates a new session now.
    projects_dir = (
        claude_data_dirs[AgentType.CLAUDE] / "projects" / "-Users-Test-Project"
    )
    _write_claude_session(projects_dir, "session-C")

    # Simulate elapsed time past the staleness-check TTL.
    store._last_staleness_check = 0.0

    caplog.clear()
    after = {m["session_id"] for m in store.list_metadata()}
    assert "session-C" in after, (
        f"new session not detected by long-lived store: {after}"
    )

    # Confirm the rebuild went through the partial (not full) path:
    # 2 unchanged hydrated from cache, 1 new parsed.
    messages = [r.getMessage() for r in caplog.records]
    partial_lines = [
        m for m in messages if "2 unchanged" in m and "1 added" in m and "0 re-parsed" in m
    ]
    assert partial_lines, f"expected partial-rebuild log, got: {messages}"


def test_long_lived_store_detects_modified_session(
    isolated_cache, claude_data_dirs, caplog
):
    """Modifying an existing session file after first list_metadata() must
    trigger re-parse of just that file on the next list call."""
    store = LocalTrajectoryStore(data_dirs=claude_data_dirs)
    store.list_metadata()  # warm

    session_a = (
        claude_data_dirs[AgentType.CLAUDE]
        / "projects"
        / "-Users-Test-Project"
        / "session-A.jsonl"
    )
    # Append a second entry — changes file size + mtime.
    session_a.write_text(
        session_a.read_text()
        + json.dumps(
            {
                "type": "user",
                "uuid": "u-session-A-2",
                "sessionId": "session-A",
                "timestamp": 1707734700000,
                "message": {"role": "user", "content": "follow-up"},
            }
        )
        + "\n"
    )

    # Simulate elapsed time past the staleness-check TTL.
    store._last_staleness_check = 0.0

    caplog.clear()
    store.list_metadata()
    messages = [r.getMessage() for r in caplog.records]
    partial_lines = [
        m for m in messages if "1 unchanged" in m and "1 re-parsed" in m and "0 added" in m
    ]
    assert partial_lines, f"expected partial re-parse log, got: {messages}"


def test_unchanged_disk_does_not_rebuild(isolated_cache, claude_data_dirs, caplog):
    """Repeated list_metadata() calls with no disk changes must not trigger
    any rebuild — the in-memory cache is returned directly."""
    store = LocalTrajectoryStore(data_dirs=claude_data_dirs)
    store.list_metadata()  # first build

    caplog.clear()
    for _ in range(3):
        store.list_metadata()

    messages = [r.getMessage() for r in caplog.records]
    # Neither fast-path nor partial-path nor full-rebuild log should appear.
    assert not any("Loaded" in m and "sessions from index cache" in m for m in messages)
    assert not any("Indexed" in m and "sessions across" in m for m in messages)


def test_staleness_check_rate_limited(isolated_cache, claude_data_dirs, monkeypatch):
    """Rapid list_metadata() calls must scan disk at most once per TTL."""
    store = LocalTrajectoryStore(data_dirs=claude_data_dirs)
    store.list_metadata()  # warm

    scan_count = 0
    real_scan = store._scan_disk_mtimes

    def counting_scan():
        nonlocal scan_count
        scan_count += 1
        return real_scan()

    monkeypatch.setattr(store, "_scan_disk_mtimes", counting_scan)

    for _ in range(20):
        store.list_metadata()

    assert scan_count == 0, (
        f"within TTL, no disk scan should happen; got {scan_count}"
    )

    # After TTL elapses, the next call does scan.
    store._last_staleness_check = 0.0
    store.list_metadata()
    assert scan_count == 1, f"after TTL reset, expected 1 scan; got {scan_count}"

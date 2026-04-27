"""OpenCode parser tests."""

import json
import sqlite3
from pathlib import Path

import pytest

from vibelens.ingest.parsers.opencode import OpencodeParser
from vibelens.models.enums import AgentType, StepSource


@pytest.fixture
def parser() -> OpencodeParser:
    return OpencodeParser()


def _build_db(
    db_path: Path, sessions: list[dict], messages: list[dict], parts: list[dict]
) -> None:
    """Create a minimal opencode.db schema and populate from input dicts."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE project (
            id text PRIMARY KEY,
            worktree text NOT NULL,
            vcs text,
            name text,
            sandboxes text NOT NULL DEFAULT '[]'
        );
        CREATE TABLE session (
            id text PRIMARY KEY,
            project_id text NOT NULL,
            parent_id text,
            slug text NOT NULL,
            directory text NOT NULL,
            title text NOT NULL,
            version text NOT NULL,
            share_url text,
            summary_additions integer,
            summary_deletions integer,
            summary_files integer,
            summary_diffs text,
            revert text,
            permission text,
            time_created integer NOT NULL,
            time_updated integer NOT NULL,
            time_compacting integer,
            time_archived integer,
            workspace_id text
        );
        CREATE TABLE message (
            id text PRIMARY KEY,
            session_id text NOT NULL,
            time_created integer NOT NULL,
            time_updated integer NOT NULL,
            data text NOT NULL
        );
        CREATE TABLE part (
            id text PRIMARY KEY,
            message_id text NOT NULL,
            session_id text NOT NULL,
            time_created integer NOT NULL,
            time_updated integer NOT NULL,
            data text NOT NULL
        );
        CREATE TABLE todo (
            session_id text NOT NULL,
            content text NOT NULL,
            status text NOT NULL,
            priority text NOT NULL,
            position integer NOT NULL,
            time_created integer NOT NULL,
            time_updated integer NOT NULL,
            PRIMARY KEY (session_id, position)
        );
        """
    )
    conn.execute(
        "INSERT INTO project (id, worktree, vcs, name) VALUES (?, ?, ?, ?)",
        ("proj-1", "/fixture/proj", "git", "fixture"),
    )
    for s in sessions:
        conn.execute(
            """INSERT INTO session
            (id, project_id, parent_id, slug, directory, title, version,
             summary_additions, summary_deletions, summary_files,
             time_created, time_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                s["id"],
                s.get("project_id", "proj-1"),
                s.get("parent_id"),
                s.get("slug", "test"),
                s.get("directory", "/fixture/proj"),
                s.get("title", "test"),
                s.get("version", "1.0.0"),
                s.get("summary_additions", 0),
                s.get("summary_deletions", 0),
                s.get("summary_files", 0),
                s.get("time_created", 1_700_000_000_000),
                s.get("time_updated", 1_700_000_000_000),
            ),
        )
    for m in messages:
        conn.execute(
            "INSERT INTO message (id, session_id, time_created, time_updated, data) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                m["id"],
                m["session_id"],
                m.get("time_created", 1_700_000_000_000),
                m.get("time_updated", 1_700_000_000_000),
                json.dumps(m["data"]),
            ),
        )
    for p in parts:
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                p["id"],
                p["message_id"],
                p["session_id"],
                p.get("time_created", 1_700_000_000_000),
                p.get("time_updated", 1_700_000_000_000),
                json.dumps(p["data"]),
            ),
        )
    conn.commit()
    conn.close()


def test_basic_session(tmp_path: Path, parser: OpencodeParser) -> None:
    """Simple session: 1 user message + 1 assistant message yields 2 steps."""
    db = tmp_path / "opencode.db"
    _build_db(
        db,
        sessions=[{"id": "ses_1", "slug": "first", "title": "First"}],
        messages=[
            {
                "id": "msg_user",
                "session_id": "ses_1",
                "data": {"role": "user", "path": {"cwd": "/fixture/proj"}},
            },
            {
                "id": "msg_asst",
                "session_id": "ses_1",
                "data": {
                    "role": "assistant",
                    "modelID": "claude-sonnet-4-6",
                    "providerID": "anthropic",
                    "agent": "build",
                    "mode": "build",
                    "cost": 0.01,
                    "tokens": {
                        "input": 100,
                        "output": 50,
                        "cache": {"read": 80, "write": 0},
                    },
                    "finish": "stop",
                },
            },
        ],
        parts=[
            {
                "id": "p1", "message_id": "msg_user", "session_id": "ses_1",
                "data": {"type": "text", "text": "Hello"},
            },
            {
                "id": "p2", "message_id": "msg_asst", "session_id": "ses_1",
                "data": {"type": "text", "text": "Hi there"},
            },
        ],
    )

    trajs = parser.parse(db)
    assert len(trajs) == 1
    traj = trajs[0]
    assert traj.session_id == "ses_1"
    assert traj.agent.name == AgentType.OPENCODE.value
    assert traj.agent.model_name == "claude-sonnet-4-6"
    user_steps = [s for s in traj.steps if s.source == StepSource.USER]
    agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
    assert len(user_steps) == 1
    assert len(agent_steps) == 1
    assert agent_steps[0].metrics is not None
    assert agent_steps[0].metrics.cost_usd == 0.01
    print(f"Basic session: {len(traj.steps)} steps, model={traj.agent.model_name}")


def test_subagent_linkage_via_state_metadata(tmp_path: Path, parser: OpencodeParser) -> None:
    """Sub-agent linkage uses tool.state.metadata.sessionId (primary)."""
    db = tmp_path / "opencode.db"
    _build_db(
        db,
        sessions=[
            {"id": "ses_parent", "slug": "p", "title": "Parent",
             "time_created": 1_700_000_000_000},
            {"id": "ses_child", "parent_id": "ses_parent", "slug": "c",
             "title": "Child", "time_created": 1_700_000_000_010},
        ],
        messages=[
            {"id": "msg_p_u", "session_id": "ses_parent",
             "data": {"role": "user"}},
            {"id": "msg_p_a", "session_id": "ses_parent",
             "data": {"role": "assistant", "modelID": "m1"}},
            {"id": "msg_c_u", "session_id": "ses_child",
             "data": {"role": "user"}},
            {"id": "msg_c_a", "session_id": "ses_child",
             "data": {"role": "assistant", "modelID": "m1"}},
        ],
        parts=[
            {"id": "p1", "message_id": "msg_p_u", "session_id": "ses_parent",
             "data": {"type": "text", "text": "go"}},
            {"id": "p2", "message_id": "msg_p_a", "session_id": "ses_parent",
             "data": {"type": "text", "text": "spawning"}},
            {
                "id": "p3", "message_id": "msg_p_a", "session_id": "ses_parent",
                "data": {
                    "type": "tool",
                    "tool": "task",
                    "callID": "call_x",
                    "state": {
                        "status": "completed",
                        "input": {"prompt": "explore"},
                        "output": "task_id: ses_child (resume)",
                        "metadata": {"sessionId": "ses_child"},
                    },
                },
            },
            {"id": "p4", "message_id": "msg_c_u", "session_id": "ses_child",
             "data": {"type": "text", "text": "explore"}},
            {"id": "p5", "message_id": "msg_c_a", "session_id": "ses_child",
             "data": {"type": "text", "text": "result"}},
        ],
    )

    trajs = parser.parse(db)
    assert len(trajs) == 2
    parent = next(t for t in trajs if t.parent_trajectory_ref is None)
    child = next(t for t in trajs if t.parent_trajectory_ref is not None)
    assert child.parent_trajectory_ref.session_id == "ses_parent"
    spawn_step = next(s for s in parent.steps if s.tool_calls)
    assert spawn_step.observation is not None
    obs = spawn_step.observation.results[0]
    assert obs.subagent_trajectory_ref is not None
    assert obs.subagent_trajectory_ref[0].session_id == "ses_child"
    print(f"Sub-agent linkage OK: {parent.session_id} -> {child.session_id}")


def test_subagent_linkage_via_regex_fallback(tmp_path: Path, parser: OpencodeParser) -> None:
    """When state.metadata.sessionId is absent, regex on output text recovers it."""
    db = tmp_path / "opencode.db"
    _build_db(
        db,
        sessions=[{"id": "ses_p2", "slug": "p2", "title": "Parent"}],
        messages=[
            {"id": "m1", "session_id": "ses_p2", "data": {"role": "user"}},
            {"id": "m2", "session_id": "ses_p2",
             "data": {"role": "assistant", "modelID": "x"}},
        ],
        parts=[
            {"id": "p1", "message_id": "m1", "session_id": "ses_p2",
             "data": {"type": "text", "text": "go"}},
            {
                "id": "p2", "message_id": "m2", "session_id": "ses_p2",
                "data": {
                    "type": "tool",
                    "tool": "task",
                    "callID": "call_y",
                    "state": {
                        "status": "completed",
                        "input": {},
                        "output": "task_id: ses_orphan\n<task_result>...",
                    },
                },
            },
        ],
    )
    trajs = parser.parse(db)
    parent = trajs[0]
    spawn_step = next(s for s in parent.steps if s.tool_calls)
    obs = spawn_step.observation.results[0]
    assert obs.subagent_trajectory_ref[0].session_id == "ses_orphan"
    print("Regex fallback OK")


def test_tool_error_uses_state_error(tmp_path: Path, parser: OpencodeParser) -> None:
    """state.status='error' produces is_error=True with state.error as content."""
    db = tmp_path / "opencode.db"
    _build_db(
        db,
        sessions=[{"id": "ses_e", "slug": "e", "title": "Err"}],
        messages=[
            {"id": "m1", "session_id": "ses_e", "data": {"role": "user"}},
            {"id": "m2", "session_id": "ses_e",
             "data": {"role": "assistant", "modelID": "x"}},
        ],
        parts=[
            {"id": "p1", "message_id": "m1", "session_id": "ses_e",
             "data": {"type": "text", "text": "search"}},
            {
                "id": "p2", "message_id": "m2", "session_id": "ses_e",
                "data": {
                    "type": "tool", "tool": "glob", "callID": "c1",
                    "state": {"status": "error", "input": {"pattern": "**/*"},
                              "error": "permission denied"},
                },
            },
        ],
    )
    trajs = parser.parse(db)
    spawn_step = next(s for s in trajs[0].steps if s.tool_calls)
    obs = spawn_step.observation.results[0]
    assert obs.is_error is True
    assert "permission denied" in (obs.content or "")
    print("Error tool handled correctly")


def test_editor_context_captured(tmp_path: Path, parser: OpencodeParser) -> None:
    """When editorContext is present (Kilo databases), it lands on Step.extra."""
    db = tmp_path / "opencode.db"
    _build_db(
        db,
        sessions=[{"id": "ses_kilo", "slug": "k", "title": "Kilo"}],
        messages=[
            {
                "id": "m1", "session_id": "ses_kilo",
                "data": {
                    "role": "user",
                    "editorContext": {"openTabs": ["a.py"], "shell": "/bin/zsh"},
                },
            },
            {"id": "m2", "session_id": "ses_kilo",
             "data": {"role": "assistant", "modelID": "x"}},
        ],
        parts=[
            {"id": "p1", "message_id": "m1", "session_id": "ses_kilo",
             "data": {"type": "text", "text": "hi"}},
            {"id": "p2", "message_id": "m2", "session_id": "ses_kilo",
             "data": {"type": "text", "text": "ok"}},
        ],
    )
    trajs = parser.parse(db)
    user_step = next(s for s in trajs[0].steps if s.source == StepSource.USER)
    assert user_step.extra is not None
    assert user_step.extra["editor_context"]["shell"] == "/bin/zsh"
    print("editor_context captured (no-op in OpenCode, populates Kilo for free)")


def test_no_db_returns_empty(tmp_path: Path, parser: OpencodeParser) -> None:
    """Discovery returns nothing when the db file doesn't exist."""
    discovered = parser.discover_session_files(tmp_path)
    assert discovered == []
    print("Empty data dir handled correctly")


def test_malformed_db_no_exception(tmp_path: Path, parser: OpencodeParser) -> None:
    """A non-SQLite file at the db path is handled gracefully (no raise)."""
    bad = tmp_path / "opencode.db"
    bad.write_text("this is not a sqlite database", encoding="utf-8")
    trajs = parser.parse(bad)
    assert trajs == []
    print("Malformed DB handled gracefully")

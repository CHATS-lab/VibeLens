"""Kilo parser tests — verify OpencodeParser subclass behaviour + kilo deltas."""

import json
import sqlite3
from pathlib import Path

import pytest

from vibelens.ingest.parsers.kilo import KiloParser
from vibelens.ingest.parsers.opencode import OpencodeParser
from vibelens.models.enums import AgentType, StepSource


def _build_kilo_db(db_path: Path) -> None:
    """Create a kilo.db schema (no icon_url_override) with editorContext data."""
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
        ("kp", "/k/proj", "git", "k"),
    )
    conn.execute(
        """INSERT INTO session
           (id, project_id, slug, directory, title, version,
            time_created, time_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("ses_kilo_1", "kp", "k1", "/k/proj", "k1", "7.0.0",
         1_700_000_000_000, 1_700_000_000_000),
    )
    conn.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "m_user", "ses_kilo_1", 1_700_000_000_000, 1_700_000_000_000,
            json.dumps({
                "role": "user",
                "editorContext": {"openTabs": ["a.ts", "b.ts"], "shell": "/bin/zsh"},
            }),
        ),
    )
    conn.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "m_asst", "ses_kilo_1", 1_700_000_000_001, 1_700_000_000_001,
            json.dumps({"role": "assistant", "modelID": "kilo-auto/free"}),
        ),
    )
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("p1", "m_user", "ses_kilo_1", 1_700_000_000_000, 1_700_000_000_000,
         json.dumps({"type": "text", "text": "hello"})),
    )
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("p2", "m_asst", "ses_kilo_1", 1_700_000_000_001, 1_700_000_000_001,
         json.dumps({"type": "text", "text": "hi"})),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def parser() -> KiloParser:
    return KiloParser()


def test_inherits_opencode_lifecycle(tmp_path: Path, parser: KiloParser) -> None:
    """KiloParser is an OpencodeParser; same parse pipeline applies."""
    assert isinstance(parser, OpencodeParser)
    assert parser.AGENT_TYPE == AgentType.KILO
    assert parser.DB_FILENAME == "kilo.db"
    db = tmp_path / "kilo.db"
    _build_kilo_db(db)
    trajs = parser.parse(db)
    assert len(trajs) == 1
    assert trajs[0].session_id == "ses_kilo_1"
    assert trajs[0].agent.name == AgentType.KILO.value
    assert trajs[0].agent.model_name == "kilo-auto/free"
    print(f"Inherited lifecycle: {len(trajs[0].steps)} steps")


def test_editor_context_populated(tmp_path: Path, parser: KiloParser) -> None:
    """Kilo's editorContext lands on Step.extra.editor_context."""
    db = tmp_path / "kilo.db"
    _build_kilo_db(db)
    trajs = parser.parse(db)
    user_step = next(s for s in trajs[0].steps if s.source == StepSource.USER)
    assert user_step.extra is not None
    ctx = user_step.extra["editor_context"]
    assert ctx["shell"] == "/bin/zsh"
    assert ctx["openTabs"] == ["a.ts", "b.ts"]
    print(f"editor_context: {ctx}")


def test_local_data_dir_resolves_to_kilo(parser: KiloParser) -> None:
    """LOCAL_DATA_DIR points at ~/.local/share/kilo/, not opencode."""
    assert Path.home() / ".local" / "share" / "kilo" == parser.LOCAL_DATA_DIR
    print(f"LOCAL_DATA_DIR: {parser.LOCAL_DATA_DIR}")


def test_no_icon_url_override_in_project(tmp_path: Path, parser: KiloParser) -> None:
    """Kilo's project table lacks icon_url_override; parser must tolerate it."""
    db = tmp_path / "kilo.db"
    _build_kilo_db(db)
    # Verify the column doesn't exist in our fixture schema.
    conn = sqlite3.connect(str(db))
    cols = [row[1] for row in conn.execute("PRAGMA table_info(project)")]
    conn.close()
    assert "icon_url_override" not in cols
    # Parser should not raise.
    trajs = parser.parse(db)
    assert trajs
    print(f"Tolerated missing column; cols={cols}")


def test_discover_finds_kilo_db_only(tmp_path: Path, parser: KiloParser) -> None:
    """discover_session_files looks for kilo.db, not opencode.db."""
    (tmp_path / "opencode.db").write_text("not_a_db", encoding="utf-8")
    (tmp_path / "kilo.db").write_text("not_a_db_either", encoding="utf-8")
    discovered = parser.discover_session_files(tmp_path)
    assert len(discovered) == 1
    assert discovered[0].name == "kilo.db"
    print(f"Discovered: {discovered[0].name}")


def test_malformed_db_no_exception(tmp_path: Path, parser: KiloParser) -> None:
    """A non-SQLite file at kilo.db is handled gracefully (no raise)."""
    bad = tmp_path / "kilo.db"
    bad.write_text("not a real sqlite file", encoding="utf-8")
    trajs = parser.parse(bad)
    assert trajs == []
    print("Malformed DB handled gracefully")

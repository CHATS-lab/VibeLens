"""Database layer using aiosqlite."""

from pathlib import Path

import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL DEFAULT '',
    project_name TEXT NOT NULL DEFAULT '',
    timestamp    TEXT,
    duration     INTEGER NOT NULL DEFAULT 0,
    message_count    INTEGER NOT NULL DEFAULT 0,
    tool_call_count  INTEGER NOT NULL DEFAULT 0,
    models       TEXT NOT NULL DEFAULT '[]',
    first_message    TEXT NOT NULL DEFAULT '',
    source_type  TEXT NOT NULL DEFAULT 'local',
    source_name  TEXT NOT NULL DEFAULT '',
    source_host  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    uuid        TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    parent_uuid TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL,
    type        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    thinking    TEXT,
    model       TEXT NOT NULL DEFAULT '',
    timestamp   TEXT,
    is_sidechain INTEGER NOT NULL DEFAULT 0,
    usage       TEXT,
    tool_calls  TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""

_db_path: Path | None = None


async def init_db(db_path: Path) -> None:
    """Create the database and tables if they don't exist."""
    global _db_path
    _db_path = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


async def get_connection() -> aiosqlite.Connection:
    """Return a connection to the database."""
    if _db_path is None:
        raise RuntimeError("Database not initialized — call init_db first")
    return await aiosqlite.connect(str(_db_path))

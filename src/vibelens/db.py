"""Database layer using aiosqlite."""

import json
from pathlib import Path

import aiosqlite

from vibelens.models.enums import DataSourceType
from vibelens.models.message import Message
from vibelens.models.session import SessionSummary
from vibelens.utils.paths import ensure_dir
from vibelens.utils.timestamps import format_isoformat

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
    ensure_dir(db_path.parent)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


async def get_connection() -> aiosqlite.Connection:
    """Return a connection to the database."""
    if _db_path is None:
        raise RuntimeError("Database not initialized — call init_db first")
    return await aiosqlite.connect(str(_db_path))


async def insert_session(conn: aiosqlite.Connection, summary: SessionSummary) -> bool:
    """Upsert a session summary into the sessions table.

    Args:
        conn: Active database connection.
        summary: Session summary to store.

    Returns:
        True if inserted, False if already existed (skipped).
    """
    cursor = await conn.execute(
        "SELECT 1 FROM sessions WHERE session_id = ?", (summary.session_id,)
    )
    if await cursor.fetchone():
        return False

    models_json = json.dumps(summary.models)
    timestamp_str = format_isoformat(summary.timestamp)

    await conn.execute(
        """
        INSERT INTO sessions
            (session_id, project_id, project_name, timestamp, duration,
             message_count, tool_call_count, models, first_message,
             source_type, source_name, source_host)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            summary.session_id,
            summary.project_id,
            summary.project_name,
            timestamp_str,
            summary.duration,
            summary.message_count,
            summary.tool_call_count,
            models_json,
            summary.first_message,
            summary.source_type.value
            if isinstance(summary.source_type, DataSourceType)
            else summary.source_type,
            summary.source_name,
            summary.source_host,
        ),
    )
    return True


async def insert_messages(conn: aiosqlite.Connection, messages: list[Message]) -> int:
    """Batch insert messages into the messages table.

    Args:
        conn: Active database connection.
        messages: List of Message objects to insert.

    Returns:
        Number of messages inserted.
    """
    if not messages:
        return 0

    rows = []
    for msg in messages:
        usage_json = json.dumps(msg.usage.model_dump()) if msg.usage else None
        tool_calls_json = json.dumps([tc.model_dump() for tc in msg.tool_calls])
        content_str = (
            msg.content
            if isinstance(msg.content, str)
            else json.dumps([block.model_dump() for block in msg.content])
        )
        timestamp_str = format_isoformat(msg.timestamp)

        rows.append(
            (
                msg.uuid,
                msg.session_id,
                msg.parent_uuid,
                msg.role,
                msg.type,
                content_str,
                msg.thinking,
                msg.model,
                timestamp_str,
                int(msg.is_sidechain),
                usage_json,
                tool_calls_json,
            )
        )

    await conn.executemany(
        """
        INSERT OR IGNORE INTO messages
            (uuid, session_id, parent_uuid, role, type, content, thinking,
             model, timestamp, is_sidechain, usage, tool_calls)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


async def query_sessions(
    conn: aiosqlite.Connection,
    source_type: str | None = None,
    project: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[SessionSummary]:
    """Query session summaries with optional filtering.

    Args:
        conn: Active database connection.
        source_type: Filter by source type (e.g. "huggingface").
        project: Filter by project name.
        limit: Maximum results to return.
        offset: Number of results to skip.

    Returns:
        List of SessionSummary objects.
    """
    conditions = []
    params: list = []

    if source_type:
        conditions.append("source_type = ?")
        params.append(source_type)
    if project:
        conditions.append("project_name = ?")
        params.append(project)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT session_id, project_id, project_name, timestamp, duration,
               message_count, tool_call_count, models, first_message,
               source_type, source_name, source_host
        FROM sessions
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """
    # LIMIT/OFFSET params must come after any WHERE params because
    # SQLite binds positional placeholders (?) left-to-right.
    params.extend([limit, offset])

    cursor = await conn.execute(query, params)
    rows = await cursor.fetchall()

    summaries = []
    for row in rows:
        models = json.loads(row[7]) if row[7] else []
        summaries.append(
            SessionSummary(
                session_id=row[0],
                project_id=row[1],
                project_name=row[2],
                timestamp=row[3],
                duration=row[4],
                message_count=row[5],
                tool_call_count=row[6],
                models=models,
                first_message=row[8],
                source_type=row[9],
                source_name=row[10],
                source_host=row[11],
            )
        )
    return summaries


async def query_session_detail(
    conn: aiosqlite.Connection, session_id: str
) -> tuple[SessionSummary | None, list[Message]]:
    """Query a session and its messages by session_id.

    Args:
        conn: Active database connection.
        session_id: The session to retrieve.

    Returns:
        Tuple of (SessionSummary or None, list of Message objects).
    """
    cursor = await conn.execute(
        """
        SELECT session_id, project_id, project_name, timestamp, duration,
               message_count, tool_call_count, models, first_message,
               source_type, source_name, source_host
        FROM sessions WHERE session_id = ?
        """,
        (session_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None, []

    models = json.loads(row[7]) if row[7] else []
    summary = SessionSummary(
        session_id=row[0],
        project_id=row[1],
        project_name=row[2],
        timestamp=row[3],
        duration=row[4],
        message_count=row[5],
        tool_call_count=row[6],
        models=models,
        first_message=row[8],
        source_type=row[9],
        source_name=row[10],
        source_host=row[11],
    )

    cursor = await conn.execute(
        """
        SELECT uuid, session_id, parent_uuid, role, type, content, thinking,
               model, timestamp, is_sidechain, usage, tool_calls
        FROM messages WHERE session_id = ?
        ORDER BY timestamp ASC
        """,
        (session_id,),
    )
    msg_rows = await cursor.fetchall()

    messages = []
    for mr in msg_rows:
        usage = json.loads(mr[10]) if mr[10] else None
        tool_calls = json.loads(mr[11]) if mr[11] else []
        messages.append(
            Message(
                uuid=mr[0],
                session_id=mr[1],
                parent_uuid=mr[2] or "",
                role=mr[3],
                type=mr[4],
                content=mr[5] or "",
                thinking=mr[6],
                model=mr[7] or "",
                timestamp=mr[8],
                is_sidechain=bool(mr[9]),
                usage=usage,
                tool_calls=tool_calls,
            )
        )
    return summary, messages


async def delete_sessions_by_source(conn: aiosqlite.Connection, source_name: str) -> int:
    """Delete all sessions and messages for a given source_name.

    Args:
        conn: Active database connection.
        source_name: The source name to delete (e.g. repo_id).

    Returns:
        Number of sessions deleted.
    """
    cursor = await conn.execute(
        "SELECT session_id FROM sessions WHERE source_name = ?",
        (source_name,),
    )
    session_ids = [row[0] for row in await cursor.fetchall()]
    if not session_ids:
        return 0

    placeholders = ",".join("?" * len(session_ids))
    await conn.execute(
        f"DELETE FROM messages WHERE session_id IN ({placeholders})",
        session_ids,
    )
    await conn.execute(
        f"DELETE FROM sessions WHERE session_id IN ({placeholders})",
        session_ids,
    )
    return len(session_ids)

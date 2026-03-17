"""SQLite-backed SessionStore implementation.

Thin wrapper around existing db.py functions. The ``token`` parameter
is accepted for protocol compliance but ignored — storage is global.
"""

from vibelens.db import (
    get_connection,
    insert_messages,
    insert_session,
    query_session_detail,
    query_sessions,
)
from vibelens.models.enums import DataSourceType
from vibelens.models.message import Message
from vibelens.models.session import SessionDetail, SessionSummary

SQLITE_SOURCE_TYPES = (DataSourceType.UPLOAD.value, DataSourceType.HUGGINGFACE.value)


class SqliteSessionStore:
    """SessionStore backed by the SQLite database.

    Delegates all persistence to the existing ``db`` module.
    Token parameter is ignored since SQLite storage is global.
    """

    async def store_session(
        self, summary: SessionSummary, messages: list[Message], token: str
    ) -> bool:
        """Store a session and its messages in SQLite.

        Args:
            summary: Session summary to store.
            messages: Messages belonging to the session.
            token: Ignored — SQLite storage is global.

        Returns:
            True if stored, False if skipped (duplicate).
        """
        conn = await get_connection()
        try:
            inserted = await insert_session(conn, summary)
            if not inserted:
                return False
            await insert_messages(conn, messages)
            await conn.commit()
            return True
        finally:
            await conn.close()

    async def list_sessions(self, token: str) -> list[SessionSummary]:
        """List sessions from SQLite (upload and huggingface sources).

        Args:
            token: Ignored — SQLite storage is global.

        Returns:
            List of session summaries.
        """
        try:
            conn = await get_connection()
        except RuntimeError:
            return []
        try:
            results: list[SessionSummary] = []
            for source_type in SQLITE_SOURCE_TYPES:
                sessions = await query_sessions(conn, source_type=source_type, limit=500)
                results.extend(sessions)
            return results
        finally:
            await conn.close()

    async def get_session(self, session_id: str, token: str) -> SessionDetail | None:
        """Retrieve a session by ID from SQLite.

        Args:
            session_id: The session to retrieve.
            token: Ignored — SQLite storage is global.

        Returns:
            SessionDetail if found, None otherwise.
        """
        try:
            conn = await get_connection()
        except RuntimeError:
            return None
        try:
            summary, messages = await query_session_detail(conn, session_id)
            if summary is None:
                return None
            return SessionDetail(summary=summary, messages=messages)
        finally:
            await conn.close()

    async def delete_by_token(self, token: str) -> int:
        """No-op for SQLite store — tokens are not tracked.

        Args:
            token: Ignored.

        Returns:
            Always 0.
        """
        return 0

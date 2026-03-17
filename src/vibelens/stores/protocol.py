"""SessionStore protocol for decoupling session persistence from endpoints."""

from typing import Protocol

from vibelens.models.message import Message
from vibelens.models.session import SessionDetail, SessionSummary


class SessionStore(Protocol):
    """Abstract storage interface for session data.

    Implementations handle where and how sessions are persisted.
    The ``token`` parameter enables per-client isolation in demo mode;
    implementations that don't need isolation (e.g. SQLite) ignore it.
    """

    async def store_session(
        self, summary: SessionSummary, messages: list[Message], token: str
    ) -> bool:
        """Store a session and its messages.

        Args:
            summary: Session summary to store.
            messages: Messages belonging to the session.
            token: Client isolation token (ignored by some implementations).

        Returns:
            True if stored, False if skipped (duplicate).
        """
        ...

    async def list_sessions(self, token: str) -> list[SessionSummary]:
        """List available sessions.

        Args:
            token: Client isolation token.

        Returns:
            List of session summaries.
        """
        ...

    async def get_session(self, session_id: str, token: str) -> SessionDetail | None:
        """Retrieve full session detail by ID.

        Args:
            session_id: The session to retrieve.
            token: Client isolation token.

        Returns:
            SessionDetail if found, None otherwise.
        """
        ...

    async def delete_by_token(self, token: str) -> int:
        """Delete all sessions associated with a token.

        Args:
            token: Client isolation token whose sessions to remove.

        Returns:
            Number of sessions deleted.
        """
        ...

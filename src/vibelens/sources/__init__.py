"""Data source protocol and registry."""

from collections.abc import AsyncIterator
from typing import Protocol

from vibelens.models import Message, RemoteSessionsQuery, SessionDetail, SessionSummary


class DataSource(Protocol):
    """Protocol that all data source adapters must implement."""

    @property
    def source_type(self) -> str:
        """Return the data source type identifier."""
        ...

    @property
    def display_name(self) -> str:
        """Return a human-readable name for UI display."""
        ...

    async def list_sessions(self, query: RemoteSessionsQuery) -> list[SessionSummary]:
        """Return session summaries with filtering and pagination."""
        ...

    async def get_session(self, session_id: str) -> SessionDetail | None:
        """Return full session data including all messages."""
        ...

    async def list_projects(self) -> list[str]:
        """Return all project names."""
        ...

    def supports_streaming(self) -> bool:
        """Whether this source supports SSE streaming."""
        ...

    async def stream_messages(
        self, session_id: str, offset: int = 0
    ) -> AsyncIterator[list[Message]]:
        """Stream message increments via SSE. Only local source supports this."""
        ...
        yield []  # noqa: B027

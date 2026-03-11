"""Data target protocol and registry."""

from typing import Protocol

from vibelens.models import PushResult, SessionDetail


class DataTarget(Protocol):
    """Protocol that all data target adapters must implement."""

    @property
    def target_type(self) -> str:
        """Return the data target type identifier."""
        ...

    async def push_sessions(self, sessions: list[SessionDetail]) -> PushResult:
        """Push sessions to this target."""
        ...

"""Abstract base class for trajectory storage backends.

Pure read-only data-access layer — no business logic (sorting, backfilling, etc.).
Write operations (save, copy) are backend-specific and live on concrete classes.
"""

from abc import ABC, abstractmethod

from vibelens.models.trajectories import Trajectory


class TrajectoryStore(ABC):
    """Read-only interface for retrieving trajectory groups.

    Both LocalStore (self mode) and DiskStore (demo mode) implement this
    ABC so services never need mode-aware dispatch.

    Write operations (save, upload) are DiskStore-specific and not on
    this interface.
    """

    @abstractmethod
    def initialize(self) -> None:
        """Set up the storage backend (create dirs, tables, connections)."""

    @abstractmethod
    def list_metadata(self, session_token: str | None = None) -> list[dict]:
        """Return all trajectory summaries without steps.

        Returns an unsorted list — sorting is the service layer's job.

        Args:
            session_token: Browser tab token for upload scoping (demo mode).

        Returns:
            List of trajectory summary dicts.
        """

    @abstractmethod
    def load(self, session_id: str, session_token: str | None = None) -> list[Trajectory] | None:
        """Load a full trajectory group by session ID.

        Args:
            session_id: Main session identifier.
            session_token: Browser tab token for upload scoping (demo mode).

        Returns:
            List of Trajectory objects, or None if not found.
        """

    @abstractmethod
    def list_projects(self) -> list[str]:
        """Return all unique project paths from stored sessions.

        Returns:
            Sorted list of project path strings.
        """

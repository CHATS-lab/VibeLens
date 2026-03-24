"""Abstract base class for trajectory storage backends.

Provides a unified index pattern shared by all backends:
  _index:          session_id -> (Path, BaseParser) for parser-based loading
  _metadata_cache: session_id -> summary dict for fast listing

Concrete methods (list_metadata, load, exists, etc.) operate on these
shared structures. Subclasses only implement initialize(), save(), and
_build_index().
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.trajectories import Trajectory
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class TrajectoryStore(ABC):
    """Base class for trajectory storage backends.

    Both LocalStore (self mode) and DiskStore (demo mode) inherit
    concrete read methods so services never need mode-aware dispatch.

    Subclasses must implement:
      - initialize(): set up directories/connections
      - save(): persist trajectories (or raise NotImplementedError)
      - _build_index(): populate _index and _metadata_cache
    """

    def __init__(self) -> None:
        self._index: dict[str, tuple[Path, BaseParser]] = {}
        self._metadata_cache: dict[str, dict] | None = None

    @abstractmethod
    def initialize(self) -> None:
        """Set up the storage backend (create dirs, tables, connections)."""

    def list_metadata(self) -> list[dict]:
        """Return all trajectory summaries without steps.

        Returns:
            Unsorted list of trajectory summary dicts.
        """
        return list(self._ensure_index().values())

    def list_projects(self) -> list[str]:
        """Return all unique project paths from stored sessions.

        Returns:
            Sorted list of project path strings.
        """
        index = self._ensure_index()
        return sorted({m.get("project_path") for m in index.values() if m.get("project_path")})

    def load(self, session_id: str) -> list[Trajectory] | None:
        """Load a full trajectory group by session ID.

        Delegates to the parser associated with the session in _index.

        Args:
            session_id: Main session identifier.

        Returns:
            List of Trajectory objects (main + sub-agents), or None.
        """
        self._ensure_index()
        entry = self._index.get(session_id)
        if not entry:
            return None

        path, parser = entry
        trajectories = parser.parse_file(path)
        if not trajectories:
            return None

        return self._sort_trajectories(trajectories)

    @abstractmethod
    def save(self, trajectories: list[Trajectory]) -> None:
        """Persist a trajectory group.

        Args:
            trajectories: Related trajectories (main + sub-agents).

        Raises:
            NotImplementedError: If backend is read-only.
        """

    def exists(self, session_id: str) -> bool:
        """Check whether a session exists without loading it.

        Args:
            session_id: Main session identifier.

        Returns:
            True if the session exists in the index.
        """
        return session_id in self._ensure_index()

    def session_count(self) -> int:
        """Return total number of indexed sessions.

        Returns:
            Number of sessions in the metadata cache.
        """
        return len(self._ensure_index())

    def get_metadata(self, session_id: str) -> dict | None:
        """Return the cached metadata dict for a single session.

        Args:
            session_id: Main session identifier.

        Returns:
            Summary dict, or None if not found.
        """
        return self._ensure_index().get(session_id)

    @abstractmethod
    def _build_index(self) -> None:
        """Build metadata index from backing store.

        Must populate both self._index (session_id -> (path, parser))
        and self._metadata_cache (session_id -> summary dict).
        """

    def _ensure_index(self) -> dict[str, dict]:
        """Lazy-load and return the cached metadata index."""
        if self._metadata_cache is None:
            self._build_index()
        return self._metadata_cache  # type: ignore[return-value]

    def invalidate_index(self) -> None:
        """Clear cached index, forcing rebuild on next access."""
        self._metadata_cache = None
        self._index = {}

    @staticmethod
    def _sort_trajectories(trajectories: list[Trajectory]) -> list[Trajectory]:
        """Sort trajectories: main first, then sub-agents by timestamp.

        Args:
            trajectories: Unsorted trajectory list.

        Returns:
            Sorted list with main trajectory first.
        """
        main = [t for t in trajectories if not t.parent_trajectory_ref]
        subs = sorted(
            (t for t in trajectories if t.parent_trajectory_ref),
            key=lambda t: t.timestamp or datetime.min,
        )
        return main + subs

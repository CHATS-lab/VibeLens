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
from vibelens.models.trajectories.trajectory_ref import TrajectoryRef
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class BaseTrajectoryStore(ABC):
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
        self._ensure_index()
        return list(self._metadata_cache.values()) if self._metadata_cache else []

    def list_projects(self) -> list[str]:
        """Return all unique project paths from stored sessions.

        Returns:
            Sorted list of project path strings.
        """
        index = self._ensure_index()
        return sorted({m.get("project_path") for m in index.values() if m.get("project_path")})

    def get_session_source(self, session_id: str) -> tuple[Path, BaseParser] | None:
        """Return the file path and parser for a session.

        Args:
            session_id: Main session identifier.

        Returns:
            Tuple of (file_path, parser), or None if not found.
        """
        self._ensure_index()
        return self._index.get(session_id)

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
            logger.warning(
                "Parser %s returned no trajectories for session %s from %s",
                type(parser).__name__,
                session_id,
                path,
            )
            return None

        self._enrich_refs_from_index(session_id, trajectories)
        return self._sort_trajectories(trajectories)

    def _enrich_refs_from_index(self, session_id: str, trajectories: list[Trajectory]) -> None:
        """Carry over continuation refs from the index to loaded trajectories.

        The index builder enriches skeletons with prev_trajectory_ref and
        next_trajectory_ref via JSONL analysis.  When sessions are
        re-parsed from disk these refs are lost, so we copy them back
        from the cached metadata onto the main trajectory.
        """
        meta = self._metadata_cache.get(session_id)
        if not meta:
            return
        main = next((t for t in trajectories if t.session_id == session_id), None)
        if not main:
            return

        ref_fields = ("prev_trajectory_ref", "next_trajectory_ref")
        for field in ref_fields:
            if getattr(main, field) is not None:
                continue
            ref_data = meta.get(field)
            if ref_data and isinstance(ref_data, dict):
                setattr(main, field, TrajectoryRef(**ref_data))

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

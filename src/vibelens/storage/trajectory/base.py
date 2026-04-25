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
        """Return summaries for top-level (non-sub-agent) trajectories.

        Sub-agents are excluded so they only surface nested under their
        parent in the UI. We treat a trajectory as a sub-agent when:

        - ``parent_trajectory_ref`` is set (the strong signal — fork-mode
          children, SQLite-linked children, Hermes db-linked children), or
        - ``extra.agent_role`` is set (Codex marks fresh sub-agents this
          way even when the parent link can't be reconstructed — e.g.
          ``codex exec`` doesn't write to ``state_5.sqlite``).

        Matches Claude's discovery-time exclusion (sub-agent files
        aren't indexed at all) so the listing layer is consistent across
        all parsers.

        Returns:
            Unsorted list of trajectory summary dicts for main sessions only.
        """
        self._ensure_index()
        if not self._metadata_cache:
            return []
        return [m for m in self._metadata_cache.values() if not _is_sub_agent_metadata(m)]

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

        Snapshots _index and _metadata_cache at call time so a concurrent
        invalidate_index() cannot cause AttributeError mid-operation.

        Args:
            session_id: Main session identifier.

        Returns:
            List of Trajectory objects (main + sub-agents), or None.
        """
        metadata_cache, index = self._ensure_index_snapshot()
        entry = index.get(session_id)
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

        self._enrich_refs_from_index(session_id, trajectories, metadata_cache)
        return self._sort_trajectories(trajectories)

    def _enrich_refs_from_index(
        self, session_id: str, trajectories: list[Trajectory], metadata_cache: dict[str, dict]
    ) -> None:
        """Carry over continuation refs from the index to loaded trajectories.

        The index builder enriches skeletons with prev_trajectory_ref and
        next_trajectory_ref via JSONL analysis.  When sessions are
        re-parsed from disk these refs are lost, so we copy them back
        from the cached metadata onto the main trajectory.

        Args:
            session_id: Main session identifier.
            trajectories: Parsed trajectory list to enrich.
            metadata_cache: Snapshot of the metadata cache dict.
        """
        meta = metadata_cache.get(session_id)
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

    def _invalidate_if_stale(self) -> None:  # noqa: B027 — intentional no-op default
        """Hook: subclasses may clear the cache when external state has changed.

        Called on every _ensure_index(_snapshot) access. The default is a
        no-op because stores with no external writer (e.g. the disk store,
        which only mutates via save()) cannot go stale.
        """

    def _ensure_index(self) -> dict[str, dict]:
        """Lazy-load and return the cached metadata index."""
        self._invalidate_if_stale()
        if self._metadata_cache is None:
            self._build_index()
        return self._metadata_cache  # type: ignore[return-value]

    def _ensure_index_snapshot(self) -> tuple[dict[str, dict], dict[str, tuple[Path, BaseParser]]]:
        """Lazy-load index and return both caches as a snapshot.

        Captures _metadata_cache and _index together after _build_index
        completes so load() holds stable local references even if a
        concurrent invalidate_index() replaces the instance attributes.

        Returns:
            Tuple of (metadata_cache, index) captured atomically after
            the index is guaranteed to be populated.
        """
        self._invalidate_if_stale()
        if self._metadata_cache is None:
            self._build_index()
        return self._metadata_cache, self._index  # type: ignore[return-value]

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


def _is_sub_agent_metadata(meta: dict) -> bool:
    """True when a trajectory metadata dict represents a sub-agent.

    Strong signal: ``parent_trajectory_ref`` is set. Fallback signal
    (Codex fresh sub-agents from ``codex exec`` mode where SQLite
    isn't written): ``extra.agent_role`` is non-empty.
    """
    if meta.get("parent_trajectory_ref"):
        return True
    extra = meta.get("extra") or {}
    return bool(extra.get("agent_role"))

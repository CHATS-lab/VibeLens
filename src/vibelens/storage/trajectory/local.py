"""Multi-agent local session store returning Trajectory objects.

Implements TrajectoryStore by reading sessions from all local agent data
directories. Uses LOCAL_PARSER_CLASSES to instantiate parsers, scans each
parser's data directory for session files, and builds a unified file index
across all agents.
"""

import threading
from dataclasses import dataclass, field
from pathlib import Path

from vibelens.ingest.fast_metrics import scan_session_metrics
from vibelens.ingest.index_builder import (
    build_partial_session_index,
    build_session_index,
)
from vibelens.ingest.index_cache import collect_file_mtimes, load_cache, save_cache
from vibelens.ingest.parsers import LOCAL_PARSER_CLASSES
from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import FinalMetrics, Trajectory
from vibelens.storage.trajectory.base import BaseTrajectoryStore
from vibelens.utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CachePartition:
    """Result of comparing the current file index against the persisted cache."""

    unchanged: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    changed: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    new: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    removed_paths: set[str] = field(default_factory=set)


def _extract_session_id(filepath: Path, agent_type: AgentType) -> str:
    """Derive a unique session_id from the file path.

    Claude Code uses the filename stem as UUID directly. Other agents
    are prefixed with their agent type to avoid ID collisions.

    Args:
        filepath: Path to the session file.
        agent_type: Parser's AgentType enum value.

    Returns:
        Unique session identifier.
    """
    stem = filepath.stem
    if agent_type == AgentType.CLAUDE:
        return stem
    return f"{agent_type.value}:{stem}"


def _partition_files(
    file_index: dict[str, tuple[Path, BaseParser]],
    cached_mtimes: dict[str, int],
    dropped_paths: dict[str, int],
) -> tuple[CachePartition, dict[str, int]]:
    """Compare current file index against the cache and partition by state.

    Args:
        file_index: Current session_id -> (filepath, parser) map after
            ``_discover_files`` and ``_remap_index``.
        cached_mtimes: filepath_str -> mtime_ns from the previous cache.
        dropped_paths: filepath_str -> mtime_ns for files the previous build
            dropped as empty/invalid. Files in here with unchanged mtimes are
            excluded from the partition entirely (not retried).

    Returns:
        Tuple of (CachePartition, fresh_dropped_paths) where ``fresh_dropped_paths``
        is the subset of ``dropped_paths`` whose files still exist with the
        same mtime — these carry forward into the next saved cache.
    """
    unchanged: dict[str, tuple[Path, BaseParser]] = {}
    changed: dict[str, tuple[Path, BaseParser]] = {}
    new: dict[str, tuple[Path, BaseParser]] = {}
    fresh_dropped: dict[str, int] = {}
    current_paths: set[str] = set()

    for sid, (fpath, parser) in file_index.items():
        path_str = str(fpath)
        try:
            current_mtime = fpath.stat().st_mtime_ns
        except OSError:
            # File vanished between _discover_files and stat; treat as removed
            # by skipping it entirely. The removed_paths logic below ignores it
            # too because it is not in cached_mtimes if previously absent, or
            # it will be in removed_paths if it was previously cached.
            continue
        current_paths.add(path_str)

        # Filter out previously-dropped paths whose mtime is unchanged.
        if path_str in dropped_paths and dropped_paths[path_str] == current_mtime:
            fresh_dropped[path_str] = current_mtime
            continue

        cached_mtime = cached_mtimes.get(path_str)
        if cached_mtime is None:
            new[sid] = (fpath, parser)
        elif cached_mtime != current_mtime:
            changed[sid] = (fpath, parser)
        else:
            unchanged[sid] = (fpath, parser)

    removed_paths = set(cached_mtimes.keys()) - current_paths
    return (
        CachePartition(unchanged=unchanged, changed=changed, new=new, removed_paths=removed_paths),
        fresh_dropped,
    )


class LocalTrajectoryStore(BaseTrajectoryStore):
    """Read sessions from all local agent data directories.

    Uses LOCAL_PARSER_CLASSES to instantiate parsers, scans each parser's
    data directory for session files, and builds a unified file index
    across all agents.

    Inherits concrete read methods (list_metadata, load, exists, etc.)
    from TrajectoryStore. Only overrides initialize, save, and _build_index.
    """

    def __init__(self, data_dirs: dict[AgentType, Path] | None = None) -> None:
        super().__init__()
        self._build_lock = threading.Lock()
        self._parsers: list[BaseParser] = [cls() for cls in LOCAL_PARSER_CLASSES]
        self._data_dirs: dict[BaseParser, Path] = {}

        if data_dirs is not None:
            for parser in self._parsers:
                if parser.AGENT_TYPE in data_dirs:
                    self._data_dirs[parser] = data_dirs[parser.AGENT_TYPE]
        else:
            for parser in self._parsers:
                if parser.LOCAL_DATA_DIR:
                    self._data_dirs[parser] = parser.LOCAL_DATA_DIR

    def get_data_dir(self, parser: BaseParser) -> Path | None:
        """Return the data directory for a parser.

        Args:
            parser: Parser instance to look up.

        Returns:
            Data directory path, or None if not configured.
        """
        return self._data_dirs.get(parser)

    def initialize(self) -> None:
        """No-op — index is loaded lazily on first access."""

    def save(self, trajectories: list[Trajectory]) -> None:
        """Not supported — LocalStore is read-only.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("LocalStore is read-only")

    def invalidate_index(self) -> None:
        """Clear in-memory index cache, keeping persistent cache.

        The persistent cache (~/.vibelens/session_index.json) is preserved
        because _build_index will revalidate it via mtime checks. If all
        files are unchanged, the cache is restored directly; otherwise a
        full rebuild runs.
        """
        super().invalidate_index()

    def _build_index(self) -> None:
        """Build metadata index from all agent data directories.

        Uses a persistent JSON cache (~/.vibelens/session_index.json) to
        skip full rebuilds when files haven't changed. Thread-safe: if
        another thread is already building, this blocks until it finishes
        and reuses the result.
        """
        with self._build_lock:
            # Another thread may have built the index while we waited
            if self._metadata_cache is not None:
                return
            self._discover_files()
            if self._try_load_from_cache():
                return
            self._full_rebuild()

    def _discover_files(self) -> None:
        """Populate _index with session_id -> (filepath, parser) for all agents."""
        self._index = {}
        for parser in self._parsers:
            data_dir = self._data_dirs.get(parser)
            if not data_dir or not data_dir.exists():
                continue
            for filepath in parser.discover_session_files(data_dir):
                session_id = _extract_session_id(filepath, parser.AGENT_TYPE)
                self._index[session_id] = (filepath, parser)

    def _try_load_from_cache(self) -> bool:
        """Load index from persistent cache, taking a partial-rebuild path when possible.

        Fast path: every file in the current index has the same mtime as the
        cache → hydrate `_metadata_cache` and return.

        Partial path: a subset of files changed/added/removed → re-parse only
        those, hydrate the rest from cache, persist updated cache.

        Returns False (falls through to ``_full_rebuild``) when the cache is
        missing, version-mismatched, or the partial rebuild itself raises.
        """
        cache = load_cache()
        if not cache:
            return False

        cached_mtimes: dict[str, int] = {k: int(v) for k, v in cache.get("file_mtimes", {}).items()}
        cached_entries: dict[str, dict] = cache.get("entries", {})
        cached_path_map: dict[str, str] = cache.get("path_to_session_id", {})
        cached_dropped: dict[str, int] = {
            k: int(v) for k, v in cache.get("dropped_paths", {}).items()
        }

        # Remap before partitioning so cached real session_ids line up with _index.
        self._remap_index(cached_path_map)

        partition, fresh_dropped = _partition_files(self._index, cached_mtimes, cached_dropped)

        # Drop dropped-paths from _index — they should not appear as live sessions.
        if fresh_dropped:
            for sid in [s for s, (fpath, _p) in self._index.items() if str(fpath) in fresh_dropped]:
                self._index.pop(sid, None)

        is_fast_path = not partition.changed and not partition.new and not partition.removed_paths
        if is_fast_path:
            self._metadata_cache = {}
            for sid in self._index:
                if sid in cached_entries:
                    meta = cached_entries[sid]
                    meta["filepath"] = str(self._index[sid][0])
                    self._metadata_cache[sid] = meta
            logger.info("Loaded %d sessions from index cache", len(self._metadata_cache))
            return True

        try:
            self._partial_rebuild(partition, cached_entries, fresh_dropped)
        except Exception:
            logger.warning("Partial rebuild failed, falling back to full rebuild", exc_info=True)
            return False
        return True

    def _partial_rebuild(
        self,
        partition: CachePartition,
        cached_entries: dict[str, dict],
        fresh_dropped: dict[str, int],
    ) -> None:
        """Re-parse only changed/new files; hydrate the rest from cache."""
        # Hydrate unchanged entries from cache.
        self._metadata_cache = {}
        for sid in partition.unchanged:
            if sid in cached_entries:
                meta = cached_entries[sid]
                meta["filepath"] = str(self._index[sid][0])
                self._metadata_cache[sid] = meta

        # Re-parse changed + new.
        only_paths = {str(fpath) for fpath, _p in partition.changed.values()} | {
            str(fpath) for fpath, _p in partition.new.values()
        }

        new_dropped: dict[str, int] = {}
        if only_paths:
            partial_skeletons, dropped_paths = build_partial_session_index(self._index, only_paths)
            _enrich_skeleton_metrics(partial_skeletons, self._index)
            for t in partial_skeletons:
                meta = t.model_dump(exclude={"steps"}, mode="json")
                entry = self._index.get(t.session_id)
                if entry:
                    meta["filepath"] = str(entry[0])
                self._metadata_cache[t.session_id] = meta
            for fpath in dropped_paths:
                try:
                    new_dropped[str(fpath)] = fpath.stat().st_mtime_ns
                except OSError:
                    continue

        # Drop removed_paths' sids — but only if they came from the cache and
        # were not re-claimed by a freshly parsed file at a different path.
        # A removed path is "stale" in the cache; if the same session_id was
        # produced by partial rebuild for a NEW path, that new entry wins.
        for sid, entry in cached_entries.items():
            cached_filepath = entry.get("filepath")
            if cached_filepath not in partition.removed_paths:
                continue
            meta = self._metadata_cache.get(sid)
            if meta is None:
                continue
            if meta.get("filepath") == cached_filepath:
                self._metadata_cache.pop(sid, None)
                self._index.pop(sid, None)
            # else: sid was re-bound to a current path; keep the new entry.

        merged_dropped = {**fresh_dropped, **new_dropped}
        post_mtimes = collect_file_mtimes(self._index)
        path_to_session_id = {str(fpath): sid for sid, (fpath, _p) in self._index.items()}
        save_cache(
            self._metadata_cache,
            post_mtimes,
            continuation_map={},
            path_to_session_id=path_to_session_id,
            dropped_paths=merged_dropped,
        )

        logger.info(
            "Loaded %d sessions from index cache "
            "(%d unchanged, %d added, %d re-parsed, %d removed)",
            len(self._metadata_cache),
            len(partition.unchanged),
            len(partition.new),
            len(partition.changed),
            len(partition.removed_paths),
        )

    def _remap_index(self, path_to_session_id: dict[str, str]) -> None:
        """Remap _index keys using the cached path -> real session_id mapping.

        After _discover_files, _index uses filename-based keys. Some sessions
        (orphans, Codex rollouts) have real IDs different from the filename.
        The cache stores the correct mapping so we can restore _index properly.
        """
        if not path_to_session_id:
            return

        new_index: dict[str, tuple[Path, BaseParser]] = {}
        for _filename_sid, (fpath, parser) in self._index.items():
            real_sid = path_to_session_id.get(str(fpath), _filename_sid)
            new_index[real_sid] = (fpath, parser)
        self._index = new_index

    def _full_rebuild(self) -> None:
        """Full index rebuild: parse all files, write cache."""
        # Capture mtimes BEFORE rebuild — build_session_index mutates _index
        # (remaps orphaned IDs, drops empty files), so we need the pre-remap
        # paths to match what _discover_files will produce on next startup.
        pre_rebuild_mtimes = collect_file_mtimes(self._index)

        trajectories, dropped_paths = build_session_index(self._index, self._data_dirs)

        # Enrich skeletons with fast-scanned metrics for dashboard stats
        _enrich_skeleton_metrics(trajectories, self._index)

        self._metadata_cache = {}
        for t in trajectories:
            meta = t.model_dump(exclude={"steps"}, mode="json")
            entry = self._index.get(t.session_id)
            if entry:
                meta["filepath"] = str(entry[0])
            self._metadata_cache[t.session_id] = meta
        logger.info(
            "Indexed %d sessions across %d agents", len(self._metadata_cache), len(self._parsers)
        )

        # Build path -> real session_id map for cache restoration
        path_to_session_id = {str(fpath): sid for sid, (fpath, _parser) in self._index.items()}
        dropped_paths_dict: dict[str, int] = {}
        for fpath in dropped_paths:
            try:
                dropped_paths_dict[str(fpath)] = fpath.stat().st_mtime_ns
            except OSError:
                continue
        save_cache(
            self._metadata_cache,
            pre_rebuild_mtimes,
            continuation_map={},
            path_to_session_id=path_to_session_id,
            dropped_paths=dropped_paths_dict,
        )


def _apply_scanned_metrics(traj: Trajectory, metrics: dict) -> None:
    """Apply fast-scanned metrics to a single trajectory in-place.

    Populates final_metrics with token counts, tool call count, model
    name, and duration computed from timestamp span.

    Args:
        traj: Skeleton trajectory to enrich.
        metrics: Dict from scan_session_metrics with token/tool/timestamp data.
    """
    from vibelens.utils import normalize_timestamp

    fm = traj.final_metrics or FinalMetrics()
    fm.total_prompt_tokens = metrics["input_tokens"]
    fm.total_completion_tokens = metrics["output_tokens"]
    fm.total_cache_read = metrics["cache_read_tokens"]
    fm.total_cache_write = metrics["cache_creation_tokens"]
    fm.tool_call_count = metrics["tool_call_count"]
    if fm.total_steps is None or fm.total_steps == 0:
        fm.total_steps = metrics["message_count"]

    if fm.duration == 0 and metrics["first_timestamp"] and metrics["last_timestamp"]:
        first_ts = normalize_timestamp(metrics["first_timestamp"])
        last_ts = normalize_timestamp(metrics["last_timestamp"])
        if first_ts and last_ts:
            fm.duration = max(0, int((last_ts - first_ts).total_seconds()))

    traj.final_metrics = fm

    if metrics["model"] and traj.agent and not traj.agent.model_name:
        traj.agent.model_name = metrics["model"]


def _enrich_skeleton_metrics(
    trajectories: list[Trajectory], file_index: dict[str, tuple[Path, BaseParser]]
) -> None:
    """Enrich skeleton trajectories with fast-scanned metrics.

    Runs scan_session_metrics on each file to populate final_metrics
    with token counts, tool call count, model name, and duration.

    Args:
        trajectories: Skeleton trajectories to enrich in-place.
        file_index: session_id -> (filepath, parser) map.
    """
    enriched = 0
    for traj in trajectories:
        entry = file_index.get(traj.session_id)
        if not entry:
            continue
        fpath, _parser = entry
        metrics = scan_session_metrics(fpath)
        if not metrics:
            continue
        _apply_scanned_metrics(traj, metrics)
        enriched += 1

    if enriched:
        logger.info("Enriched %d skeletons with fast-scanned metrics", enriched)

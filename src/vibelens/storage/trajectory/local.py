"""Multi-agent local session store returning Trajectory objects.

Implements TrajectoryStore by reading sessions from all local agent data
directories. Uses LOCAL_PARSER_CLASSES to instantiate parsers, scans each
parser's data directory for session files, and builds a unified file index
across all agents.
"""

import threading
from pathlib import Path

from vibelens.ingest.fast_metrics import scan_session_metrics
from vibelens.ingest.index_builder import build_session_index
from vibelens.ingest.index_cache import collect_file_mtimes, load_cache, save_cache
from vibelens.ingest.parsers import LOCAL_PARSER_CLASSES
from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import FinalMetrics, Trajectory
from vibelens.storage.trajectory.base import BaseTrajectoryStore
from vibelens.utils import get_logger

logger = get_logger(__name__)


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


def _has_stale_files(
    file_index: dict[str, tuple[Path, BaseParser]], cached_mtimes: dict[str, float]
) -> bool:
    """Check whether any files changed or were removed since the cache was written.

    Args:
        file_index: Current session_id -> (filepath, parser) map.
        cached_mtimes: filepath_str -> mtime_ns from previous cache.

    Returns:
        True if any file is new, changed, or removed.
    """
    current_paths: set[str] = set()
    for _sid, (fpath, _parser) in file_index.items():
        path_str = str(fpath)
        current_paths.add(path_str)
        try:
            current_mtime = fpath.stat().st_mtime_ns
        except OSError:
            return True
        cached_mtime = cached_mtimes.get(path_str)
        if cached_mtime is None or current_mtime != cached_mtime:
            return True

    return bool(set(cached_mtimes.keys()) - current_paths)


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
        """Load index from persistent cache if no files changed.

        Returns True only on a perfect cache hit (zero stale files).
        Any staleness falls through to _full_rebuild.
        """
        cache = load_cache()
        if not cache:
            return False

        cached_mtimes = cache.get("file_mtimes", {})
        cached_entries = cache.get("entries", {})
        cached_path_map = cache.get("path_to_session_id", {})

        if _has_stale_files(self._index, cached_mtimes):
            return False

        self._remap_index(cached_path_map)
        self._metadata_cache = {}
        for sid in self._index:
            if sid in cached_entries:
                meta = cached_entries[sid]
                meta["filepath"] = str(self._index[sid][0])
                self._metadata_cache[sid] = meta
        logger.info("Loaded %d sessions from index cache", len(self._metadata_cache))
        return True

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
        """Full index rebuild: parse all files, enrich refs, write cache."""
        # Capture mtimes BEFORE rebuild — build_session_index mutates _index
        # (remaps orphaned IDs, drops empty files), so we need the pre-remap
        # paths to match what _discover_files will produce on next startup.
        pre_rebuild_mtimes = collect_file_mtimes(self._index)

        trajectories = build_session_index(self._index, self._data_dirs)

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
        continuation_map = _extract_continuation_map(self._metadata_cache)
        save_cache(self._metadata_cache, pre_rebuild_mtimes, continuation_map, path_to_session_id)


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


def _extract_continuation_map(metadata_cache: dict[str, dict]) -> dict[str, str]:
    """Extract continuation relationships from metadata for cache persistence.

    Args:
        metadata_cache: session_id -> metadata dict with optional prev_trajectory_ref.

    Returns:
        Dict mapping current_session_id -> previous_session_id.
    """
    result: dict[str, str] = {}
    for sid, meta in metadata_cache.items():
        ref = meta.get("prev_trajectory_ref")
        if ref and isinstance(ref, dict) and ref.get("session_id"):
            result[sid] = ref["session_id"]
    return result

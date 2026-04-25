"""Multi-agent local session store returning Trajectory objects.

Implements TrajectoryStore by reading sessions from all local agent data
directories. Uses LOCAL_PARSER_CLASSES to instantiate parsers, scans each
parser's data directory for session files, and builds a unified file index
across all agents.
"""

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from vibelens.ingest.index_builder import (
    build_partial_session_index,
    build_session_index,
)
from vibelens.ingest.index_cache import collect_file_mtimes, load_cache, save_cache
from vibelens.ingest.parsers import LOCAL_PARSER_CLASSES
from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import Trajectory
from vibelens.storage.trajectory.base import BaseTrajectoryStore
from vibelens.utils import get_logger

logger = get_logger(__name__)

# Minimum interval between disk scans on the read hot path. A full walk of
# ~/.claude/projects/ is ~100-200 ms with thousands of session files; a single
# HTTP request fans out to many _ensure_index() calls, so without a TTL we
# walk disk 10+ times per page load. 10s cap trades that cost against
# new-session detection latency.
_STALENESS_CHECK_MIN_INTERVAL_S = 10


@dataclass(frozen=True)
class CachePartition:
    """Result of comparing the current file index against the persisted cache."""

    unchanged: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    changed: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    new: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    removed_paths: set[str] = field(default_factory=set)


def _extract_session_id(filepath: Path, agent_type: AgentType) -> str:
    """Derive a unique session_id from the file path.

    Agents whose session files are named with globally-unique UUIDs
    (Claude) can use the filename stem directly. Agents whose filenames
    are not unique across sessions (e.g. Codex rollouts, Gemini chat logs)
    are prefixed with their agent type to avoid id collisions inside the
    shared index dict.

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


def _coerce_stats(raw: dict) -> dict[str, list[int]]:
    """Coerce a cached stat map into the canonical ``[mtime_ns, size]`` shape.

    Tolerates either the new list-of-two-ints format or any prior shape
    (single int mtime, missing size). Entries that can't be coerced are
    dropped — they fall through to ``new`` in the partition and get
    re-parsed.
    """
    out: dict[str, list[int]] = {}
    for path_str, value in raw.items():
        if isinstance(value, list) and len(value) == 2:
            try:
                out[path_str] = [int(value[0]), int(value[1])]
            except (TypeError, ValueError):
                continue
    return out


def _partition_files(
    file_index: dict[str, tuple[Path, BaseParser]],
    cached_stats: dict[str, list[int]],
    dropped_paths: dict[str, list[int]],
) -> tuple[CachePartition, dict[str, list[int]], dict[str, list[int]]]:
    """Compare current file index against the cache and partition by state.

    Compares ``[mtime_ns, size]`` per file. The size component catches
    in-place rewrites that don't move mtime.

    Args:
        file_index: Current session_id -> (filepath, parser) map after
            discovery and ``_remap_index``.
        cached_stats: filepath_str -> ``[mtime_ns, size]`` from the
            previous cache.
        dropped_paths: filepath_str -> ``[mtime_ns, size]`` for files the
            previous build dropped as empty/invalid. Files here with an
            unchanged stat tuple are excluded from the partition entirely.

    Returns:
        Tuple of ``(CachePartition, fresh_dropped, current_stats)`` where
        ``current_stats`` maps filepath_str to the live ``[mtime_ns, size]``
        captured during this pass. Callers reuse it to avoid a second
        ``stat()`` per file.
    """
    unchanged: dict[str, tuple[Path, BaseParser]] = {}
    changed: dict[str, tuple[Path, BaseParser]] = {}
    new: dict[str, tuple[Path, BaseParser]] = {}
    fresh_dropped: dict[str, list[int]] = {}
    current_stats: dict[str, list[int]] = {}

    for sid, (fpath, parser) in file_index.items():
        path_str = str(fpath)
        try:
            st = fpath.stat()
        except OSError:
            continue
        current_stat = [st.st_mtime_ns, st.st_size]
        current_stats[path_str] = current_stat

        if path_str in dropped_paths and dropped_paths[path_str] == current_stat:
            fresh_dropped[path_str] = current_stat
            continue

        cached_stat = cached_stats.get(path_str)
        if cached_stat is None:
            new[sid] = (fpath, parser)
        elif cached_stat != current_stat:
            changed[sid] = (fpath, parser)
        else:
            unchanged[sid] = (fpath, parser)

    removed_paths = set(cached_stats.keys()) - set(current_stats.keys())
    return (
        CachePartition(unchanged=unchanged, changed=changed, new=new, removed_paths=removed_paths),
        fresh_dropped,
        current_stats,
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
        self._indexed_mtimes: dict[str, int] = {}
        self._last_staleness_check: float = 0.0

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
        self._indexed_mtimes = {}
        self._last_staleness_check = 0.0

    def _invalidate_if_stale(self) -> None:
        """Drop the in-memory index if any session file was added/modified/removed.

        Rate-limited: at most one disk walk per _STALENESS_CHECK_MIN_INTERVAL_S.
        A single HTTP request typically triggers many _ensure_index() calls
        down different code paths; without this gate each one would walk disk.
        """
        if self._metadata_cache is None:
            return
        now = time.monotonic()
        if now - self._last_staleness_check < _STALENESS_CHECK_MIN_INTERVAL_S:
            return
        self._last_staleness_check = now
        if self._scan_disk_mtimes() == self._indexed_mtimes:
            return
        # Release the lock before _build_index reacquires it — threading.Lock
        # is non-reentrant. A concurrent rebuild racing past this clear is
        # harmless: worst case is one extra rebuild.
        with self._build_lock:
            if self._metadata_cache is not None:
                self._metadata_cache = None
                self._index = {}

    def _scan_disk_mtimes(self) -> dict[str, int]:
        """Return {filepath_str: mtime_ns} for every currently-discoverable session file."""
        return {
            str(fpath): mtime
            for _parser, fpath, mtime in self._walk_session_files()
            if mtime is not None
        }

    def _walk_session_files(self) -> Iterator[tuple[BaseParser, Path, int | None]]:
        """Iterate (parser, filepath, mtime_ns) for all session files on disk.

        mtime is None when the file vanished between rglob and stat.
        """
        for parser in self._parsers:
            data_dir = self._data_dirs.get(parser)
            if not data_dir or not data_dir.exists():
                continue
            for filepath in parser.discover_session_files(data_dir):
                try:
                    mtime = filepath.stat().st_mtime_ns
                except OSError:
                    mtime = None
                yield parser, filepath, mtime

    def _build_index(self) -> None:
        """Build metadata index from all agent data directories.

        Uses a persistent JSON cache (~/.vibelens/session_index.json) to
        skip full rebuilds when files haven't changed. Thread-safe: if
        another thread is already building, this blocks until it finishes
        and reuses the result.
        """
        with self._build_lock:
            if self._metadata_cache is not None:
                return
            # Snapshot mtimes for every discovered file, including ones that
            # later get dropped as empty/invalid — otherwise _invalidate_if_stale
            # would see them as "new" on every call and thrash.
            self._index = {}
            mtimes: dict[str, int] = {}
            for parser, fpath, mtime in self._walk_session_files():
                sid = _extract_session_id(fpath, parser.AGENT_TYPE)
                self._index[sid] = (fpath, parser)
                if mtime is not None:
                    mtimes[str(fpath)] = mtime
            if not self._try_load_from_cache():
                self._full_rebuild()
            self._indexed_mtimes = mtimes
            self._last_staleness_check = time.monotonic()

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

        cached_stats: dict[str, list[int]] = _coerce_stats(cache.get("file_mtimes", {}))
        cached_entries: dict[str, dict] = cache.get("entries", {})
        cached_path_map: dict[str, str] = cache.get("path_to_session_id", {})
        cached_dropped: dict[str, list[int]] = _coerce_stats(cache.get("dropped_paths", {}))

        # Remap before partitioning so cached real session_ids line up with _index.
        self._remap_index(cached_path_map)

        partition, fresh_dropped, current_stats = _partition_files(
            self._index, cached_stats, cached_dropped
        )

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
        fresh_dropped: dict[str, list[int]],
    ) -> None:
        """Re-parse only changed/new files; hydrate the rest from cache."""
        # Hydrate unchanged entries from cache.
        self._metadata_cache = {}
        for sid in partition.unchanged:
            if sid in cached_entries:
                meta = cached_entries[sid]
                meta["filepath"] = str(self._index[sid][0])
                self._metadata_cache[sid] = meta

        # Re-parse changed + new. Both go through parser.parse in
        # _enrich; we no longer try to do a fast-scanner incremental on
        # appended files because the dashboard needs len(steps) truth and
        # that cannot be merged from a delta without re-running parser
        # merge logic on the full file.
        only_paths = {str(fpath) for fpath, _p in partition.changed.values()} | {
            str(fpath) for fpath, _p in partition.new.values()
        }

        new_dropped: dict[str, list[int]] = {}
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
                    st = fpath.stat()
                    new_dropped[str(fpath)] = [st.st_mtime_ns, st.st_size]
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

        After the initial walk, _index uses filename-based keys. Some sessions
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
        # paths to match what the discovery walk will produce on next startup.
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
        dropped_paths_dict: dict[str, list[int]] = {}
        for fpath in dropped_paths:
            try:
                st = fpath.stat()
                dropped_paths_dict[str(fpath)] = [st.st_mtime_ns, st.st_size]
            except OSError:
                continue
        save_cache(
            self._metadata_cache,
            pre_rebuild_mtimes,
            continuation_map={},
            path_to_session_id=path_to_session_id,
            dropped_paths=dropped_paths_dict,
        )


def _enrich_skeleton_metrics(
    trajectories: list[Trajectory],
    file_index: dict[str, tuple[Path, BaseParser]],
) -> None:
    """Replace skeleton final_metrics with parser-computed truth.

    The skeleton path (``parser.parse_skeleton_for_file``) emits placeholder
    metrics — ``total_steps`` is ``None``, no ``daily_breakdown``. To match
    the dashboard's ``messages == len(traj.steps)`` contract we re-parse
    each file through the full parser and adopt its ``final_metrics``,
    which ``helpers.compute_final_metrics`` populates from real per-step
    aggregations (``total_steps = len(steps)``, ``daily_breakdown.messages``
    summing to the same).

    Cost: ~25-30 ms per file (1480 sessions ≈ 30 s on cold start). This
    replaces the previous fast-scanner path (~3 ms per file) — accuracy
    over speed because the fast scanner counted JSONL lines, not steps,
    and produced a ~2-7× over-count for active Claude sessions.

    Parallelism notes (carried over from the fast-scanner era):

    * ``ThreadPoolExecutor`` does not help — most per-file work after the
      orjson decode holds the GIL.
    * ``ProcessPoolExecutor`` gives a real ~3× speedup but adds spawn cost
      and breaks for stdin-launched processes (no re-importable
      ``__main__``); not worth the operational complexity here.
    """
    enriched = 0
    for traj in trajectories:
        entry = file_index.get(traj.session_id)
        if not entry:
            continue
        fpath, parser = entry
        try:
            full_trajs = parser.parse(fpath)
        except Exception:
            logger.warning(
                "Failed to full-parse %s for enrichment, skipping", fpath, exc_info=True
            )
            continue
        if not full_trajs:
            continue
        main = full_trajs[0]
        if main.final_metrics is not None:
            traj.final_metrics = main.final_metrics
        if (
            main.agent
            and main.agent.model_name
            and traj.agent
            and not traj.agent.model_name
        ):
            traj.agent.model_name = main.agent.model_name
        enriched += 1

    if enriched:
        logger.info("Enriched %d skeletons via parser.parse", enriched)

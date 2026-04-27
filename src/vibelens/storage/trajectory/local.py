"""Multi-agent local session store returning Trajectory objects.

Implements TrajectoryStore by reading sessions from all local agent data
directories. Each parser's ``discover_sessions`` is the single source of
truth for "what sessions exist, where they live, and when they last changed".
LocalStore is format-agnostic — it never knows whether a file holds one
session or many.
"""

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from vibelens.ingest.index_builder import build_session_index
from vibelens.ingest.index_cache import load_cache, save_cache
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
    """Result of comparing the current session index against the persisted cache."""

    unchanged: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    changed: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    new: dict[str, tuple[Path, "BaseParser"]] = field(default_factory=dict)
    removed_sids: set[str] = field(default_factory=set)


def _coerce_stats(raw: dict) -> dict[str, list[int]]:
    """Coerce a cached stat map into the canonical ``[mtime_ns, size]`` shape.

    Used only for ``dropped_paths`` (file-keyed). Entries that can't be
    coerced are dropped.
    """
    out: dict[str, list[int]] = {}
    for path_str, value in raw.items():
        if isinstance(value, list) and len(value) == 2:
            try:
                out[path_str] = [int(value[0]), int(value[1])]
            except (TypeError, ValueError):
                continue
    return out


def _partition_sessions(
    file_index: dict[str, tuple[Path, BaseParser]],
    current_mtimes: dict[str, int],
    cached_entries: dict[str, dict],
) -> CachePartition:
    """Compare current sessions against cached entries by per-session mtime.

    Cache stores ``session_mtime_ns`` and ``filepath`` inside each entry.
    A session is unchanged when both match; changed when either differs;
    new when not in cache at all.

    Args:
        file_index: Current session_id -> (filepath, parser) map.
        current_mtimes: session_id -> mtime_ns from this discovery walk.
        cached_entries: session_id -> cached metadata dict.

    Returns:
        CachePartition with unchanged/changed/new dicts plus removed_sids.
    """
    unchanged: dict[str, tuple[Path, BaseParser]] = {}
    changed: dict[str, tuple[Path, BaseParser]] = {}
    new: dict[str, tuple[Path, BaseParser]] = {}

    for sid, (fpath, parser) in file_index.items():
        cached = cached_entries.get(sid)
        if cached is None:
            new[sid] = (fpath, parser)
            continue
        cached_mtime = cached.get("session_mtime_ns")
        cached_path = cached.get("filepath")
        current_mtime = current_mtimes.get(sid)
        if cached_path != str(fpath) or cached_mtime != current_mtime:
            changed[sid] = (fpath, parser)
        else:
            unchanged[sid] = (fpath, parser)

    removed_sids = set(cached_entries) - set(file_index)
    return CachePartition(unchanged=unchanged, changed=changed, new=new, removed_sids=removed_sids)


class LocalTrajectoryStore(BaseTrajectoryStore):
    """Read sessions from all local agent data directories.

    Uses LOCAL_PARSER_CLASSES to instantiate parsers. Each parser's
    ``discover_sessions`` declares the sessions it owns; LocalStore merges
    them into a single index without knowing format-specific details
    (single- vs multi-session-per-file, filename vs SQL session_ids).

    Inherits concrete read methods (list_metadata, load, exists, etc.)
    from BaseTrajectoryStore. Only overrides initialize, save, and
    _build_index.
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
        because _build_index will revalidate it via per-session mtime checks.
        If all sessions are unchanged, the cache is restored directly;
        otherwise a partial/full rebuild runs.
        """
        super().invalidate_index()
        self._indexed_mtimes = {}
        self._last_staleness_check = 0.0

    def _invalidate_if_stale(self) -> None:
        """Drop the in-memory index when any session's mtime drifted.

        Rate-limited: at most one parser walk per _STALENESS_CHECK_MIN_INTERVAL_S.
        Per-session mtime tracking means OpenCode/Kilo touching a single row
        in their SQLite DB is detected without re-parsing the whole file.
        """
        if self._metadata_cache is None:
            return
        now = time.monotonic()
        if now - self._last_staleness_check < _STALENESS_CHECK_MIN_INTERVAL_S:
            return
        self._last_staleness_check = now
        if self._scan_session_mtimes() == self._indexed_mtimes:
            return
        # Release the lock before _build_index reacquires it — threading.Lock
        # is non-reentrant. A concurrent rebuild racing past this clear is
        # harmless: worst case is one extra rebuild.
        with self._build_lock:
            if self._metadata_cache is not None:
                self._metadata_cache = None
                self._index = {}

    def _scan_session_mtimes(self) -> dict[str, int]:
        """Return {session_id: mtime_ns} for every currently-discoverable session."""
        return {sid: mtime for _parser, _path, sid, mtime in self._walk_session_files()}

    def _walk_session_files(self) -> Iterator[tuple[BaseParser, Path, str, int]]:
        """Yield ``(parser, file_path, session_id, mtime_ns)`` per session.

        Session_id and mtime_ns come from each parser's ``discover_sessions``
        — for single-session-per-file formats this is the file's stem +
        ``Path.stat().st_mtime_ns``; for multi-session-per-file formats it's
        per-row data from the parser's native storage (e.g. SQLite ``id`` and
        ``time_updated`` columns).
        """
        for parser in self._parsers:
            data_dir = self._data_dirs.get(parser)
            if not data_dir or not data_dir.exists():
                continue
            for entry in parser.discover_sessions(data_dir):
                yield parser, entry.path, entry.session_id, entry.mtime_ns

    def _build_index(self) -> None:
        """Build metadata index from all agent data directories.

        Uses a persistent JSON cache (~/.vibelens/session_index.json) to
        skip full rebuilds when sessions haven't changed. Thread-safe: if
        another thread is already building, this blocks until it finishes
        and reuses the result.
        """
        with self._build_lock:
            if self._metadata_cache is not None:
                return
            self._index = {}
            mtimes_by_sid: dict[str, int] = {}
            for parser, fpath, sid, mtime in self._walk_session_files():
                if sid in self._index:
                    logger.warning(
                        "Session id collision: %r already mapped to %s; "
                        "dropping new entry from %s. Add a namespace prefix to "
                        "the parser to avoid this.",
                        sid,
                        self._index[sid][0],
                        fpath,
                    )
                    continue
                self._index[sid] = (fpath, parser)
                mtimes_by_sid[sid] = mtime
            if not self._try_load_from_cache(mtimes_by_sid):
                self._full_rebuild(mtimes_by_sid)
            self._indexed_mtimes = mtimes_by_sid
            self._last_staleness_check = time.monotonic()

    def _try_load_from_cache(self, current_mtimes: dict[str, int]) -> bool:
        """Load index from persistent cache, taking a partial-rebuild path when possible.

        Fast path: every session has the same mtime as cache → hydrate
        ``_metadata_cache`` and return.

        Partial path: a subset of sessions changed/added/removed → re-parse
        only those, hydrate the rest from cache, persist updated cache.

        Returns False (falls through to ``_full_rebuild``) when the cache is
        missing, version-mismatched, or the partial rebuild itself raises.
        """
        cache = load_cache()
        if not cache:
            return False

        cached_entries: dict[str, dict] = cache.get("entries", {})
        cached_dropped: dict[str, list[int]] = _coerce_stats(cache.get("dropped_paths", {}))

        partition = _partition_sessions(self._index, current_mtimes, cached_entries)

        # Drop dropped-paths from _index — they should not appear as live sessions
        # if they're still unchanged on disk.
        if cached_dropped:
            for sid in [
                s for s, (fpath, _p) in self._index.items() if str(fpath) in cached_dropped
            ]:
                try:
                    st = self._index[sid][0].stat()
                except OSError:
                    continue
                if cached_dropped[str(self._index[sid][0])] == [st.st_mtime_ns, st.st_size]:
                    self._index.pop(sid, None)
                    current_mtimes.pop(sid, None)
                    partition.unchanged.pop(sid, None)
                    partition.changed.pop(sid, None)
                    partition.new.pop(sid, None)

        is_fast_path = not partition.changed and not partition.new and not partition.removed_sids
        if is_fast_path:
            self._metadata_cache = {}
            for sid in self._index:
                if sid in cached_entries:
                    meta = dict(cached_entries[sid])
                    meta["filepath"] = str(self._index[sid][0])
                    meta["session_mtime_ns"] = current_mtimes.get(sid)
                    self._metadata_cache[sid] = meta
            logger.info("Loaded %d sessions from index cache", len(self._metadata_cache))
            return True

        try:
            self._partial_rebuild(partition, cached_entries, cached_dropped, current_mtimes)
        except Exception:
            logger.warning("Partial rebuild failed, falling back to full rebuild", exc_info=True)
            return False
        return True

    def _partial_rebuild(
        self,
        partition: CachePartition,
        cached_entries: dict[str, dict],
        cached_dropped: dict[str, list[int]],
        current_mtimes: dict[str, int],
    ) -> None:
        """Re-parse only changed/new sessions via ``parse_session``; hydrate the rest.

        Uses per-sid ``parse_session(path, sid)`` rather than the
        skeleton + enrichment pipeline. For multi-session-per-file
        formats (OpenCode, Kilo) this is the win: the SQL-filtered
        load touches only the changed session's rows instead of
        re-reading the whole DB.
        """
        self._metadata_cache = {}
        for sid in partition.unchanged:
            if sid in cached_entries:
                meta = dict(cached_entries[sid])
                meta["filepath"] = str(self._index[sid][0])
                meta["session_mtime_ns"] = current_mtimes.get(sid)
                self._metadata_cache[sid] = meta

        new_dropped: dict[str, list[int]] = {}
        # Group dirty sids by (path, parser) so we open each file once even
        # when multi-session formats have several sids changed in the same db.
        dirty: dict[str, tuple[Path, BaseParser]] = {**partition.changed, **partition.new}
        for sid, (fpath, parser) in dirty.items():
            try:
                trajectories = parser.parse_session(fpath, sid)
            except Exception:
                logger.warning("parse_session(%s) raised, treating as dropped", sid, exc_info=True)
                trajectories = None
            if not trajectories:
                self._index.pop(sid, None)
                try:
                    st = fpath.stat()
                    new_dropped[str(fpath)] = [st.st_mtime_ns, st.st_size]
                except OSError:
                    pass
                continue
            main = next((t for t in trajectories if t.session_id == sid), None)
            if main is None or not main.first_message:
                self._index.pop(sid, None)
                continue
            for t in trajectories:
                entry = self._index.get(t.session_id)
                if not entry:
                    continue
                meta = t.model_dump(exclude={"steps"}, mode="json")
                meta["filepath"] = str(entry[0])
                meta["session_mtime_ns"] = current_mtimes.get(t.session_id)
                self._metadata_cache[t.session_id] = meta

        for sid in partition.removed_sids:
            self._metadata_cache.pop(sid, None)
            self._index.pop(sid, None)

        merged_dropped = {**cached_dropped, **new_dropped}
        save_cache(self._metadata_cache, dropped_paths=merged_dropped)

        logger.info(
            "Loaded %d sessions from index cache "
            "(%d unchanged, %d added, %d re-parsed, %d removed)",
            len(self._metadata_cache),
            len(partition.unchanged),
            len(partition.new),
            len(partition.changed),
            len(partition.removed_sids),
        )

    def _full_rebuild(self, current_mtimes: dict[str, int]) -> None:
        """Full index rebuild: parse all sessions, write cache."""
        trajectories, dropped_paths = build_session_index(self._index, self._data_dirs)

        # Enrich skeletons with parser-truth metrics for dashboard stats.
        _enrich_skeleton_metrics(trajectories, self._index)

        self._metadata_cache = {}
        for t in trajectories:
            meta = t.model_dump(exclude={"steps"}, mode="json")
            entry = self._index.get(t.session_id)
            if entry:
                meta["filepath"] = str(entry[0])
            meta["session_mtime_ns"] = current_mtimes.get(t.session_id)
            self._metadata_cache[t.session_id] = meta
        logger.info(
            "Indexed %d sessions across %d agents", len(self._metadata_cache), len(self._parsers)
        )

        dropped_paths_dict: dict[str, list[int]] = {}
        for fpath in dropped_paths:
            try:
                st = fpath.stat()
                dropped_paths_dict[str(fpath)] = [st.st_mtime_ns, st.st_size]
            except OSError:
                continue
        save_cache(self._metadata_cache, dropped_paths=dropped_paths_dict)


def _enrich_skeleton_metrics(
    trajectories: list[Trajectory], file_index: dict[str, tuple[Path, BaseParser]]
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
    # Cache parse results per file path. Multi-session files (opencode.db,
    # kilo.db) share one path across many skeletons; without this cache we'd
    # re-parse the whole db once per skeleton.
    parse_cache: dict[Path, dict[str, Trajectory]] = {}
    enriched = 0
    for traj in trajectories:
        entry = file_index.get(traj.session_id)
        if not entry:
            continue
        fpath, parser = entry
        if fpath not in parse_cache:
            try:
                full_trajs = parser.parse(fpath)
            except Exception:
                logger.warning(
                    "Failed to full-parse %s for enrichment, skipping", fpath, exc_info=True
                )
                parse_cache[fpath] = {}
                continue
            parse_cache[fpath] = {t.session_id: t for t in full_trajs}
        # Match by session_id when the file holds multiple; fall back to the
        # first parsed trajectory for legacy single-session formats whose
        # skeleton sid was filename-derived rather than the real id.
        full_by_id = parse_cache[fpath]
        if not full_by_id:
            continue
        main = full_by_id.get(traj.session_id) or next(iter(full_by_id.values()))
        if main.final_metrics is not None:
            traj.final_metrics = main.final_metrics
        if main.agent and main.agent.model_name and traj.agent and not traj.agent.model_name:
            traj.agent.model_name = main.agent.model_name
        enriched += 1

    if enriched:
        logger.info("Enriched %d skeletons via parser.parse", enriched)

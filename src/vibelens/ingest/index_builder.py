"""Session index builder for LocalStore.

Builds skeleton trajectories from parser indexes with polymorphic dispatch,
plus deduplication/validation. Session_ids are authoritative — they come
from each parser's ``discover_sessions`` and never need remapping here.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import Trajectory, TrajectoryRef
from vibelens.utils import get_logger

logger = get_logger(__name__)

# Per-file skeleton parsing is I/O-bound; cap thread count to avoid
# thrashing the disk scheduler.
INDEX_PARSE_WORKERS = min(8, (os.cpu_count() or 4))


def build_session_index(
    file_index: dict[str, tuple[Path, BaseParser]], data_dirs: dict[BaseParser, Path]
) -> tuple[list[Trajectory], list[Path]]:
    """Build validated, deduplicated skeleton trajectories from all agents.

    Each parser's ``parse_session_index`` method is called first for a fast
    index path. If it returns None, falls back to per-file skeleton parsing.

    Args:
        file_index: Mutable session_id -> (filepath, parser) map. May be
            mutated by ``_dedup_and_validate`` to drop empty sessions.
        data_dirs: Parser -> resolved data directory for index lookups.

    Returns:
        Tuple of (validated skeleton Trajectory list, list of dropped file
        paths from empty/invalid sessions).
    """
    parsers = list({parser for _, parser in file_index.values()})
    silent_drops: list[Path] = []
    skeletons = _collect_all_skeletons(parsers, file_index, data_dirs, dropped_sink=silent_drops)
    valid, dropped_paths = _dedup_and_validate(skeletons, file_index)
    dropped_paths = dropped_paths + silent_drops
    # TODO(perf-spec 2026-04-18): re-enable once _enrich_continuation_refs
    # bug is fixed (it currently misses some chains). The partial-rebuild
    # path in storage/trajectory/local.py also assumes this is disabled —
    # restoring it requires reasoning about cross-file chain invalidation.
    # _enrich_continuation_refs(valid, file_index)
    return valid, dropped_paths


def _collect_all_skeletons(
    parsers: list[BaseParser],
    file_index: dict[str, tuple[Path, BaseParser]],
    data_dirs: dict[BaseParser, Path],
    dropped_sink: list[Path] | None = None,
) -> list[Trajectory]:
    """Collect skeleton trajectories from all parsers using polymorphic dispatch.

    When a parser's fast index (e.g. history.jsonl) exists but doesn't
    cover all discovered sessions, orphans are parsed individually as a
    fallback. This handles sessions created by Claude Code Desktop or
    other tools that don't write to the index file.

    Args:
        parsers: Parser instances to dispatch over.
        file_index: Mutable session_id -> (path, parser) map.
        data_dirs: Parser -> data directory map.
        dropped_sink: Optional list to receive paths of files that produced
            no parseable trajectory.
    """
    all_trajectories: list[Trajectory] = []

    for parser in parsers:
        data_dir = data_dirs.get(parser)
        if data_dir:
            skeletons = parser.parse_session_index(data_dir)
            if skeletons is not None:
                reconciled = _reconcile_index_skeletons(parser, skeletons, file_index)
                all_trajectories.extend(reconciled)
                indexed_ids = {t.session_id for t in reconciled}
                orphaned = _build_orphaned_skeletons(
                    parser, file_index, indexed_ids, dropped_sink=dropped_sink
                )
                if orphaned:
                    logger.info(
                        "Recovered %d sessions not in %s index via file parsing",
                        len(orphaned),
                        parser.AGENT_TYPE.value,
                    )
                    all_trajectories.extend(orphaned)
                continue
        all_trajectories.extend(
            _build_file_parse_skeletons(parser, file_index, dropped_sink=dropped_sink)
        )

    return all_trajectories


def _build_orphaned_skeletons(
    parser: BaseParser,
    file_index: dict[str, tuple[Path, BaseParser]],
    indexed_ids: set[str],
    dropped_sink: list[Path] | None = None,
) -> list[Trajectory]:
    """Parse session files not covered by the parser's fast index.

    Deduplicates by file path so a multi-session-per-file format doesn't
    re-parse the same db once per orphan sid. Each path is opened once
    via ``parse_skeletons_for_file`` (plural) which yields one skeleton
    per session.

    Args:
        parser: The parser instance to use.
        file_index: Mutable session file index (mutated to drop empty sessions).
        indexed_ids: Session IDs already covered by the fast index.
        dropped_sink: Optional list to receive paths of files that produced
            no parseable trajectory. Lets the caller persist them so the
            next startup doesn't retry.

    Returns:
        Skeleton trajectories for orphaned sessions.
    """
    orphan_paths: dict[str, list[str]] = {}
    for sid, (fpath, p) in file_index.items():
        if p is parser and sid not in indexed_ids:
            orphan_paths.setdefault(str(fpath), []).append(sid)
    if not orphan_paths:
        return []

    def _scan(path_str: str) -> tuple[str, list[Trajectory]]:
        try:
            return path_str, parser.parse_skeletons_for_file(Path(path_str))
        except Exception:
            logger.debug("Failed to parse orphaned file %s, skipping", path_str)
            return path_str, []

    with ThreadPoolExecutor(max_workers=INDEX_PARSE_WORKERS) as pool:
        scanned = list(pool.map(_scan, orphan_paths.keys()))

    result: list[Trajectory] = []
    for path_str, skels in scanned:
        if not skels:
            for sid in orphan_paths[path_str]:
                file_index.pop(sid, None)
            if dropped_sink is not None:
                dropped_sink.append(Path(path_str))
            continue
        result.extend(skels)
    return result


def _reconcile_index_skeletons(
    parser: BaseParser, skeletons: list[Trajectory], file_index: dict[str, tuple[Path, BaseParser]]
) -> list[Trajectory]:
    """Filter skeletons to those whose session_id is in file_index for this parser.

    Session_ids come from ``parser.discover_sessions`` (the cache key) and
    must match what the parser's fast index returns. Mismatches are dropped
    silently — discovery is the single source of truth.
    """
    return [
        t for t in skeletons if t.session_id in file_index and file_index[t.session_id][1] is parser
    ]


def _build_file_parse_skeletons(
    parser: BaseParser,
    file_index: dict[str, tuple[Path, BaseParser]],
    dropped_sink: list[Path] | None = None,
) -> list[Trajectory]:
    """Build skeletons by lightly parsing each session file in parallel.

    Dispatches to ``parse_skeletons_for_file`` (plural) so multi-session
    formats yield N skeletons per file in one pass. Files are processed
    in a thread pool because the work is dominated by I/O.

    Args:
        parser: The parser instance to use.
        file_index: Session file index. Empty sessions are dropped from it
            and recorded in dropped_sink.
        dropped_sink: Optional list to receive paths of files that produced
            no parseable trajectory.

    Returns:
        Skeleton trajectories for all parseable files.
    """
    paths_to_sids: dict[str, list[str]] = {}
    for sid, (fpath, p) in file_index.items():
        if p is parser:
            paths_to_sids.setdefault(str(fpath), []).append(sid)
    if not paths_to_sids:
        return []

    def _scan(path_str: str) -> tuple[str, list[Trajectory]]:
        try:
            return path_str, parser.parse_skeletons_for_file(Path(path_str))
        except Exception:
            logger.warning("Failed to index %s, skipping", path_str)
            return path_str, []

    with ThreadPoolExecutor(max_workers=INDEX_PARSE_WORKERS) as pool:
        scanned = list(pool.map(_scan, paths_to_sids.keys()))

    result: list[Trajectory] = []
    for path_str, skels in scanned:
        if not skels:
            for sid in paths_to_sids[path_str]:
                file_index.pop(sid, None)
            if dropped_sink is not None:
                dropped_sink.append(Path(path_str))
            continue
        result.extend(skels)
    return result


def _dedup_and_validate(
    skeletons: list[Trajectory], file_index: dict[str, tuple[Path, BaseParser]]
) -> tuple[list[Trajectory], list[Path]]:
    """Remove duplicates and drop sessions with no first_message.

    Empty/corrupt files that exist on disk but have no parseable content
    are removed from file_index so they don't show as 404s in the sidebar.

    Args:
        skeletons: Raw skeleton trajectory list (may contain dupes).
        file_index: Mutable session file index for pruning empty entries.

    Returns:
        Tuple of (deduplicated valid skeletons, list of dropped file paths).
    """
    seen_ids: set[str] = set()
    valid: list[Trajectory] = []
    dropped_paths: list[Path] = []

    for traj in skeletons:
        if traj.session_id in seen_ids:
            continue
        seen_ids.add(traj.session_id)
        if not traj.first_message:
            entry = file_index.pop(traj.session_id, None)
            if entry is not None:
                dropped_paths.append(entry[0])
            continue
        valid.append(traj)

    if dropped_paths:
        logger.info("Dropped %d empty sessions from index", len(dropped_paths))
    return valid, dropped_paths


def _enrich_continuation_refs(
    skeletons: list[Trajectory], file_index: dict[str, tuple[Path, BaseParser]]
) -> None:
    """Scan Claude Code JSONL files for continuation refs and back-fill skeletons.

    For each Claude Code session file, checks if it contains entries from
    multiple sessionIds (indicating a continuation). Builds bidirectional
    maps and sets prev_trajectory_ref / next_trajectory_ref on the
    cached skeleton objects.

    Args:
        skeletons: Validated skeleton trajectories to enrich in-place.
        file_index: Session file index for locating JSONL files.
    """
    claude_entries = {
        sid: fpath
        for sid, (fpath, parser) in file_index.items()
        if parser.AGENT_TYPE == AgentType.CLAUDE
    }
    if not claude_entries:
        return

    # continuation_map: current session -> previous session it continues from
    continuation_map: dict[str, str] = {}
    for session_id, filepath in claude_entries.items():
        prev_id = _scan_continuation_session_id(filepath, session_id)
        if prev_id and prev_id in claude_entries:
            continuation_map[session_id] = prev_id

    if not continuation_map:
        return

    # Build reverse map: previous session -> next session that continues it
    continued_by: dict[str, str] = {prev: curr for curr, prev in continuation_map.items()}

    # Apply refs to skeleton objects
    skeleton_by_id = {t.session_id: t for t in skeletons}
    linked = 0

    for current_id, prev_id in continuation_map.items():
        current_traj = skeleton_by_id.get(current_id)
        if current_traj and not current_traj.prev_trajectory_ref:
            current_traj.prev_trajectory_ref = TrajectoryRef(session_id=prev_id)
            linked += 1

    for prev_id, next_id in continued_by.items():
        prev_traj = skeleton_by_id.get(prev_id)
        if prev_traj and not prev_traj.next_trajectory_ref:
            prev_traj.next_trajectory_ref = TrajectoryRef(session_id=next_id)

    if linked:
        logger.info("Enriched %d continuation chain links", linked)


_SESSION_ID_PATTERN = re.compile(r'"sessionId"\s*:\s*"([^"]+)"')


def _scan_continuation_session_id(filepath: Path, expected_id: str) -> str | None:
    """Check if a JSONL file contains entries from multiple sessions.

    Claude Code continuation sessions embed the tail of the previous
    conversation at the start of the file. These entries carry the
    previous session's sessionId. This function uses a fast regex scan
    instead of json.loads() to extract sessionId values.

    Args:
        filepath: Path to the Claude Code JSONL session file.
        expected_id: The session ID derived from the filename.

    Returns:
        The previous sessionId if found, None otherwise.
    """
    seen_ids: set[str] = set()
    try:
        with open(filepath, encoding="utf-8") as fh:
            for line in fh:
                match = _SESSION_ID_PATTERN.search(line)
                if not match:
                    continue
                seen_ids.add(match.group(1))
                if len(seen_ids) >= 2:
                    break
    except OSError:
        return None

    if len(seen_ids) < 2:
        return None

    # The "other" ID (not matching the filename-based expected_id) is the previous session
    seen_ids.discard(expected_id)
    if seen_ids:
        return seen_ids.pop()

    return None

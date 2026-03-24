"""Session index builder for LocalStore.

Builds skeleton trajectories from parser indexes with polymorphic dispatch,
plus deduplication/validation and continuation chain enrichment.
"""

import json
from pathlib import Path

from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import Trajectory, TrajectoryRef
from vibelens.utils import get_logger

logger = get_logger(__name__)


def build_session_index(
    file_index: dict[str, tuple[Path, BaseParser]],
    data_dirs: dict[BaseParser, Path],
) -> list[Trajectory]:
    """Build validated, deduplicated skeleton trajectories from all agents.

    Each parser's ``parse_session_index`` method is called first for a fast
    index path. If it returns None, falls back to full-file parsing.

    Mutates file_index to remap session IDs when parsers produce
    different IDs than filename-based keys.

    Args:
        file_index: Mutable session_id -> (filepath, parser) map.
        data_dirs: Parser -> resolved data directory for index lookups.

    Returns:
        Deduplicated skeleton Trajectory list (no steps).
    """
    parsers = list({parser for _, parser in file_index.values()})
    skeletons = _collect_all_skeletons(parsers, file_index, data_dirs)
    valid = _dedup_and_validate(skeletons, file_index)
    _enrich_continuation_refs(valid, file_index)
    return valid


def _collect_all_skeletons(
    parsers: list[BaseParser],
    file_index: dict[str, tuple[Path, BaseParser]],
    data_dirs: dict[BaseParser, Path],
) -> list[Trajectory]:
    """Collect skeleton trajectories from all parsers using polymorphic dispatch."""
    all_trajectories: list[Trajectory] = []

    for parser in parsers:
        data_dir = data_dirs.get(parser)
        if data_dir:
            skeletons = parser.parse_session_index(data_dir)
            if skeletons is not None:
                all_trajectories.extend(_reconcile_index_skeletons(parser, skeletons, file_index))
                continue
        all_trajectories.extend(_build_file_parse_skeletons(parser, file_index))

    return all_trajectories


def _reconcile_index_skeletons(
    parser: BaseParser, skeletons: list[Trajectory], file_index: dict[str, tuple[Path, BaseParser]]
) -> list[Trajectory]:
    """Match index skeletons to file_index entries, remapping IDs when needed.

    Handles two matching strategies:
    1. Direct session_id match (Claude Code)
    2. Path-based match via extra.rollout_path (Codex), with ID remapping

    Args:
        parser: Parser that produced the skeletons.
        skeletons: Skeleton trajectories from the parser's fast index.
        file_index: Mutable session file index for ID remapping.

    Returns:
        Skeleton trajectories that match known session files.
    """
    path_to_old_sid = {str(fpath): sid for sid, (fpath, p) in file_index.items() if p is parser}

    result: list[Trajectory] = []
    for traj in skeletons:
        # Direct match by session_id
        if traj.session_id in file_index and file_index[traj.session_id][1] is parser:
            result.append(traj)
            continue

        # Path-based match (Codex rollout_path)
        rollout_path = (traj.extra or {}).get("rollout_path", "")
        old_sid = path_to_old_sid.get(rollout_path)
        if not old_sid:
            continue
        # Remap file_index from filename-based key to real session_id
        if traj.session_id != old_sid:
            entry = file_index.pop(old_sid, None)
            if entry:
                file_index[traj.session_id] = entry
        result.append(traj)

    return result


def _build_file_parse_skeletons(
    parser: BaseParser, file_index: dict[str, tuple[Path, BaseParser]]
) -> list[Trajectory]:
    """Build skeletons by fully parsing each session file.

    Collects entries first to avoid mutating file_index during iteration.
    Remaps session IDs when the parser produces different IDs than
    filename-based keys.

    Args:
        parser: The parser instance to use.
        file_index: Mutable session file index for ID remapping.

    Returns:
        Skeleton trajectories (steps cleared) for all parseable files.
    """
    parser_entries = [(sid, fpath, p) for sid, (fpath, p) in file_index.items() if p is parser]

    result: list[Trajectory] = []
    for old_sid, fpath, p in parser_entries:
        try:
            trajs = p.parse_file(fpath)
            if not trajs:
                continue
            main = trajs[0]
            # Remap: parser may produce a session_id different from filename key
            real_sid = main.session_id
            if real_sid != old_sid:
                file_index.pop(old_sid, None)
                file_index[real_sid] = (fpath, p)
            main.steps = []
            result.append(main)
        except Exception:
            logger.warning("Failed to index %s, skipping", fpath)

    return result


def _dedup_and_validate(
    skeletons: list[Trajectory], file_index: dict[str, tuple[Path, BaseParser]]
) -> list[Trajectory]:
    """Remove duplicates and drop sessions with no first_message.

    Empty/corrupt files that exist on disk but have no parseable content
    are removed from file_index so they don't show as 404s in the sidebar.

    Args:
        skeletons: Raw skeleton trajectory list (may contain dupes).
        file_index: Mutable session file index for pruning empty entries.

    Returns:
        Deduplicated, validated skeleton list.
    """
    seen_ids: set[str] = set()
    valid: list[Trajectory] = []
    dropped = 0

    for traj in skeletons:
        if traj.session_id in seen_ids:
            continue
        seen_ids.add(traj.session_id)
        if not traj.first_message:
            file_index.pop(traj.session_id, None)
            dropped += 1
            continue
        valid.append(traj)

    if dropped:
        logger.info("Dropped %d empty sessions from index", dropped)
    return valid


def _enrich_continuation_refs(
    skeletons: list[Trajectory], file_index: dict[str, tuple[Path, BaseParser]]
) -> None:
    """Scan Claude Code JSONL files for continuation refs and back-fill skeletons.

    For each Claude Code session file, checks if it contains entries from
    multiple sessionIds (indicating a continuation). Builds bidirectional
    maps and sets last_trajectory_ref / continued_trajectory_ref on the
    cached skeleton objects.

    Args:
        skeletons: Validated skeleton trajectories to enrich in-place.
        file_index: Session file index for locating JSONL files.
    """
    claude_entries = {
        sid: fpath
        for sid, (fpath, parser) in file_index.items()
        if parser.AGENT_TYPE == AgentType.CLAUDE_CODE
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
        if current_traj and not current_traj.last_trajectory_ref:
            current_traj.last_trajectory_ref = TrajectoryRef(session_id=prev_id)
            linked += 1

    for prev_id, next_id in continued_by.items():
        prev_traj = skeleton_by_id.get(prev_id)
        if prev_traj and not prev_traj.continued_trajectory_ref:
            prev_traj.continued_trajectory_ref = TrajectoryRef(session_id=next_id)

    if linked:
        logger.info("Enriched %d continuation chain links", linked)


def _scan_continuation_session_id(filepath: Path, expected_id: str) -> str | None:
    """Check if a JSONL file contains entries from multiple sessions.

    Claude Code continuation sessions embed the tail of the previous
    conversation at the start of the file. These entries carry the
    previous session's sessionId. This function does a fast line-level
    scan to detect the secondary (previous) sessionId.

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
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                sid = entry.get("sessionId")
                if not sid:
                    continue
                seen_ids.add(sid)
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

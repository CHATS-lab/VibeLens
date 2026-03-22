"""Multi-agent local session store returning Trajectory objects.

Implements TrajectoryStore by reading sessions from all local agent data
directories. Discovers parsers via BaseParser.local_parsers(), scans each
parser's data directory for session files, and builds a unified file index
across all agents.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from vibelens.ingest.discovery import discover_session_files
from vibelens.ingest.parsers.base import BaseParser, _import_all_parsers
from vibelens.ingest.parsers.claude_code import ClaudeCodeParser
from vibelens.ingest.parsers.codex import CodexParser
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import Trajectory
from vibelens.storage.base import TrajectoryStore
from vibelens.utils import get_logger

if TYPE_CHECKING:
    from vibelens.config import Settings

logger = get_logger(__name__)

# Maps parser AGENT_NAME to the AgentType enum used by discovery.py.
_AGENT_NAME_TO_TYPE: dict[str, str] = {
    "claude-code": AgentType.CLAUDE_CODE,
    "codex": AgentType.CODEX,
    "gemini": AgentType.GEMINI,
}


def _agent_name_to_type(agent_name: str) -> str | None:
    """Map a parser's AGENT_NAME to an AgentType enum value."""
    return _AGENT_NAME_TO_TYPE.get(agent_name)


def _extract_session_id(filepath: Path, agent_name: str) -> str:
    """Derive a unique session_id from the file path.

    Claude Code uses the filename stem as UUID directly. Other agents
    are prefixed with their agent name to avoid ID collisions.

    Args:
        filepath: Path to the session file.
        agent_name: Parser's AGENT_NAME string.

    Returns:
        Unique session identifier.
    """
    stem = filepath.stem
    if agent_name == "claude-code":
        return stem
    return f"{agent_name}:{stem}"


class LocalStore(TrajectoryStore):
    """Read sessions from all local agent data directories.

    Discovers parsers via BaseParser.local_parsers(), scans each parser's
    data directory for session files using discovery.py, and builds a
    unified file index across all agents. The sidebar index uses
    Claude Code's history.jsonl when available, plus file-based skeleton
    generation for other agents.
    """

    def __init__(self, settings: "Settings | None" = None) -> None:
        _import_all_parsers()
        self._parsers: list[BaseParser] = [cls() for cls in BaseParser.local_parsers()]
        self._index_cache: list[Trajectory] | None = None
        self._file_index: dict[str, tuple[Path, BaseParser]] = {}

        # Allow settings to override default data directories
        if settings:
            dir_overrides: dict[str, Path] = {
                "claude-code": settings.claude_dir,
                "codex": settings.codex_dir,
                "gemini": settings.gemini_dir,
            }
            for parser in self._parsers:
                override = dir_overrides.get(parser.AGENT_NAME)
                if override:
                    parser.LOCAL_DATA_DIR = override

    def initialize(self) -> None:
        """No-op — index is loaded lazily on first access."""

    def list_metadata(self, session_token: str | None = None) -> list[dict]:
        """Return skeleton trajectories as summary dicts (no steps).

        Args:
            session_token: Ignored in self-use mode (single-user).

        Returns:
            Unsorted list of trajectory summary dicts.
        """
        trajectories = self._load_index()
        return [t.model_dump(exclude={"steps"}, mode="json") for t in trajectories]

    def load(self, session_id: str, session_token: str | None = None) -> list[Trajectory] | None:
        """Parse a full session file and return trajectories.

        Looks up the correct parser from the file index so each agent
        format is parsed by its own parser.

        Args:
            session_id: The session identifier to load.
            session_token: Ignored in self-use mode (single-user).

        Returns:
            List of Trajectory objects (main + sub-agents), or None.
        """
        self._load_index()

        entry = self._file_index.get(session_id)
        if not entry:
            return None

        session_file, parser = entry
        trajectories = parser.parse_file(session_file)
        if not trajectories:
            return None

        # Sort: main trajectory first, then sub-agents by timestamp
        main = [t for t in trajectories if not t.parent_trajectory_ref]
        subs = sorted(
            (t for t in trajectories if t.parent_trajectory_ref),
            key=lambda t: t.timestamp or datetime.min,
        )
        return main + subs

    def list_projects(self) -> list[str]:
        """Return all unique project paths from the session index.

        Returns:
            Sorted list of project path strings.
        """
        trajectories = self._load_index()
        return sorted({t.project_path for t in trajectories if t.project_path})

    def _load_index(self) -> list[Trajectory]:
        """Load or return cached skeleton trajectories from all agents."""
        if self._index_cache is not None:
            return self._index_cache

        self._build_file_index()
        all_trajectories: list[Trajectory] = []

        for parser in self._parsers:
            if isinstance(parser, ClaudeCodeParser) and parser.LOCAL_DATA_DIR:
                # Tier 1: Claude Code fast history index
                index_trajs = parser.parse_history_index(parser.LOCAL_DATA_DIR)
                all_trajectories.extend(t for t in index_trajs if t.session_id in self._file_index)
            elif isinstance(parser, CodexParser) and parser.LOCAL_DATA_DIR:
                # Tier 2: Codex SQLite index (fast, no file parsing)
                index_trajs = parser.parse_session_index(parser.LOCAL_DATA_DIR)
                if index_trajs:
                    # Build reverse map: filepath -> old file_index key
                    path_to_old_sid = {
                        str(fpath): sid
                        for sid, (fpath, p) in self._file_index.items()
                        if p is parser
                    }
                    for t in index_trajs:
                        rollout_path = (t.extra or {}).get("rollout_path", "")
                        old_sid = path_to_old_sid.get(rollout_path)
                        if not old_sid:
                            continue
                        # Remap file_index from filename-based key to real session_id
                        if t.session_id != old_sid:
                            entry = self._file_index.pop(old_sid, None)
                            if entry:
                                self._file_index[t.session_id] = entry
                        all_trajectories.append(t)
                else:
                    # Fall back to full-file parse if no SQLite index
                    self._parse_files_for_index(parser, all_trajectories)
            else:
                # Tier 3: Full-file parse fallback
                self._parse_files_for_index(parser, all_trajectories)

        # Deduplicate and validate: drop sessions with no first_message
        # (empty/corrupt files that exist on disk but have no parseable
        # content — they show in the sidebar but return 404 when clicked).
        seen_ids: set[str] = set()
        valid: list[Trajectory] = []
        dropped = 0
        for t in all_trajectories:
            if t.session_id in seen_ids:
                continue
            seen_ids.add(t.session_id)
            if not t.first_message:
                self._file_index.pop(t.session_id, None)
                dropped += 1
                continue
            valid.append(t)

        self._index_cache = valid
        if dropped:
            logger.info("Dropped %d empty sessions from index", dropped)
        logger.info(
            "Indexed %d sessions across %d agents", len(self._index_cache), len(self._parsers)
        )
        return self._index_cache

    def _parse_files_for_index(
        self, parser: BaseParser, all_trajectories: list[Trajectory]
    ) -> None:
        """Parse individual files to build skeleton metadata for a parser.

        Collects entries first to avoid mutating _file_index during iteration.
        Remaps session IDs when the parser produces different IDs than
        filename-based keys.

        Args:
            parser: The parser instance to use.
            all_trajectories: Accumulator list to append skeletons to.
        """
        parser_entries = [
            (sid, fpath, p) for sid, (fpath, p) in self._file_index.items() if p is parser
        ]
        for old_sid, fpath, p in parser_entries:
            try:
                trajs = p.parse_file(fpath)
                if not trajs:
                    continue
                main = trajs[0]
                # Remap file_index: the parser may produce a session_id
                # different from the filename-based key (e.g. Codex uses
                # UUID from session_meta, not the rollout filename).
                real_sid = main.session_id
                if real_sid != old_sid:
                    self._file_index.pop(old_sid, None)
                    self._file_index[real_sid] = (fpath, p)
                main.steps = []
                all_trajectories.append(main)
            except Exception:
                logger.warning("Failed to index %s, skipping", fpath)

    def _build_file_index(self) -> None:
        """Scan all agent data directories and map session_id -> (path, parser)."""
        for parser in self._parsers:
            data_dir = parser.LOCAL_DATA_DIR
            if not data_dir or not data_dir.exists():
                continue
            agent_type = _agent_name_to_type(parser.AGENT_NAME)
            if not agent_type:
                continue
            files = discover_session_files(data_dir, agent_type)
            for filepath in files:
                session_id = _extract_session_id(filepath, parser.AGENT_NAME)
                self._file_index[session_id] = (filepath, parser)

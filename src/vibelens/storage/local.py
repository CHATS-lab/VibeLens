"""Multi-agent local session store returning Trajectory objects.

Implements TrajectoryStore by reading sessions from all local agent data
directories. Uses LOCAL_PARSER_CLASSES to instantiate parsers, scans each
parser's data directory for session files, and builds a unified file index
across all agents.
"""

from pathlib import Path

from vibelens.config import Settings
from vibelens.ingest.index_builder import build_session_index
from vibelens.ingest.parsers import LOCAL_PARSER_CLASSES
from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import Trajectory
from vibelens.storage.base import TrajectoryStore
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
    if agent_type == AgentType.CLAUDE_CODE:
        return stem
    return f"{agent_type.value}:{stem}"


class LocalStore(TrajectoryStore):
    """Read sessions from all local agent data directories.

    Uses LOCAL_PARSER_CLASSES to instantiate parsers, scans each parser's
    data directory for session files, and builds a unified file index
    across all agents.

    Inherits concrete read methods (list_metadata, load, exists, etc.)
    from TrajectoryStore. Only overrides initialize, save, and _build_index.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self._parsers: list[BaseParser] = [cls() for cls in LOCAL_PARSER_CLASSES]
        self._data_dirs: dict[BaseParser, Path] = {}

        # Resolve data directory for each parser: settings override > class default
        overrides: dict[AgentType, Path] = {}
        if settings:
            overrides = {
                AgentType.CLAUDE_CODE: settings.claude_dir,
                AgentType.CODEX: settings.codex_dir,
                AgentType.GEMINI: settings.gemini_dir,
            }
        for parser in self._parsers:
            data_dir = overrides.get(parser.AGENT_TYPE) or parser.LOCAL_DATA_DIR
            if data_dir:
                self._data_dirs[parser] = data_dir

    def initialize(self) -> None:
        """No-op — index is loaded lazily on first access."""

    def save(self, trajectories: list[Trajectory]) -> None:
        """Not supported — LocalStore is read-only.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("LocalStore is read-only")

    def _build_index(self) -> None:
        """Build metadata index from all agent data directories.

        Scans each parser's data directory for session files, then builds
        skeleton trajectories for fast listing. Populates both _index
        (session_id -> (path, parser)) and _metadata_cache (session_id -> summary dict).
        """
        self._index = {}
        for parser in self._parsers:
            data_dir = self._data_dirs.get(parser)
            if not data_dir or not data_dir.exists():
                continue
            for filepath in parser.discover_session_files(data_dir):
                session_id = _extract_session_id(filepath, parser.AGENT_TYPE)
                self._index[session_id] = (filepath, parser)

        # Build metadata cache with skeleton trajectories for fast listing without file I/O
        trajectories = build_session_index(self._index, self._data_dirs)
        self._metadata_cache = {
            t.session_id: t.model_dump(exclude={"steps"}, mode="json") for t in trajectories
        }
        logger.info(
            "Indexed %d sessions across %d agents", len(self._metadata_cache), len(self._parsers)
        )

"""Local Claude Code session store returning Trajectory objects.

Implements TrajectoryStore by reading sessions from the local ~/.claude/
directory. Lazily loads the history index on first access.
"""

from datetime import datetime
from pathlib import Path

from vibelens.ingest.parsers.claude_code import ClaudeCodeParser
from vibelens.models.trajectories import Trajectory
from vibelens.stores.base import TrajectoryStore
from vibelens.utils import get_logger

logger = get_logger(__name__)


class LocalStore(TrajectoryStore):
    """Read sessions from local ~/.claude/ directory.

    Lazily loads the history index on first access, filters to sessions
    that have .jsonl files on disk, then parses individual session files
    on demand into Trajectory objects.
    """

    def __init__(self, claude_dir: Path) -> None:
        self._claude_dir = claude_dir
        self._index_cache: list[Trajectory] | None = None
        self._projects_dir = claude_dir / "projects"
        self._file_index: dict[str, Path] = {}
        self._parser = ClaudeCodeParser()

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

        Args:
            session_id: The session UUID to load.
            session_token: Ignored in self-use mode (single-user).

        Returns:
            List of Trajectory objects (main + sub-agents), or None.
        """
        self._load_index()

        session_file = self._file_index.get(session_id)
        if not session_file:
            return None

        trajectories = self._parser.parse_file(session_file)
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
        """Load or return cached skeleton trajectories from history.jsonl."""
        if self._index_cache is not None:
            return self._index_cache

        self._build_file_index()
        all_trajectories = self._parser.parse_history_index(self._claude_dir)

        # history.jsonl can reference sessions whose JSONL files have been
        # deleted or never fully written. Filter to IDs with actual files.
        self._index_cache = [t for t in all_trajectories if t.session_id in self._file_index]
        logger.info(
            "Loaded %d sessions (%d skipped, no file on disk)",
            len(self._index_cache),
            len(all_trajectories) - len(self._index_cache),
        )
        return self._index_cache

    def _build_file_index(self) -> None:
        """Scan project directories and map session_id -> file path."""
        if not self._projects_dir.exists():
            return
        for project_dir in self._projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for jsonl_file in project_dir.glob("*.jsonl"):
                session_id = jsonl_file.stem
                self._file_index[session_id] = jsonl_file

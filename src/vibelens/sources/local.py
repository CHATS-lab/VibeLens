"""Local Claude Code JSONL data source."""

from pathlib import Path

from vibelens.ingest.claude_code import ClaudeCodeParser
from vibelens.models.session import SessionDetail, SessionSummary
from vibelens.utils import get_logger

logger = get_logger(__name__)


class LocalSource:
    """Read sessions from local ~/.claude/ directory.

    Lazily loads the history index on first access, filters to sessions
    that have .jsonl files on disk, then parses individual session files
    on demand.
    """

    def __init__(self, claude_dir: Path) -> None:
        self._claude_dir = claude_dir
        self._sessions_cache: list[SessionSummary] | None = None
        self._projects_dir = claude_dir / "projects"
        self._file_index: dict[str, Path] = {}
        self._parser = ClaudeCodeParser()

    @property
    def source_type(self) -> str:
        return "local"

    @property
    def display_name(self) -> str:
        return f"Local ({self._claude_dir})"

    def list_sessions(
        self, project_name: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[SessionSummary]:
        """Return filtered, paginated session summaries.

        Args:
            project_name: Filter by project name.
            limit: Max number of results.
            offset: Number of results to skip.

        Returns:
            Paginated list of SessionSummary objects.
        """
        sessions = self._load_index()
        if project_name:
            sessions = [s for s in sessions if s.project_name == project_name]
        return sessions[offset : offset + limit]

    def get_session(self, session_id: str) -> SessionDetail | None:
        """Load and parse a full session by ID.

        Args:
            session_id: The session UUID to load.

        Returns:
            SessionDetail with main messages and sub-agent sessions.
        """
        self._load_index()

        session_file = self._file_index.get(session_id)
        if not session_file:
            return None

        summary = self._find_summary(session_id)
        messages, sub_sessions = self._parser.parse_session_with_subagents(session_file)
        metadata = self._parser.compute_session_metadata(messages)

        if summary is None:
            summary = SessionSummary(
                session_id=session_id,
                message_count=metadata.message_count,
                first_message=metadata.first_message,
            )

        summary.message_count = metadata.message_count
        summary.tool_call_count = metadata.tool_call_count
        summary.models = metadata.models
        summary.duration = metadata.duration
        if metadata.first_message and not summary.first_message:
            summary.first_message = metadata.first_message

        return SessionDetail(
            summary=summary, messages=messages, sub_sessions=sub_sessions
        )

    def list_projects(self) -> list[str]:
        """Return all unique project names from the session index.

        Returns:
            Sorted list of project name strings.
        """
        sessions = self._load_index()
        projects = sorted({s.project_name for s in sessions if s.project_name})
        return projects

    def _load_index(self) -> list[SessionSummary]:
        """Load or return cached session index, filtered to sessions with files."""
        if self._sessions_cache is not None:
            return self._sessions_cache

        self._build_file_index()
        all_sessions = self._parser.parse_history_index(self._claude_dir)
        self._sessions_cache = [s for s in all_sessions if s.session_id in self._file_index]
        logger.info(
            "Loaded %d sessions (%d skipped, no file on disk)",
            len(self._sessions_cache),
            len(all_sessions) - len(self._sessions_cache),
        )
        return self._sessions_cache

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

    def _find_summary(self, session_id: str) -> SessionSummary | None:
        """Find a session summary by ID from the cached index."""
        for session in self._load_index():
            if session.session_id == session_id:
                return session
        return None

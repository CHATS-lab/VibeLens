"""Abstract base class for format-specific session parsers.

The parser lifecycle has four phases. ``BaseParser``'s methods are
ordered to match:

1. **Discovery** — ``discover_session_files``, ``get_session_files``:
   find which files on disk make up the agent's sessions.
2. **Indexing (fast path)** — ``parse_session_index``,
   ``parse_skeleton_for_file``: build skeleton trajectories for the
   session-list UI without doing full content parses. Optional;
   parsers without a fast index let these fall through to a full parse.
3. **Parsing (full path)** — ``parse`` (abstract), ``parse_file``:
   convert raw file content into ATIF :class:`Trajectory` objects.
4. **Building** — ``build_agent``, ``assemble_trajectory``: helpers
   used by ``parse`` to produce the final Trajectory model.

Cross-parser pure helpers (constants, error markers, JSONL iteration,
first-message detection, final-metrics rollup, diagnostics) live in
:mod:`vibelens.ingest.parsers.helpers`.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from vibelens.ingest.parsers.helpers import compute_final_metrics, find_first_user_text
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import Agent, Step, Trajectory, TrajectoryRef
from vibelens.models.trajectories.trajectory import DEFAULT_ATIF_VERSION
from vibelens.utils import log_duration
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class BaseParser(ABC):
    """Abstract base for format-specific session parsers.

    Subclasses must set ``AGENT_TYPE`` to their ``AgentType`` enum value
    (e.g. ``AgentType.CLAUDE_CODE``, ``AgentType.CODEX``).

    Parsers that read from a local data directory set ``LOCAL_DATA_DIR``
    to the default path (e.g. ``Path.home() / ".claude"``); parsers for
    imported formats leave it as ``None`` to opt out of local discovery.

    Every concrete parser must implement :meth:`parse`. The other
    lifecycle methods have sensible defaults that subclasses can
    override when their format permits a faster path.
    """

    AGENT_TYPE: AgentType
    LOCAL_DATA_DIR: Path | None = None

    # Discovery

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Discover session files in the given directory.

        Override in subclasses to apply agent-specific filename filters.
        Default returns an empty list.
        """
        return []

    def get_session_files(self, session_file: Path) -> list[Path]:
        """Return all files related to a session including sub-agent files.

        Default returns just the session file. Override in parsers with
        multi-file sessions (e.g., Claude Code sub-agents).
        """
        return [session_file]

    def parse_session_index(self, data_dir: Path) -> list[Trajectory] | None:
        """Build skeleton trajectories from a fast index if available.

        Parsers with an external index (history.jsonl, SQLite DB) override
        this to avoid full-file parsing during listing. Returns None to
        signal no fast index is available, triggering file-parse fallback.
        """
        return None

    def parse_skeleton_for_file(self, file_path: Path) -> Trajectory | None:
        """Lightweight per-file skeleton extraction.

        Default implementation full-parses the file via :meth:`parse_file`
        and clears the steps list — correct but slow. Parsers whose format
        permits a head-of-file scan (append-only JSONL, SQLite-indexed,
        small JSON document) should override to avoid building the entire
        Trajectory.

        Returns ``None`` when the file produces no usable trajectory; the
        caller drops it from the index.
        """
        try:
            trajs = self.parse_file(file_path)
        except Exception:  # noqa: BLE001 — parser-level failures are logged elsewhere
            return None
        if not trajs:
            return None
        main = trajs[0]
        main.steps = []
        return main

    @abstractmethod
    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse raw file content into Trajectory objects.

        Each parser implements format-specific logic to convert raw
        text into ATIF models.

        Args:
            content: Raw file content string.
            source_path: Optional original file path for resolving
                relative resources (e.g. sub-agent files).

        Returns:
            List of Trajectory objects (one per session in the content).
        """

    def parse_file(self, file_path: Path) -> list[Trajectory]:
        """Read a file and parse it into Trajectory objects."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read file %s: %s", file_path, exc)
            return []
        with log_duration(
            logger,
            "parse_file",
            level=logging.DEBUG,
            parser=type(self).__name__,
            bytes=len(content),
        ):
            return self.parse(content, source_path=str(file_path))

    def build_agent(self, version: str | None = None, model: str | None = None) -> Agent:
        """Create an ATIF Agent model using this parser's AGENT_TYPE."""
        return Agent(name=self.AGENT_TYPE.value, version=version, model_name=model)

    def assemble_trajectory(
        self,
        session_id: str,
        agent: Agent,
        steps: list[Step],
        project_path: str | None = None,
        prev_trajectory_ref: TrajectoryRef | None = None,
        parent_trajectory_ref: TrajectoryRef | None = None,
        extra: dict | None = None,
    ) -> Trajectory:
        """Assemble a Trajectory with auto-computed first_message and final_metrics."""
        timestamp = steps[0].timestamp if steps and steps[0].timestamp else None

        return Trajectory(
            schema_version=DEFAULT_ATIF_VERSION,
            session_id=session_id,
            project_path=project_path,
            timestamp=timestamp,
            first_message=find_first_user_text(steps),
            agent=agent,
            steps=steps,
            final_metrics=compute_final_metrics(steps, agent.model_name if agent else None),
            prev_trajectory_ref=prev_trajectory_ref,
            parent_trajectory_ref=parent_trajectory_ref,
            extra=extra,
        )

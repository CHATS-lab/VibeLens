"""Abstract base class for format-specific session parsers.

Every parser follows a 4-stage pipeline:

    1. ``_decode_file``      file_path → raw (dict / list[dict] / format-specific)
    2. ``_extract_metadata`` raw       → Trajectory header (steps stay [])
    3. ``_build_steps``      raw + traj → list[Step]
    4. ``_finalize``         (provided) backfill timestamp / first_message /
                             final_metrics, merge diagnostics into extra

After stage 4, ``_load_subagents`` runs to discover and parse direct children.

Multi-session-per-file formats (dataclaw, claude_web, parsed) override
``parse(file_path)`` directly and call ``_finalize`` per record.
"""

import logging
from abc import ABC
from pathlib import Path
from typing import Any

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.helpers import (
    build_diagnostics_extra,
    compute_final_metrics,
    find_first_user_text,
)
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import Agent, Step, Trajectory
from vibelens.utils import log_duration
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class BaseParser(ABC):
    """Format-specific session parser. See module docstring for the 4-stage pipeline.

    Subclasses set ``AGENT_TYPE``. Parsers that read from a local data directory
    set ``LOCAL_DATA_DIR``; manual-import formats leave it ``None``. Set
    ``DISCOVER_GLOB`` to use the default rglob-based ``discover_session_files``.
    """

    AGENT_TYPE: AgentType
    LOCAL_DATA_DIR: Path | None = None
    DISCOVER_GLOB: str | None = None

    # ---- Discovery ----
    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Default: rglob ``DISCOVER_GLOB``. Override for complex layouts."""
        if self.DISCOVER_GLOB is None:
            return []
        return sorted(data_dir.rglob(self.DISCOVER_GLOB))

    def get_session_files(self, session_file: Path) -> list[Path]:
        """Files related to a session for cache invalidation."""
        return [session_file]

    # ---- Indexing ----
    def parse_session_index(self, data_dir: Path) -> list[Trajectory] | None:
        """Build skeletons from a fast index (SQLite, JSON catalog) if available."""
        return None

    def parse_skeleton_for_file(self, file_path: Path) -> Trajectory | None:
        """Default: full-parse + clear steps. Override for head-of-file scan."""
        try:
            trajs = self.parse(file_path)
        except Exception:  # noqa: BLE001 — parser-level failures are logged elsewhere
            return None
        if not trajs:
            return None
        main = trajs[0]
        main.steps = []
        return main

    # ---- Parsing ----
    def parse(self, file_path: Path) -> list[Trajectory]:
        """Parse a session file into ``[main, *sub-agents]``.

        Default template runs the 4-stage pipeline. Multi-session-per-file
        parsers (dataclaw, claude_web, parsed) override directly.
        """
        with log_duration(logger, "parse", level=logging.DEBUG, parser=type(self).__name__):
            main = self._parse_trajectory(file_path)
            if main is None:
                return []
            # Sub-agent file invoked directly — don't recurse for nested children.
            if main.parent_trajectory_ref is not None:
                return [main]
            return [main, *self._load_subagents(main, file_path)]

    def _parse_trajectory(self, file_path: Path) -> Trajectory | None:
        """One file → one Trajectory, no sub-agent recursion."""
        diagnostics = DiagnosticsCollector()
        raw = self._decode_file(file_path, diagnostics)
        if raw is None:
            return None
        traj = self._extract_metadata(raw, file_path, diagnostics)
        if traj is None:
            return None
        traj.steps = self._build_steps(raw, traj, file_path, diagnostics)
        if not traj.steps:
            return None
        return self._finalize(traj, diagnostics)

    def _decode_file(self, file_path: Path, diagnostics: DiagnosticsCollector) -> Any:
        """Read + parse the raw format. Return ``None`` to skip the file."""
        raise NotImplementedError(f"{type(self).__name__} must override _decode_file")

    def _extract_metadata(
        self, raw: Any, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> Trajectory | None:
        """Build a Trajectory header (session_id + agent + refs; ``steps`` stay ``[]``).

        Return ``None`` if the raw payload is structurally invalid.
        """
        raise NotImplementedError(f"{type(self).__name__} must override _extract_metadata")

    def _build_steps(
        self, raw: Any, traj: Trajectory, file_path: Path, diagnostics: DiagnosticsCollector
    ) -> list[Step]:
        """Build ordered Steps from ``raw``. May mutate ``traj`` (e.g. backfill
        ``traj.agent.model_name`` or ``traj.project_path``) when those fields
        depend on per-step information.

        Set ``observation.results[*].subagent_trajectory_ref`` on observations
        when the format records spawn IDs in step content (Claude, Codex). Pure
        sibling/file-based linkage stays in ``_load_subagents``.
        """
        raise NotImplementedError(f"{type(self).__name__} must override _build_steps")

    def _load_subagents(self, main: Trajectory, file_path: Path) -> list[Trajectory]:
        """Discover + parse direct sub-agents of ``main``. Default: none."""
        return []

    def _finalize(self, traj: Trajectory, diagnostics: DiagnosticsCollector) -> Trajectory:
        """Backfill derived fields and merge diagnostics into ``extra``.

        Used by both the 4-stage template and multi-session parsers that
        override ``parse`` directly.
        """
        if traj.timestamp is None and traj.steps and traj.steps[0].timestamp:
            traj.timestamp = traj.steps[0].timestamp
        if traj.first_message is None:
            traj.first_message = find_first_user_text(traj.steps)
        if traj.final_metrics is None:
            traj.final_metrics = compute_final_metrics(
                traj.steps, traj.agent.model_name if traj.agent else None
            )
        diag_extra = build_diagnostics_extra(diagnostics)
        if diag_extra:
            traj.extra = {**(traj.extra or {}), **diag_extra}
        return traj

    # ---- Building ----
    def build_agent(
        self,
        version: str | None = None,
        model_name: str | None = None,
        tool_definitions: list | None = None,
    ) -> Agent:
        """Create an Agent for this parser's ``AGENT_TYPE``."""
        return Agent(
            name=self.AGENT_TYPE.value,
            version=version,
            model_name=model_name,
            tool_definitions=tool_definitions,
        )

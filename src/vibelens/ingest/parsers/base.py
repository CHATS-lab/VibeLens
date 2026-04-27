"""Abstract base class for format-specific session parsers.

Every parser follows a 4-stage pipeline:

    1. ``_decode_file``      file_path → raw (dict / list[dict] / format-specific)
    2. ``_extract_metadata`` raw       → Trajectory header (steps stay [])
    3. ``_build_steps``      raw + traj → list[Step]
    4. ``_finalize``         (provided) backfill created_at / updated_at /
                             first_message / final_metrics, merge diagnostics

After stage 4, ``_load_subagents`` runs to discover and parse direct children.

Multi-session-per-file formats (dataclaw, claude_web, parsed) override
``parse(file_path)`` directly and call ``_finalize`` per record.
"""

import logging
from abc import ABC
from pathlib import Path
from typing import Any, NamedTuple

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


class DiscoveredSession(NamedTuple):
    """A session discovered by a parser, with everything LocalStore needs to
    track it in the index and detect changes.

    Returned by ``BaseParser.discover_sessions``. The parser declares what
    sessions exist, where each one lives, and when each was last modified.
    Used at startup, on every cache-staleness check, and on full rebuild.
    """

    path: Path
    session_id: str
    mtime_ns: int


class BaseParser(ABC):
    """Format-specific session parser. See module docstring for the 4-stage pipeline.

    Subclasses set ``AGENT_TYPE``. Parsers that read from a local data directory
    set ``LOCAL_DATA_DIR``; manual-import formats leave it ``None``. Set
    ``DISCOVER_GLOB`` to use the default rglob-based ``discover_session_files``.

    ``NAMESPACE_SESSION_IDS`` controls how the default ``discover_sessions``
    forms session_ids from filenames. ``True`` (default) prefixes with the
    agent type — safe for any format. ``False`` is opt-in for parsers whose
    filenames are already globally unique (Claude UUIDs).
    """

    AGENT_TYPE: AgentType
    LOCAL_DATA_DIR: Path | None = None
    DISCOVER_GLOB: str | None = None
    NAMESPACE_SESSION_IDS: bool = True

    # ---- Discovery ----
    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Default: rglob ``DISCOVER_GLOB``. Override for complex layouts."""
        if self.DISCOVER_GLOB is None:
            return []
        return sorted(data_dir.rglob(self.DISCOVER_GLOB))

    def discover_sessions(self, data_dir: Path) -> list[DiscoveredSession]:
        """Enumerate every session this parser owns under ``data_dir``.

        Default: 1 session per file, ``session_id`` from the filename via
        ``_namespace_session_id``, ``mtime_ns`` from ``Path.stat()``.
        Multi-session-per-file formats (OpenCode, Kilo) override to read
        per-session ids and timestamps from the format's native storage
        (e.g. SQLite session table).
        """
        out: list[DiscoveredSession] = []
        for fpath in self.discover_session_files(data_dir):
            try:
                mtime = fpath.stat().st_mtime_ns
            except OSError:
                continue
            out.append(
                DiscoveredSession(
                    path=fpath, session_id=self._namespace_session_id(fpath), mtime_ns=mtime
                )
            )
        return out

    def _namespace_session_id(self, file_path: Path) -> str:
        """Filename-based session_id, optionally prefixed with the agent type.

        Used by the default ``discover_sessions`` only. Subclasses with
        non-filename-based ids (OpencodeParser's SQL ``id``) override
        ``discover_sessions`` directly and never call this.

        Claude inherits ``NAMESPACE_SESSION_IDS = False`` so its uuids stay
        unprefixed; every other default-impl parser prefixes ``agent_type:``
        to avoid index collisions on common stems.
        """
        stem = file_path.stem
        if self.NAMESPACE_SESSION_IDS:
            return f"{self.AGENT_TYPE.value}:{stem}"
        return stem

    def get_session_files(self, session_file: Path) -> list[Path]:
        """Files related to a session for cache invalidation."""
        return [session_file]

    # ---- Indexing ----
    def parse_session_index(self, data_dir: Path) -> list[Trajectory] | None:
        """Build skeletons from a fast index (SQLite, JSON catalog) if available."""
        return None

    def parse_skeleton_for_file(self, file_path: Path) -> Trajectory | None:
        """Default: full-parse + clear steps. Override for head-of-file scan.

        Returns the *main* trajectory only. For files holding multiple
        sessions, use :meth:`parse_skeletons_for_file` instead.
        """
        try:
            trajs = self.parse(file_path)
        except Exception:  # noqa: BLE001 — parser-level failures are logged elsewhere
            return None
        if not trajs:
            return None
        main = trajs[0]
        main.steps = []
        return main

    def parse_skeletons_for_file(self, file_path: Path) -> list[Trajectory]:
        """Return ALL skeleton trajectories that live in this file (steps cleared).

        Default: 1-element list from :meth:`parse_skeleton_for_file` — matches
        the historical "1 file = 1 session" assumption used by Claude, Codex,
        Gemini, OpenClaw, Hermes.

        Override for multi-session-per-file formats where one file holds
        many sessions (e.g. OpenCode/Kilo SQLite databases). The override
        returns N trajectories sharing the same on-disk path; the LocalStore
        index treats each as a distinct session row.
        """
        skel = self.parse_skeleton_for_file(file_path)
        return [skel] if skel else []

    # ---- Loading a specific session ----
    def parse_session(self, file_path: Path, session_id: str) -> list[Trajectory] | None:
        """Return ``[main, *sub_agents]`` for one specific session in this file.

        Default: parse the whole file, then filter to the requested session
        plus any sub-agents whose ``parent_trajectory_ref.session_id`` points
        at it. Works for every existing parser:

        - Single-session-per-file (Claude, Codex, ...): ``parse(file_path)``
          already returns ``[main, *children]`` for that one session, so the
          filter is a no-op.
        - Multi-session-per-file (OpenCode, Kilo): ``parse(file_path)``
          returns N trajectories; the filter narrows to the requested one
          and its descendants.

        Subclasses may override for efficiency (e.g. issue a SQL WHERE
        clause to skip rows for other sessions).
        """
        try:
            trajs = self.parse(file_path)
        except Exception:  # noqa: BLE001
            return None
        if not trajs:
            return None
        main = next((t for t in trajs if t.session_id == session_id), None)
        if main is None:
            return None
        children = [
            t
            for t in trajs
            if t.parent_trajectory_ref is not None
            and t.parent_trajectory_ref.session_id == session_id
        ]
        return [main, *children]

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
        if traj.steps:
            if traj.created_at is None:
                traj.created_at = next((s.timestamp for s in traj.steps if s.timestamp), None)
            if traj.updated_at is None:
                traj.updated_at = next(
                    (s.timestamp for s in reversed(traj.steps) if s.timestamp), None
                )
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

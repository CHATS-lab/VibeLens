"""Base ContextExtractor ABC using the template method pattern.

Defines the core abstraction for context extraction from trajectory groups.
Subclasses override only ``format_step`` to control per-step formatting.
Compaction interleaving, metadata header, and index tracking are shared
across all subclasses.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from vibelens.context.formatter import build_metadata_block
from vibelens.context.params import ContextParams
from vibelens.models.context import SessionContext
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory
from vibelens.models.trajectories.step import Step
from vibelens.utils.content import content_to_text


@dataclass
class _IndexTracker:
    """Assigns sequential 0-based indices to steps during formatting."""

    _counter: int = 0
    index_to_real_id: dict[int, str] = field(default_factory=dict)

    def assign(self, real_id: str) -> int:
        """Assign the next sequential index to a real step ID."""
        idx = self._counter
        self.index_to_real_id[idx] = real_id
        self._counter += 1
        return idx


def _format_steps_available(tracker: _IndexTracker) -> str:
    """Format a whitelist of valid step indices for this session.

    Provides an explicit list of step indices the LLM may cite in
    example_refs. Prevents the LLM from inventing indices outside the
    range actually emitted by the extractor.

    Args:
        tracker: Index tracker populated during step formatting.

    Returns:
        A "STEPS_AVAILABLE: [...]" line, or empty string if no steps.
    """
    indices = sorted(tracker.index_to_real_id.keys())
    if not indices:
        return ""
    return f"STEPS_AVAILABLE: {indices}"


class ContextExtractor(ABC):
    """Template method base class for compressing trajectory groups into LLM-ready text.

    Subclasses implement ``format_step`` to control how individual steps are rendered.
    All structural logic (main trajectory detection, compaction interleaving, index
    tracking, metadata header) is shared in this base class.
    """

    def __init__(self, params: ContextParams) -> None:
        """Store extraction parameters.

        Args:
            params: Context extraction parameters controlling detail level.
        """
        self.params = params

    def extract(
        self, trajectory_group: list[Trajectory], session_index: int | None = None
    ) -> SessionContext:
        """Extract compressed context from a session's trajectory group.

        Template method: calls internal helpers in a fixed order and returns
        a populated SessionContext. Subclasses do not override this method.

        Args:
            trajectory_group: All trajectories for one session (main + sub-agents).
            session_index: Optional 0-based index within the analysis batch.

        Returns:
            SessionContext with compressed text representation.
        """
        main = self._find_main_trajectory(trajectory_group)
        compaction_agents = self._find_compaction_agents(trajectory_group)
        tracker = _IndexTracker()

        context_text = self._extract_steps(main, compaction_agents, tracker)
        header = build_metadata_block(main, session_index=session_index, include_details=True)
        steps_available = _format_steps_available(tracker)
        parts = [header]
        if steps_available:
            parts.append(steps_available)
        if context_text:
            parts.append(context_text)
        full_text = "\n\n".join(parts)

        return SessionContext(
            session_id=main.session_id,
            project_path=main.project_path,
            context_text=full_text,
            trajectory_group=trajectory_group,
            prev_trajectory_ref_id=(
                main.prev_trajectory_ref.session_id if main.prev_trajectory_ref else None
            ),
            next_trajectory_ref_id=(
                main.next_trajectory_ref.session_id if main.next_trajectory_ref else None
            ),
            created_at=main.created_at,
            updated_at=main.updated_at,
            session_index=session_index,
            step_index2id=tracker.index_to_real_id,
        )

    @abstractmethod
    def format_step(self, step: Step, tracker: _IndexTracker) -> str:
        """Format a single step into a string for the context block.

        This is the single override point for subclasses. Return an empty
        string to skip a step entirely.

        Args:
            step: The trajectory step to format.
            tracker: Index tracker for assigning sequential step indices.

        Returns:
            Formatted step string, or empty string to omit the step.
        """

    def _find_main_trajectory(self, trajectory_group: list[Trajectory]) -> Trajectory:
        """Find the main (non-sub-agent) trajectory in the group.

        The main trajectory is identified by the absence of parent_trajectory_ref.
        Falls back to the first trajectory for single-trajectory groups.

        Args:
            trajectory_group: All trajectories in the session group.

        Returns:
            The main trajectory.
        """
        for t in trajectory_group:
            if t.parent_trajectory_ref is None:
                return t
        return trajectory_group[0]

    def _find_compaction_agents(self, trajectory_group: list[Trajectory]) -> list[Trajectory]:
        """Find compaction sub-agents sorted by creation time.

        Compaction agents are detected via the ``extra["is_compaction"]`` flag
        set by parsers during ingestion.

        Args:
            trajectory_group: All trajectories in the session group.

        Returns:
            Compaction agent trajectories sorted by ``created_at``.
        """
        compaction = [t for t in trajectory_group if (t.extra or {}).get("is_compaction")]
        compaction.sort(key=lambda t: t.created_at or datetime.min)
        return compaction

    def _extract_steps(
        self, main: Trajectory, compaction_agents: list[Trajectory], tracker: _IndexTracker
    ) -> str:
        """Dispatch to the appropriate step extraction strategy.

        Uses compaction-aware extraction when compaction agents are present,
        otherwise formats all steps directly.

        Args:
            main: The main trajectory.
            compaction_agents: Detected compaction sub-agents.
            tracker: Index tracker for sequential step numbering.

        Returns:
            Formatted steps as a single string.
        """
        if not compaction_agents:
            return self._format_all_steps(main.steps, tracker)
        return self._extract_with_compactions(main, compaction_agents, tracker)

    def _format_all_steps(self, steps: list[Step], tracker: _IndexTracker) -> str:
        """Format all steps by calling format_step on each, skipping empty results.

        Args:
            steps: Steps to format.
            tracker: Index tracker for sequential step numbering.

        Returns:
            Non-empty step strings joined by double newlines.
        """
        parts: list[str] = []
        for step in steps:
            formatted = self.format_step(step, tracker)
            if formatted:
                parts.append(formatted)
        return "\n\n".join(parts)

    def _extract_with_compactions(
        self, main: Trajectory, compaction_agents: list[Trajectory], tracker: _IndexTracker
    ) -> str:
        """Extract context for sessions with compaction sub-agents.

        Interleaves compaction summaries at their chronological position among
        steps. Each summary is inserted just before the first step whose
        timestamp exceeds the compaction boundary. Falls back to summaries-first
        if timestamps are unavailable.

        Args:
            main: The main trajectory.
            compaction_agents: Compaction sub-agents sorted by timestamp.
            tracker: Index tracker for sequential step numbering.

        Returns:
            Steps and compaction summaries interleaved as a single string.
        """
        boundaries = self._build_compaction_boundaries(compaction_agents)
        parts: list[str] = []

        boundary_idx = 0
        summary_counter = 0

        for step in main.steps:
            while boundary_idx < len(boundaries):
                boundary_ts, summary_text = boundaries[boundary_idx]
                step_ts = step.timestamp

                if boundary_ts is None or step_ts is None:
                    break

                if boundary_ts < step_ts:
                    summary_counter += 1
                    parts.append(f"--- COMPACTION SUMMARY {summary_counter} ---")
                    parts.append(summary_text)
                    boundary_idx += 1
                else:
                    break

            formatted = self.format_step(step, tracker)
            if formatted:
                parts.append(formatted)

        while boundary_idx < len(boundaries):
            _, summary_text = boundaries[boundary_idx]
            summary_counter += 1
            parts.append(f"--- COMPACTION SUMMARY {summary_counter} ---")
            parts.append(summary_text)
            boundary_idx += 1

        return "\n\n".join(parts)

    def _build_compaction_boundaries(
        self, compaction_agents: list[Trajectory]
    ) -> list[tuple[datetime | None, str]]:
        """Extract timestamped summaries from compaction agents.

        Each compaction agent's first AGENT step is used as the summary.
        The compaction agent's ``created_at`` marks when the compaction occurred.

        Args:
            compaction_agents: Compaction sub-agents sorted by ``created_at``.

        Returns:
            Sorted list of (timestamp, summary_text) pairs.
        """
        boundaries: list[tuple[datetime | None, str]] = []
        for agent in compaction_agents:
            for step in agent.steps:
                if step.source == StepSource.AGENT:
                    summary = content_to_text(step.message)
                    if summary.strip():
                        boundaries.append((agent.created_at, summary.strip()))
                    break
        boundaries.sort(key=lambda b: b[0] or datetime.min)
        return boundaries

"""Context models for LLM-powered analysis services.

SessionContext holds the compressed representation of a single agent session.
SessionContextBatch wraps multiple session contexts with step-ref resolution,
trajectory aggregation, and optional batching metadata for LLM calls.
"""

from datetime import datetime
from functools import cached_property

from pydantic import BaseModel, ConfigDict, Field

from vibelens.models.analysis.step_ref import StepRef
from vibelens.models.trajectories import Trajectory
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class SessionContext(BaseModel):
    """Compressed context for one session, ready for LLM consumption."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str = Field(description="Real session UUID.")
    project_path: str | None = Field(default=None, description="Project directory path.")
    context_text: str = Field(description="Compressed LLM-ready text representation.")
    trajectory_group: list[Trajectory] = Field(
        default_factory=list,
        description="Raw trajectories for validation and cost computation.",
    )
    prev_trajectory_ref_id: str | None = Field(
        default=None, description="Previous session ID in continuation chain."
    )
    next_trajectory_ref_id: str | None = Field(
        default=None, description="Next session ID in continuation chain."
    )
    timestamp: datetime | None = Field(default=None, description="Session start timestamp.")
    step_index2id: dict[int, str] = Field(
        default_factory=dict, description="0-based step index to real step UUID mapping."
    )

    def resolve_step_ref(self, ref: StepRef) -> StepRef | None:
        """Resolve 0-indexed step indices to real UUIDs and validate against trajectory steps.

        Combines index resolution (via step_index2id) and validation
        (via trajectory_group steps). Returns None for unresolvable or
        invalid start refs. Clears invalid end refs rather than dropping.

        Args:
            ref: Step reference with potentially synthetic step indices.

        Returns:
            Resolved and validated StepRef, or None if unresolvable.
        """
        if ref.session_id != self.session_id:
            return None

        start_id = self._resolve_index(ref.start_step_id)
        if start_id is None or start_id not in self._valid_step_ids:
            logger.warning(
                "Dropping ref: unresolvable start_step_id %r in session %s",
                ref.start_step_id,
                self.session_id,
            )
            return None

        end_id = None
        if ref.end_step_id:
            end_id = self._resolve_index(ref.end_step_id)
            if end_id is None or end_id not in self._valid_step_ids:
                logger.warning(
                    "Clearing invalid end_step_id %r in session %s",
                    ref.end_step_id,
                    self.session_id,
                )
                end_id = None

        return StepRef(session_id=self.session_id, start_step_id=start_id, end_step_id=end_id)

    @cached_property
    def _valid_step_ids(self) -> set[str]:
        """All real step IDs from trajectory_group for validation."""
        ids: set[str] = set()
        for traj in self.trajectory_group:
            for step in traj.steps:
                ids.add(step.step_id)
        return ids

    def _resolve_index(self, step_id: str) -> str | None:
        """Resolve a step ID: map int-like strings via step_index2id, pass through UUIDs."""
        try:
            return self.step_index2id.get(int(step_id))
        except (ValueError, TypeError):
            return step_id


class SessionContextBatch(BaseModel):
    """Batch of session contexts for LLM consumption.

    Serves two roles depending on lifecycle stage:
    - After extraction: wraps all loaded contexts with session_ids/skipped tracking.
    - After batching: subset sized for one LLM call, with batch_id and token count.

    Provides resolve_step_ref delegation and trajectory aggregation.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    contexts: list[SessionContext] = Field(description="Extracted session contexts.")
    session_ids: list[str] = Field(
        default_factory=list, description="Session IDs that were successfully loaded."
    )
    skipped_session_ids: list[str] = Field(
        default_factory=list, description="Session IDs that were skipped during loading."
    )
    batch_id: str | None = Field(
        default=None, description="Batch identifier, set when used as an LLM-sized batch."
    )
    total_tokens: int = Field(
        default=0, description="Total token count of context texts in this batch."
    )
    project_paths: set[str] = Field(
        default_factory=set, description="Distinct project paths across batch contexts."
    )

    @cached_property
    def all_trajectories(self) -> list[Trajectory]:
        """Flat list of all trajectories across all session contexts."""
        result: list[Trajectory] = []
        for ctx in self.contexts:
            result.extend(ctx.trajectory_group)
        return result

    def resolve_step_ref(self, ref: StepRef) -> StepRef | None:
        """Resolve and validate a step ref by delegating to the matching SessionContext.

        Args:
            ref: Step reference with session_id identifying the target context.

        Returns:
            Resolved and validated StepRef, or None if session unknown or ref invalid.
        """
        ctx = self._context_lookup.get(ref.session_id)
        if ctx is None:
            logger.warning("Dropping ref: unknown session_id %r", ref.session_id)
            return None
        return ctx.resolve_step_ref(ref)

    @cached_property
    def _context_lookup(self) -> dict[str, SessionContext]:
        """Session ID to SessionContext mapping for fast dispatch."""
        return {ctx.session_id: ctx for ctx in self.contexts}

    def __len__(self) -> int:
        return len(self.contexts)

    def __iter__(self):
        return iter(self.contexts)

    def __bool__(self) -> bool:
        return len(self.contexts) > 0

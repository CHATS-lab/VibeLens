"""StepRef — reusable locator for a step or step range within a session trajectory."""

from pydantic import BaseModel, Field, model_validator


class StepRef(BaseModel):
    """Reference to a step or step range within a session trajectory.

    Point ref: only start_step_id is set.
    Range ref: both start_step_id and end_step_id are set (and differ).
    """

    session_id: str = Field(description="Session containing the referenced step(s).")
    start_step_id: str = Field(description="Step ID of the first (or only) step.")
    end_step_id: str | None = Field(
        default=None, description="Last step for range refs. None for point refs."
    )

    @model_validator(mode="after")
    def normalize_point_ref(self) -> "StepRef":
        """Collapse start==end into a point ref."""
        if self.end_step_id == self.start_step_id:
            self.end_step_id = None
        return self

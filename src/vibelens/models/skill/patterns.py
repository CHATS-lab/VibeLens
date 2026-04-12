"""Shared skill analysis primitives used across all modes."""

from pydantic import BaseModel, Field, computed_field

from vibelens.models.step_ref import StepRef
from vibelens.utils.compat import StrEnum


class SkillMode(StrEnum):
    """Skill personalization analysis mode."""

    CREATION = "creation"
    RETRIEVAL = "retrieval"
    EVOLUTION = "evolution"


class WorkflowPattern(BaseModel):
    """A recurring workflow pattern detected from trajectory analysis.

    The LLM generates title, description, and example_refs.
    frequency is computed from the number of example_refs.
    """

    title: str = Field(
        description="Short pattern name, 3-8 words (e.g. 'Search-Read-Edit Cycle')."
    )
    description: str = Field(
        description="What this pattern does and when it occurs. 1-2 sentences, under 40 words."
    )
    example_refs: list[StepRef] = Field(
        default_factory=list, description="Step references where this pattern was observed."
    )

    @computed_field
    @property
    def frequency(self) -> int:
        """Number of occurrences, derived from example_refs count."""
        return len(self.example_refs)

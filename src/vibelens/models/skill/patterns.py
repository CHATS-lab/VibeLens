"""Shared skill analysis primitives used across all modes."""

from vibelens.models.session.patterns import WorkflowPattern
from vibelens.utils.compat import StrEnum


class SkillMode(StrEnum):
    """Skill personalization analysis mode."""

    CREATION = "creation"
    RETRIEVAL = "retrieval"
    EVOLUTION = "evolution"


__all__ = ["SkillMode", "WorkflowPattern"]

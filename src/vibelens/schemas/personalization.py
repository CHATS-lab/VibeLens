"""Personalization API schemas — unified request models and catalog response."""

from pydantic import BaseModel, Field


class PersonalizationRequest(BaseModel):
    """Unified request body for all personalization analyses."""

    session_ids: list[str] = Field(description="Session IDs to analyze.")
    skill_names: list[str] | None = Field(
        default=None,
        description="Skill names to target for evolution. None means all installed skills.",
    )

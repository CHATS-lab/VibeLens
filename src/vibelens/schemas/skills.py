"""Skill analysis API schemas — request models and lightweight metadata."""

from pydantic import BaseModel, Field

from vibelens.models.skill import SkillMode


class SkillWriteRequest(BaseModel):
    """Request body for creating or updating a skill."""

    name: str = Field(description="Skill name in kebab-case.")
    content: str = Field(description="Full SKILL.md content including frontmatter.")


class SkillLoadRequest(BaseModel):
    """Request body for loading skills from an agent-native store into the central store."""

    overwrite: bool = Field(default=False, description="Overwrite existing central skills.")


class SkillSyncRequest(BaseModel):
    """Request body for syncing a skill to agent interfaces."""

    targets: list[str] = Field(
        description="Agent interface keys to sync to (e.g. 'claude_code', 'codex')."
    )


class FeaturedSkillInstallRequest(BaseModel):
    """Request body for installing a featured skill from the catalog."""

    slug: str = Field(description="Skill slug from featured-skills.json.")
    targets: list[str] = Field(
        default_factory=list,
        description="Agent interface keys to install to. Empty = central only.",
    )


class SkillAnalysisRequest(BaseModel):
    """Request for LLM-powered skill analysis across sessions."""

    session_ids: list[str] = Field(description="Session IDs to analyze.")
    mode: SkillMode = Field(description="Analysis mode: retrieval, creation, or evolution.")
    skill_names: list[str] | None = Field(
        default=None,
        description="Skill names to target for evolution mode. None means all installed skills.",
    )



class SkillAnalysisMeta(BaseModel):
    """Lightweight metadata for a persisted skill analysis."""

    analysis_id: str = Field(description="Unique ID for this analysis.")
    mode: SkillMode = Field(description="Analysis mode used.")
    title: str = Field(default="", description="LLM-generated analysis title.")
    session_ids: list[str] = Field(description="Sessions that were analyzed.")
    created_at: str = Field(description="ISO timestamp of analysis.")
    model: str = Field(description="Model used for analysis.")
    cost_usd: float | None = Field(default=None, description="Inference cost.")
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock analysis duration in seconds."
    )

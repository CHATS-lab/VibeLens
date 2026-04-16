"""Skill API schemas — request and response models."""

from pydantic import BaseModel, Field

from vibelens.models.extension.skill import Skill


class SkillInstallRequest(BaseModel):
    """Create a new skill."""

    name: str = Field(description="Kebab-case skill name.")
    content: str = Field(description="Full SKILL.md content.")
    sync_to: list[str] = Field(
        default_factory=list,
        description="Agent keys to sync to after install.",
    )


class SkillModifyRequest(BaseModel):
    """Update skill content."""

    content: str = Field(description="New SKILL.md content.")


class SkillSyncRequest(BaseModel):
    """Sync skill to specific agents."""

    agents: list[str] = Field(description="Agent keys to sync to.")


class SyncTargetResponse(BaseModel):
    """An agent platform available for skill sync."""

    key: str = Field(description="Agent identifier (e.g. 'claude').")
    label: str = Field(description="Display name (e.g. 'Claude').")
    skill_count: int = Field(description="Number of skills in agent dir.")
    skills_dir: str = Field(description="Agent skills directory path.")


class SkillDetailResponse(BaseModel):
    """Full skill detail including content."""

    skill: Skill = Field(description="Skill metadata with install status.")
    content: str = Field(description="Raw SKILL.md text.")
    path: str = Field(description="Central store path.")


class SkillListResponse(BaseModel):
    """Paginated skill listing with available sync targets."""

    items: list[Skill] = Field(description="Page of skills with install status.")
    total: int = Field(description="Total matching skills.")
    page: int = Field(description="Current page number.")
    page_size: int = Field(description="Items per page.")
    sync_targets: list[SyncTargetResponse] = Field(
        description="Agent platforms available for sync.",
    )

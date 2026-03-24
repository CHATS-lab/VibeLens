"""Skill domain model — metadata for a locally installed agent skill."""

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from vibelens.models.enums import AgentType

VALID_SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillInfo(BaseModel):
    """Metadata for a locally installed skill."""

    name: str = Field(description="Skill identifier in kebab-case.")
    description: str = Field(description="Trigger description from frontmatter.")
    agent_type: AgentType = Field(
        description="Which agent this skill belongs to (e.g. claude_code, codex)."
    )
    path: Path = Field(description="Absolute path to skill directory.")
    allowed_tools: list[str] = Field(default_factory=list, description="Tools the skill can use.")
    subdirs: list[str] = Field(
        default_factory=list,
        description="Present subdirectories (e.g. ['scripts', 'references', 'agents']).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata from frontmatter."
    )
    line_count: int = Field(default=0, description="Total lines in the skill definition file.")

    @field_validator("name")
    @classmethod
    def validate_kebab_case(cls, v: str) -> str:
        """Ensure name is valid kebab-case."""
        if not VALID_SKILL_NAME.match(v):
            raise ValueError(f"Skill name must be kebab-case: {v!r}")
        return v

"""Source metadata for skills."""

from pydantic import BaseModel, Field

from vibelens.models.enums import AgentType
from vibelens.utils.compat import StrEnum


class SkillSourceType(StrEnum):
    """Unified source/store type for skills.

    Every AgentType member is mirrored here, plus CENTRAL and URL.
    When adding a new agent to AgentType, add a matching line here.
    """

    AIDER = AgentType.AIDER
    AMP = AgentType.AMP
    ANTIGRAVITY = AgentType.ANTIGRAVITY
    CLAUDE_CODE = AgentType.CLAUDE_CODE
    CODEX = AgentType.CODEX
    COPILOT = AgentType.COPILOT
    CURSOR = AgentType.CURSOR
    DATACLAW = AgentType.DATACLAW
    GEMINI = AgentType.GEMINI
    GEMINI_CLI = AgentType.GEMINI_CLI
    KIMI = AgentType.KIMI
    OPENCODE = AgentType.OPENCODE
    OPENCLAW = AgentType.OPENCLAW
    OPENHANDS = AgentType.OPENHANDS
    PARSED = AgentType.PARSED
    QWEN_CODE = AgentType.QWEN_CODE
    CENTRAL = "central"
    URL = "url"


class SkillSource(BaseModel):
    """One source from which a skill is available or was loaded."""

    source_type: SkillSourceType = Field(description="Source/store type for this skill.")
    source_path: str = Field(description="Local path or URL for the source.")

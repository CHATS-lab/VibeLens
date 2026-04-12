"""Enumeration types for VibeLens domain models."""

from vibelens.utils.compat import StrEnum


class AgentType(StrEnum):
    """Known agent CLI types.

    Includes both trajectory-parsed agents (claude_code, codex, gemini, dataclaw)
    and skill-only agents (cursor, opencode, etc.) that we scan for installed skills.
    """

    AIDER = "aider"
    AMP = "amp"
    ANTIGRAVITY = "antigravity"
    CLAUDE_CODE = "claude_code"
    CLAUDE_CODE_WEB = "claude_code_web"
    CODEX = "codex"
    COPILOT = "copilot"
    CURSOR = "cursor"
    DATACLAW = "dataclaw"
    GEMINI = "gemini"
    GEMINI_CLI = "gemini_cli"
    KIMI = "kimi"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    OPENHANDS = "openhands"
    PARSED = "parsed"
    QWEN_CODE = "qwen_code"


class StepSource(StrEnum):
    """Originator of a trajectory step (ATIF v1.6)."""

    SYSTEM = "system"
    USER = "user"
    AGENT = "agent"


class ContentType(StrEnum):
    """Content part type within a multimodal message (ATIF v1.6)."""

    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"


class DataSourceType(StrEnum):
    """Supported data source types."""

    LOCAL = "local"
    HUGGINGFACE = "huggingface"
    MONGODB = "mongodb"
    UPLOAD = "upload"


class DataTargetType(StrEnum):
    """Supported data target types."""

    MONGODB = "mongodb"
    HUGGINGFACE = "huggingface"


class AppMode(StrEnum):
    """Application operating mode."""

    SELF = "self"
    DEMO = "demo"
    TEST = "test"


class SessionPhase(StrEnum):
    """Semantic phase of a coding agent session."""

    EXPLORATION = "exploration"
    IMPLEMENTATION = "implementation"
    DEBUGGING = "debugging"
    VERIFICATION = "verification"
    PLANNING = "planning"
    MIXED = "mixed"


class ElementType(StrEnum):
    """File-based element types that can be created or evolved."""

    SKILL = "skill"
    SUBAGENT = "subagent"
    COMMAND = "command"
    HOOK = "hook"

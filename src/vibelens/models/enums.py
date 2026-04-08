"""Enumeration types for VibeLens domain models."""

from enum import StrEnum


class AgentType(StrEnum):
    """Known agent CLI types.

    Includes both trajectory-parsed agents (claude_code, codex, gemini, dataclaw)
    and skill-only agents (cursor, opencode, etc.) that we scan for installed skills.
    """

    CLAUDE_CODE = "claude_code"
    CLAUDE_CODE_WEB = "claude_code_web"
    CODEX = "codex"
    GEMINI = "gemini"
    DATACLAW = "dataclaw"
    PARSED = "parsed"
    CURSOR = "cursor"
    OPENCODE = "opencode"
    ANTIGRAVITY = "antigravity"
    KIMI_CLI = "kimi_cli"
    OPENCLAW = "openclaw"
    OPENHANDS = "openhands"
    QWEN_CODE = "qwen_code"
    GEMINI_CLI = "gemini_cli"
    COPILOT = "copilot"


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

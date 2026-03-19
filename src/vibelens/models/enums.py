"""Enumeration types for VibeLens domain models."""

from enum import StrEnum


class AgentType(StrEnum):
    """Supported agent CLI types."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    GEMINI = "gemini"


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


class SessionPhase(StrEnum):
    """Semantic phase of a coding agent session."""

    EXPLORATION = "exploration"
    IMPLEMENTATION = "implementation"
    DEBUGGING = "debugging"
    VERIFICATION = "verification"
    PLANNING = "planning"
    MIXED = "mixed"

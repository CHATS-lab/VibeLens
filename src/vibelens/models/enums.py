"""Enumeration types for VibeLens domain models."""

from vibelens.utils.compat import StrEnum


class AgentType(StrEnum):
    """Known agent CLI types.

    Includes both trajectory-parsed agents (claude, codex, gemini, dataclaw)
    and skill-only agents (cursor, opencode, etc.) that we scan for installed skills.
    """

    AIDER = "aider"
    ANTIGRAVITY = "antigravity"
    CLAUDE = "claude"
    CLAUDE_WEB = "claude_web"
    CODEX = "codex"
    COPILOT = "copilot"
    CURSOR = "cursor"
    DATACLAW = "dataclaw"
    GEMINI = "gemini"
    KIMI = "kimi"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    OPENHANDS = "openhands"
    PARSED = "parsed"
    QWEN = "qwen"


class ExtensionSource(StrEnum):
    """Unified source/store type for extensions.

    Every AgentType member is mirrored here, plus CENTRAL.
    When adding a new agent to AgentType, add a matching line here.
    """

    AIDER = AgentType.AIDER
    ANTIGRAVITY = AgentType.ANTIGRAVITY
    CLAUDE = AgentType.CLAUDE
    CODEX = AgentType.CODEX
    COPILOT = AgentType.COPILOT
    CURSOR = AgentType.CURSOR
    DATACLAW = AgentType.DATACLAW
    GEMINI = AgentType.GEMINI
    KIMI = AgentType.KIMI
    OPENCODE = AgentType.OPENCODE
    OPENCLAW = AgentType.OPENCLAW
    OPENHANDS = AgentType.OPENHANDS
    QWEN = AgentType.QWEN
    CENTRAL = "central"


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


class AppMode(StrEnum):
    """Application operating mode."""

    SELF = "self"
    DEMO = "demo"
    TEST = "test"


class SessionPhase(StrEnum):
    """Semantic phase of a coding agent session."""

    EXPLORATION = "exploration"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    DEBUGGING = "debugging"
    MIXED = "mixed"


class AgentExtensionType(StrEnum):
    """Types of agent extensions that can be discovered, installed, and managed."""

    SKILL = "skill"
    SUBAGENT = "subagent"
    COMMAND = "command"
    HOOK = "hook"
    REPO = "repo"

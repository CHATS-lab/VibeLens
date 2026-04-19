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
    HERMES = "hermes"
    KIMI = "kimi"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    OPENHANDS = "openhands"
    QWEN = "qwen"
    PARSED = "parsed"


class ExtensionSource(StrEnum):
    """Unified source/store type for extensions.

    Values must be plain strings matching AgentType values.  Using
    ``AgentType.XXX`` as values causes StrEnum to store the *repr*
    (e.g. ``"AgentType.CLAUDE"``) instead of the plain value on some
    Python versions, breaking platform key lookups.
    """

    AIDER = "aider"
    ANTIGRAVITY = "antigravity"
    CLAUDE = "claude"
    CODEX = "codex"
    COPILOT = "copilot"
    CURSOR = "cursor"
    DATACLAW = "dataclaw"
    GEMINI = "gemini"
    HERMES = "hermes"
    KIMI = "kimi"
    OPENCODE = "opencode"
    OPENCLAW = "openclaw"
    OPENHANDS = "openhands"
    QWEN = "qwen"
    CENTRAL = "central"


class AgentExtensionType(StrEnum):
    """Types of agent extensions that can be discovered, installed, and managed."""

    SKILL = "skill"
    PLUGIN = "plugin"
    SUBAGENT = "subagent"
    COMMAND = "command"
    HOOK = "hook"
    MCP_SERVER = "mcp_server"
    REPO = "repo"


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

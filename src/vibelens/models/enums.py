"""Enumeration types for VibeLens domain models."""

from vibelens.utils.compat import StrEnum


class AgentType(StrEnum):
    """Known agent CLI types.

    Includes both trajectory-parsed agents (claude, codex, gemini, dataclaw)
    and skill-only agents (cursor, opencode, etc.) that we scan for installed
    extensions. ``CLAUDE_WEB`` is a real trajectory source. ``AIDER`` is
    referenced by the LLM-backend layer (``llm/backends/aider_cli.py``,
    ``models/llm/inference.py``) — it has no parser and no PLATFORMS row.
    """

    AIDER = "aider"
    AMP = "amp"
    ANTIGRAVITY = "antigravity"
    AUGMENT = "augment"
    AUTOCLAW = "autoclaw"
    CLAUDE = "claude"
    CLAUDE_WEB = "claude_web"
    CODEBUDDY = "codebuddy"
    CODEX = "codex"
    COPILOT = "copilot"
    CURSOR = "cursor"
    DATACLAW = "dataclaw"
    EASYCLAW = "easyclaw"
    FACTORY = "factory"
    GEMINI = "gemini"
    HERMES = "hermes"
    JUNIE = "junie"
    KILO = "kilo"
    KIMI = "kimi"
    KIRO = "kiro"
    OB1 = "ob1"
    OPENCLAW = "openclaw"
    OPENCODE = "opencode"
    OPENHANDS = "openhands"
    QCLAW = "qclaw"
    QODER = "qoder"
    QWEN = "qwen"
    TRAE = "trae"
    TRAE_CN = "trae-cn"
    WORKBUDDY = "workbuddy"


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

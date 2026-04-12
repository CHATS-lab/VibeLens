"""Tests for AgentType and BackendType official name renames."""
from vibelens.models.enums import AgentType
from vibelens.models.llm.inference import BackendType


def test_agent_type_has_aider_and_amp():
    """AgentType includes Aider and Amp (previously backend-only)."""
    assert AgentType.AIDER == "aider"
    assert AgentType.AMP == "amp"


def test_agent_type_kimi_renamed():
    """KIMI_CLI renamed to KIMI."""
    assert AgentType.KIMI == "kimi"
    assert not hasattr(AgentType, "KIMI_CLI")


def test_backend_type_uses_underscores():
    """BackendType string values use underscores, not hyphens."""
    assert BackendType.CLAUDE_CODE == "claude_code"
    assert BackendType.CODEX == "codex"
    assert BackendType.GEMINI == "gemini"
    assert BackendType.CURSOR == "cursor"
    assert BackendType.KIMI == "kimi"
    assert BackendType.OPENCLAW == "openclaw"
    assert BackendType.OPENCODE == "opencode"
    assert BackendType.AIDER == "aider"
    assert BackendType.AMP == "amp"


def test_backend_type_no_cli_suffix():
    """Old *_CLI members no longer exist."""
    assert not hasattr(BackendType, "CLAUDE_CLI")
    assert not hasattr(BackendType, "CODEX_CLI")
    assert not hasattr(BackendType, "GEMINI_CLI")


def test_backend_and_agent_names_overlap():
    """Every CLI backend has a matching AgentType member (name alignment)."""
    cli_backends = {
        bt for bt in BackendType
        if bt not in (BackendType.LITELLM, BackendType.MOCK, BackendType.DISABLED)
    }
    for bt in cli_backends:
        assert hasattr(AgentType, bt.name), f"AgentType missing {bt.name}"

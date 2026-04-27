"""AgentType is the only agent-identity enum after Task 0."""

from vibelens.models.enums import AgentType


def test_extension_source_no_longer_exists():
    import vibelens.models.enums as enums_mod

    assert not hasattr(enums_mod, "ExtensionSource"), (
        "ExtensionSource should be deleted; AgentType is the single source of truth"
    )


def test_agent_type_covers_every_extension_source_value():
    expected = {
        "aider", "antigravity", "claude", "codex", "copilot", "cursor",
        "dataclaw", "gemini", "hermes", "kimi", "opencode", "openclaw",
        "openhands", "qwen",
    }
    values = {at.value for at in AgentType}
    assert expected.issubset(values)


def test_agent_type_has_non_extension_synthetics():
    values = {at.value for at in AgentType}
    assert "claude_web" in values
    assert "parsed" in values

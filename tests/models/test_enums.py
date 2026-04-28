"""AgentType is the only agent-identity enum after Task 0."""

import pytest

from vibelens.models.enums import AgentType


def test_extension_source_no_longer_exists():
    import vibelens.models.enums as enums_mod

    assert not hasattr(enums_mod, "ExtensionSource"), (
        "ExtensionSource should be deleted; AgentType is the single source of truth"
    )


def test_agent_type_covers_every_extension_source_value():
    expected = {
        "aider",
        "antigravity",
        "claude",
        "codex",
        "copilot",
        "cursor",
        "dataclaw",
        "gemini",
        "hermes",
        "kimi",
        "opencode",
        "openclaw",
        "openhands",
        "qwen",
    }
    values = {at.value for at in AgentType}
    assert expected.issubset(values)


def test_agent_type_has_non_extension_synthetics():
    values = {at.value for at in AgentType}
    # CLAUDE_WEB stays — it's a real trajectory source.
    assert "claude_web" in values
    # PARSED removed in this work; ParsedTrajectoryParser uses AGENT_TYPE = None instead.
    assert "parsed" not in values


def test_parsed_parser_agent_type_is_none():
    """`ParsedTrajectoryParser` is a deserializer; it has no source agent."""
    from vibelens.ingest.parsers.parsed import ParsedTrajectoryParser

    assert ParsedTrajectoryParser.AGENT_TYPE is None


def test_real_parser_agent_types_intact():
    """All real parsers keep their concrete `AgentType` value."""
    from vibelens.ingest.parsers.claude import ClaudeParser
    from vibelens.ingest.parsers.codex import CodexParser
    from vibelens.ingest.parsers.gemini import GeminiParser

    assert ClaudeParser.AGENT_TYPE == AgentType.CLAUDE
    assert CodexParser.AGENT_TYPE == AgentType.CODEX
    assert GeminiParser.AGENT_TYPE == AgentType.GEMINI


def test_build_agent_raises_for_none_agent_type():
    """`build_agent` must refuse to build an Agent without an `AGENT_TYPE`."""
    from vibelens.ingest.parsers.parsed import ParsedTrajectoryParser

    parser = ParsedTrajectoryParser()
    with pytest.raises(AssertionError, match="AGENT_TYPE is None"):
        parser.build_agent()

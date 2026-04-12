"""Tests for GEMINI/GEMINI_CLI merge."""
from vibelens.models.enums import AgentType
from vibelens.models.skill.source import SkillSourceType
from vibelens.storage.skill.agent import AGENT_SKILL_REGISTRY


def test_gemini_cli_removed_from_agent_type():
    """GEMINI_CLI no longer exists in AgentType."""
    assert not hasattr(AgentType, "GEMINI_CLI")
    assert AgentType.GEMINI == "gemini"


def test_gemini_cli_removed_from_skill_source_type():
    """GEMINI_CLI no longer exists in SkillSourceType."""
    assert not hasattr(SkillSourceType, "GEMINI_CLI")
    assert SkillSourceType.GEMINI == "gemini"


def test_agent_skill_registry_uses_gemini():
    """AGENT_SKILL_REGISTRY uses GEMINI key, not GEMINI_CLI."""
    assert SkillSourceType.GEMINI in AGENT_SKILL_REGISTRY
    gemini_path = AGENT_SKILL_REGISTRY[SkillSourceType.GEMINI]
    assert "/.gemini/skills" in str(gemini_path)


def test_legacy_alias_maps_gemini_cli():
    """Legacy 'gemini_cli' backend alias maps to 'gemini'."""
    from vibelens.config.llm_config import LEGACY_BACKEND_ALIASES

    assert LEGACY_BACKEND_ALIASES["gemini_cli"] == "gemini"

"""Tests for the Skill model."""

from vibelens.models.extension.skill import Skill


def test_skill_defaults():
    """Skill with only name should have sensible defaults."""
    skill = Skill(name="my-skill")
    assert skill.name == "my-skill"
    assert skill.description == ""
    assert skill.tags == []
    assert skill.allowed_tools == []
    assert skill.content_hash == ""
    assert skill.installed_in == []


def test_skill_full_fields():
    """Skill with all fields set."""
    skill = Skill(
        name="test-skill",
        description="A test skill",
        tags=["testing", "demo"],
        allowed_tools=["Bash", "Read"],
        content_hash="abc123",
        installed_in=["claude", "codex"],
    )
    assert skill.description == "A test skill"
    assert skill.tags == ["testing", "demo"]
    assert skill.allowed_tools == ["Bash", "Read"]
    assert skill.installed_in == ["claude", "codex"]


def test_skill_name_validation_rejects_non_kebab():
    """Non-kebab-case names are rejected."""
    import pytest

    with pytest.raises(ValueError, match="kebab-case"):
        Skill(name="Not Valid")

    with pytest.raises(ValueError, match="kebab-case"):
        Skill(name="camelCase")


def test_skill_name_validation_accepts_kebab():
    """Valid kebab-case names are accepted."""
    skill = Skill(name="multi-word-skill")
    assert skill.name == "multi-word-skill"

    skill = Skill(name="simple")
    assert skill.name == "simple"


def test_skill_serialization():
    """Skill serializes to dict cleanly."""
    skill = Skill(name="my-skill", description="desc", tags=["a"])
    data = skill.model_dump()
    assert data["name"] == "my-skill"
    assert data["tags"] == ["a"]
    assert data["installed_in"] == []

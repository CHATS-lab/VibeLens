"""Tests for the AgentExtensionType enum, ExtensionItem, and ExtensionInfo models."""

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import (
    EXTENSION_TYPE_LABELS,
    FILE_BASED_TYPES,
    ExtensionInfo,
    ExtensionItem,
)


def test_agent_extension_type_values():
    """All 5 extension types are present."""
    assert AgentExtensionType.SKILL == "skill"
    assert AgentExtensionType.SUBAGENT == "subagent"
    assert AgentExtensionType.COMMAND == "command"
    assert AgentExtensionType.HOOK == "hook"
    assert AgentExtensionType.REPO == "repo"
    assert len(AgentExtensionType) == 5
    print(f"All 5 extension types: {list(AgentExtensionType)}")


def test_file_based_types():
    """FILE_BASED_TYPES includes skill, subagent, command, hook but not repo."""
    assert AgentExtensionType.SKILL in FILE_BASED_TYPES
    assert AgentExtensionType.SUBAGENT in FILE_BASED_TYPES
    assert AgentExtensionType.COMMAND in FILE_BASED_TYPES
    assert AgentExtensionType.HOOK in FILE_BASED_TYPES
    assert AgentExtensionType.REPO not in FILE_BASED_TYPES
    print(f"FILE_BASED_TYPES: {FILE_BASED_TYPES}")


def test_extension_type_labels():
    """All 5 types have human-readable labels."""
    assert len(EXTENSION_TYPE_LABELS) == 5
    assert EXTENSION_TYPE_LABELS[AgentExtensionType.SKILL] == "Skill"
    assert EXTENSION_TYPE_LABELS[AgentExtensionType.REPO] == "Repository"
    print(f"Labels: {EXTENSION_TYPE_LABELS}")


def test_extension_item_is_file_based():
    """is_file_based computed field works for all types."""
    base_kwargs = dict(
        extension_id="test:1",
        name="test-item",
        description="Test",
        tags=["test"],
        category="test",
        platforms=["claude_code"],
        quality_score=50.0,
        popularity=0.5,
        updated_at="2026-01-01T00:00:00Z",
        source_url="https://github.com/test/repo",
        repo_full_name="test/repo",
        install_method="skill_file",
    )
    skill_item = ExtensionItem(extension_type=AgentExtensionType.SKILL, **base_kwargs)
    repo_item = ExtensionItem(extension_type=AgentExtensionType.REPO, **base_kwargs)

    assert skill_item.is_file_based is True
    assert repo_item.is_file_based is False
    print(f"skill.is_file_based={skill_item.is_file_based}, "
          f"repo.is_file_based={repo_item.is_file_based}")


def test_extension_info_has_extension_type():
    """ExtensionInfo.extension_type defaults to SKILL."""
    info = ExtensionInfo(
        name="test-ext",
        description="A test extension",
        content_hash="abc123",
    )
    assert info.extension_type == AgentExtensionType.SKILL
    print(f"Default extension_type: {info.extension_type}")

    info_cmd = ExtensionInfo(
        name="test-cmd",
        extension_type=AgentExtensionType.COMMAND,
        description="A test command",
        content_hash="def456",
    )
    assert info_cmd.extension_type == AgentExtensionType.COMMAND
    print(f"Explicit extension_type: {info_cmd.extension_type}")

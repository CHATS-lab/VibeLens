"""Tests for AgentExtensionItem and extension type utilities."""

import pytest
from pydantic import ValidationError

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import (
    EXTENSION_TYPE_LABELS,
    FILE_BASED_TYPES,
    AgentExtensionItem,
)


def test_agent_extension_type_values():
    """All 7 extension types are present."""
    assert AgentExtensionType.SKILL == "skill"
    assert AgentExtensionType.SUBAGENT == "subagent"
    assert AgentExtensionType.COMMAND == "command"
    assert AgentExtensionType.HOOK == "hook"
    assert AgentExtensionType.REPO == "repo"
    assert AgentExtensionType.PLUGIN == "plugin"
    assert AgentExtensionType.MCP_SERVER == "mcp_server"
    assert len(AgentExtensionType) == 7


def test_file_based_types():
    expected = {
        AgentExtensionType.SKILL,
        AgentExtensionType.SUBAGENT,
        AgentExtensionType.COMMAND,
        AgentExtensionType.HOOK,
    }
    assert FILE_BASED_TYPES == expected


def test_extension_type_labels():
    for t in AgentExtensionType:
        assert t in EXTENSION_TYPE_LABELS


def _summary_kwargs() -> dict:
    """Minimal kwargs for an always-populated item."""
    return {
        "extension_id": "tree:acme/widget:skills/alpha",
        "extension_type": AgentExtensionType.SKILL,
        "name": "alpha",
        "source_url": "https://github.com/acme/widget/tree/main/skills/alpha",
        "repo_full_name": "acme/widget",
        "discovery_source": "seed",
        "topics": ["ai", "tooling"],
        "quality_score": 72.5,
        "popularity": 0.42,
        "stars": 12345,
        "forks": 100,
    }


def test_loads_from_hub_aliases():
    """Hub JSON (item_id/item_type) populates VibeLens-name fields."""
    item = AgentExtensionItem.model_validate(
        {
            "item_id": "tree:acme/widget:skills/alpha",
            "item_type": "skill",
            "name": "alpha",
            "source_url": "https://github.com/acme/widget",
            "repo_full_name": "acme/widget",
            "discovery_source": "seed",
            "topics": [],
            "quality_score": 50.0,
            "popularity": 0.1,
            "stars": 10,
            "forks": 0,
        }
    )
    assert item.extension_id == "tree:acme/widget:skills/alpha"
    assert item.extension_type == AgentExtensionType.SKILL


def test_loads_from_vibelens_names():
    """Direct construction with extension_id/extension_type also works."""
    item = AgentExtensionItem(**_summary_kwargs())
    assert item.extension_id.startswith("tree:")
    assert item.extension_type == AgentExtensionType.SKILL


def test_detail_fields_default_to_none():
    """Detail-only fields are None unless supplied."""
    item = AgentExtensionItem(**_summary_kwargs())
    assert item.repo_description is None
    assert item.readme_description is None
    assert item.author is None
    assert item.scores is None
    assert item.item_metadata is None
    assert item.validation_errors is None
    assert item.author_followers is None
    assert item.contributors_count is None
    assert item.created_at is None
    assert item.discovery_origin is None


def test_reserved_fields_default_to_none():
    """`platforms` and `install_command` are reserved and default to None."""
    item = AgentExtensionItem(**_summary_kwargs())
    assert item.platforms is None
    assert item.install_command is None


def test_is_valid_true_when_no_validation_errors():
    item = AgentExtensionItem(**_summary_kwargs())
    assert item.is_valid is True


def test_is_valid_false_when_validation_errors_present():
    item = AgentExtensionItem(**_summary_kwargs(), validation_errors=["bad"])
    assert item.is_valid is False


def test_display_description_fallback_order():
    kwargs = _summary_kwargs()
    item = AgentExtensionItem(
        **kwargs,
        description="primary",
        readme_description="secondary",
        repo_description="tertiary",
    )
    assert item.display_description == "primary"

    item = AgentExtensionItem(
        **kwargs, readme_description="secondary", repo_description="tertiary"
    )
    assert item.display_description == "secondary"

    item = AgentExtensionItem(**kwargs, repo_description="tertiary")
    assert item.display_description == "tertiary"

    item = AgentExtensionItem(**kwargs)
    assert item.display_description is None


def test_is_file_based():
    for t in (
        AgentExtensionType.SKILL,
        AgentExtensionType.SUBAGENT,
        AgentExtensionType.COMMAND,
        AgentExtensionType.HOOK,
    ):
        item = AgentExtensionItem(**{**_summary_kwargs(), "extension_type": t})
        assert item.is_file_based is True

    for t in (
        AgentExtensionType.PLUGIN,
        AgentExtensionType.MCP_SERVER,
        AgentExtensionType.REPO,
    ):
        item = AgentExtensionItem(**{**_summary_kwargs(), "extension_type": t})
        assert item.is_file_based is False


def test_extra_fields_ignored_forward_compat():
    """Unknown hub fields don't break validation."""
    payload = {
        "item_id": "x:y",
        "item_type": "skill",
        "name": "n",
        "source_url": "https://github.com/x/y",
        "repo_full_name": "x/y",
        "discovery_source": "seed",
        "topics": [],
        "quality_score": 1.0,
        "popularity": 0.0,
        "stars": 0,
        "forks": 0,
        "future_field_we_dont_know_about": {"anything": 42},
    }
    item = AgentExtensionItem.model_validate(payload)
    assert item.name == "n"


def test_missing_required_field_raises():
    kwargs = _summary_kwargs()
    del kwargs["name"]
    with pytest.raises(ValidationError):
        AgentExtensionItem(**kwargs)

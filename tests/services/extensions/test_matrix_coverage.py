"""Smoke test: every declared (agent, type) pair has the required path field."""

import pytest

from vibelens.models.enums import AgentExtensionType, AgentType
from vibelens.services.extensions.platforms import PLATFORMS


@pytest.mark.parametrize("source", list(PLATFORMS.keys()))
def test_every_platform_has_required_paths_for_its_types(source: AgentType):
    platform = PLATFORMS[source]
    for t in platform.supported_types:
        if t == AgentExtensionType.SKILL:
            assert platform.skills_dir is not None, (
                f"{source} supports skill but has no skills_dir"
            )
        elif t == AgentExtensionType.COMMAND:
            assert platform.commands_dir is not None, (
                f"{source} supports command but has no commands_dir"
            )
        elif t == AgentExtensionType.SUBAGENT:
            assert platform.subagents_dir is not None, (
                f"{source} supports subagent but has no subagents_dir"
            )
        elif t == AgentExtensionType.HOOK:
            assert platform.hook_config_path is not None, (
                f"{source} supports hook but has no hook_config_path"
            )
        elif t == AgentExtensionType.PLUGIN and source != AgentType.CLAUDE:
            assert platform.plugins_dir is not None, (
                f"{source} supports plugin but has no plugins_dir"
            )

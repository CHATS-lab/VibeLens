"""Tests for the upload agent registry and drift checks."""

from vibelens.models.enums import AgentType
from vibelens.services.upload.agents import (
    UPLOAD_SPECS,
    UploadAgentSpec,
    ZipCommand,
    list_user_facing_specs,
)


def test_zip_command_requires_command_and_output():
    cmd = ZipCommand(command="zip foo.zip bar/", output="~/Desktop/foo.zip")
    assert cmd.command == "zip foo.zip bar/"
    assert cmd.output == "~/Desktop/foo.zip"


def test_local_zip_spec_carries_per_os_commands():
    spec = UploadAgentSpec(
        agent_type=AgentType.CLAUDE,
        display_name="Claude Code",
        source="local_zip",
        commands={
            "macos": ZipCommand(
                command="cd ~/.claude && zip -r ~/Desktop/x.zip projects/",
                output="~/Desktop/x.zip",
            ),
        },
    )
    assert spec.user_facing is True
    assert "macos" in spec.commands
    assert spec.external_instructions == []


def test_external_export_spec_carries_instructions():
    spec = UploadAgentSpec(
        agent_type=AgentType.CLAUDE_WEB,
        display_name="Claude Web",
        source="external_export",
        external_instructions=["Download from claude.ai"],
    )
    assert spec.commands == {}
    assert spec.external_instructions == ["Download from claude.ai"]


def test_drift_check_catches_missing_specs():
    missing = set(AgentType) - set(UPLOAD_SPECS)
    assert not missing, f"AgentType values without upload spec: {sorted(missing)}"


def test_user_facing_specs_have_actionable_content():
    for spec in list_user_facing_specs():
        if spec.source == "local_zip":
            assert spec.commands, f"{spec.agent_type} is local_zip but has no commands"
        else:
            assert spec.external_instructions, (
                f"{spec.agent_type} is external_export but has no instructions"
            )


def test_get_upload_command_matches_registry():
    """get_upload_command (the legacy /upload/commands surface) must read
    directly from UPLOAD_SPECS — no shadow data path."""
    from vibelens.services.upload.agents import get_upload_command

    for agent in (AgentType.CLAUDE, AgentType.CODEX, AgentType.GEMINI):
        for os_name in ("macos", "linux", "windows"):
            payload = get_upload_command(agent.value, os_name)
            spec = UPLOAD_SPECS[agent]
            zc = spec.commands.get(os_name)
            assert zc is not None, f"{agent}/{os_name} missing in registry"
            assert zc.command == payload["command"]


def test_internal_only_agents_excluded_from_user_facing():
    user_facing_types = {s.agent_type for s in list_user_facing_specs()}
    assert AgentType.AIDER not in user_facing_types
    assert AgentType.QWEN not in user_facing_types
    assert AgentType.CLAUDE in user_facing_types

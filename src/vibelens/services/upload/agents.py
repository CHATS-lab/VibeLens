"""Upload spec per agent: where the data lives and how the user packages it.

This module is the single source of truth for upload-side agent metadata.
Add a new agent by extending AgentType and adding one entry here. The drift
check at import time prevents shipping a server with an AgentType that has
no upload spec.
"""

from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from vibelens.models.enums import AgentType


class ZipCommand(BaseModel):
    """One platform's shell snippet for producing the upload zip."""

    command: str = Field(description="Shell snippet the user pastes to produce the zip.")
    output: str = Field(description="Where the resulting zip lands. Shown in the UI.")


class UploadAgentSpec(BaseModel):
    """Agent metadata required to render the upload wizard."""

    agent_type: AgentType = Field(description="Canonical agent identifier.")
    display_name: str = Field(description="Human-readable label in the picker.")
    description: str = Field(default="", description="One-line tooltip in the agent picker.")
    source: Literal["local_zip", "external_export"] = Field(
        description="local_zip: user runs a shell command. external_export: user follows steps.",
    )
    user_facing: bool = Field(default=True, description="Whether to expose in the wizard.")
    commands: dict[str, ZipCommand] = Field(
        default_factory=dict,
        description=(
            "Per-OS shell snippet. Keyed by os_platform: macos, linux, windows. "
            "Omit a key when the agent doesn't run on that OS — frontend renders "
            "'not supported on $OS' for missing keys."
        ),
    )
    external_instructions: list[str] = Field(
        default_factory=list,
        description="Step-by-step text shown when source=external_export.",
    )


# `local_data_dir` is intentionally NOT here — the parser's LOCAL_DATA_DIR is the
# single source of truth. The upload spec is UX-only.


def _macos_zip(agent_dir: str, payload: str, output_name: str) -> ZipCommand:
    """macOS bash command. Outputs to ~/Desktop/ — the file should land
    somewhere the user will obviously find it after running the command.

    macOS resource forks (._*) and __MACOSX/ are excluded.
    """
    return ZipCommand(
        command=(
            f"cd {agent_dir} && zip -r ~/Desktop/{output_name} {payload}"
            " -x '**/._*' '**/__MACOSX/*'"
        ),
        output=f"~/Desktop/{output_name}",
    )


def _linux_zip(agent_dir: str, payload: str, output_name: str) -> ZipCommand:
    """Linux bash command. Outputs to ~/Desktop/ for visibility parity with
    macOS. ``mkdir -p`` is a safety net for headless setups without a
    pre-existing Desktop dir."""
    return ZipCommand(
        command=(
            f"mkdir -p ~/Desktop && cd {agent_dir} "
            f"&& zip -r ~/Desktop/{output_name} {payload}"
        ),
        output=f"~/Desktop/{output_name}",
    )


def _windows_zip(subdir: str, paths: str, output_name: str) -> ZipCommand:
    """Windows PowerShell Compress-Archive command. Outputs to the user's
    Desktop. All paths are quoted to survive home directories with spaces
    (e.g. ``C:\\Users\\Jane Smith``)."""
    return ZipCommand(
        command=(
            f'cd "$env:USERPROFILE\\{subdir}"; '
            f"Compress-Archive -Path {paths} "
            f'-DestinationPath "$env:USERPROFILE\\Desktop\\{output_name}"'
        ),
        output=f"%USERPROFILE%\\Desktop\\{output_name}",
    )


UPLOAD_SPECS: dict[AgentType, UploadAgentSpec] = {
    AgentType.CLAUDE: UploadAgentSpec(
        agent_type=AgentType.CLAUDE,
        display_name="Claude Code",
        description="Anthropic's official CLI",
        source="local_zip",
        commands={
            "macos": _macos_zip("~/.claude", "projects/", "claude-data.zip"),
            "linux": _linux_zip("~/.claude", "projects/", "claude-data.zip"),
            "windows": _windows_zip(".claude", "projects\\*", "claude-data.zip"),
        },
    ),
    AgentType.CODEX: UploadAgentSpec(
        agent_type=AgentType.CODEX,
        display_name="Codex CLI",
        description="OpenAI's coding CLI",
        source="local_zip",
        commands={
            "macos": _macos_zip("~/.codex", "sessions/ state_5.sqlite*", "codex-data.zip"),
            "linux": _linux_zip("~/.codex", "sessions/ state_5.sqlite*", "codex-data.zip"),
            "windows": _windows_zip(".codex", "sessions\\*, state_5.sqlite*", "codex-data.zip"),
        },
    ),
    AgentType.GEMINI: UploadAgentSpec(
        agent_type=AgentType.GEMINI,
        display_name="Gemini CLI",
        description="Google's coding CLI",
        source="local_zip",
        commands={
            # Gemini's tmp/ holds non-session files we don't want; explicit -i filters.
            "macos": ZipCommand(
                command=(
                    "cd ~/.gemini && zip -r ~/Desktop/gemini-data.zip tmp/"
                    " -i '*.json' -i '.project_root'"
                ),
                output="~/Desktop/gemini-data.zip",
            ),
            "linux": ZipCommand(
                command=(
                    "cd ~/.gemini && zip -r ~/Desktop/gemini-data.zip tmp/"
                    " -i '*.json' -i '.project_root'"
                ),
                output="~/Desktop/gemini-data.zip",
            ),
            "windows": _windows_zip(".gemini", "tmp\\*", "gemini-data.zip"),
        },
    ),
    AgentType.CLAUDE_WEB: UploadAgentSpec(
        agent_type=AgentType.CLAUDE_WEB,
        display_name="Claude Web",
        description="claude.ai data export",
        source="external_export",
        external_instructions=[
            "Open claude.ai → Settings",
            'Scroll to "Export Data" and click Export',
            "Wait for the email, then download the zip",
            "Upload the downloaded zip below",
        ],
    ),
    AgentType.CODEBUDDY: UploadAgentSpec(
        agent_type=AgentType.CODEBUDDY,
        display_name="Code Buddy",
        description="Tencent CodeBuddy CLI",
        source="local_zip",
        commands={
            "macos": _macos_zip("~/.codebuddy", "projects/", "codebuddy-data.zip"),
            "linux": _linux_zip("~/.codebuddy", "projects/", "codebuddy-data.zip"),
            "windows": _windows_zip(".codebuddy", "projects\\*", "codebuddy-data.zip"),
        },
    ),
    AgentType.COPILOT: UploadAgentSpec(
        agent_type=AgentType.COPILOT,
        display_name="Copilot CLI",
        description="GitHub's official CLI",
        source="local_zip",
        commands={
            "macos": _macos_zip("~/.copilot", "session-state/", "copilot-data.zip"),
            "linux": _linux_zip("~/.copilot", "session-state/", "copilot-data.zip"),
            "windows": _windows_zip(".copilot", "session-state\\*", "copilot-data.zip"),
        },
    ),
    AgentType.CURSOR: UploadAgentSpec(
        agent_type=AgentType.CURSOR,
        display_name="Cursor",
        description="Cursor's agent chats",
        source="local_zip",
        commands={
            "macos": _macos_zip("~/.cursor", "chats/", "cursor-data.zip"),
            "linux": _linux_zip("~/.cursor", "chats/", "cursor-data.zip"),
            "windows": _windows_zip(".cursor", "chats\\*", "cursor-data.zip"),
        },
    ),
    AgentType.HERMES: UploadAgentSpec(
        agent_type=AgentType.HERMES,
        display_name="Hermes",
        description="Hermes Agent",
        source="local_zip",
        commands={
            "macos": _macos_zip("~/.hermes", "sessions/ state.db*", "hermes-data.zip"),
            "linux": _linux_zip("~/.hermes", "sessions/ state.db*", "hermes-data.zip"),
            "windows": _windows_zip(".hermes", "sessions\\*, state.db*", "hermes-data.zip"),
        },
    ),
    AgentType.KILO: UploadAgentSpec(
        agent_type=AgentType.KILO,
        display_name="Kilo",
        description="Local-first coding agent",
        source="local_zip",
        commands={
            # Windows omitted: kilo doesn't ship for Windows.
            "macos": _macos_zip(
                "~/.local/share/kilo", "kilo.db*", "kilo-data.zip"
            ),
            "linux": _linux_zip(
                "~/.local/share/kilo", "kilo.db*", "kilo-data.zip"
            ),
        },
    ),
    AgentType.KIRO: UploadAgentSpec(
        agent_type=AgentType.KIRO,
        display_name="Kiro",
        description="AWS Kiro CLI",
        source="local_zip",
        commands={
            "macos": _macos_zip("~/.kiro", "sessions/", "kiro-data.zip"),
            "linux": _linux_zip("~/.kiro", "sessions/", "kiro-data.zip"),
            "windows": _windows_zip(".kiro", "sessions\\*", "kiro-data.zip"),
        },
    ),
    AgentType.OPENCLAW: UploadAgentSpec(
        agent_type=AgentType.OPENCLAW,
        display_name="OpenClaw",
        description="OpenClaw agent",
        source="local_zip",
        commands={
            "macos": _macos_zip("~/.openclaw", "agents/", "openclaw-data.zip"),
            "linux": _linux_zip("~/.openclaw", "agents/", "openclaw-data.zip"),
            "windows": _windows_zip(".openclaw", "agents\\*", "openclaw-data.zip"),
        },
    ),
    AgentType.OPENCODE: UploadAgentSpec(
        agent_type=AgentType.OPENCODE,
        display_name="OpenCode",
        description="SST OpenCode",
        source="local_zip",
        # Hidden from the wizard — Kilo (the fork) covers the same SQLite
        # database family and is the only one we surface to users.
        user_facing=False,
        commands={
            "macos": _macos_zip(
                "~/.local/share/opencode",
                "opencode.db* storage/ snapshot/",
                "opencode-data.zip",
            ),
            "linux": _linux_zip(
                "~/.local/share/opencode",
                "opencode.db* storage/ snapshot/",
                "opencode-data.zip",
            ),
        },
    ),
    AgentType.DATACLAW: UploadAgentSpec(
        agent_type=AgentType.DATACLAW,
        display_name="Dataclaw",
        description="HuggingFace research dataset",
        # Hidden from the user-facing wizard — researcher-only format.
        source="external_export",
        user_facing=False,
        external_instructions=[
            "Visit huggingface.co/datasets/chats-lab/dataclaw",
            "Download the conversations.jsonl file you want to import",
            "Zip it: `zip dataclaw-data.zip conversations.jsonl`",
            "Upload the zip below",
        ],
    ),
    # Skill-only agents (no on-disk session parser yet) — needed only to
    # satisfy the drift check; hidden from the wizard via user_facing=False.
    AgentType.AIDER: UploadAgentSpec(
        agent_type=AgentType.AIDER,
        display_name="Aider",
        source="external_export",
        user_facing=False,
    ),
    AgentType.ANTIGRAVITY: UploadAgentSpec(
        agent_type=AgentType.ANTIGRAVITY,
        display_name="Antigravity",
        source="external_export",
        user_facing=False,
    ),
    AgentType.KIMI: UploadAgentSpec(
        agent_type=AgentType.KIMI,
        display_name="Kimi",
        source="external_export",
        user_facing=False,
    ),
    AgentType.OPENHANDS: UploadAgentSpec(
        agent_type=AgentType.OPENHANDS,
        display_name="OpenHands",
        source="external_export",
        user_facing=False,
    ),
    AgentType.QWEN: UploadAgentSpec(
        agent_type=AgentType.QWEN,
        display_name="Qwen",
        source="external_export",
        user_facing=False,
    ),
    # Capability-matrix expansion (2026-04-25): 12 new agents are matrix-only,
    # not exposed in the upload wizard until a parser ships per-agent.
    AgentType.AMP: UploadAgentSpec(
        agent_type=AgentType.AMP,
        display_name="Amp",
        source="external_export",
        user_facing=False,
    ),
    AgentType.AUGMENT: UploadAgentSpec(
        agent_type=AgentType.AUGMENT,
        display_name="Augment",
        source="external_export",
        user_facing=False,
    ),
    AgentType.AUTOCLAW: UploadAgentSpec(
        agent_type=AgentType.AUTOCLAW,
        display_name="AutoClaw",
        source="external_export",
        user_facing=False,
    ),
    AgentType.EASYCLAW: UploadAgentSpec(
        agent_type=AgentType.EASYCLAW,
        display_name="EasyClaw",
        source="external_export",
        user_facing=False,
    ),
    AgentType.FACTORY: UploadAgentSpec(
        agent_type=AgentType.FACTORY,
        display_name="Factory Droid",
        source="external_export",
        user_facing=False,
    ),
    AgentType.JUNIE: UploadAgentSpec(
        agent_type=AgentType.JUNIE,
        display_name="Junie",
        source="external_export",
        user_facing=False,
    ),
    AgentType.OB1: UploadAgentSpec(
        agent_type=AgentType.OB1,
        display_name="OB-1",
        source="external_export",
        user_facing=False,
    ),
    AgentType.QCLAW: UploadAgentSpec(
        agent_type=AgentType.QCLAW,
        display_name="QClaw",
        source="external_export",
        user_facing=False,
    ),
    AgentType.QODER: UploadAgentSpec(
        agent_type=AgentType.QODER,
        display_name="Qoder",
        source="external_export",
        user_facing=False,
    ),
    AgentType.TRAE: UploadAgentSpec(
        agent_type=AgentType.TRAE,
        display_name="Trae",
        source="external_export",
        user_facing=False,
    ),
    AgentType.TRAE_CN: UploadAgentSpec(
        agent_type=AgentType.TRAE_CN,
        display_name="Trae CN",
        source="external_export",
        user_facing=False,
    ),
    AgentType.WORKBUDDY: UploadAgentSpec(
        agent_type=AgentType.WORKBUDDY,
        display_name="WorkBuddy",
        source="external_export",
        user_facing=False,
    ),
}


_missing = set(AgentType) - set(UPLOAD_SPECS)
if _missing:
    raise RuntimeError(
        f"AgentType values without upload spec: {sorted(_missing)}. "
        "Add an entry to UPLOAD_SPECS in services/upload/agents.py."
    )


def list_user_facing_specs() -> list[UploadAgentSpec]:
    """Return the user-facing registry the frontend renders."""
    return [s for s in UPLOAD_SPECS.values() if s.user_facing]


def get_upload_command(agent_type: str, os_platform: str) -> dict:
    """Backward-compat lookup for the legacy /upload/commands route.

    Returns a dict with 'command' and 'description' keys. Raises HTTP 400
    on unknown agent or os.
    """
    try:
        agent = AgentType(agent_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown agent_type: {agent_type}") from None
    spec = UPLOAD_SPECS.get(agent)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"No commands for agent: {agent}")
    if spec.source == "external_export":
        first = spec.external_instructions[0] if spec.external_instructions else "External export"
        return {
            "command": f"# {first}",
            "description": "Upload the zip from the external export",
        }
    zc = spec.commands.get(os_platform)
    if zc is None:
        raise HTTPException(status_code=400, detail=f"Unknown os_platform: {os_platform}")
    return {"command": zc.command, "description": f"Output: {zc.output}"}

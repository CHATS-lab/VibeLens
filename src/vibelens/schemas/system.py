"""System-level request and response models."""

from typing import Literal

from pydantic import BaseModel, Field

InstallMethod = Literal["uv", "pip", "npx", "source", "unknown"]


class InstallCommands(BaseModel):
    """Upgrade commands for the three distribution channels."""

    uv: str = Field(description="Upgrade command for uv tool installs.")
    pip: str = Field(description="Upgrade command for pip installs.")
    npx: str = Field(description="Upgrade command for npm/npx installs.")


class VersionInfo(BaseModel):
    """Versioning snapshot returned by ``GET /api/version``."""

    current: str = Field(description="Currently running VibeLens version.")
    latest: str | None = Field(
        description=(
            "Latest stable, non-yanked release on PyPI. Null if the check was "
            "skipped, disabled, or failed."
        )
    )
    update_available: bool = Field(
        description="True when latest is a newer stable version than current."
    )
    is_dev_build: bool = Field(
        description=(
            "True when current is newer than the latest PyPI release "
            "(source/dev install)."
        )
    )
    install_method: InstallMethod = Field(
        description="Best-guess install method used for the running process."
    )
    install_commands: InstallCommands = Field(
        description="Upgrade commands keyed by install channel."
    )

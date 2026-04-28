"""Agent capabilities endpoint — single source of truth for "which agents
can I sync this extension type to" across the entire frontend.

The frontend ``client.syncTargets.get()`` cache derives ``Record<type,
SyncTarget[]>`` from this response. The legacy ``sync_targets`` field on
list responses (``/extensions/{type}``) is now redundant; consumers should
prefer this endpoint.
"""

from collections.abc import Callable

from fastapi import APIRouter

from vibelens.deps import (
    get_command_service,
    get_hook_service,
    get_plugin_service,
    get_skill_service,
    get_subagent_service,
)
from vibelens.models.enums import AgentExtensionType
from vibelens.schemas.extensions import AgentCapabilitiesResponse, AgentCapability
from vibelens.services.extensions.platforms import (
    EXTENSION_TYPE_DIR_FIELD,
    PLATFORMS,
    platform_dir_for,
)

router = APIRouter(tags=["agents"])

# Per-type service factory. Keyed by ``AgentExtensionType`` so callers
# don't pass raw strings. Includes only types that have a managed service —
# matches ``EXTENSION_TYPE_DIR_FIELD`` so iteration order is consistent.
_SERVICE_FACTORIES: dict[AgentExtensionType, Callable[[], object]] = {
    AgentExtensionType.SKILL: get_skill_service,
    AgentExtensionType.COMMAND: get_command_service,
    AgentExtensionType.SUBAGENT: get_subagent_service,
    AgentExtensionType.HOOK: get_hook_service,
    AgentExtensionType.PLUGIN: get_plugin_service,
}


@router.get("/agents", response_model=AgentCapabilitiesResponse)
def list_agents() -> AgentCapabilitiesResponse:
    """List all platforms with install state, supported types, install dirs,
    and current item counts — everything the frontend needs to render install
    dialogs and sync pills.

    ``installed`` mirrors :func:`installed_platforms`: an agent counts as
    installed when ``root`` *or* any ``extra_paths`` value exists on disk.
    Agents like Kilo split their layout across two parents and need this
    OR-detect.
    """
    counts: dict[tuple[str, AgentExtensionType], int] = {}
    for ext_type in EXTENSION_TYPE_DIR_FIELD:
        for target in _SERVICE_FACTORIES[ext_type]().list_sync_targets():
            counts[(target.agent, ext_type)] = target.count

    agents: list[AgentCapability] = []
    # Sort platforms by source key so every agent listing in the frontend
    # comes out alphabetical without per-consumer sort calls.
    for platform in sorted(PLATFORMS.values(), key=lambda p: p.source.value.lower()):
        installed = any(
            d.expanduser().is_dir() for d in (platform.root, *platform.extra_paths.values())
        )
        dirs_by_type: dict[str, str] = {}
        counts_by_type: dict[str, int] = {}
        for ext_type in platform.supported_types:
            install_dir = platform_dir_for(platform, ext_type)
            if install_dir is None:
                continue
            dirs_by_type[ext_type.value] = str(install_dir.expanduser().resolve())
            counts_by_type[ext_type.value] = counts.get((platform.source.value, ext_type), 0)
        agents.append(
            AgentCapability(
                key=platform.source.value,
                installed=installed,
                supported_types=sorted(t.value for t in platform.supported_types),
                dirs_by_type=dirs_by_type,
                counts_by_type=counts_by_type,
            )
        )
    return AgentCapabilitiesResponse(agents=agents)

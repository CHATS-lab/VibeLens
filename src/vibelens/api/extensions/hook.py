"""Hook management API routes."""

from fastapi import APIRouter, HTTPException

from vibelens.deps import get_hook_service
from vibelens.schemas.extensions import ExtensionSyncRequest, SyncTargetResponse
from vibelens.schemas.hooks import (
    HookDetailResponse,
    HookInstallRequest,
    HookListResponse,
    HookModifyRequest,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/hooks", tags=["hooks"])

DEFAULT_PAGE_SIZE = 50


@router.post("/import/{agent}")
def import_from_agent(agent: str, name: str, event_name: str, matcher: str) -> dict:
    """Import a hook group from an agent's settings.json into central.

    Query params:
        name: Kebab-case name for the new central hook.
        event_name: Event name (e.g. ``PreToolUse``).
        matcher: Matcher field identifying the group.
    """
    service = get_hook_service()
    try:
        hook = service.import_from_agent(
            agent=agent, name=name, event_name=event_name, matcher=matcher
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return hook.model_dump()


@router.get("")
def list_hooks(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    search: str | None = None,
    refresh: bool = False,
) -> HookListResponse:
    """List hooks with pagination, optional search, and sync targets."""
    service = get_hook_service()
    if refresh:
        service.invalidate()
    hooks, total = service.list_items(page=page, page_size=page_size, search=search)
    targets = sorted(service.list_sync_targets(), key=lambda t: t.agent.lower())
    return HookListResponse(
        items=hooks,
        total=total,
        page=page,
        page_size=page_size,
        sync_targets=[SyncTargetResponse(agent=t.agent, count=t.count, dir=t.dir) for t in targets],
    )


@router.get("/{name}")
def get_hook(name: str) -> HookDetailResponse:
    """Get full hook detail including raw JSON content."""
    service = get_hook_service()
    try:
        hook = service.get_item(name)
        content = service.get_item_content(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Hook {name!r} not found") from None
    return HookDetailResponse(
        hook=hook,
        content=content,
        path=service.get_item_path(name),
    )


@router.post("")
def install_hook(req: HookInstallRequest) -> dict:
    """Install a new hook."""
    service = get_hook_service()
    try:
        hook = service.install(
            name=req.name,
            description=req.description,
            topics=req.topics,
            hook_config=req.hook_config,
            sync_to=req.sync_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return hook.model_dump()


@router.put("/{name}")
def modify_hook(name: str, req: HookModifyRequest) -> dict:
    """Update a hook's fields (partial update). Auto-syncs where installed."""
    service = get_hook_service()
    try:
        hook = service.modify(
            name=name,
            description=req.description,
            topics=req.topics,
            hook_config=req.hook_config,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Hook {name!r} not found") from None
    return hook.model_dump()


@router.delete("/{name}")
def uninstall_hook(name: str) -> dict:
    """Delete a hook from central and every agent settings.json."""
    service = get_hook_service()
    try:
        removed_from = service.uninstall(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Hook {name!r} not found") from None
    return {"deleted": name, "removed_from": removed_from}


@router.post("/{name}/agents")
def sync_hook(name: str, req: ExtensionSyncRequest) -> dict:
    """Sync a hook to specified agent platforms."""
    service = get_hook_service()
    try:
        results = service.sync_to_agents(name, req.agents)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Hook {name!r} not found") from None
    hook = service.get_item(name)
    return {"name": name, "results": results, "hook": hook.model_dump()}


@router.delete("/{name}/agents/{agent}")
def unsync_hook(name: str, agent: str) -> dict:
    """Remove a hook from a single agent platform."""
    service = get_hook_service()
    try:
        service.uninstall_from_agent(name, agent)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Hook {name!r} not in agent {agent!r}"
        ) from None
    hook = service.get_item(name)
    return {"name": name, "agent": agent, "hook": hook.model_dump()}

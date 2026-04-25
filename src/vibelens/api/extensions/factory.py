"""Lightweight route factory for file-based extension CRUD (skill, command, subagent)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from vibelens.models.enums import AgentExtensionType
from vibelens.schemas.extensions import (
    ExtensionDetailResponse,
    ExtensionFileResponse,
    ExtensionInstallRequest,
    ExtensionListResponse,
    ExtensionModifyRequest,
    ExtensionSyncRequest,
    ExtensionTreeEntry,
    ExtensionTreeResponse,
    SyncTargetResponse,
)
from vibelens.services.extensions.base_service import BaseExtensionService

DEFAULT_PAGE_SIZE = 50
TREE_MAX_ENTRIES = 500
FILE_READ_MAX_BYTES = 200_000


def build_typed_router(
    service_getter: Callable[[], BaseExtensionService[Any]], extension_type: AgentExtensionType
) -> APIRouter:
    """Generate CRUD router for a file-based extension type.

    Used for skill, command, subagent, plugin. Hook has a hand-written router.
    """
    type_name = extension_type.value
    plural = f"{type_name}s"
    label = type_name.capitalize()
    router = APIRouter(prefix=f"/{plural}", tags=[plural])

    @router.post("/import/{agent}")
    def import_from_agent(agent: str) -> dict:
        service = service_getter()
        try:
            imported = service.import_all_from_agent(agent)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
        return {"agent": agent, "imported": imported, "count": len(imported)}

    @router.get("")
    def list_items(
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: str | None = None,
        refresh: bool = False,
    ) -> ExtensionListResponse:
        service = service_getter()
        if refresh:
            service.invalidate()
        items, total = service.list_items(page=page, page_size=page_size, search=search)
        targets = service.list_sync_targets()
        return ExtensionListResponse(
            items=[i.model_dump() for i in items],
            total=total,
            page=page,
            page_size=page_size,
            sync_targets=[
                SyncTargetResponse(agent=t.agent, count=t.count, dir=t.dir) for t in targets
            ],
        )

    @router.get("/{name}")
    def get_item(name: str) -> ExtensionDetailResponse:
        service = service_getter()
        try:
            item = service.get_item(name)
            content = service.get_item_content(name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"{label} {name!r} not found") from None
        return ExtensionDetailResponse(
            item=item.model_dump(), content=content, path=service.get_item_path(name)
        )

    @router.get("/{name}/tree")
    def list_item_files(name: str) -> ExtensionTreeResponse:
        service = service_getter()
        root = Path(service.get_item_root(name))
        if not root.exists():
            raise HTTPException(status_code=404, detail=f"{label} {name!r} not found")
        entries, truncated = _walk_tree(root)
        return ExtensionTreeResponse(
            name=name, root=str(root), entries=entries, truncated=truncated
        )

    @router.get("/{name}/files/{path:path}")
    def read_item_file(name: str, path: str) -> ExtensionFileResponse:
        service = service_getter()
        root = Path(service.get_item_root(name))
        if not root.exists():
            raise HTTPException(status_code=404, detail=f"{label} {name!r} not found")
        return _read_file_within(root=root, relative=path)

    @router.post("")
    def install_item(req: ExtensionInstallRequest) -> dict:
        service = service_getter()
        try:
            item = service.install(
                name=req.name,
                content=req.content,
                sync_to=req.sync_to,
                link_type=req.link_type,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return item.model_dump()

    @router.put("/{name}")
    def modify_item(name: str, req: ExtensionModifyRequest) -> dict:
        service = service_getter()
        try:
            item = service.modify(name=name, content=req.content, link_type=req.link_type)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"{label} {name!r} not found") from None
        return item.model_dump()

    @router.delete("/{name}")
    def uninstall_item(name: str) -> dict:
        service = service_getter()
        try:
            removed_from = service.uninstall(name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"{label} {name!r} not found") from None
        return {"deleted": name, "removed_from": removed_from}

    @router.post("/{name}/agents")
    def sync_item(name: str, req: ExtensionSyncRequest) -> dict:
        service = service_getter()
        try:
            results = service.sync_to_agents(name, req.agents, link_type=req.link_type)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"{label} {name!r} not found") from None
        item = service.get_item(name)
        return {"name": name, "results": results, type_name: item.model_dump()}

    @router.delete("/{name}/agents/{agent}")
    def unsync_item(name: str, agent: str) -> dict:
        service = service_getter()
        try:
            service.uninstall_from_agent(name, agent)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"{label} {name!r} not in agent {agent!r}"
            ) from None
        item = service.get_item(name)
        return {"name": name, "agent": agent, type_name: item.model_dump()}

    return router


def _walk_tree(root: Path) -> tuple[list[ExtensionTreeEntry], bool]:
    """Flatten a directory into sorted (path, kind) entries, capped at the limit.

    Single-file roots produce one entry with the file's basename. Directory
    roots walk recursively, skipping hidden OS junk like ``.DS_Store``.
    """
    if root.is_file():
        return [ExtensionTreeEntry(path=root.name, kind="file", size=root.stat().st_size)], False

    entries: list[ExtensionTreeEntry] = []
    truncated = False
    for p in sorted(root.rglob("*")):
        if p.name == ".DS_Store":
            continue
        if len(entries) >= TREE_MAX_ENTRIES:
            truncated = True
            break
        rel = p.relative_to(root).as_posix()
        if p.is_dir():
            entries.append(ExtensionTreeEntry(path=rel, kind="dir", size=None))
        elif p.is_file():
            entries.append(ExtensionTreeEntry(path=rel, kind="file", size=p.stat().st_size))
    return entries, truncated


def _read_file_within(*, root: Path, relative: str) -> ExtensionFileResponse:
    """Read a text file rooted at ``root``, guarding against path escapes."""
    if root.is_file():
        if relative not in ("", root.name):
            raise HTTPException(status_code=404, detail=f"File {relative!r} not found")
        return _read_text_capped(path=root, relative=root.name)

    try:
        candidate = (root / relative).resolve(strict=False)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid path: {exc}") from exc
    root_resolved = root.resolve(strict=False)
    if not candidate.is_relative_to(root_resolved):
        raise HTTPException(status_code=404, detail="File not found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return _read_text_capped(path=candidate, relative=relative)


def _read_text_capped(*, path: Path, relative: str) -> ExtensionFileResponse:
    """Read up to ``FILE_READ_MAX_BYTES`` of UTF-8 text from ``path``."""
    raw = path.read_bytes()
    truncated = len(raw) > FILE_READ_MAX_BYTES
    payload = raw[:FILE_READ_MAX_BYTES] if truncated else raw
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    return ExtensionFileResponse(path=relative, content=text, truncated=truncated)

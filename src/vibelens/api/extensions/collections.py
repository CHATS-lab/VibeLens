"""FastAPI router for ExtensionCollection CRUD + install + export/import."""

import json
from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from vibelens.models.collection import ExtensionCollection
from vibelens.schemas.extensions import (
    CollectionCreateRequest,
    CollectionImportRequest,
    CollectionInstallRequest,
    CollectionInstallResponse,
    CollectionListResponse,
    CollectionResponse,
    CollectionUpdateRequest,
)
from vibelens.services.extensions.collection_service import CollectionService


def _to_response(collection: ExtensionCollection) -> CollectionResponse:
    return CollectionResponse.model_validate(collection.model_dump(mode="json"))


def build_collections_router(
    service_getter: Callable[[], CollectionService],
) -> APIRouter:
    """Build the /collections sub-router."""
    router = APIRouter(prefix="/collections", tags=["collections"])

    @router.post("")
    def create_collection(req: CollectionCreateRequest) -> CollectionResponse:
        service = service_getter()
        try:
            coll = service.create(
                name=req.name,
                description=req.description,
                items=[(it.extension_type, it.name) for it in req.items],
                tags=req.tags,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _to_response(coll)

    @router.get("")
    def list_collections() -> CollectionListResponse:
        service = service_getter()
        items = [_to_response(c) for c in service.list_all()]
        return CollectionListResponse(items=items, total=len(items))

    @router.get("/{name}")
    def get_collection(name: str) -> CollectionResponse:
        service = service_getter()
        try:
            return _to_response(service.get(name))
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown collection: {name!r}") from None

    @router.put("/{name}")
    def update_collection(name: str, req: CollectionUpdateRequest) -> CollectionResponse:
        service = service_getter()
        try:
            coll = service.update(
                name=name,
                description=req.description,
                items=(
                    [(it.extension_type, it.name) for it in req.items]
                    if req.items is not None
                    else None
                ),
                tags=req.tags,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown collection: {name!r}") from None
        return _to_response(coll)

    @router.delete("/{name}")
    def delete_collection(name: str) -> dict:
        service = service_getter()
        deleted = service.delete(name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"unknown collection: {name!r}")
        return {"deleted": name}

    @router.post("/{name}/install")
    def install_collection(name: str, req: CollectionInstallRequest) -> CollectionInstallResponse:
        service = service_getter()
        try:
            results = service.install_to_agents(
                collection_name=name,
                agents=req.agents,
                link_type=req.link_type,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown collection: {name!r}") from None
        return CollectionInstallResponse(name=name, results=results)

    @router.get("/{name}/export")
    def export_collection(name: str) -> dict:
        service = service_getter()
        try:
            payload = service.export_json(name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown collection: {name!r}") from None
        return json.loads(payload)

    @router.post("/import")
    def import_collection(req: CollectionImportRequest) -> CollectionResponse:
        service = service_getter()
        try:
            imported = service.import_json(json.dumps(req.payload))
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _to_response(imported)

    return router

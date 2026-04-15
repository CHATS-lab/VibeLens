"""Extension browsing and install endpoints."""

from fastapi import APIRouter, HTTPException, Query

from vibelens.schemas.extensions import (
    ExtensionInstallRequest,
    ExtensionInstallResponse,
    ExtensionListResponse,
    ExtensionMetaResponse,
)
from vibelens.services.extensions.browse import (
    get_extension_by_id,
    get_extension_metadata,
    install_extension,
    list_extensions,
    resolve_extension_content,
)

router = APIRouter(prefix="/extensions", tags=["extensions"])


@router.get("")
async def list_extensions_endpoint(
    search: str | None = Query(default=None, description="Search name, description, tags"),
    extension_type: str | None = Query(default=None, description="Filter by extension type"),
    category: str | None = Query(default=None, description="Filter by category"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    sort: str = Query(
        default="quality", description="Sort: quality, name, popularity, recent, relevance"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=200, description="Items per page"),
) -> ExtensionListResponse:
    """List extension catalog items with search, filters, and pagination."""
    try:
        items, total = list_extensions(
            search=search,
            extension_type=extension_type,
            category=category,
            platform=platform,
            sort=sort,
            page=page,
            per_page=per_page,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExtensionListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/meta")
async def extension_meta() -> ExtensionMetaResponse:
    """Return extension catalog metadata for frontend filter and sort options."""
    try:
        categories, has_profile = get_extension_metadata()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExtensionMetaResponse(categories=categories, has_profile=has_profile)


@router.get("/{item_id:path}/content")
async def get_extension_content(item_id: str) -> dict:
    """Fetch displayable content for an extension item."""
    try:
        return await resolve_extension_content(item_id=item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id:path}/install")
async def install_extension_endpoint(
    item_id: str, body: ExtensionInstallRequest
) -> ExtensionInstallResponse:
    """Install an extension item to the target agent platform."""
    try:
        name, path = install_extension(
            item_id=item_id, target_platform=body.target_platform, overwrite=body.overwrite
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail="File already exists. Set overwrite=true to replace."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExtensionInstallResponse(
        success=True,
        installed_path=str(path),
        message=f"Installed {name} to {path}",
    )


@router.get("/{item_id:path}")
async def get_extension_item(item_id: str) -> dict:
    """Get full extension item by ID, including install_content."""
    item = get_extension_by_id(item_id=item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item.model_dump(mode="json")

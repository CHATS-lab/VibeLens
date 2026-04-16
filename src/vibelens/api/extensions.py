"""Extension browsing and install endpoints."""

from fastapi import APIRouter, HTTPException, Query

from vibelens.schemas.extensions import (
    ExtensionInstallRequest,
    ExtensionInstallResponse,
    ExtensionInstallResult,
    ExtensionListResponse,
    ExtensionMetaResponse,
)
from vibelens.services.extensions.catalog import (
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
    """Install an extension item to one or more agent platforms."""
    platforms = body.target_platforms
    results: dict[str, ExtensionInstallResult] = {}
    first_path = ""

    for platform in platforms:
        try:
            name, path = install_extension(
                item_id=item_id, target_platform=platform, overwrite=body.overwrite
            )
            results[platform] = ExtensionInstallResult(
                success=True, installed_path=str(path), message=f"Installed {name} to {path}"
            )
            if not first_path:
                first_path = str(path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileExistsError:
            # Auto-retry with overwrite for multi-platform installs
            try:
                name, path = install_extension(
                    item_id=item_id, target_platform=platform, overwrite=True
                )
                results[platform] = ExtensionInstallResult(
                    success=True, installed_path=str(path), message=f"Overwrote {name} at {path}"
                )
                if not first_path:
                    first_path = str(path)
            except Exception as inner_exc:
                results[platform] = ExtensionInstallResult(success=False, message=str(inner_exc))
        except ValueError as exc:
            results[platform] = ExtensionInstallResult(success=False, message=str(exc))

    all_ok = all(r.success for r in results.values())
    return ExtensionInstallResponse(
        success=all_ok,
        installed_path=first_path,
        message=f"Installed to {sum(r.success for r in results.values())}"
        f"/{len(platforms)} platforms",
        results=results,
    )


# NOTE: This catch-all detail route must be declared LAST. The `:path` converter
# is greedy, so declaring it before `/content` or `/install` routes causes it to
# swallow those suffixes for item IDs containing slashes or colons.
@router.get("/{item_id:path}")
async def get_extension_item(item_id: str) -> dict:
    """Get full extension item by ID, including install_content."""
    item = get_extension_by_id(item_id=item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item.model_dump(mode="json")

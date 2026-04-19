"""Extension catalog browsing and install endpoints."""

from fastapi import APIRouter, HTTPException, Query

from vibelens.schemas.extensions import (
    CatalogInstallRequest,
    CatalogInstallResponse,
    CatalogInstallResult,
    CatalogListResponse,
    ExtensionFileResponse,
    ExtensionMetaResponse,
    ExtensionTreeEntry,
    ExtensionTreeResponse,
)
from vibelens.services.extensions.catalog import (
    fetch_extension_file,
    get_extension_metadata,
    install_extension,
    list_extension_tree,
    list_extensions,
    resolve_extension_content,
)
from vibelens.storage.extension.catalog import load_catalog
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["catalog"])


@router.get("")
async def list_extensions_endpoint(
    search: str | None = Query(default=None, description="Search name, description, topics."),
    extension_type: str | None = Query(default=None, description="Filter by extension type."),
    category: str | None = Query(
        default=None,
        deprecated=True,
        description="Deprecated: filter ignored since the 2026-04 catalog migration.",
    ),
    platform: str | None = Query(
        default=None,
        deprecated=True,
        description="Deprecated: platforms are not derived in this release.",
    ),
    sort: str = Query(
        default="quality", description="Sort: quality, name, popularity, recent, relevance."
    ),
    page: int = Query(default=1, ge=1, description="Page number."),
    per_page: int = Query(default=50, ge=1, le=200, description="Items per page."),
) -> CatalogListResponse:
    """List extension catalog items with search, type filter, and pagination.

    The ``category`` and ``platform`` query parameters are accepted for
    backward compatibility with older clients and ignored server-side.
    """
    if category is not None or platform is not None:
        logger.debug("ignoring deprecated filter(s): category=%r platform=%r", category, platform)
    try:
        items, total = list_extensions(
            search=search, extension_type=extension_type, sort=sort, page=page, per_page=per_page
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CatalogListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/meta")
async def extension_meta() -> ExtensionMetaResponse:
    """Return catalog-wide topics + profile availability for filter/sort UI."""
    try:
        topics, has_profile = get_extension_metadata()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExtensionMetaResponse(topics=topics, has_profile=has_profile)


@router.get("/{item_id:path}/content")
async def get_extension_content(item_id: str) -> dict:
    """Fetch displayable content for an extension item."""
    try:
        return await resolve_extension_content(item_id=item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{item_id:path}/tree")
async def get_extension_tree(item_id: str) -> ExtensionTreeResponse:
    """List the remote file structure for a catalog item (via GitHub Contents API)."""
    try:
        payload = list_extension_tree(item_id=item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExtensionTreeResponse(
        name=payload["name"],
        root=payload["root"],
        entries=[ExtensionTreeEntry(**e) for e in payload["entries"]],
        truncated=payload["truncated"],
    )


@router.get("/{item_id:path}/files/{relative:path}")
async def get_extension_file(item_id: str, relative: str) -> ExtensionFileResponse:
    """Fetch a single file from a catalog item's remote tree."""
    try:
        payload = fetch_extension_file(item_id=item_id, relative=relative)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExtensionFileResponse(**payload)


@router.post("/{item_id:path}/install")
async def install_extension_endpoint(
    item_id: str, body: CatalogInstallRequest
) -> CatalogInstallResponse:
    """Install an extension item to one or more agent platforms.

    HOOK / MCP_SERVER / REPO items return 501 (service gates them).
    """
    platforms = body.target_platforms
    logger.info(
        "Install request: item=%s, platforms=%s, overwrite=%s", item_id, platforms, body.overwrite
    )
    results: dict[str, CatalogInstallResult] = {}
    first_path = ""

    for platform in platforms:
        try:
            name, path = install_extension(
                item_id=item_id, target_platform=platform, overwrite=body.overwrite
            )
            results[platform] = CatalogInstallResult(
                success=True, installed_path=str(path), message=f"Installed {name} to {path}"
            )
            if not first_path:
                first_path = str(path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except FileExistsError:
            try:
                name, path = install_extension(
                    item_id=item_id, target_platform=platform, overwrite=True
                )
                results[platform] = CatalogInstallResult(
                    success=True, installed_path=str(path), message=f"Overwrote {name} at {path}"
                )
                if not first_path:
                    first_path = str(path)
            except Exception as inner_exc:
                logger.error("Install retry failed for %s on %s: %s", item_id, platform, inner_exc)
                results[platform] = CatalogInstallResult(success=False, message=str(inner_exc))
        except (ValueError, OSError) as exc:
            logger.error("Install failed for %s on %s: %s", item_id, platform, exc)
            results[platform] = CatalogInstallResult(success=False, message=str(exc))

    all_ok = all(r.success for r in results.values())
    if not all_ok:
        failed = {k: v.message for k, v in results.items() if not v.success}
        logger.error("Install incomplete for %s: %s", item_id, failed)
    summary = f"Installed to {sum(r.success for r in results.values())}/{len(platforms)} platforms"
    return CatalogInstallResponse(
        success=all_ok, installed_path=first_path, message=summary, results=results
    )


# NOTE: This catch-all detail route must be declared LAST. The `:path` converter
# is greedy; declaring it before `/content` or `/install` causes it to swallow
# those suffixes for item IDs containing slashes or colons.
@router.get("/{item_id:path}")
async def get_extension_item(item_id: str) -> dict:
    """Return the full extension record; falls back to the summary on offset failure."""
    snap = load_catalog()
    if snap is None:
        raise HTTPException(status_code=404, detail="catalog unavailable")
    full = snap.get_full(item_id)
    if full is not None:
        return full.model_dump(mode="json")
    summary = snap.get_item(item_id)
    if summary is None:
        logger.error("catalog lookup failed: %s not found", item_id)
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    logger.warning("returning summary for %s; detail hydration failed", item_id)
    return summary.model_dump(mode="json")

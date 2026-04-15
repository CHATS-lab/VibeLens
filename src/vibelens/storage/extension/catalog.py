"""Runtime catalog loader and manager.

Loads catalog.json from the bundled path or user cache, picks the newer
version, and supports background update checks.
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr

from vibelens.models.extension import ExtensionItem
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

_cached_catalog: "CatalogSnapshot | None" = None
_cache_checked = False

# Bundled catalog shipped with VibeLens releases (inside package data)
# parent chain: extension/ → storage/ → vibelens/
_VIBELENS_PACKAGE_DIR = Path(__file__).resolve().parent.parent.parent
BUNDLED_CATALOG_PATH = _VIBELENS_PACKAGE_DIR / "data" / "catalog.json"
# User-cached catalog downloaded from update URL
USER_CATALOG_DIR = Path.home() / ".vibelens" / "catalog"


class CatalogSnapshot(BaseModel):
    """In-memory snapshot of the loaded catalog."""

    version: str = Field(description="Catalog version date string (e.g. 2026-04-10).")
    schema_version: int = Field(default=1, description="Catalog schema version.")
    items: list[ExtensionItem] = Field(default_factory=list, description="All catalog items.")
    _index: dict[str, ExtensionItem] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        """Build item lookup index after loading."""
        self._index = {item.extension_id: item for item in self.items}

    def get_item(self, item_id: str) -> ExtensionItem | None:
        """Look up a catalog item by ID.

        Args:
            item_id: Unique item identifier.

        Returns:
            ExtensionItem or None if not found.
        """
        return self._index.get(item_id)


def load_catalog_from_path(path: Path) -> CatalogSnapshot | None:
    """Load and parse a catalog.json file.

    Args:
        path: Path to catalog.json.

    Returns:
        CatalogSnapshot or None if file missing/corrupt.
    """
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        items = [ExtensionItem.model_validate(item) for item in data.get("items", [])]
        return CatalogSnapshot(
            version=data.get("version", "unknown"),
            schema_version=data.get("schema_version", 1),
            items=items,
        )
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.warning("Failed to load catalog from %s: %s", path, exc)
        return None


def load_catalog() -> CatalogSnapshot | None:
    """Load the best available catalog, cached after first call.

    On first call, checks both the user-cached catalog and the bundled
    catalog, picks whichever has the newer version date, and caches the
    result for all subsequent calls. Use ``reset_catalog_cache()`` to
    force a reload.

    Returns:
        CatalogSnapshot or None if no catalog available.
    """
    global _cached_catalog, _cache_checked  # noqa: PLW0603
    if _cache_checked:
        return _cached_catalog

    _cached_catalog = _load_best_catalog()
    _cache_checked = True
    return _cached_catalog


def reset_catalog_cache() -> None:
    """Clear the cached catalog so the next ``load_catalog()`` reloads from disk."""
    global _cached_catalog, _cache_checked  # noqa: PLW0603
    _cached_catalog = None
    _cache_checked = False


def _load_best_catalog() -> CatalogSnapshot | None:
    """Pick the best catalog from user cache and bundled paths.

    Returns:
        CatalogSnapshot or None if no catalog available.
    """
    user_path = USER_CATALOG_DIR / "catalog.json"
    user_catalog = load_catalog_from_path(user_path)
    bundled_catalog = load_catalog_from_path(BUNDLED_CATALOG_PATH)

    if user_catalog and bundled_catalog:
        if user_catalog.version >= bundled_catalog.version:
            logger.info(
                "Using user-cached catalog v%s (%d items)",
                user_catalog.version,
                len(user_catalog.items),
            )
            return user_catalog
        logger.info(
            "Using bundled catalog v%s (%d items)",
            bundled_catalog.version,
            len(bundled_catalog.items),
        )
        return bundled_catalog

    result = user_catalog or bundled_catalog
    if result:
        logger.info("Loaded catalog v%s (%d items)", result.version, len(result.items))
    else:
        logger.warning("No catalog available (checked %s and %s)", user_path, BUNDLED_CATALOG_PATH)
    return result

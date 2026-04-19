"""Runtime catalog loader for the bundled agent-tool-hub catalog.

Reads ``src/vibelens/data/catalog/`` produced by ``scripts/build_catalog.py``
and exposes a :class:`CatalogSnapshot` with summary items in memory and
byte-offset hydration for full records.
"""

import json
import shutil
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr

from vibelens.models.extension import AgentExtensionItem
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

USER_CATALOG_DIR = Path.home() / ".vibelens" / "catalog"

_cached_catalog: "CatalogSnapshot | None" = None
_cache_checked: bool = False


class CatalogManifest(BaseModel):
    """Top-level metadata emitted by ``scripts/build_catalog.py``."""

    generated_on: str = Field(description="YYYY-MM-DD source date from the hub.")
    hub_source: str = Field(description="Source directory name, e.g. full-20260418-122745.")
    total: int = Field(description="Number of summary items.")
    item_counts: dict[str, int] = Field(description="Items per type.")
    file_sizes: dict[str, int] = Field(description="Byte size of each agent-*.json file.")


class CatalogSnapshot(BaseModel):
    """In-memory catalog snapshot with on-demand detail hydration."""

    manifest: CatalogManifest
    items: list[AgentExtensionItem] = Field(
        default_factory=list, description="Summary-projected items."
    )
    data_dir: Path = Field(description="Directory containing agent-*.json for detail reads.")
    offsets: dict[str, tuple[str, int, int]] = Field(
        default_factory=dict,
        description="Byte offsets per extension_id; empty when sanity check fails.",
    )

    _index: dict[str, AgentExtensionItem] = PrivateAttr(default_factory=dict)
    _hydrated: set[str] = PrivateAttr(default_factory=set)

    def model_post_init(self, __context: object) -> None:
        self._index = {item.extension_id: item for item in self.items}

    def get_item(self, extension_id: str) -> AgentExtensionItem | None:
        """Return the summary or hydrated record for ``extension_id``."""
        return self._index.get(extension_id)

    def get_full(self, extension_id: str) -> AgentExtensionItem | None:
        """Hydrate and return the full record for ``extension_id``.

        Returns ``None`` if the id is unknown, offsets are degraded, or the
        byte slice fails to parse.
        """
        if extension_id in self._hydrated:
            return self._index.get(extension_id)

        offset_entry = self.offsets.get(extension_id)
        if offset_entry is None:
            return None

        type_value, byte_offset, byte_length = offset_entry
        path = self.data_dir / f"agent-{type_value}.json"
        try:
            with path.open("rb") as f:
                f.seek(byte_offset)
                buf = f.read(byte_length)
            full = AgentExtensionItem.model_validate_json(buf)
        except (OSError, ValueError) as exc:
            logger.warning(
                "failed to hydrate %s from %s (offset=%d length=%d): %s",
                extension_id,
                path,
                byte_offset,
                byte_length,
                exc,
            )
            return None

        self._index[extension_id] = full
        self._hydrated.add(extension_id)
        return full


def _catalog_dir() -> Path:
    """Locate the bundled catalog directory via importlib.resources."""
    return Path(str(files("vibelens") / "data" / "catalog"))


def load_catalog() -> CatalogSnapshot | None:
    """Load the bundled catalog, caching the result."""
    global _cached_catalog, _cache_checked  # noqa: PLW0603
    if _cache_checked:
        return _cached_catalog

    _cached_catalog = load_catalog_from_dir(_catalog_dir())
    _cache_checked = True
    return _cached_catalog


def reset_catalog_cache() -> None:
    """Drop the cached catalog so the next call reloads from disk."""
    global _cached_catalog, _cache_checked  # noqa: PLW0603
    _cached_catalog = None
    _cache_checked = False


def load_catalog_from_dir(dir_path: Path) -> CatalogSnapshot | None:
    """Load a catalog from the given directory layout.

    Returns ``None`` when the manifest or summary is missing. Raises
    ``FileNotFoundError`` if the manifest exists but per-type JSONs don't
    (catalog is structurally incomplete).
    """
    manifest_path = dir_path / "manifest.json"
    summary_path = dir_path / "catalog-summary.json"
    offsets_path = dir_path / "catalog-offsets.json"

    if not (manifest_path.is_file() and summary_path.is_file()):
        logger.warning("no catalog at %s (manifest or summary missing)", dir_path)
        return None

    manifest = CatalogManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    for type_value in manifest.item_counts:
        expected = dir_path / f"agent-{type_value}.json"
        if not expected.is_file():
            raise FileNotFoundError(f"catalog missing {expected.name}")

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    items = [AgentExtensionItem.model_validate(raw) for raw in summary_payload.get("items", [])]

    offsets: dict[str, tuple[str, int, int]] = {}
    if offsets_path.is_file():
        loaded = _load_offsets(offsets_path)
        if _sanity_check_offsets(loaded, dir_path):
            offsets = loaded
        else:
            logger.warning("catalog offsets failed sanity check; detail hydration disabled")

    snap = CatalogSnapshot(manifest=manifest, items=items, data_dir=dir_path, offsets=offsets)

    logger.info(
        "loaded catalog v%s (%d items, hub=%s)",
        manifest.generated_on,
        manifest.total,
        manifest.hub_source,
    )
    return snap


def _load_offsets(path: Path) -> dict[str, tuple[str, int, int]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: (v[0], int(v[1]), int(v[2])) for k, v in raw.items()}


def _sanity_check_offsets(offsets: dict[str, tuple[str, int, int]], dir_path: Path) -> bool:
    """Seek + parse first and last id per type. Return False on any failure."""
    by_type: dict[str, list[str]] = {}
    for eid, (type_value, _, _) in offsets.items():
        by_type.setdefault(type_value, []).append(eid)

    for type_value, ids in by_type.items():
        if not ids:
            continue
        path = dir_path / f"agent-{type_value}.json"
        if not path.is_file():
            return False
        try:
            with path.open("rb") as f:
                for eid in (ids[0], ids[-1]):
                    _, offset, length = offsets[eid]
                    f.seek(offset)
                    buf = f.read(length)
                    parsed = json.loads(buf)
                    if parsed.get("item_id") != eid:
                        return False
        except (OSError, ValueError):
            return False
    return True


def _clear_user_catalog() -> None:
    """Remove the legacy user catalog directory if present."""
    if USER_CATALOG_DIR.exists():
        logger.info("cleared legacy user catalog at %s", USER_CATALOG_DIR)
        shutil.rmtree(USER_CATALOG_DIR, ignore_errors=True)


load_catalog_from_path = load_catalog_from_dir

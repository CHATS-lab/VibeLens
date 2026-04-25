"""Filesystem JSON store for ExtensionCollection.

Lives next to the per-type extension stores even though it does not extend
``BaseExtensionStore``: collections are sibling artifacts about extensions
(named bundles of `(extension_type, name)` references), so they share the
``~/.vibelens/extensions/`` runtime root and belong in the same package.
"""

from pathlib import Path

from pydantic import ValidationError

from vibelens.models.collection import ExtensionCollection
from vibelens.utils.json import atomic_write_json, load_json_file
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# On-disk file extension for a single collection.
COLLECTION_EXTENSION = ".json"
# JSON indentation; matches HookStore so on-disk files are diff-friendly.
JSON_INDENT = 2


class CollectionStore:
    """CRUD on a directory of *.json collection files."""

    def __init__(self, root: Path, *, create: bool = False) -> None:
        self._root = root.expanduser().resolve()
        if create:
            self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _path_for(self, name: str) -> Path:
        return self._root / f"{name}{COLLECTION_EXTENSION}"

    def write(self, collection: ExtensionCollection) -> Path:
        """Serialize and persist a collection atomically."""
        path = self._path_for(collection.name)
        atomic_write_json(path, collection.model_dump(mode="json"), indent=JSON_INDENT)
        return path

    def read(self, name: str) -> ExtensionCollection | None:
        """Load a collection by name. Returns None if missing or unparseable."""
        data = load_json_file(self._path_for(name))
        if data is None:
            return None
        try:
            return ExtensionCollection.model_validate(data)
        except ValidationError as exc:
            logger.warning(f"Invalid collection schema for {name!r}: {exc}")
            return None

    def list_names(self) -> list[str]:
        """Return stems of all *.json files in the root."""
        if not self._root.is_dir():
            return []
        return sorted(
            entry.stem
            for entry in self._root.iterdir()
            if entry.is_file() and entry.suffix == COLLECTION_EXTENSION
        )

    def delete(self, name: str) -> bool:
        """Remove a collection file. Returns True if it existed."""
        try:
            self._path_for(name).unlink()
            return True
        except FileNotFoundError:
            return False

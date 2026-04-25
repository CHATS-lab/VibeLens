"""Base plugin store + canonical manifest parsing.

The central plugin store uses Claude's layout as the canonical on-disk
form:

    <root>/
    ├── my-plugin/
    │   ├── .claude-plugin/
    │   │   └── plugin.json          (required manifest)
    │   ├── skills/                  (optional)
    │   ├── commands/                (optional)
    │   └── agents/                  (optional)
    └── another-plugin/
        └── .claude-plugin/
            └── plugin.json

Per-agent stores subclass ``PluginStore`` and override
``_manifest_rel_path`` to match the agent's on-disk layout. The base
``_copy_impl`` renames the manifest location during cross-store copies
so each store writes its native layout.
"""

import json
import shutil
from pathlib import Path

from vibelens.models.extension.plugin import Plugin
from vibelens.storage.extension.base_store import BaseExtensionStore
from vibelens.utils.content import compute_content_hash
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CANONICAL_MANIFEST_DIR = ".claude-plugin"
MANIFEST_FILENAME = "plugin.json"
CANONICAL_MANIFEST_REL = Path(CANONICAL_MANIFEST_DIR) / MANIFEST_FILENAME


class PluginStore(BaseExtensionStore[Plugin]):
    """CRUD on a directory of plugin subdirectories using Claude's layout.

    Subclasses override ``_manifest_rel_path`` to place the manifest
    elsewhere (e.g. ``Path(".codex-plugin/plugin.json")`` or
    ``Path("plugin.json")`` for Copilot's root layout).
    """

    _manifest_rel_path: Path = CANONICAL_MANIFEST_REL

    def _item_path(self, name: str) -> Path:
        """Return path to this store's native manifest inside the plugin dir."""
        return self._root / name / self._manifest_rel_path

    def _item_root(self, name: str) -> Path:
        """Return the plugin's on-disk directory (containing manifest + assets)."""
        return self._root / name

    def _parse(self, name: str, text: str) -> Plugin:
        return parse_plugin_manifest(name=name, text=text)

    def _iter_candidate_names(self) -> list[str]:
        return [
            entry.name
            for entry in self._root.iterdir()
            if entry.is_dir() and (entry / self._manifest_rel_path).is_file()
        ]

    def _delete_impl(self, name: str) -> bool:
        plugin_dir = self._root / name
        if not (plugin_dir.is_symlink() or plugin_dir.is_dir()):
            return False
        self._replace_target(plugin_dir)
        return True

    def _copy_impl(self, source: BaseExtensionStore[Plugin], name: str) -> bool:
        """Copy the plugin tree and relocate the manifest to this store's layout.

        ``source._item_root(name)`` is used instead of ``source.root / name``
        so stores with non-trivial layouts (e.g. ClaudePluginStore scanning
        ``<cache>/<marketplace>/<name>/<version>/``) can point at the right
        on-disk directory.
        """
        source_dir = source._item_root(name)
        source_manifest_rel = getattr(source, "_manifest_rel_path", CANONICAL_MANIFEST_REL)
        source_manifest = source_dir / source_manifest_rel
        if not source_manifest.is_file():
            return False
        target_dir = self._root / name
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        self._replace_target(target_dir)
        shutil.copytree(source_dir, target_dir)
        _relocate_manifest(
            plugin_dir=target_dir,
            current_rel=source_manifest_rel,
            target_rel=self._manifest_rel_path,
        )
        return True


def parse_plugin_manifest(name: str, text: str) -> Plugin:
    """Parse a plugin manifest JSON into a Plugin model.

    Args:
        name: Plugin directory name.
        text: Full manifest content.

    Returns:
        Parsed Plugin.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    description = str(data.get("description") or "")
    version = str(data.get("version") or "0.0.0")
    raw_tags = data.get("keywords") or []
    tags = (
        [str(tag).strip() for tag in raw_tags if str(tag).strip()]
        if isinstance(raw_tags, list)
        else []
    )
    content_hash = compute_content_hash(text)

    return Plugin(
        name=name, description=description, version=version, tags=tags, content_hash=content_hash
    )


def _relocate_manifest(plugin_dir: Path, current_rel: Path, target_rel: Path) -> None:
    """Move a manifest from ``plugin_dir/current_rel`` to ``plugin_dir/target_rel``.

    Also removes the emptied source manifest directory if it is now empty.
    """
    if current_rel == target_rel:
        return
    current_path = plugin_dir / current_rel
    target_path = plugin_dir / target_rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(current_path), str(target_path))
    _remove_empty_ancestors(root=plugin_dir, leaf=current_path.parent)


def _remove_empty_ancestors(root: Path, leaf: Path) -> None:
    """Walk up from leaf toward root, removing empty directories."""
    current = leaf
    while current != root and current.is_dir():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent

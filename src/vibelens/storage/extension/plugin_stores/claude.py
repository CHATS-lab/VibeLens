"""Claude-specific plugin store backed by the VibeLens marketplace merge.

Installing a plugin on Claude requires touching four files plus a cache copy
of the plugin tree. This store presents a BaseExtensionStore interface over
that flow so PluginService can treat Claude uniformly with other agents.

Reads scan ``~/.claude/plugins/cache/{marketplace}/{name}/{version}/`` — the
canonical Claude plugin cache layout. This surfaces every plugin Claude has
installed, regardless of which marketplace it came from (superpowers, local
plugin folders, VibeLens itself, etc.). Writes route through
``claude_installer`` to keep all four registry files in sync.
"""

import json
from pathlib import Path

from vibelens.models.extension.plugin import Plugin
from vibelens.storage.extension.base_store import BaseExtensionStore
from vibelens.storage.extension.plugin_stores.base import (
    CANONICAL_MANIFEST_DIR,
    MANIFEST_FILENAME,
    parse_plugin_manifest,
)
from vibelens.storage.extension.plugin_stores.claude_installer import (
    ClaudePluginInstallRequest,
    install_claude_plugin,
    uninstall_claude_plugin,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class ClaudePluginStore(BaseExtensionStore[Plugin]):
    """BaseExtensionStore facade over the full Claude plugin cache.

    The underlying directory is ``~/.claude/plugins/cache/``. Plugin files
    live at ``{marketplace}/{name}/{version}/`` — three levels deeper. The
    store scans every marketplace to discover plugins.
    """

    _manifest_rel_path: Path = Path(CANONICAL_MANIFEST_DIR) / MANIFEST_FILENAME

    def _version_dir(self, name: str) -> Path | None:
        """Return the latest version directory for ``name`` across all marketplaces.

        Claude's cache layout is ``<cache>/<marketplace>/<name>/<version>/``.
        When a plugin exists under multiple marketplaces (rare), the most
        recently modified version wins.
        """
        if not self._root.is_dir():
            return None
        candidates: list[Path] = []
        for marketplace_dir in self._root.iterdir():
            if not marketplace_dir.is_dir():
                continue
            plugin_root = marketplace_dir / name
            if not plugin_root.is_dir():
                continue
            for version_dir in plugin_root.iterdir():
                if version_dir.is_dir() and (
                    version_dir / CANONICAL_MANIFEST_DIR / MANIFEST_FILENAME
                ).is_file():
                    candidates.append(version_dir)
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime)
        return candidates[-1]

    def _item_path(self, name: str) -> Path:
        """Return the plugin.json path for the latest installed version.

        When no version is on disk yet, returns a nonexistent-but-honest
        path under the VibeLens marketplace bucket so ``read_raw`` reports
        missing cleanly — callers should not treat the returned path as
        writable.
        """
        version_dir = self._version_dir(name)
        if version_dir is None:
            return (
                self._root / "vibelens" / name / CANONICAL_MANIFEST_DIR / MANIFEST_FILENAME
            )
        return version_dir / CANONICAL_MANIFEST_DIR / MANIFEST_FILENAME

    def _item_root(self, name: str) -> Path:
        """Return the plugin's current version directory (containing manifest + assets)."""
        version_dir = self._version_dir(name)
        if version_dir is None:
            return self._root / "vibelens" / name
        return version_dir

    def _parse(self, name: str, text: str) -> Plugin:
        return parse_plugin_manifest(name=name, text=text)

    def _iter_candidate_names(self) -> list[str]:
        """Walk ``<cache>/<marketplace>/<name>/`` to collect plugin names.

        De-duplicates across marketplaces by name (``_version_dir`` picks
        the most recent when there's a collision).
        """
        if not self._root.is_dir():
            return []
        names: set[str] = set()
        for marketplace_dir in self._root.iterdir():
            if not marketplace_dir.is_dir():
                continue
            for plugin_dir in marketplace_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                has_version = any(
                    v.is_dir()
                    and (v / CANONICAL_MANIFEST_DIR / MANIFEST_FILENAME).is_file()
                    for v in plugin_dir.iterdir()
                )
                if has_version:
                    names.add(plugin_dir.name)
        return sorted(names)

    def _delete_impl(self, name: str) -> bool:
        """Uninstall via the 4-file merge driver."""
        try:
            uninstall_claude_plugin(name=name)
        except FileNotFoundError:
            return False
        return True

    def _copy_impl(self, source: BaseExtensionStore[Plugin], name: str) -> bool:
        """Install via the 4-file merge driver from a source plugin directory."""
        source_manifest = source.root / name / CANONICAL_MANIFEST_DIR / MANIFEST_FILENAME
        if not source_manifest.is_file():
            return False
        manifest_text = source_manifest.read_text(encoding="utf-8")
        plugin = parse_plugin_manifest(name=name, text=manifest_text)
        request = _build_install_request(plugin=plugin, manifest_text=manifest_text)
        install_claude_plugin(request=request, overwrite=True)
        return True


def _build_install_request(plugin: Plugin, manifest_text: str) -> ClaudePluginInstallRequest:
    """Wrap a Plugin + raw manifest into the installer's typed input."""
    manifest_data = json.loads(manifest_text) if manifest_text.strip() else {}
    content_payload = json.dumps({"plugin.json": manifest_data})
    return ClaudePluginInstallRequest(
        name=plugin.name,
        description=plugin.description,
        install_content=content_payload,
        source_url="",
        log_id=f"local/{plugin.name}",
    )

"""Claude Code plugin installer — storage-layer driver for the 4-file merge.

Installing a Claude plugin requires writing four JSON files in sync plus a
cache copy of the plugin tree. We own a synthetic marketplace named
``vibelens`` so every plugin we install is namespaced away from the user's
real plugins; uninstall filters strictly on the ``@vibelens`` suffix to
guarantee we never touch other marketplaces' state.

Schema drift: ``installed_plugins.json`` carries ``"version": 2``. If the
user's file carries a different version, refuse to write and surface a
remediation error.

This module lives in the storage layer because it performs filesystem and
JSON work only — no service dependencies. It is used by
``ClaudePluginStore`` to present the merge as a ``BaseExtensionStore``.
"""

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vibelens.utils.github import download_directory
from vibelens.utils.json import atomic_write_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

VIBELENS_MARKETPLACE_NAME = "vibelens"
INSTALLED_PLUGINS_SCHEMA_VERSION = 2
DEFAULT_PLUGIN_VERSION = "0.0.0"
JSON_INDENT = 2


@dataclass(frozen=True)
class ClaudePluginInstallRequest:
    """Typed input for ``install_claude_plugin``.

    Attributes:
        name: Kebab-case plugin name.
        description: Human-readable description (written to marketplace manifest).
        install_content: JSON payload ``{"plugin.json": {...}}`` when the plugin
            ships inline; ``None`` when fetching from ``source_url``.
        source_url: GitHub tree URL to download the plugin tree from, used when
            ``install_content`` is ``None``.
        log_id: Opaque identifier for log messages (e.g. the catalog
            ``extension_id``). Must not be empty.
    """

    name: str
    description: str
    install_content: str | None
    source_url: str
    log_id: str


def install_claude_plugin(request: ClaudePluginInstallRequest, overwrite: bool) -> Path:
    """Install a Claude plugin by merging the four registry files.

    Args:
        request: Typed install request.
        overwrite: If True, replace existing cache and registry entries.

    Returns:
        Path to the plugin's cache directory.

    Raises:
        RuntimeError: If installed_plugins.json uses an unsupported schema.
        ValueError: If plugin source cannot be fetched or manifest is missing.
        FileExistsError: If overwrite is False and plugin is already installed.
    """
    home = Path.home()
    cache_root = home / ".claude" / "plugins" / "cache" / VIBELENS_MARKETPLACE_NAME / request.name

    if cache_root.exists() and not overwrite:
        raise FileExistsError(f"Plugin already installed at {cache_root}")

    with tempfile.TemporaryDirectory(prefix="vibelens-plugin-") as scratch:
        source_dir = _fetch_plugin_content(request=request, scratch=Path(scratch))
        version = _read_plugin_version(source_dir=source_dir)
        cache_target = cache_root / version

        if cache_target.exists():
            shutil.rmtree(cache_target)
        cache_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, cache_target)

        marketplace_root = home / ".vibelens" / "claude_marketplace"
        marketplace_plugin_dir = marketplace_root / "plugins" / request.name
        if marketplace_plugin_dir.exists():
            shutil.rmtree(marketplace_plugin_dir)
        marketplace_plugin_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, marketplace_plugin_dir)

        _merge_vibelens_marketplace(marketplace_root=marketplace_root, request=request)
        _merge_known_marketplaces(home=home, marketplace_root=marketplace_root)
        _merge_installed_plugins(
            home=home, name=request.name, version=version, cache_path=cache_target
        )
        _merge_settings_enabled_plugins(home=home, name=request.name, enabled=True)

        logger.info("Installed claude plugin %s version %s", request.log_id, version)
        return cache_target


def uninstall_claude_plugin(name: str, log_id: str = "") -> Path:
    """Remove a Claude plugin from all four registry files and the cache.

    Args:
        name: Plugin name to uninstall.
        log_id: Opaque identifier for log messages.

    Returns:
        Path that was removed from the cache.

    Raises:
        FileNotFoundError: If the plugin is not installed via VibeLens.
    """
    home = Path.home()
    cache_root = home / ".claude" / "plugins" / "cache" / VIBELENS_MARKETPLACE_NAME / name
    marketplace_root = home / ".vibelens" / "claude_marketplace"
    marketplace_plugin_dir = marketplace_root / "plugins" / name

    if not cache_root.exists() and not marketplace_plugin_dir.exists():
        raise FileNotFoundError(f"Plugin {name} not installed via VibeLens")

    _merge_settings_enabled_plugins(home=home, name=name, enabled=None)
    _remove_installed_plugins_entry(home=home, name=name)
    _remove_vibelens_marketplace_entry(marketplace_root=marketplace_root, name=name)

    if marketplace_plugin_dir.exists():
        shutil.rmtree(marketplace_plugin_dir)
    if cache_root.exists():
        shutil.rmtree(cache_root)

    logger.info("Uninstalled claude plugin %s", log_id or name)
    return cache_root


def _fetch_plugin_content(request: ClaudePluginInstallRequest, scratch: Path) -> Path:
    """Return a directory containing the plugin files ready to copy.

    Validates that the resulting directory has ``.claude-plugin/plugin.json``
    before returning, so the caller never writes a malformed cache entry.
    """
    target = scratch / request.name

    if request.install_content:
        content_payload = json.loads(request.install_content)
        if not isinstance(content_payload, dict) or "plugin.json" not in content_payload:
            raise ValueError(
                f"Plugin {request.name}: install_content must include 'plugin.json'"
            )
        target.mkdir(parents=True)
        (target / ".claude-plugin").mkdir()
        (target / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(content_payload["plugin.json"], indent=JSON_INDENT), encoding="utf-8"
        )
        return target

    if not request.source_url:
        raise ValueError(f"Plugin {request.name}: no install_content or source_url")
    target.mkdir(parents=True)
    if not download_directory(source_url=request.source_url, target_dir=target):
        raise ValueError(f"Failed to fetch plugin from {request.source_url}")
    if not (target / ".claude-plugin" / "plugin.json").is_file():
        raise ValueError(
            f"Plugin {request.name}: downloaded tree missing .claude-plugin/plugin.json"
        )
    return target


def _read_plugin_version(source_dir: Path) -> str:
    manifest_path = source_dir / ".claude-plugin" / "plugin.json"
    if not manifest_path.is_file():
        return DEFAULT_PLUGIN_VERSION
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_PLUGIN_VERSION
    version = manifest.get("version")
    return str(version) if version else DEFAULT_PLUGIN_VERSION


def _merge_vibelens_marketplace(
    marketplace_root: Path, request: ClaudePluginInstallRequest
) -> None:
    manifest_path = marketplace_root / ".claude-plugin" / "marketplace.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = _read_json(manifest_path) or {
        "name": VIBELENS_MARKETPLACE_NAME,
        "description": "Extensions installed via VibeLens",
        "owner": {"name": "vibelens"},
        "plugins": [],
    }
    plugin_entries = [
        entry for entry in manifest.get("plugins", []) if entry.get("name") != request.name
    ]
    plugin_entries.append(
        {
            "name": request.name,
            "description": request.description,
            "source": f"./plugins/{request.name}",
        }
    )
    manifest["plugins"] = plugin_entries
    atomic_write_json(manifest_path, manifest, indent=JSON_INDENT)


def _remove_vibelens_marketplace_entry(marketplace_root: Path, name: str) -> None:
    manifest_path = marketplace_root / ".claude-plugin" / "marketplace.json"
    manifest = _read_json(manifest_path)
    if not manifest:
        return
    manifest["plugins"] = [
        entry for entry in manifest.get("plugins", []) if entry.get("name") != name
    ]
    atomic_write_json(manifest_path, manifest, indent=JSON_INDENT)


def _merge_known_marketplaces(home: Path, marketplace_root: Path) -> None:
    path = home / ".claude" / "plugins" / "known_marketplaces.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    registry = _read_json(path) or {}
    registry[VIBELENS_MARKETPLACE_NAME] = {
        "source": {"source": "directory", "path": str(marketplace_root)},
        "installLocation": str(marketplace_root),
        "lastUpdated": _now_iso(),
    }
    atomic_write_json(path, registry, indent=JSON_INDENT)


def _merge_installed_plugins(home: Path, name: str, version: str, cache_path: Path) -> None:
    path = home / ".claude" / "plugins" / "installed_plugins.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    install_state = _read_json(path) or {
        "version": INSTALLED_PLUGINS_SCHEMA_VERSION,
        "plugins": {},
    }
    if install_state.get("version") != INSTALLED_PLUGINS_SCHEMA_VERSION:
        raise RuntimeError(
            f"unsupported installed_plugins.json version {install_state.get('version')!r}; "
            f"expected {INSTALLED_PLUGINS_SCHEMA_VERSION}. "
            f"Run 'claude plugin install' manually."
        )
    plugin_key = f"{name}@{VIBELENS_MARKETPLACE_NAME}"
    now = _now_iso()
    install_records = list(install_state.setdefault("plugins", {}).get(plugin_key, []))
    install_records = [record for record in install_records if record.get("scope") != "user"]
    install_records.append(
        {
            "scope": "user",
            "installPath": str(cache_path),
            "version": version,
            "installedAt": now,
            "lastUpdated": now,
        }
    )
    install_state["plugins"][plugin_key] = install_records
    atomic_write_json(path, install_state, indent=JSON_INDENT)


def _remove_installed_plugins_entry(home: Path, name: str) -> None:
    path = home / ".claude" / "plugins" / "installed_plugins.json"
    install_state = _read_json(path)
    if not install_state:
        return
    plugin_key = f"{name}@{VIBELENS_MARKETPLACE_NAME}"
    install_state.get("plugins", {}).pop(plugin_key, None)
    atomic_write_json(path, install_state, indent=JSON_INDENT)


def _merge_settings_enabled_plugins(home: Path, name: str, enabled: bool | None) -> None:
    path = home / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = _read_json(path) or {}
    enabled_plugins = settings.setdefault("enabledPlugins", {})
    plugin_key = f"{name}@{VIBELENS_MARKETPLACE_NAME}"
    if enabled is None:
        enabled_plugins.pop(plugin_key, None)
    else:
        enabled_plugins[plugin_key] = enabled
    atomic_write_json(path, settings, indent=JSON_INDENT)


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read %s; treating as empty", path)
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

"""Tests for ClaudePluginStore cache scanning across marketplaces.

The store's ``_root`` is the full ``~/.claude/plugins/cache/`` directory,
one level above any single marketplace. It must walk
``<cache>/<marketplace>/<plugin>/<version>/.claude-plugin/plugin.json``
and surface every installed plugin regardless of source.
"""

import json
import os
import time
from pathlib import Path

import pytest

from vibelens.storage.extension.plugin_stores.base import (
    CANONICAL_MANIFEST_DIR,
    MANIFEST_FILENAME,
)
from vibelens.storage.extension.plugin_stores.claude import ClaudePluginStore


def _write_plugin(
    *,
    cache_root: Path,
    marketplace: str,
    name: str,
    version: str,
    description: str = "test plugin",
) -> Path:
    """Write a plugin at ``<cache>/<marketplace>/<name>/<version>/``.

    Returns the plugin's version directory.
    """
    version_dir = cache_root / marketplace / name / version
    manifest_dir = version_dir / CANONICAL_MANIFEST_DIR
    manifest_dir.mkdir(parents=True)
    (manifest_dir / MANIFEST_FILENAME).write_text(
        json.dumps({"name": name, "version": version, "description": description})
    )
    return version_dir


@pytest.fixture
def cache_root(tmp_path):
    root = tmp_path / "claude_cache"
    root.mkdir()
    return root


def test_list_names_discovers_plugins_across_marketplaces(cache_root: Path):
    _write_plugin(
        cache_root=cache_root, marketplace="superpowers-dev", name="superpowers", version="5.0.7"
    )
    _write_plugin(
        cache_root=cache_root, marketplace="local-plugins", name="claude-dev", version="2.0.1"
    )
    _write_plugin(
        cache_root=cache_root, marketplace="vibelens", name="ad-creative", version="1.0.0"
    )

    store = ClaudePluginStore(cache_root)
    names = store.list_names()

    assert sorted(names) == ["ad-creative", "claude-dev", "superpowers"]


def test_list_names_empty_for_fresh_cache(cache_root: Path):
    store = ClaudePluginStore(cache_root)
    assert store.list_names() == []


def test_list_names_ignores_plugins_without_manifest(cache_root: Path):
    """A version dir that's missing ``.claude-plugin/plugin.json`` shouldn't surface."""
    (cache_root / "marketplace-a" / "orphan" / "1.0.0").mkdir(parents=True)
    _write_plugin(cache_root=cache_root, marketplace="marketplace-a", name="valid", version="1.0.0")

    store = ClaudePluginStore(cache_root)
    assert store.list_names() == ["valid"]


def test_read_returns_latest_version_across_marketplaces(cache_root: Path):
    """When a name exists under multiple marketplaces, the most recent mtime wins."""
    older = _write_plugin(
        cache_root=cache_root,
        marketplace="old-mp",
        name="shared",
        version="1.0.0",
        description="old",
    )
    newer = _write_plugin(
        cache_root=cache_root,
        marketplace="new-mp",
        name="shared",
        version="2.0.0",
        description="new",
    )
    now = time.time()
    os.utime(older, (now - 100, now - 100))
    os.utime(newer, (now, now))

    store = ClaudePluginStore(cache_root)
    plugin = store.read("shared")
    assert plugin.description == "new"
    assert plugin.version == "2.0.0"


def test_item_root_points_at_version_dir(cache_root: Path):
    """_item_root is what the tree endpoint walks — must be the version dir,
    so tree includes the manifest + any sibling skills/commands dirs.
    """
    version_dir = _write_plugin(
        cache_root=cache_root, marketplace="mp", name="demo", version="1.0.0"
    )
    (version_dir / "skills").mkdir()
    (version_dir / "skills" / "thing.md").write_text("x")

    store = ClaudePluginStore(cache_root)
    root = store._item_root("demo")
    assert root == version_dir
    assert (root / CANONICAL_MANIFEST_DIR / MANIFEST_FILENAME).is_file()
    assert (root / "skills" / "thing.md").is_file()

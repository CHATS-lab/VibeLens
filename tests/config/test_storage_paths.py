"""Verify StorageConfig defaults point under extensions/."""

from pathlib import Path

from vibelens.config.settings import StorageConfig


def test_managed_dirs_under_extensions() -> None:
    """All managed-* dirs default under ~/.vibelens/extensions/."""
    config = StorageConfig()
    extensions_root = Path.home() / ".vibelens" / "extensions"

    assert config.managed_skills_dir == extensions_root / "skills"
    assert config.managed_commands_dir == extensions_root / "commands"
    assert config.managed_subagents_dir == extensions_root / "subagents"
    assert config.managed_hooks_dir == extensions_root / "hooks"
    assert config.managed_plugins_dir == extensions_root / "plugins"
    assert config.managed_collections_dir == extensions_root / "collections"

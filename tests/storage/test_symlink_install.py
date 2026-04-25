"""Tests for symlink-based install (BaseExtensionStore.link_from)."""

import sys
from pathlib import Path

import pytest

from vibelens.storage.extension.command_store import CommandStore
from vibelens.storage.extension.skill_store import SkillStore

SKILL_BODY = "---\ndescription: t\n---\n# T\n"


def test_link_from_creates_symlink_for_skill(tmp_path: Path) -> None:
    """link_from creates a symlink at the agent path pointing to the central dir."""
    if sys.platform == "win32":
        pytest.skip("symlinks require dev mode on Windows")

    central = SkillStore(root=tmp_path / "central", create=True)
    agent = SkillStore(root=tmp_path / "agent", create=True)
    central.write("alpha", SKILL_BODY)

    agent.link_from(central, "alpha")

    agent_path = agent._item_root("alpha")
    assert agent_path.is_symlink()
    assert agent_path.resolve() == central._item_root("alpha").resolve()
    assert (agent_path / "SKILL.md").read_text() == SKILL_BODY


def test_edits_through_symlink_propagate(tmp_path: Path) -> None:
    """Editing the central content shows up via the agent symlink."""
    if sys.platform == "win32":
        pytest.skip("symlinks require dev mode on Windows")

    central = SkillStore(root=tmp_path / "central", create=True)
    agent = SkillStore(root=tmp_path / "agent", create=True)
    central.write("alpha", SKILL_BODY)
    agent.link_from(central, "alpha")

    central.write("alpha", "---\ndescription: updated\n---\n")
    agent_content = (agent._item_root("alpha") / "SKILL.md").read_text()

    assert "updated" in agent_content


def test_link_from_replaces_existing(tmp_path: Path) -> None:
    """link_from replaces an existing copy or symlink at the target path."""
    if sys.platform == "win32":
        pytest.skip("symlinks require dev mode on Windows")

    central = SkillStore(root=tmp_path / "central", create=True)
    agent = SkillStore(root=tmp_path / "agent", create=True)
    central.write("alpha", SKILL_BODY)
    agent.copy_from(central, "alpha")
    assert not agent._item_root("alpha").is_symlink()

    agent.link_from(central, "alpha")

    assert agent._item_root("alpha").is_symlink()


def test_link_from_works_for_command(tmp_path: Path) -> None:
    """link_from also works for file-based extensions (commands)."""
    if sys.platform == "win32":
        pytest.skip("symlinks require dev mode on Windows")

    central = CommandStore(root=tmp_path / "central", create=True)
    agent = CommandStore(root=tmp_path / "agent", create=True)
    central.write("greet", "---\ndescription: t\n---\nHello\n")

    agent.link_from(central, "greet")

    agent_path = agent._item_path("greet")
    assert agent_path.is_symlink()
    assert agent_path.read_text().startswith("---")

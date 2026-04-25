"""Tests for link_type plumbing in BaseExtensionService."""

import sys
from pathlib import Path

import pytest

from vibelens.services.extensions.skill_service import SkillService
from vibelens.storage.extension.skill_store import SkillStore

SKILL_BODY = "---\ndescription: t\n---\n# T\n"


@pytest.fixture
def skill_service(tmp_path: Path) -> SkillService:
    central = SkillStore(root=tmp_path / "central", create=True)
    agents = {
        "claude": SkillStore(root=tmp_path / "claude", create=True),
        "cursor": SkillStore(root=tmp_path / "cursor", create=True),
    }
    return SkillService(central=central, agents=agents)


def test_install_with_symlink_creates_symlinks(skill_service, tmp_path: Path) -> None:
    """install with link_type=symlink creates symlinks in agent stores."""
    if sys.platform == "win32":
        pytest.skip("symlinks require dev mode on Windows")

    skill_service.install(
        name="alpha",
        content=SKILL_BODY,
        sync_to=["claude", "cursor"],
        link_type="symlink",
    )

    assert (tmp_path / "claude" / "alpha").is_symlink()
    assert (tmp_path / "cursor" / "alpha").is_symlink()


def test_install_with_copy_creates_copies(skill_service, tmp_path: Path) -> None:
    """install with link_type=copy creates copies, not symlinks."""
    skill_service.install(
        name="alpha",
        content=SKILL_BODY,
        sync_to=["claude"],
        link_type="copy",
    )

    assert (tmp_path / "claude" / "alpha").is_dir()
    assert not (tmp_path / "claude" / "alpha").is_symlink()


def test_sync_to_agents_respects_link_type(skill_service, tmp_path: Path) -> None:
    """sync_to_agents accepts link_type and threads it to the store."""
    if sys.platform == "win32":
        pytest.skip("symlinks require dev mode on Windows")

    skill_service.install(name="alpha", content=SKILL_BODY)
    results = skill_service.sync_to_agents("alpha", ["claude"], link_type="symlink")

    assert results == {"claude": True}
    assert (tmp_path / "claude" / "alpha").is_symlink()


def test_modify_preserves_link_type(skill_service, tmp_path: Path) -> None:
    """modify with link_type=copy preserves a copy install on re-sync."""
    skill_service.install(
        name="alpha",
        content=SKILL_BODY,
        sync_to=["claude"],
        link_type="copy",
    )
    assert (tmp_path / "claude" / "alpha").is_dir()
    assert not (tmp_path / "claude" / "alpha").is_symlink()

    skill_service.modify(
        name="alpha",
        content="---\ndescription: updated\n---\n",
        link_type="copy",
    )

    assert not (tmp_path / "claude" / "alpha").is_symlink()

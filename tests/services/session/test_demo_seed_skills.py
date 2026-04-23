"""Tests for seed_example_skills() — bundled skill seeding into the central store."""

from pathlib import Path

from vibelens.services.session.demo import _EXAMPLE_SKILL_SIDECAR, seed_example_skills


def _make_settings(session_paths: list[Path], managed_skills_dir: Path):
    """Build a minimal stand-in for vibelens Settings with just the fields we need."""
    return type(
        "S",
        (),
        {
            "demo": type("D", (), {"session_paths": session_paths})(),
            "storage": type("St", (), {"managed_skills_dir": managed_skills_dir})(),
        },
    )()


def _write_bundled_skill(root: Path, name: str, body: str) -> Path:
    """Create a bundled example skill at root/skills/<name>/SKILL.md."""
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return skill_dir


def test_seed_example_skills_empty_destination(tmp_path, monkeypatch):
    """Fresh destination → skill copied with .is_example sidecar."""
    example_root = tmp_path / "examples"
    body = "---\nname: frontend-design\n---\n\n# Body\n"
    _write_bundled_skill(example_root, "frontend-design", body)
    managed = tmp_path / "managed_skills"

    monkeypatch.setattr(
        "vibelens.services.session.demo.get_settings",
        lambda: _make_settings([example_root], managed),
    )

    seed_example_skills()

    dst = managed / "frontend-design"
    print(f"seeded files: {sorted(p.name for p in dst.iterdir())}")
    assert (dst / "SKILL.md").is_file()
    assert (dst / _EXAMPLE_SKILL_SIDECAR).is_file()
    assert "# Body" in (dst / "SKILL.md").read_text(encoding="utf-8")


def test_seed_example_skills_overwrites_seeded_copy(tmp_path, monkeypatch):
    """Destination with .is_example sidecar is overwritten on reseed."""
    example_root = tmp_path / "examples"
    body = "---\nname: frontend-design\n---\n\n# Bundled\n"
    _write_bundled_skill(example_root, "frontend-design", body)
    managed = tmp_path / "managed_skills"

    monkeypatch.setattr(
        "vibelens.services.session.demo.get_settings",
        lambda: _make_settings([example_root], managed),
    )

    seed_example_skills()
    # Simulate a user edit to the seeded copy while leaving the sidecar in place.
    dst = managed / "frontend-design"
    (dst / "SKILL.md").write_text("# User edit that should be reverted\n", encoding="utf-8")
    print(f"after user edit: {(dst / 'SKILL.md').read_text(encoding='utf-8')!r}")

    seed_example_skills()

    reloaded = (dst / "SKILL.md").read_text(encoding="utf-8")
    print(f"after reseed: {reloaded!r}")
    assert "# Bundled" in reloaded
    assert (dst / _EXAMPLE_SKILL_SIDECAR).is_file()


def test_seed_example_skills_preserves_user_customization(tmp_path, monkeypatch):
    """Destination without .is_example sidecar is left alone on reseed."""
    example_root = tmp_path / "examples"
    body = "---\nname: frontend-design\n---\n\n# Bundled\n"
    _write_bundled_skill(example_root, "frontend-design", body)
    managed = tmp_path / "managed_skills"

    # Pre-populate a user-authored skill with the same name, no sidecar.
    user_skill = managed / "frontend-design"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text("# My own skill\n", encoding="utf-8")

    monkeypatch.setattr(
        "vibelens.services.session.demo.get_settings",
        lambda: _make_settings([example_root], managed),
    )

    seed_example_skills()

    reloaded = (user_skill / "SKILL.md").read_text(encoding="utf-8")
    print(f"user skill after seed attempt: {reloaded!r}")
    assert reloaded == "# My own skill\n"
    assert not (user_skill / _EXAMPLE_SKILL_SIDECAR).exists()


def test_seed_example_skills_missing_source_dir(tmp_path, monkeypatch):
    """No skills/ subdirectory under the examples root → no-op, no errors."""
    example_root = tmp_path / "examples"
    example_root.mkdir()
    managed = tmp_path / "managed_skills"

    monkeypatch.setattr(
        "vibelens.services.session.demo.get_settings",
        lambda: _make_settings([example_root], managed),
    )

    seed_example_skills()

    print(f"managed exists: {managed.exists()}")
    assert not managed.exists() or not any(managed.iterdir())

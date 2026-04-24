"""Tests verifying the prompts/ refactor: renamed files, split templates, updated registry."""

import importlib
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "vibelens" / "prompts" / "templates"


class TestCreationPrompts:
    """Verify creation prompts export correctly from the new module path."""

    def test_creation_module_exports_proposal_prompt(self) -> None:
        from vibelens.prompts.creation import CREATION_PROPOSAL_PROMPT

        assert CREATION_PROPOSAL_PROMPT.task_id == "creation_proposal"
        print(f"SKILL_CREATION_PROPOSAL_PROMPT task_id: {CREATION_PROPOSAL_PROMPT.task_id}")

    def test_creation_module_exports_synthesis_prompt(self) -> None:
        from vibelens.prompts.creation import CREATION_PROPOSAL_SYNTHESIS_PROMPT

        expected_id = "creation_proposal_synthesis"
        assert CREATION_PROPOSAL_SYNTHESIS_PROMPT.task_id == expected_id
        print(f"SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT task_id: {expected_id}")

    def test_creation_module_exports_generate_prompt(self) -> None:
        from vibelens.prompts.creation import CREATION_PROMPT

        assert CREATION_PROMPT.task_id == "creation"
        print(f"SKILL_CREATION_GENERATE_PROMPT task_id: {CREATION_PROMPT.task_id}")


class TestEvolutionPrompts:
    """Verify evolution prompts export correctly from the new module path."""

    def test_evolution_module_exports_proposal_prompt(self) -> None:
        from vibelens.prompts.evolution import EVOLUTION_PROPOSAL_PROMPT

        assert EVOLUTION_PROPOSAL_PROMPT.task_id == "evolution_proposal"
        print(f"SKILL_EVOLUTION_PROPOSAL_PROMPT task_id: {EVOLUTION_PROPOSAL_PROMPT.task_id}")

    def test_evolution_module_exports_synthesis_prompt(self) -> None:
        from vibelens.prompts.evolution import EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT

        expected_id = "evolution_proposal_synthesis"
        assert EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT.task_id == expected_id
        print(f"SKILL_EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT task_id: {expected_id}")

    def test_evolution_module_exports_edit_prompt(self) -> None:
        from vibelens.prompts.evolution import EVOLUTION_PROMPT

        assert EVOLUTION_PROMPT.task_id == "evolution"
        print(f"SKILL_EVOLUTION_EDIT_PROMPT task_id: {EVOLUTION_PROMPT.task_id}")


class TestOldModuleRemoved:
    """Verify the old skill_retrieval module is no longer importable."""

    def test_skill_retrieval_module_not_importable(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("vibelens.prompts.skill_retrieval")
        print("vibelens.prompts.skill_retrieval correctly raises ModuleNotFoundError")


class TestTemplateDirectories:
    """Verify template files are in the correct directories after the split."""

    EXPECTED_CREATION_FILES = [
        "creation_proposal_system.j2",
        "creation_proposal_user.j2",
        "creation_proposal_synthesis_system.j2",
        "creation_proposal_synthesis_user.j2",
        "creation_system.j2",
        "creation_user.j2",
    ]

    EXPECTED_EVOLUTION_FILES = [
        "evolution_proposal_system.j2",
        "evolution_proposal_user.j2",
        "evolution_proposal_synthesis_system.j2",
        "evolution_proposal_synthesis_user.j2",
        "evolution_system.j2",
        "evolution_user.j2",
    ]

    def test_creation_templates_exist(self) -> None:
        creation_dir = TEMPLATES_DIR / "creation"
        assert creation_dir.is_dir(), f"Missing directory: {creation_dir}"
        actual_files = sorted(f.name for f in creation_dir.glob("*.j2"))
        expected = sorted(self.EXPECTED_CREATION_FILES)
        assert actual_files == expected, f"Expected {expected}, got {actual_files}"
        print(f"Creation templates ({len(actual_files)} files): {actual_files}")

    def test_evolution_templates_exist(self) -> None:
        evolution_dir = TEMPLATES_DIR / "evolution"
        assert evolution_dir.is_dir(), f"Missing directory: {evolution_dir}"
        actual_files = sorted(f.name for f in evolution_dir.glob("*.j2"))
        expected = sorted(self.EXPECTED_EVOLUTION_FILES)
        assert actual_files == expected, f"Expected {expected}, got {actual_files}"
        print(f"Evolution templates ({len(actual_files)} files): {actual_files}")

    def test_skill_directory_removed(self) -> None:
        skill_dir = TEMPLATES_DIR / "skill"
        assert not skill_dir.exists(), f"templates/skill/ should not exist: {skill_dir}"
        print("templates/skill/ directory correctly removed")

    def test_recommendation_directory_exists(self) -> None:
        rec_dir = TEMPLATES_DIR / "recommendation"
        assert rec_dir.is_dir(), f"Missing directory: {rec_dir}"
        print(f"templates/recommendation/ directory exists at {rec_dir}")


class TestPromptRegistry:
    """Verify the PROMPT_REGISTRY no longer contains retrieval entries."""

    def test_registry_has_no_skill_retrieval_key(self) -> None:
        from vibelens.prompts import PROMPT_REGISTRY

        assert "skill_retrieval" not in PROMPT_REGISTRY
        print(f"PROMPT_REGISTRY keys: {list(PROMPT_REGISTRY.keys())}")

    def test_registry_contains_friction_and_evolution(self) -> None:
        from vibelens.prompts import PROMPT_REGISTRY

        assert "friction" in PROMPT_REGISTRY
        assert "evolution_proposal" in PROMPT_REGISTRY
        print(f"Registry contains expected keys: {list(PROMPT_REGISTRY.keys())}")

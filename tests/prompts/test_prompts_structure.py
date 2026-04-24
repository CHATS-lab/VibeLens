"""Structural tests for the ``vibelens.prompts`` package.

Assert the current layout of the prompts package: what modules export which
prompt objects, what templates exist in each subdirectory, and what partials
live under ``_partials/``. These tests guard against accidental drift — if
someone moves a template or renames an export, a test here fails and names
the missing piece.

Update these tests when the structure legitimately changes.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "src" / "vibelens" / "prompts" / "templates"


class TestCreationPrompts:
    """Creation prompts are exported from ``vibelens.prompts.creation``."""

    def test_proposal_prompt_export(self) -> None:
        from vibelens.prompts.creation import CREATION_PROPOSAL_PROMPT

        assert CREATION_PROPOSAL_PROMPT.task_id == "creation_proposal"
        print(f"CREATION_PROPOSAL_PROMPT task_id: {CREATION_PROPOSAL_PROMPT.task_id}")

    def test_synthesis_prompt_export(self) -> None:
        from vibelens.prompts.creation import CREATION_PROPOSAL_SYNTHESIS_PROMPT

        assert CREATION_PROPOSAL_SYNTHESIS_PROMPT.task_id == "creation_proposal_synthesis"
        print(
            f"CREATION_PROPOSAL_SYNTHESIS_PROMPT task_id: "
            f"{CREATION_PROPOSAL_SYNTHESIS_PROMPT.task_id}"
        )

    def test_generate_prompt_export(self) -> None:
        from vibelens.prompts.creation import CREATION_PROMPT

        assert CREATION_PROMPT.task_id == "creation"
        print(f"CREATION_PROMPT task_id: {CREATION_PROMPT.task_id}")


class TestEvolutionPrompts:
    """Evolution prompts are exported from ``vibelens.prompts.evolution``."""

    def test_proposal_prompt_export(self) -> None:
        from vibelens.prompts.evolution import EVOLUTION_PROPOSAL_PROMPT

        assert EVOLUTION_PROPOSAL_PROMPT.task_id == "evolution_proposal"
        print(f"EVOLUTION_PROPOSAL_PROMPT task_id: {EVOLUTION_PROPOSAL_PROMPT.task_id}")

    def test_synthesis_prompt_export(self) -> None:
        from vibelens.prompts.evolution import EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT

        assert EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT.task_id == "evolution_proposal_synthesis"
        print(
            f"EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT task_id: "
            f"{EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT.task_id}"
        )

    def test_edit_prompt_export(self) -> None:
        from vibelens.prompts.evolution import EVOLUTION_PROMPT

        assert EVOLUTION_PROMPT.task_id == "evolution"
        print(f"EVOLUTION_PROMPT task_id: {EVOLUTION_PROMPT.task_id}")


class TestTemplateDirectories:
    """Each prompt domain has a dedicated template directory with a fixed file set."""

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

    def test_creation_templates(self) -> None:
        creation_dir = TEMPLATES_DIR / "creation"
        assert creation_dir.is_dir(), f"Missing directory: {creation_dir}"
        actual = sorted(f.name for f in creation_dir.glob("*.j2"))
        expected = sorted(self.EXPECTED_CREATION_FILES)
        assert actual == expected, f"Expected {expected}, got {actual}"
        print(f"Creation templates ({len(actual)} files): {actual}")

    def test_evolution_templates(self) -> None:
        evolution_dir = TEMPLATES_DIR / "evolution"
        assert evolution_dir.is_dir(), f"Missing directory: {evolution_dir}"
        actual = sorted(f.name for f in evolution_dir.glob("*.j2"))
        expected = sorted(self.EXPECTED_EVOLUTION_FILES)
        assert actual == expected, f"Expected {expected}, got {actual}"
        print(f"Evolution templates ({len(actual)} files): {actual}")

    def test_recommendation_directory(self) -> None:
        rec_dir = TEMPLATES_DIR / "recommendation"
        assert rec_dir.is_dir(), f"Missing directory: {rec_dir}"
        print(f"recommendation directory exists at {rec_dir}")


class TestPartials:
    """The ``_partials/`` directory holds shared Jinja fragments with a fixed set."""

    PARTIALS_DIR = TEMPLATES_DIR / "_partials"

    EXPECTED_PARTIALS = [
        "_audience.j2",
        "_backend_rules.j2",
        "_example_refs.j2",
        "_output_envelope.j2",
        "_rationale_format.j2",
        "_skill_authoring.j2",
        "_skill_shape.j2",
        "_title_blocklist.j2",
    ]

    def test_partials_set(self) -> None:
        assert self.PARTIALS_DIR.is_dir(), f"Missing directory: {self.PARTIALS_DIR}"
        actual = sorted(f.name for f in self.PARTIALS_DIR.glob("*.j2"))
        expected = sorted(self.EXPECTED_PARTIALS)
        assert actual == expected, f"Expected {expected}, got {actual}"
        print(f"Partials ({len(actual)} files): {actual}")

    def test_output_envelope_includes_common_rules(self) -> None:
        envelope = (self.PARTIALS_DIR / "_output_envelope.j2").read_text()
        assert "## Output Rules" in envelope
        assert "single JSON object" in envelope
        assert "Do NOT ask clarifying questions" in envelope
        print("_output_envelope.j2 contains inlined common output rules")

    def test_example_refs_covers_step_and_session(self) -> None:
        refs = (self.PARTIALS_DIR / "_example_refs.j2").read_text()
        assert "`example_refs`" in refs
        assert "`session_ids`" in refs
        assert "Cap: at most" in refs
        print("_example_refs.j2 covers both example_refs and session_ids rules")


class TestPromptRegistry:
    """``PROMPT_REGISTRY`` contains the currently shipped prompts."""

    EXPECTED_KEYS = {
        "evolution_proposal",
        "friction",
        "recommendation_profile",
    }

    def test_registry_keys(self) -> None:
        from vibelens.prompts import PROMPT_REGISTRY

        actual = set(PROMPT_REGISTRY.keys())
        assert actual == self.EXPECTED_KEYS, (
            f"Registry mismatch. Expected {self.EXPECTED_KEYS}, got {actual}"
        )
        print(f"PROMPT_REGISTRY keys ({len(actual)}): {sorted(actual)}")

"""Tests for model restructuring — verifies new models and moved imports."""

from vibelens.models.enums import ElementType
from vibelens.models.step_ref import StepRef


class TestElementType:
    """Verify ElementType enum added to enums.py."""

    def test_element_type_values(self):
        assert ElementType.SKILL == "skill"
        assert ElementType.SUBAGENT == "subagent"
        assert ElementType.COMMAND == "command"
        assert ElementType.HOOK == "hook"

    def test_element_type_is_str(self):
        assert isinstance(ElementType.SKILL, str)

    def test_element_type_membership(self):
        assert len(ElementType) == 4


class TestStepRefMove:
    """Verify StepRef importable from models.step_ref (new canonical location)."""

    def test_import_from_new_location(self):
        ref = StepRef(session_id="s1", start_step_id="step-1")
        assert ref.session_id == "s1"
        assert ref.start_step_id == "step-1"
        assert ref.end_step_id is None

    def test_point_ref_normalization(self):
        ref = StepRef(session_id="s1", start_step_id="x", end_step_id="x")
        assert ref.end_step_id is None

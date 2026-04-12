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


class TestSessionPackage:
    """Verify models/session/ package with moved models."""

    def test_correlator_import(self):
        from vibelens.models.session.correlator import CorrelatedGroup, CorrelatedSession

        session = CorrelatedSession(agent_name="claude-code", session_id="s1")
        assert session.is_main is True
        group = CorrelatedGroup(project_path="/tmp/proj")
        assert group.time_overlap_seconds == 0

    def test_phase_import(self):
        from vibelens.models.session.phase import PhaseSegment

        seg = PhaseSegment(phase="exploration", start_index=0, end_index=5)
        assert seg.dominant_tool_category == ""

    def test_tool_graph_import(self):
        from vibelens.models.session.tool_graph import ToolDependencyGraph, ToolEdge

        edge = ToolEdge(
            source_tool_call_id="a",
            target_tool_call_id="b",
            relation="sequential",
        )
        assert edge.shared_resource == ""
        graph = ToolDependencyGraph(session_id="s1")
        assert graph.edges == []

    def test_workflow_pattern_import(self):
        from vibelens.models.session.patterns import WorkflowPattern

        pattern = WorkflowPattern(
            title="Search-Read-Edit Cycle",
            description="Agent searches for files, reads them, then edits.",
        )
        assert pattern.frequency == 0

    def test_session_init_reexports(self):
        from vibelens.models.session import (
            CorrelatedGroup,
            CorrelatedSession,
            PhaseSegment,
            ToolDependencyGraph,
            ToolEdge,
            WorkflowPattern,
        )

        assert CorrelatedGroup is not None
        assert CorrelatedSession is not None
        assert PhaseSegment is not None
        assert ToolDependencyGraph is not None
        assert ToolEdge is not None
        assert WorkflowPattern is not None

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


class TestFrictionPackage:
    """Verify models/friction/ package with moved models."""

    def test_friction_type_import(self):
        from vibelens.models.friction import FrictionType

        ft = FrictionType(
            type_name="changed-wrong-files",
            description="Agent edited the wrong file",
            severity=3,
        )
        assert ft.type_name == "changed-wrong-files"

    def test_friction_analysis_result_import(self):
        from vibelens.models.friction import FrictionAnalysisResult

        assert FrictionAnalysisResult is not None

    def test_friction_init_reexports(self):
        from vibelens.models.friction import (
            FrictionAnalysisOutput,
            FrictionAnalysisResult,
            FrictionCost,
            FrictionType,
            Mitigation,
        )

        assert FrictionAnalysisOutput is not None
        assert FrictionAnalysisResult is not None
        assert FrictionCost is not None
        assert FrictionType is not None
        assert Mitigation is not None


class TestRecommendationPackage:
    """Verify models/recommendation/ package with new models."""

    def test_item_type_values(self):
        from vibelens.models.recommendation.catalog import ItemType

        assert ItemType.SKILL == "skill"
        assert ItemType.SUBAGENT == "subagent"
        assert ItemType.COMMAND == "command"
        assert ItemType.HOOK == "hook"
        assert ItemType.REPO == "repo"
        assert len(ItemType) == 5

    def test_file_based_types(self):
        from vibelens.models.recommendation.catalog import FILE_BASED_TYPES, ItemType

        assert ItemType.SKILL in FILE_BASED_TYPES
        assert ItemType.REPO not in FILE_BASED_TYPES
        assert len(FILE_BASED_TYPES) == 4

    def test_catalog_item(self):
        from vibelens.models.recommendation.catalog import CatalogItem

        item = CatalogItem(
            item_id="test-runner",
            item_type="skill",
            name="Test Runner",
            description="Runs tests automatically",
            tags=["testing"],
            category="development",
            platforms=["claude-code"],
            quality_score=85.0,
            popularity=0.7,
            updated_at="2026-04-01T00:00:00Z",
            source_url="https://github.com/example/test-runner",
            repo_full_name="example/test-runner",
            install_method="skill_file",
        )
        assert item.is_file_based is True

    def test_catalog_item_repo_not_file_based(self):
        from vibelens.models.recommendation.catalog import CatalogItem

        item = CatalogItem(
            item_id="postgres-mcp",
            item_type="repo",
            name="Postgres MCP",
            description="MCP server for PostgreSQL",
            tags=["database"],
            category="data",
            platforms=["claude-code"],
            quality_score=90.0,
            popularity=0.9,
            updated_at="2026-04-01T00:00:00Z",
            source_url="https://github.com/example/postgres-mcp",
            repo_full_name="example/postgres-mcp",
            install_method="mcp_config",
        )
        assert item.is_file_based is False

    def test_user_profile(self):
        from vibelens.models.recommendation.profile import UserProfile

        profile = UserProfile(
            domains=["web-dev"],
            languages=["python", "typescript"],
            frameworks=["fastapi"],
            agent_platforms=["claude-code"],
            bottlenecks=["slow tests"],
            workflow_style="iterative debugger",
            search_keywords=["testing", "fastapi"],
        )
        assert len(profile.languages) == 2

    def test_recommendation_result(self):
        from vibelens.models.recommendation.results import RecommendationResult

        assert RecommendationResult is not None

"""Session analytics and pattern detection.

Analytical modules operate on parsed ATIF trajectories to produce
higher-level insights: conversation phase classification, tool call
dependency graphs, and cross-agent session correlation.
"""

from vibelens.analysis.correlator import (
    CorrelatedGroup,
    CorrelatedSession,
    correlate_sessions,
)
from vibelens.analysis.phase_detector import detect_phases
from vibelens.analysis.pricing import (
    ModelPricing,
    compute_step_cost,
    compute_trajectory_cost,
    lookup_pricing,
    normalize_model_name,
)
from vibelens.analysis.tool_graph import ToolDependencyGraph, ToolEdge, build_tool_graph
from vibelens.models.analysis.phase import PhaseSegment

__all__ = [
    "CorrelatedGroup",
    "CorrelatedSession",
    "ModelPricing",
    "PhaseSegment",
    "ToolDependencyGraph",
    "ToolEdge",
    "build_tool_graph",
    "compute_step_cost",
    "compute_trajectory_cost",
    "correlate_sessions",
    "detect_phases",
    "lookup_pricing",
    "normalize_model_name",
]

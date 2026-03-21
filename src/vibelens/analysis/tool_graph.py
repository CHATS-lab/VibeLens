"""Tool call dependency graph construction.

Infers causal relationships between tool calls within a session:
read→edit chains, error→retry loops, search→read flows, and temporal
sequencing.  Produces a DAG that reveals the agent's problem-solving
strategy beyond a flat chronological list.
"""

from pydantic import BaseModel, Field

from vibelens.analysis.constants import TOOL_CATEGORY_MAP
from vibelens.models.trajectories import Step

_FILE_PATH_KEYS = {"file_path", "path", "filename", "notebook_path", "directory"}


class ToolEdge(BaseModel):
    """Directed edge between two tool calls."""

    source_tool_call_id: str = Field(description="ID of the preceding tool call.")
    target_tool_call_id: str = Field(description="ID of the following tool call.")
    relation: str = Field(
        description="Edge type: read_before_write, error_retry, search_then_read, sequential."
    )
    shared_resource: str = Field(
        default="", description="File path or pattern shared between source and target."
    )


class ToolDependencyGraph(BaseModel):
    """DAG of causal dependencies between tool calls in a session."""

    session_id: str = Field(description="Session this graph belongs to.")
    nodes: list[str] = Field(
        default_factory=list, description="Tool call IDs in topological order."
    )
    edges: list[ToolEdge] = Field(
        default_factory=list, description="Directed edges between tool calls."
    )
    root_nodes: list[str] = Field(
        default_factory=list, description="Tool call IDs with no predecessors."
    )


def build_tool_graph(steps: list[Step], session_id: str = "") -> ToolDependencyGraph:
    """Build a dependency graph from a session's tool calls.

    Args:
        steps: Ordered steps from a single session.
        session_id: Session identifier for the graph.

    Returns:
        ToolDependencyGraph with inferred edges.
    """
    flat_calls = _flatten_tool_calls(steps)
    if not flat_calls:
        return ToolDependencyGraph(session_id=session_id)
    nodes = [tc_id for tc_id, _, _, _ in flat_calls]
    edges: list[ToolEdge] = []
    has_predecessor: set[str] = set()

    edges.extend(_find_read_before_write(flat_calls, has_predecessor))
    edges.extend(_find_error_retry(flat_calls, has_predecessor))
    edges.extend(_find_search_then_read(flat_calls, has_predecessor))
    edges.extend(_find_sequential(flat_calls, has_predecessor))

    root_nodes = [n for n in nodes if n not in has_predecessor]

    return ToolDependencyGraph(
        session_id=session_id, nodes=nodes, edges=edges, root_nodes=root_nodes
    )


def _flatten_tool_calls(steps: list[Step]) -> list[tuple[str, str, str, dict | str | None]]:
    """Extract (id, name, category, input) tuples in chronological order."""
    result = []
    for step in steps:
        for tc in step.tool_calls:
            if not tc.tool_call_id:
                continue
            category = TOOL_CATEGORY_MAP.get(tc.function_name, "other")
            result.append((tc.tool_call_id, tc.function_name, category, tc.arguments))
    return result


def _extract_file_path(raw_input: dict | str | None) -> str:
    """Extract a file path from tool input arguments."""
    if not isinstance(raw_input, dict):
        return ""
    for key in _FILE_PATH_KEYS:
        value = raw_input.get(key, "")
        if isinstance(value, str) and value:
            return value
    return ""


def _find_read_before_write(
    calls: list[tuple[str, str, str, dict | str | None]], has_predecessor: set[str]
) -> list[ToolEdge]:
    """Detect Read(path=X) followed by Edit/Write(path=X)."""
    edges: list[ToolEdge] = []
    read_paths: dict[str, str] = {}
    for tc_id, _name, category, raw_input in calls:
        path = _extract_file_path(raw_input)
        if not path:
            continue
        if category == "file_read":
            read_paths[path] = tc_id
        elif category == "file_write" and path in read_paths:
            source_id = read_paths[path]
            edges.append(
                ToolEdge(
                    source_tool_call_id=source_id,
                    target_tool_call_id=tc_id,
                    relation="read_before_write",
                    shared_resource=path,
                )
            )
            has_predecessor.add(tc_id)
    return edges


def _find_error_retry(
    calls: list[tuple[str, str, str, dict | str | None]], has_predecessor: set[str]
) -> list[ToolEdge]:
    """Detect tool with is_error followed by same tool name.

    NOTE: Currently inert — the flattened tuple doesn't carry ``is_error``,
    so ``prev_error_name`` is never set. This is a placeholder for when
    the tuple is extended to include error status. The sequential fallback
    in ``_find_sequential`` covers the gap for now.
    """
    edges: list[ToolEdge] = []
    prev_error_name: str = ""
    prev_error_id: str = ""
    for _idx, (tc_id, name, _category, _raw_input) in enumerate(calls):
        if prev_error_name and name == prev_error_name:
            edges.append(
                ToolEdge(
                    source_tool_call_id=prev_error_id,
                    target_tool_call_id=tc_id,
                    relation="error_retry",
                )
            )
            has_predecessor.add(tc_id)
            prev_error_name = ""
            prev_error_id = ""
            continue
        prev_error_name = ""
        prev_error_id = ""
    return edges


def _find_search_then_read(
    calls: list[tuple[str, str, str, dict | str | None]], has_predecessor: set[str]
) -> list[ToolEdge]:
    """Detect Grep/Glob followed by Read targeting found paths."""
    edges: list[ToolEdge] = []
    last_search_id: str = ""
    for tc_id, _name, category, raw_input in calls:
        if category == "search":
            last_search_id = tc_id
        elif category == "file_read" and last_search_id:
            edges.append(
                ToolEdge(
                    source_tool_call_id=last_search_id,
                    target_tool_call_id=tc_id,
                    relation="search_then_read",
                    shared_resource=_extract_file_path(raw_input),
                )
            )
            has_predecessor.add(tc_id)
    return edges


def _find_sequential(
    calls: list[tuple[str, str, str, dict | str | None]], has_predecessor: set[str]
) -> list[ToolEdge]:
    """Add sequential edges for tool calls that weren't linked by stronger relations.

    Only connects calls that don't already have a predecessor from
    read_before_write, error_retry, or search_then_read — acting as
    a fallback to ensure every non-root node has exactly one inbound edge.
    """
    edges: list[ToolEdge] = []
    for i in range(1, len(calls)):
        tc_id = calls[i][0]
        if tc_id in has_predecessor:
            continue
        prev_id = calls[i - 1][0]
        edges.append(
            ToolEdge(source_tool_call_id=prev_id, target_tool_call_id=tc_id, relation="sequential")
        )
        has_predecessor.add(tc_id)
    return edges

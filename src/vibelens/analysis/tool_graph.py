"""Tool call dependency graph construction.

Infers causal relationships between tool calls within a session:
read→edit chains, error→retry loops, search→read flows, write→test
cycles, iterative edits, and temporal sequencing.  Produces a DAG
that reveals the agent's problem-solving strategy beyond a flat
chronological list.
"""

from vibelens.analysis.tool_categories import TOOL_CATEGORY_MAP
from vibelens.models.analysis.tool_graph import ToolDependencyGraph, ToolEdge
from vibelens.models.trajectories import Step

_FILE_PATH_KEYS = {"file_path", "path", "filename", "notebook_path", "directory"}

MAX_READ_WRITE_DISTANCE = 20
MAX_SEARCH_READ_DISTANCE = 12
MAX_WRITE_TEST_DISTANCE = 5
MAX_ERROR_RETRY_DISTANCE = 6


class _FlatCall:
    """A single tool call with its metadata for graph construction."""

    __slots__ = ("tc_id", "name", "category", "raw_input", "is_error", "step_id", "index")

    def __init__(
        self,
        tc_id: str,
        name: str,
        category: str,
        raw_input: dict | str | None,
        is_error: bool,
        step_id: str,
        index: int,
    ):
        self.tc_id = tc_id
        self.name = name
        self.category = category
        self.raw_input = raw_input
        self.is_error = is_error
        self.step_id = step_id
        self.index = index


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
    nodes = [c.tc_id for c in flat_calls]
    edges: list[ToolEdge] = []
    has_predecessor: set[str] = set()

    edges.extend(_find_read_before_write(flat_calls, has_predecessor))
    edges.extend(_find_search_then_read(flat_calls, has_predecessor))
    edges.extend(_find_write_then_test(flat_calls, has_predecessor))
    edges.extend(_find_multi_edit(flat_calls, has_predecessor))
    edges.extend(_find_error_retry(flat_calls, has_predecessor))
    edges.extend(_find_sequential(flat_calls, has_predecessor))

    root_nodes = [n for n in nodes if n not in has_predecessor]

    return ToolDependencyGraph(
        session_id=session_id, nodes=nodes, edges=edges, root_nodes=root_nodes
    )


def _flatten_tool_calls(steps: list[Step]) -> list[_FlatCall]:
    """Extract tool call metadata in chronological order.

    Joins each tool call with its observation error status from the
    same step, enabling error_retry detection downstream.
    """
    result: list[_FlatCall] = []
    index = 0

    for step in steps:
        # Build error lookup from observation results in this step
        error_ids: set[str] = set()
        if step.observation:
            for obs_result in step.observation.results:
                has_error = (
                    obs_result.source_call_id
                    and obs_result.extra
                    and obs_result.extra.get("is_error")
                )
                if has_error:
                    error_ids.add(obs_result.source_call_id)

        for tc in step.tool_calls:
            if not tc.tool_call_id:
                continue
            category = TOOL_CATEGORY_MAP.get(tc.function_name, "other")
            is_error = tc.tool_call_id in error_ids
            result.append(
                _FlatCall(
                    tc_id=tc.tool_call_id,
                    name=tc.function_name,
                    category=category,
                    raw_input=tc.arguments,
                    is_error=is_error,
                    step_id=step.step_id,
                    index=index,
                )
            )
            index += 1

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


def _find_read_before_write(calls: list[_FlatCall], has_predecessor: set[str]) -> list[ToolEdge]:
    """Detect Read(path=X) followed by Edit/Write(path=X) within a bounded window.

    Only links a write to the most recent read of the same path
    within MAX_READ_WRITE_DISTANCE calls.
    """
    edges: list[ToolEdge] = []
    # Map: file_path -> (tc_id, call_index)
    read_paths: dict[str, tuple[str, int]] = {}

    for call in calls:
        path = _extract_file_path(call.raw_input)
        if not path:
            continue
        if call.category == "file_read":
            read_paths[path] = (call.tc_id, call.index)
        elif call.category == "file_write" and path in read_paths:
            source_id, source_idx = read_paths[path]
            if call.index - source_idx <= MAX_READ_WRITE_DISTANCE:
                edges.append(
                    ToolEdge(
                        source_tool_call_id=source_id,
                        target_tool_call_id=call.tc_id,
                        relation="read_before_write",
                        shared_resource=path,
                    )
                )
                has_predecessor.add(call.tc_id)

    return edges


def _find_search_then_read(calls: list[_FlatCall], has_predecessor: set[str]) -> list[ToolEdge]:
    """Detect search (Grep/Glob) followed by Read within a proximity window.

    Only connects a read to the most recent preceding search if:
    - The read is within MAX_SEARCH_READ_DISTANCE calls of the search
    - No non-search/non-read category call breaks the chain (i.e., the
      agent hasn't context-switched to writing/shell between search and read)
    """
    edges: list[ToolEdge] = []
    last_search_id: str = ""
    last_search_idx: int = -1

    for call in calls:
        if call.category == "search":
            last_search_id = call.tc_id
            last_search_idx = call.index
        elif call.category == "file_read" and last_search_id:
            distance = call.index - last_search_idx
            if distance <= MAX_SEARCH_READ_DISTANCE:
                edges.append(
                    ToolEdge(
                        source_tool_call_id=last_search_id,
                        target_tool_call_id=call.tc_id,
                        relation="search_then_read",
                        shared_resource=_extract_file_path(call.raw_input),
                    )
                )
                has_predecessor.add(call.tc_id)
        elif call.category not in ("search", "file_read", "other"):
            # Agent moved on to writing/shell/web — reset the search context
            last_search_id = ""
            last_search_idx = -1

    return edges


def _find_write_then_test(calls: list[_FlatCall], has_predecessor: set[str]) -> list[ToolEdge]:
    """Detect file_write followed by shell (edit→test cycle).

    Links the most recent write to a subsequent shell command
    within MAX_WRITE_TEST_DISTANCE calls, representing the
    common pattern of editing code then running tests/lint/build.
    """
    edges: list[ToolEdge] = []
    last_write_id: str = ""
    last_write_idx: int = -1
    last_write_path: str = ""

    for call in calls:
        if call.category == "file_write":
            last_write_id = call.tc_id
            last_write_idx = call.index
            last_write_path = _extract_file_path(call.raw_input)
        elif call.category == "shell" and last_write_id:
            distance = call.index - last_write_idx
            if distance <= MAX_WRITE_TEST_DISTANCE:
                edges.append(
                    ToolEdge(
                        source_tool_call_id=last_write_id,
                        target_tool_call_id=call.tc_id,
                        relation="write_then_test",
                        shared_resource=last_write_path,
                    )
                )
                has_predecessor.add(call.tc_id)
                # Reset so we don't link the same write to multiple shells
                last_write_id = ""
                last_write_idx = -1
        elif call.category not in ("file_write", "other"):
            # Agent moved on to a different activity — reset
            last_write_id = ""
            last_write_idx = -1

    return edges


def _find_multi_edit(calls: list[_FlatCall], has_predecessor: set[str]) -> list[ToolEdge]:
    """Detect repeated writes to the same file (iterative refinement).

    When the same file is edited multiple times, links consecutive
    edits to show the refinement chain.
    """
    edges: list[ToolEdge] = []
    # Map: file_path -> tc_id of last write
    last_write_by_path: dict[str, str] = {}

    for call in calls:
        if call.category != "file_write":
            continue
        path = _extract_file_path(call.raw_input)
        if not path:
            continue
        if path in last_write_by_path:
            source_id = last_write_by_path[path]
            edges.append(
                ToolEdge(
                    source_tool_call_id=source_id,
                    target_tool_call_id=call.tc_id,
                    relation="multi_edit",
                    shared_resource=path,
                )
            )
            has_predecessor.add(call.tc_id)
        last_write_by_path[path] = call.tc_id

    return edges


def _find_error_retry(calls: list[_FlatCall], has_predecessor: set[str]) -> list[ToolEdge]:
    """Detect a failed tool call followed by the same tool name (retry).

    Scans forward from each errored call for a retry of the same
    tool within MAX_ERROR_RETRY_DISTANCE calls.
    """
    edges: list[ToolEdge] = []
    consumed: set[str] = set()

    for i, call in enumerate(calls):
        if not call.is_error or call.tc_id in consumed:
            continue
        # Look ahead for a retry of the same tool
        for j in range(i + 1, min(i + 1 + MAX_ERROR_RETRY_DISTANCE, len(calls))):
            candidate = calls[j]
            if candidate.tc_id in consumed:
                continue
            if candidate.name == call.name:
                edges.append(
                    ToolEdge(
                        source_tool_call_id=call.tc_id,
                        target_tool_call_id=candidate.tc_id,
                        relation="error_retry",
                    )
                )
                has_predecessor.add(candidate.tc_id)
                consumed.add(candidate.tc_id)
                break

    return edges


def _find_sequential(calls: list[_FlatCall], has_predecessor: set[str]) -> list[ToolEdge]:
    """Add sequential edges for tool calls not linked by stronger relations.

    Only connects calls that don't already have a predecessor from
    semantic patterns — acting as a fallback to ensure every non-root
    node has exactly one inbound edge.
    """
    edges: list[ToolEdge] = []
    for i in range(1, len(calls)):
        if calls[i].tc_id in has_predecessor:
            continue
        prev_id = calls[i - 1].tc_id
        edges.append(
            ToolEdge(
                source_tool_call_id=prev_id,
                target_tool_call_id=calls[i].tc_id,
                relation="sequential",
            )
        )
        has_predecessor.add(calls[i].tc_id)

    return edges

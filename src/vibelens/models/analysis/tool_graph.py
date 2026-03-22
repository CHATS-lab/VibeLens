"""Tool dependency graph models for session flow analysis."""

from pydantic import BaseModel, Field


class ToolEdge(BaseModel):
    """Directed edge between two tool calls."""

    source_tool_call_id: str = Field(description="ID of the preceding tool call.")
    target_tool_call_id: str = Field(description="ID of the following tool call.")
    relation: str = Field(
        description="Edge type: read_before_write, error_retry, search_then_read, "
        "write_then_test, multi_edit, sequential."
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

"""Tests for vibelens.ingest.tool_graph — tool call dependency DAG."""

from vibelens.ingest.tool_graph import ToolEdge, build_tool_graph
from vibelens.models.message import Message, ToolCall


def _msg(session_id: str, tool_calls: list[ToolCall]) -> Message:
    """Build a minimal message with tool calls."""
    return Message(
        uuid="m1",
        session_id=session_id,
        role="assistant",
        type="assistant",
        tool_calls=tool_calls,
    )


# ─── build_tool_graph
class TestBuildToolGraph:
    def test_empty_messages(self):
        graph = build_tool_graph([])
        assert graph.session_id == ""
        assert graph.nodes == []
        assert graph.edges == []
        print(f"  empty graph: {graph}")

    def test_no_tool_calls(self):
        msg = Message(
            uuid="m1", session_id="s1",
            role="user", type="user", content="hi",
        )
        graph = build_tool_graph([msg])
        assert graph.session_id == "s1"
        assert graph.nodes == []

    def test_single_tool_call(self):
        tc = ToolCall(
            id="tc1", name="Read", category="file_read",
            input={"file_path": "/a.py"},
        )
        graph = build_tool_graph([_msg("s1", [tc])])
        assert len(graph.nodes) == 1
        assert graph.root_nodes == ["tc1"]
        print(f"  single node graph: {graph.nodes}")

    def test_read_before_write_edge(self):
        tc_read = ToolCall(
            id="tc1", name="Read", category="file_read",
            input={"file_path": "/a.py"},
        )
        tc_write = ToolCall(
            id="tc2", name="Edit", category="file_write",
            input={"file_path": "/a.py"},
        )
        graph = build_tool_graph([_msg("s1", [tc_read, tc_write])])
        rbw = [e for e in graph.edges if e.relation == "read_before_write"]
        assert len(rbw) == 1
        assert rbw[0].source_tool_call_id == "tc1"
        assert rbw[0].target_tool_call_id == "tc2"
        assert rbw[0].shared_resource == "/a.py"
        print(f"  read->write edge: {rbw[0]}")

    def test_search_then_read_edge(self):
        tc_search = ToolCall(
            id="tc1", name="Grep", category="search",
            input={"pattern": "TODO"},
        )
        tc_read = ToolCall(
            id="tc2", name="Read", category="file_read",
            input={"file_path": "/found.py"},
        )
        graph = build_tool_graph([_msg("s1", [tc_search, tc_read])])
        str_edges = [
            e for e in graph.edges if e.relation == "search_then_read"
        ]
        assert len(str_edges) == 1
        assert str_edges[0].source_tool_call_id == "tc1"
        assert str_edges[0].shared_resource == "/found.py"
        print(f"  search->read edge: {str_edges[0]}")

    def test_sequential_fallback(self):
        tc1 = ToolCall(
            id="tc1", name="Bash", category="shell",
            input={"command": "ls"},
        )
        tc2 = ToolCall(
            id="tc2", name="Bash", category="shell",
            input={"command": "pwd"},
        )
        graph = build_tool_graph([_msg("s1", [tc1, tc2])])
        seq = [e for e in graph.edges if e.relation == "sequential"]
        assert len(seq) == 1
        assert seq[0].source_tool_call_id == "tc1"
        assert seq[0].target_tool_call_id == "tc2"

    def test_root_nodes_exclude_targets(self):
        tc1 = ToolCall(
            id="tc1", name="Read", category="file_read",
            input={"file_path": "/a.py"},
        )
        tc2 = ToolCall(
            id="tc2", name="Edit", category="file_write",
            input={"file_path": "/a.py"},
        )
        tc3 = ToolCall(
            id="tc3", name="Bash", category="shell",
            input={"command": "test"},
        )
        graph = build_tool_graph([_msg("s1", [tc1, tc2, tc3])])
        assert "tc1" in graph.root_nodes
        assert "tc2" not in graph.root_nodes
        print(f"  root_nodes: {graph.root_nodes}")

    def test_no_id_tool_calls_skipped(self):
        tc = ToolCall(
            id="", name="Read", category="file_read", input={},
        )
        graph = build_tool_graph([_msg("s1", [tc])])
        assert graph.nodes == []

    def test_different_file_paths_no_rbw(self):
        tc_read = ToolCall(
            id="tc1", name="Read", category="file_read",
            input={"file_path": "/a.py"},
        )
        tc_write = ToolCall(
            id="tc2", name="Edit", category="file_write",
            input={"file_path": "/b.py"},
        )
        graph = build_tool_graph([_msg("s1", [tc_read, tc_write])])
        rbw = [e for e in graph.edges if e.relation == "read_before_write"]
        assert len(rbw) == 0

    def test_multiple_messages(self):
        tc1 = ToolCall(
            id="tc1", name="Read", category="file_read",
            input={"file_path": "/x.py"},
        )
        tc2 = ToolCall(
            id="tc2", name="Edit", category="file_write",
            input={"file_path": "/x.py"},
        )
        msg1 = _msg("s1", [tc1])
        msg2 = _msg("s1", [tc2])
        graph = build_tool_graph([msg1, msg2])
        rbw = [e for e in graph.edges if e.relation == "read_before_write"]
        assert len(rbw) == 1
        print(f"  cross-message edge: {rbw[0]}")


# ─── ToolEdge model
class TestToolEdge:
    def test_defaults(self):
        edge = ToolEdge(
            source_tool_call_id="a",
            target_tool_call_id="b",
            relation="sequential",
        )
        assert edge.shared_resource == ""

    def test_with_resource(self):
        edge = ToolEdge(
            source_tool_call_id="a",
            target_tool_call_id="b",
            relation="read_before_write",
            shared_resource="/file.py",
        )
        assert edge.shared_resource == "/file.py"

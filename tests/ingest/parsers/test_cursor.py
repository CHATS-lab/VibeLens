"""Cursor parser tests — pin the activation-only contract.

Cursor has no dedicated skill-activation tool. SKILL.md is auto-discovered
and injected as context server-side; subsequent ``ReadFile`` of SKILL.md is
working-memory access (often re-read multiple times), not activation. The
parser therefore leaves ``is_skill`` unset for both ToolCall construction
sites (``_build_tool_pair`` for the main SQLite path, and the inline
``tool_use`` branch for sub-agent JSONL).
"""

import json
from pathlib import Path

from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.ingest.parsers.cursor import (
    CursorParser,
    _build_tool_pair,
    _parse_subagent_file,
)


def test_main_site_does_not_tag_skill_path() -> None:
    """``_build_tool_pair`` (main SQLite blob format) leaves is_skill unset
    even when the path points at a SKILL.md."""
    diagnostics = DiagnosticsCollector()
    block = {
        "type": "tool-call",
        "toolCallId": "tc_x",
        "toolName": "ReadFile",
        "args": {"path": "/Users/x/.cursor/skills-cursor/foo/SKILL.md"},
    }
    tc, _ = _build_tool_pair(block, results_by_call_id={}, diagnostics=diagnostics)
    print(f"main site: tc.is_skill={tc.is_skill}")
    assert tc.is_skill is None


def test_subagent_site_does_not_tag_skill_path(tmp_path: Path) -> None:
    """The sub-agent JSONL path (Anthropic-style ``tool_use`` block) also
    leaves is_skill unset for SKILL.md reads."""
    parser = CursorParser()
    sub_path = tmp_path / "sub.jsonl"
    events = [
        {
            "role": "user",
            "message": {"content": [
                {"type": "text", "text": "<user_query>x</user_query>"}
            ]},
        },
        {
            "role": "assistant",
            "message": {"content": [
                {
                    "type": "tool_use",
                    "id": "tc_a",
                    "name": "ReadFile",
                    "input": {"path": "/Users/x/.cursor/skills-cursor/foo/SKILL.md"},
                },
            ]},
        },
    ]
    with sub_path.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    sub_traj = _parse_subagent_file(
        sub_path, parent_session_id="parent", agent_builder=parser.build_agent
    )
    assert sub_traj is not None
    tcs = [tc for s in sub_traj.steps for tc in s.tool_calls]
    print(f"subagent site: {[(tc.function_name, tc.is_skill) for tc in tcs]}")
    assert all(tc.is_skill is None for tc in tcs)

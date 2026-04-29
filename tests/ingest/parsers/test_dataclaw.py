"""Unit tests for vibelens.ingest.parsers.dataclaw parser."""

import json
from pathlib import Path

import pytest

from vibelens.ingest.parsers.dataclaw import DataclawParser, _build_steps, _build_tool_calls
from vibelens.models.enums import AgentType, StepSource


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _make_record(
    session_id: str = "sess-1",
    project: str = "/home/user/project",
    model: str = "claude-sonnet-4-5",
    messages: list[dict] | None = None,
    start_time: str = "2025-01-15T10:00:00Z",
) -> dict:
    if messages is None:
        messages = [
            {"role": "user", "content": "Hello", "timestamp": "2025-01-15T10:00:00Z"},
            {"role": "assistant", "content": "Hi there", "timestamp": "2025-01-15T10:00:05Z"},
        ]
    return {
        "session_id": session_id,
        "project": project,
        "model": model,
        "messages": messages,
        "start_time": start_time,
    }


@pytest.fixture
def parser() -> DataclawParser:
    return DataclawParser()


def test_basic_single_session(tmp_path: Path, parser: DataclawParser) -> None:
    """A JSONL file with one record yields one trajectory with correct metadata."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record()])
    trajs = parser.parse(f)
    assert len(trajs) == 1
    traj = trajs[0]
    assert traj.session_id == "sess-1"
    assert traj.agent.name == AgentType.DATACLAW.value
    assert traj.agent.model_name == "claude-sonnet-4-5"
    assert traj.project_path == "/home/user/project"
    print(f"Basic: session={traj.session_id}, steps={len(traj.steps)}")


def test_multi_session_file(tmp_path: Path, parser: DataclawParser) -> None:
    """Multiple records in one file yield one trajectory per record."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [
        _make_record(session_id="sess-1"),
        _make_record(session_id="sess-2"),
        _make_record(session_id="sess-3"),
    ])
    trajs = parser.parse(f)
    assert len(trajs) == 3
    assert {t.session_id for t in trajs} == {"sess-1", "sess-2", "sess-3"}
    print(f"Multi-session: {[t.session_id for t in trajs]}")


def test_step_sources_mapped_correctly(tmp_path: Path, parser: DataclawParser) -> None:
    """User messages -> StepSource.USER; assistant messages -> StepSource.AGENT."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record()])
    traj = parser.parse(f)[0]
    sources = [s.source for s in traj.steps]
    assert StepSource.USER in sources
    assert StepSource.AGENT in sources
    print(f"sources: {sources}")


def test_deterministic_step_ids_stable_across_parses(
    tmp_path: Path, parser: DataclawParser
) -> None:
    """Parsing the same file twice produces identical step IDs."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record()])
    ids_a = [s.step_id for s in parser.parse(f)[0].steps]
    ids_b = [s.step_id for s in parser.parse(f)[0].steps]
    assert ids_a == ids_b
    print(f"Stable step IDs: {ids_a}")


def test_missing_session_id_derives_stable_id(tmp_path: Path, parser: DataclawParser) -> None:
    """Records without session_id get a deterministic ID from project+start_time."""
    record = _make_record()
    del record["session_id"]
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [record, record])
    trajs = parser.parse(f)
    assert len(trajs) == 2
    assert trajs[0].session_id == trajs[1].session_id
    assert trajs[0].session_id != ""
    print(f"Derived session_id: {trajs[0].session_id}")


def test_tool_uses_become_tool_calls(tmp_path: Path, parser: DataclawParser) -> None:
    """tool_uses in an assistant message become ToolCall objects on the step."""
    messages = [
        {"role": "user", "content": "list files", "timestamp": "2025-01-15T10:00:00Z"},
        {
            "role": "assistant",
            "content": "Let me check.",
            "timestamp": "2025-01-15T10:00:05Z",
            "tool_uses": [
                {"tool": "Bash", "input": {"command": "ls"}},
                {"tool": "Read", "input": {"path": "/tmp/a"}},
            ],
        },
    ]
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record(messages=messages)])
    traj = parser.parse(f)[0]
    agent_step = next(s for s in traj.steps if s.source == StepSource.AGENT)
    assert len(agent_step.tool_calls) == 2
    names = [tc.function_name for tc in agent_step.tool_calls]
    assert "Bash" in names
    assert "Read" in names
    print(f"tool_calls: {names}")


def test_tool_uses_produce_no_observation(tmp_path: Path, parser: DataclawParser) -> None:
    """Tool calls from dataclaw have no paired observation — outputs are scrubbed at source."""
    messages = [
        {"role": "user", "content": "run something", "timestamp": "2025-01-15T10:00:00Z"},
        {
            "role": "assistant",
            "content": "Running it.",
            "timestamp": "2025-01-15T10:00:05Z",
            "tool_uses": [{"tool": "Bash", "input": {"command": "ls"}}],
        },
    ]
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record(messages=messages)])
    traj = parser.parse(f)[0]
    agent_step = next(s for s in traj.steps if s.source == StepSource.AGENT)
    assert len(agent_step.tool_calls) == 1
    assert agent_step.observation is None
    print("tool outputs scrubbed -> observation is None")


def test_thinking_field_becomes_reasoning_content(tmp_path: Path, parser: DataclawParser) -> None:
    """thinking field in a message becomes step.reasoning_content."""
    messages = [
        {"role": "user", "content": "why?", "timestamp": "2025-01-15T10:00:00Z"},
        {
            "role": "assistant",
            "content": "Because reasons.",
            "timestamp": "2025-01-15T10:00:05Z",
            "thinking": "I need to reason about this carefully.",
        },
    ]
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record(messages=messages)])
    traj = parser.parse(f)[0]
    agent_step = next(s for s in traj.steps if s.source == StepSource.AGENT)
    assert agent_step.reasoning_content == "I need to reason about this carefully."
    print(f"reasoning: {agent_step.reasoning_content}")


def test_model_name_on_agent_steps_only(tmp_path: Path, parser: DataclawParser) -> None:
    """Session-level model is set on assistant steps; user steps have model_name=None."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record(model="claude-opus-4-7")])
    traj = parser.parse(f)[0]
    user_step = next(s for s in traj.steps if s.source == StepSource.USER)
    agent_step = next(s for s in traj.steps if s.source == StepSource.AGENT)
    assert user_step.model_name is None
    assert agent_step.model_name == "claude-opus-4-7"
    print(f"model on agent only: {agent_step.model_name}")


def test_source_type_extra_is_huggingface(tmp_path: Path, parser: DataclawParser) -> None:
    """Every trajectory carries extra.source_type == 'huggingface'."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record()])
    traj = parser.parse(f)[0]
    assert traj.extra is not None
    assert traj.extra.get("source_type") == "huggingface"
    print(f"source_type: {traj.extra['source_type']}")


def test_first_message_populated(tmp_path: Path, parser: DataclawParser) -> None:
    """Trajectory.first_message reflects the first user message content."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record(messages=[
        {"role": "user", "content": "Tell me a joke.", "timestamp": "2025-01-15T10:00:00Z"},
        {
            "role": "assistant",
            "content": "Why did the chicken...",
            "timestamp": "2025-01-15T10:00:05Z",
        },
    ])])
    traj = parser.parse(f)[0]
    assert traj.first_message == "Tell me a joke."
    print(f"first_message: {traj.first_message}")


def test_malformed_jsonl_lines_skipped(tmp_path: Path, parser: DataclawParser) -> None:
    """Corrupt JSONL lines are skipped; surrounding valid records still parse."""
    f = tmp_path / "conversations.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps(_make_record("sess-ok")) + "\n"
        + "{not valid json\n"
        + json.dumps(_make_record("sess-also-ok")) + "\n",
        encoding="utf-8",
    )
    trajs = parser.parse(f)
    assert len(trajs) == 2
    assert {t.session_id for t in trajs} == {"sess-ok", "sess-also-ok"}
    print("Malformed lines skipped")


def test_empty_file_returns_empty_list(tmp_path: Path, parser: DataclawParser) -> None:
    """An empty file produces no trajectories."""
    f = tmp_path / "empty.jsonl"
    f.write_text("", encoding="utf-8")
    assert parser.parse(f) == []
    print("empty file -> []")


def test_record_with_no_messages_skipped(tmp_path: Path, parser: DataclawParser) -> None:
    """A record with an empty messages list produces no steps and is skipped."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record(messages=[])])
    assert parser.parse(f) == []
    print("empty messages record skipped")


def test_iter_trajectories_yields_same_results(tmp_path: Path, parser: DataclawParser) -> None:
    """iter_trajectories yields the same trajectories as parse()."""
    f = tmp_path / "conversations.jsonl"
    _write_jsonl(f, [_make_record("s1"), _make_record("s2")])
    from_parse = parser.parse(f)
    from_iter = list(parser.iter_trajectories(f))
    assert len(from_parse) == len(from_iter)
    assert {t.session_id for t in from_parse} == {t.session_id for t in from_iter}
    print(f"parse and iter_trajectories agree: {len(from_parse)} trajectories")


def test_build_steps_role_mapping() -> None:
    """_build_steps maps 'user' -> USER and 'assistant' -> AGENT sources."""
    messages = [
        {"role": "user", "content": "ping", "timestamp": "2025-01-15T10:00:00Z"},
        {"role": "assistant", "content": "pong", "timestamp": "2025-01-15T10:00:05Z"},
    ]
    steps = _build_steps(messages, "sess-x", "claude-sonnet-4-5")
    assert len(steps) == 2
    assert steps[0].source == StepSource.USER
    assert steps[1].source == StepSource.AGENT
    print(f"sources: {[s.source for s in steps]}")


def test_build_steps_unknown_roles_skipped() -> None:
    """Messages with roles other than user/assistant are silently skipped."""
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    steps = _build_steps(messages, "sess-x", "")
    assert len(steps) == 2
    print(f"system message skipped, {len(steps)} steps remain")


def test_build_steps_model_on_agent_steps_only() -> None:
    """model_name is applied to assistant steps; user steps get None."""
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    steps = _build_steps(messages, "s", "claude-opus-4-7")
    user_step = next(s for s in steps if s.source == StepSource.USER)
    agent_step = next(s for s in steps if s.source == StepSource.AGENT)
    assert user_step.model_name is None
    assert agent_step.model_name == "claude-opus-4-7"
    print(f"model on agent step: {agent_step.model_name}")


def test_build_steps_deterministic_step_ids() -> None:
    """Step IDs from _build_steps are stable across identical calls."""
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    steps_a = _build_steps(messages, "sess-stable", "m")
    steps_b = _build_steps(messages, "sess-stable", "m")
    assert [s.step_id for s in steps_a] == [s.step_id for s in steps_b]
    print(f"stable IDs: {[s.step_id for s in steps_a]}")


def test_build_tool_calls_extracts_name_and_args() -> None:
    """_build_tool_calls converts raw tool_uses into ToolCall objects."""
    raw = [
        {"tool": "Write", "input": {"path": "/a.txt", "content": "hello"}},
        {"tool": "Bash", "input": {"command": "echo hi"}},
    ]
    calls = _build_tool_calls(raw, "sess-z", 0)
    assert len(calls) == 2
    assert calls[0].function_name == "Write"
    assert calls[0].arguments == {"path": "/a.txt", "content": "hello"}
    assert calls[1].function_name == "Bash"
    print(f"tool calls: {[c.function_name for c in calls]}")


def test_build_tool_calls_deterministic_ids() -> None:
    """Tool call IDs from _build_tool_calls are stable across identical calls."""
    raw = [{"tool": "Read", "input": {"path": "/x"}}]
    calls_a = _build_tool_calls(raw, "s", 1)
    calls_b = _build_tool_calls(raw, "s", 1)
    assert calls_a[0].tool_call_id == calls_b[0].tool_call_id
    print(f"stable tool_call_id: {calls_a[0].tool_call_id}")


def test_build_tool_calls_unknown_tool_name_defaults() -> None:
    """Entries missing the 'tool' key fall back to 'unknown'."""
    raw = [{"input": {"command": "ls"}}]
    calls = _build_tool_calls(raw, "s", 0)
    assert len(calls) == 1
    assert calls[0].function_name == "unknown"
    print(f"default function_name: {calls[0].function_name}")


def test_build_tool_calls_empty_list() -> None:
    """Empty tool_uses input produces an empty list."""
    assert _build_tool_calls([], "s", 0) == []
    print("empty tool_uses -> []")


def test_build_tool_calls_non_dict_entries_skipped() -> None:
    """Non-dict entries in tool_uses are silently skipped."""
    raw = [{"tool": "Bash", "input": {}}, "not a dict", None]
    calls = _build_tool_calls(raw, "s", 0)
    assert len(calls) == 1
    assert calls[0].function_name == "Bash"
    print(f"non-dict skipped, {len(calls)} call parsed")

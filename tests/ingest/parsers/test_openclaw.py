"""Unit tests for vibelens.ingest.parsers.openclaw parser."""

import base64
import json
from pathlib import Path

import pytest

from vibelens.ingest.parsers.openclaw import (
    OpenClawParser,
    _build_metrics,
    _collect_tool_results,
    _decompose_content,
    _extract_session_meta,
)
from vibelens.models.enums import AgentType, ContentType, StepSource


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


@pytest.fixture
def parser() -> OpenClawParser:
    return OpenClawParser()


def _session_event(session_id: str = "sess-abc", cwd: str = "/home/user/proj") -> dict:
    return {"type": "session", "id": session_id, "cwd": cwd}


def _user_event(
    text: str = "Hello",
    msg_id: str = "m-u1",
    ts: str = "2025-01-15T10:00:00Z",
) -> dict:
    return {
        "type": "message",
        "id": msg_id,
        "timestamp": ts,
        "message": {"role": "user", "content": text},
    }


def _assistant_event(
    text: str = "Hi there",
    msg_id: str = "m-a1",
    ts: str = "2025-01-15T10:00:05Z",
    model: str = "claude-sonnet-4-5",
    usage: dict | None = None,
    content: str | list | None = None,
) -> dict:
    msg: dict = {
        "role": "assistant",
        "model": model,
        "content": content if content is not None else [{"type": "text", "text": text}],
    }
    if usage is not None:
        msg["usage"] = usage
    return {"type": "message", "id": msg_id, "timestamp": ts, "message": msg}


def test_basic_user_assistant_pair(tmp_path: Path, parser: OpenClawParser) -> None:
    """One user + one assistant event yields a single trajectory with 2 steps."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event("sess-1"),
        _user_event("What time is it?"),
        _assistant_event("It's 10 AM.", usage={"input": 10, "output": 5}),
    ])
    trajs = parser.parse(f)
    assert len(trajs) == 1
    traj = trajs[0]
    assert traj.session_id == "sess-1"
    assert traj.agent.name == AgentType.OPENCLAW.value
    assert traj.project_path == "/home/user/proj"
    user_steps = [s for s in traj.steps if s.source == StepSource.USER]
    agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
    assert len(user_steps) == 1
    assert len(agent_steps) == 1
    assert user_steps[0].message == "What time is it?"
    assert agent_steps[0].message == "It's 10 AM."
    print(f"Basic: {len(traj.steps)} steps, session={traj.session_id}")


def test_model_from_model_change_event(tmp_path: Path, parser: OpenClawParser) -> None:
    """model_change event sets the agent model name as provider/modelId."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        {"type": "model_change", "provider": "anthropic", "modelId": "claude-opus-4-7"},
        _user_event(),
        _assistant_event(model="claude-opus-4-7"),
    ])
    trajs = parser.parse(f)
    assert trajs[0].agent.model_name == "anthropic/claude-opus-4-7"
    print(f"model_change: {trajs[0].agent.model_name}")


def test_model_fallback_to_first_assistant(tmp_path: Path, parser: OpenClawParser) -> None:
    """Without a model_change event, model falls back to the first assistant message."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        _user_event(),
        _assistant_event(model="claude-haiku-4-5"),
    ])
    trajs = parser.parse(f)
    assert trajs[0].agent.model_name == "claude-haiku-4-5"
    print(f"model fallback: {trajs[0].agent.model_name}")


def test_model_snapshot_custom_event(tmp_path: Path, parser: OpenClawParser) -> None:
    """custom/model-snapshot event sets model when no model_change is present."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        {
            "type": "custom",
            "customType": "model-snapshot",
            "data": {"provider": "openai", "modelId": "gpt-4o"},
        },
        _user_event(),
        _assistant_event(model="gpt-4o"),
    ])
    trajs = parser.parse(f)
    assert trajs[0].agent.model_name == "openai/gpt-4o"
    print(f"model-snapshot: {trajs[0].agent.model_name}")


def test_metrics_mapped_from_usage(tmp_path: Path, parser: OpenClawParser) -> None:
    """Usage block maps to Metrics; prompt_tokens = input + cacheRead per ATIF convention."""
    usage = {
        "input": 100,
        "output": 50,
        "cacheRead": 200,
        "cacheWrite": 10,
        "cost": {"total": 0.042},
    }
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [_session_event(), _user_event(), _assistant_event(usage=usage)])
    trajs = parser.parse(f)
    agent_step = next(s for s in trajs[0].steps if s.source == StepSource.AGENT)
    m = agent_step.metrics
    assert m is not None
    # prompt_tokens = input(100) + cacheRead(200) = 300
    assert m.prompt_tokens == 300
    assert m.completion_tokens == 50
    assert m.cache_read_tokens == 200
    assert m.cache_write_tokens == 10
    assert m.cost_usd == pytest.approx(0.042)
    print(f"metrics: prompt={m.prompt_tokens} completion={m.completion_tokens} cost={m.cost_usd}")


def test_tool_call_paired_with_tool_result(tmp_path: Path, parser: OpenClawParser) -> None:
    """toolCall content block is paired with its matching toolResult message."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        _user_event("list files"),
        _assistant_event(content=[
            {"type": "text", "text": "Let me check."},
            {"type": "toolCall", "id": "tc-1", "name": "Bash", "arguments": {"command": "ls"}},
        ], usage={"input": 20, "output": 10}),
        {
            "type": "message",
            "id": "m-r1",
            "timestamp": "2025-01-15T10:00:10Z",
            "message": {
                "role": "toolResult",
                "toolCallId": "tc-1",
                "content": "file_a.py\nfile_b.py",
                "isError": False,
            },
        },
    ])
    trajs = parser.parse(f)
    agent_step = next(s for s in trajs[0].steps if s.source == StepSource.AGENT)
    assert len(agent_step.tool_calls) == 1
    assert agent_step.tool_calls[0].function_name == "Bash"
    assert agent_step.observation is not None
    result = agent_step.observation.results[0]
    assert "file_a.py" in result.content
    assert result.is_error is False
    print(f"tool call+result: {agent_step.tool_calls[0].function_name}, is_error={result.is_error}")


def test_tool_result_is_error_true(tmp_path: Path, parser: OpenClawParser) -> None:
    """isError=True on a toolResult maps to ObservationResult.is_error=True."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        _user_event("run broken command"),
        _assistant_event(content=[
            {"type": "toolCall", "id": "tc-err", "name": "Bash", "arguments": {"command": "bad"}},
        ]),
        {
            "type": "message",
            "id": "m-rerr",
            "timestamp": "2025-01-15T10:00:10Z",
            "message": {
                "role": "toolResult",
                "toolCallId": "tc-err",
                "content": "command not found",
                "isError": True,
            },
        },
    ])
    trajs = parser.parse(f)
    agent_step = next(s for s in trajs[0].steps if s.source == StepSource.AGENT)
    assert agent_step.observation.results[0].is_error is True
    print("is_error=True propagated correctly")


def test_image_content_block_decoded(tmp_path: Path, parser: OpenClawParser) -> None:
    """image block in assistant content is decoded into a ContentPart; message becomes a list."""
    fake_png = base64.b64encode(b"PNG_DATA").decode()
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        _user_event("here is a screenshot"),
        _assistant_event(content=[
            {"type": "text", "text": "I see the image."},
            {"type": "image", "data": fake_png},
        ]),
    ])
    trajs = parser.parse(f)
    agent_step = next(s for s in trajs[0].steps if s.source == StepSource.AGENT)
    assert isinstance(agent_step.message, list)
    image_parts = [p for p in agent_step.message if p.type == ContentType.IMAGE]
    assert len(image_parts) == 1
    assert image_parts[0].source.base64 == fake_png
    assert image_parts[0].source.media_type == "image/png"
    print(f"image decoded end-to-end: {image_parts[0].source.media_type}")


def test_thinking_content_block(tmp_path: Path, parser: OpenClawParser) -> None:
    """thinking blocks surface as step.reasoning_content; text stays in message."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        _user_event("hard question"),
        _assistant_event(content=[
            {"type": "thinking", "thinking": "Let me reason carefully."},
            {"type": "text", "text": "The answer is 42."},
        ]),
    ])
    trajs = parser.parse(f)
    agent_step = next(s for s in trajs[0].steps if s.source == StepSource.AGENT)
    assert agent_step.reasoning_content == "Let me reason carefully."
    assert agent_step.message == "The answer is 42."
    print(f"reasoning: {agent_step.reasoning_content}")


def test_step_id_populated_from_event_id(tmp_path: Path, parser: OpenClawParser) -> None:
    """Step.step_id is taken from the event's top-level id field."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        _user_event(msg_id="event-u42"),
        _assistant_event(msg_id="event-a99"),
    ])
    trajs = parser.parse(f)
    step_ids = [s.step_id for s in trajs[0].steps]
    assert "event-u42" in step_ids
    assert "event-a99" in step_ids
    print(f"step_ids: {step_ids}")


def test_tool_result_messages_not_emitted_as_steps(tmp_path: Path, parser: OpenClawParser) -> None:
    """role:toolResult messages are consumed internally and don't become steps."""
    f = tmp_path / "session.jsonl"
    _write_jsonl(f, [
        _session_event(),
        _user_event(),
        _assistant_event(content=[
            {"type": "toolCall", "id": "tc-1", "name": "Bash", "arguments": {}},
        ]),
        {
            "type": "message",
            "id": "m-r1",
            "message": {"role": "toolResult", "toolCallId": "tc-1", "content": "ok"},
        },
    ])
    trajs = parser.parse(f)
    # Only user + assistant steps -- toolResult is not a step
    assert len(trajs[0].steps) == 2
    print(f"steps={len(trajs[0].steps)} (toolResult not emitted)")


def test_malformed_jsonl_bad_lines_skipped(tmp_path: Path, parser: OpenClawParser) -> None:
    """Corrupt JSONL lines are skipped; valid events still yield a trajectory."""
    f = tmp_path / "session.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps(_session_event()) + "\n"
        + "{not valid json\n"
        + json.dumps(_user_event()) + "\n"
        + json.dumps(_assistant_event()) + "\n",
        encoding="utf-8",
    )
    trajs = parser.parse(f)
    assert len(trajs) == 1
    assert len(trajs[0].steps) == 2
    print("malformed line skipped, valid steps remain")


def test_empty_file_returns_empty_list(tmp_path: Path, parser: OpenClawParser) -> None:
    """An empty file produces no trajectories."""
    f = tmp_path / "empty.jsonl"
    f.write_text("", encoding="utf-8")
    assert parser.parse(f) == []
    print("empty file -> []")


def test_header_only_no_messages_returns_empty(tmp_path: Path, parser: OpenClawParser) -> None:
    """A file with only a session header and no message events returns nothing."""
    f = tmp_path / "header_only.jsonl"
    _write_jsonl(f, [_session_event()])
    assert parser.parse(f) == []
    print("header-only file -> []")


def test_discover_finds_session_jsonl_files(tmp_path: Path, parser: OpenClawParser) -> None:
    """discover_session_files returns JSONL files under agents/*/sessions/."""
    sess_dir = tmp_path / "agents" / "main" / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "abc-123.jsonl").write_text("{}\n", encoding="utf-8")
    (sess_dir / "def-456.jsonl").write_text("{}\n", encoding="utf-8")
    found = parser.discover_session_files(tmp_path)
    names = [f.name for f in found]
    assert "abc-123.jsonl" in names
    assert "def-456.jsonl" in names
    print(f"Discovered: {names}")


def test_discover_excludes_sessions_index(tmp_path: Path, parser: OpenClawParser) -> None:
    """sessions.json index file is excluded from discovery."""
    sess_dir = tmp_path / "agents" / "main" / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "sessions.json").write_text("{}", encoding="utf-8")
    (sess_dir / "real-session.jsonl").write_text("{}\n", encoding="utf-8")
    found = parser.discover_session_files(tmp_path)
    names = [f.name for f in found]
    assert "sessions.json" not in names
    assert "real-session.jsonl" in names
    print(f"Index excluded: {names}")


def test_discover_excludes_clean_suffix_files(tmp_path: Path, parser: OpenClawParser) -> None:
    """-clean.jsonl files are excluded from discovery."""
    sess_dir = tmp_path / "agents" / "main" / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "abc-clean.jsonl").write_text("{}\n", encoding="utf-8")
    (sess_dir / "abc.jsonl").write_text("{}\n", encoding="utf-8")
    found = parser.discover_session_files(tmp_path)
    names = [f.name for f in found]
    assert "abc-clean.jsonl" not in names
    assert "abc.jsonl" in names
    print(f"Clean file excluded: {names}")


def test_discover_excludes_files_outside_sessions_dir(
    tmp_path: Path, parser: OpenClawParser
) -> None:
    """JSONL files not under a sessions/ path segment are excluded."""
    wrong_dir = tmp_path / "agents" / "main"
    wrong_dir.mkdir(parents=True)
    (wrong_dir / "stray.jsonl").write_text("{}\n", encoding="utf-8")
    sess_dir = wrong_dir / "sessions"
    sess_dir.mkdir()
    (sess_dir / "valid.jsonl").write_text("{}\n", encoding="utf-8")
    found = parser.discover_session_files(tmp_path)
    names = [f.name for f in found]
    assert "stray.jsonl" not in names
    assert "valid.jsonl" in names
    print(f"Stray excluded, valid found: {names}")


def test_discover_no_agents_dir_returns_empty(tmp_path: Path, parser: OpenClawParser) -> None:
    """discover_session_files returns [] when the agents/ directory doesn't exist."""
    found = parser.discover_session_files(tmp_path)
    assert found == []
    print("No agents/ dir -> []")


def test_discover_excludes_reset_files(tmp_path: Path, parser: OpenClawParser) -> None:
    """*.jsonl.reset.<timestamp>.Z historical reset snapshots are not discovered.

    Reset files end in .Z (gzip-compressed), so the *.jsonl rglob never matches
    them. We use a colon-free timestamp in the filename so the test runs on Windows.
    """
    sess_dir = tmp_path / "agents" / "main" / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "real.jsonl").write_text("{}\n", encoding="utf-8")
    # Windows forbids ':' in filenames; use compact ISO form without colons.
    (sess_dir / "real.jsonl.reset.20250101T000000.Z").write_bytes(b"\x1f\x8b")
    found = parser.discover_session_files(tmp_path)
    names = [f.name for f in found]
    assert "real.jsonl" in names
    assert not any("reset" in n for n in names)
    print(f"Reset file excluded: {names}")


def test_parse_session_index_returns_skeletons(tmp_path: Path, parser: OpenClawParser) -> None:
    """parse_session_index builds skeleton trajectories from sessions.json."""
    index_dir = tmp_path / "agents" / "main" / "sessions"
    index_dir.mkdir(parents=True)
    (index_dir / "sessions.json").write_text(
        json.dumps({
            "s1": {
                "sessionId": "sid-1",
                "createdAt": "2025-01-01T00:00:00Z",
                "updatedAt": "2025-01-02T00:00:00Z",
            },
            "s2": {
                "sessionId": "sid-2",
                "createdAt": "2025-01-03T00:00:00Z",
                "updatedAt": "2025-01-04T00:00:00Z",
            },
        }),
        encoding="utf-8",
    )
    skeletons = parser.parse_session_index(tmp_path)
    assert skeletons is not None
    assert len(skeletons) == 2
    ids = {t.session_id for t in skeletons}
    assert ids == {"sid-1", "sid-2"}
    assert all(t.extra and t.extra.get("is_skeleton") for t in skeletons)
    print(f"Skeletons: {ids}")


def test_parse_session_index_missing_file_returns_none(
    tmp_path: Path, parser: OpenClawParser
) -> None:
    """parse_session_index returns None when sessions.json doesn't exist."""
    assert parser.parse_session_index(tmp_path) is None
    print("Missing index -> None")


def test_extract_session_meta_session_event() -> None:
    """session event populates session_id and cwd."""
    entries = [
        {"type": "session", "id": "sid-xyz", "cwd": "/workspace"},
        {"type": "message", "message": {"role": "user", "content": "hi"}},
    ]
    meta = _extract_session_meta(entries)
    assert meta["session_id"] == "sid-xyz"
    assert meta["cwd"] == "/workspace"
    print(f"meta: {meta}")


def test_extract_session_meta_model_change_wins() -> None:
    """model_change takes priority over the first assistant message model."""
    entries = [
        {"type": "model_change", "provider": "anthropic", "modelId": "claude-opus-4"},
        {
            "type": "message",
            "message": {"role": "assistant", "model": "other-model", "content": ""},
        },
    ]
    meta = _extract_session_meta(entries)
    assert meta["model"] == "anthropic/claude-opus-4"
    print(f"model: {meta['model']}")


def test_extract_session_meta_delivery_mirror_skipped() -> None:
    """delivery-mirror model placeholder is ignored in fallback logic."""
    entries = [
        {
            "type": "message",
            "message": {"role": "assistant", "model": "delivery-mirror", "content": ""},
        },
        {
            "type": "message",
            "message": {"role": "assistant", "model": "claude-sonnet-4-5", "content": "hi"},
        },
    ]
    meta = _extract_session_meta(entries)
    assert meta["model"] == "claude-sonnet-4-5"
    print(f"delivery-mirror skipped, model={meta['model']}")


def test_decompose_content_plain_string() -> None:
    """A plain string returns (stripped_text, None, [])."""
    text, reasoning, calls = _decompose_content("  Hello world  ")
    assert text == "Hello world"
    assert reasoning is None
    assert calls == []
    print("plain string OK")


def test_decompose_content_text_and_thinking() -> None:
    """Text + thinking blocks split into message and reasoning_content."""
    blocks = [
        {"type": "thinking", "thinking": "My reasoning."},
        {"type": "text", "text": "My answer."},
    ]
    text, reasoning, calls = _decompose_content(blocks)
    assert text == "My answer."
    assert reasoning == "My reasoning."
    assert calls == []
    print(f"text={text!r} reasoning={reasoning!r}")


def test_decompose_content_tool_call_block() -> None:
    """toolCall blocks are extracted into ToolCall objects."""
    blocks = [
        {"type": "toolCall", "id": "tc-1", "name": "Read", "arguments": {"path": "/tmp/a"}},
    ]
    text, reasoning, calls = _decompose_content(blocks)
    assert len(calls) == 1
    assert calls[0].tool_call_id == "tc-1"
    assert calls[0].function_name == "Read"
    assert calls[0].arguments == {"path": "/tmp/a"}
    print(f"tool call: {calls[0].function_name}")


def test_decompose_content_multiple_text_blocks_joined() -> None:
    """Multiple text blocks are joined with double newlines."""
    blocks = [
        {"type": "text", "text": "Part one."},
        {"type": "text", "text": "Part two."},
    ]
    text, _, _ = _decompose_content(blocks)
    assert "Part one." in text
    assert "Part two." in text
    print(f"joined: {text!r}")


def test_decompose_content_image_block() -> None:
    """image blocks are decoded into ContentPart with Base64Source; message becomes a list."""
    fake_data = base64.b64encode(b"fake_png_bytes").decode()
    blocks = [
        {"type": "text", "text": "See this:"},
        {"type": "image", "data": fake_data},
    ]
    message, reasoning, calls = _decompose_content(blocks)
    assert isinstance(message, list)
    image_parts = [p for p in message if p.type == ContentType.IMAGE]
    assert len(image_parts) == 1
    assert image_parts[0].source.base64 == fake_data
    assert image_parts[0].source.media_type == "image/png"
    print(f"image block -> ContentPart: {image_parts[0].source.media_type}")


def test_collect_tool_results_indexes_by_id() -> None:
    """_collect_tool_results maps toolCallId -> output/is_error."""
    entries = [
        {
            "message": {
                "role": "toolResult",
                "toolCallId": "tc-x",
                "content": "output text",
                "isError": False,
            }
        },
        {
            "message": {
                "role": "toolResult",
                "toolCallId": "tc-y",
                "content": "err msg",
                "isError": True,
            }
        },
        {"message": {"role": "user", "content": "ignored"}},
    ]
    result = _collect_tool_results(entries)
    assert result["tc-x"]["output"] == "output text"
    assert result["tc-x"]["is_error"] is False
    assert result["tc-y"]["is_error"] is True
    assert "tc-y" in result
    assert len(result) == 2
    print(f"indexed {len(result)} results")


def test_collect_tool_results_skips_missing_id() -> None:
    """toolResult entries without a toolCallId are ignored."""
    entries = [
        {"message": {"role": "toolResult", "content": "orphan"}},
    ]
    result = _collect_tool_results(entries)
    assert result == {}
    print("missing toolCallId skipped")


def test_build_metrics_maps_all_fields() -> None:
    """_build_metrics maps all OpenClaw usage keys; prompt_tokens = input + cacheRead."""
    usage = {"input": 100, "output": 50, "cacheRead": 30, "cacheWrite": 5, "cost": {"total": 0.01}}
    m = _build_metrics(usage)
    assert m is not None
    # prompt_tokens = input(100) + cacheRead(30) = 130
    assert m.prompt_tokens == 130
    assert m.completion_tokens == 50
    assert m.cache_read_tokens == 30
    assert m.cache_write_tokens == 5
    assert m.cost_usd == pytest.approx(0.01)
    print(f"all fields mapped: prompt={m.prompt_tokens} completion={m.completion_tokens}")


def test_build_metrics_none_usage_returns_none() -> None:
    """_build_metrics returns None for a None usage argument."""
    assert _build_metrics(None) is None
    print("None usage -> None metrics")


def test_build_metrics_partial_usage_no_cost() -> None:
    """_build_metrics works when cost key is absent."""
    usage = {"input": 10, "output": 5}
    m = _build_metrics(usage)
    assert m is not None
    assert m.prompt_tokens == 10
    assert m.cost_usd is None
    print(f"no cost: prompt={m.prompt_tokens} cost={m.cost_usd}")

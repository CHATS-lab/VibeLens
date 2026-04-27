"""Code Buddy parser tests."""

import json
from pathlib import Path

import pytest

from vibelens.ingest.parsers.codebuddy import CodebuddyParser
from vibelens.models.enums import AgentType, StepSource


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


@pytest.fixture
def parser() -> CodebuddyParser:
    return CodebuddyParser()


def test_basic_user_assistant_pair(tmp_path: Path, parser: CodebuddyParser) -> None:
    """One user message + one assistant message yields 2 steps."""
    main = tmp_path / "projects" / "p" / "sid-1.jsonl"
    _write_jsonl(
        main,
        [
            {
                "id": "u1",
                "timestamp": 1700000000000,
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Who are you?"}],
                "sessionId": "sid-1",
                "cwd": "/tmp/proj",
                "providerData": {"agent": "cli"},
            },
            {
                "id": "a1",
                "parentId": "u1",
                "timestamp": 1700000001000,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "I am Code Buddy."}],
                "sessionId": "sid-1",
                "cwd": "/tmp/proj",
                "providerData": {
                    "messageId": "m1",
                    "model": "codewise-default-x",
                    "rawUsage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "credit": 0.5,
                    },
                    "agent": "cli",
                },
            },
        ],
    )
    trajs = parser.parse(main)
    assert len(trajs) == 1
    traj = trajs[0]
    assert traj.session_id == "sid-1"
    assert traj.agent.name == AgentType.CODEBUDDY.value
    assert traj.agent.model_name == "codewise-default-x"
    assert traj.first_message == "Who are you?"
    user_steps = [s for s in traj.steps if s.source == StepSource.USER]
    agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
    assert len(user_steps) == 1
    assert len(agent_steps) == 1
    assert agent_steps[0].metrics is not None
    # Code Buddy reports `credit` (Tencent billing unit, not USD-verified) —
    # parser stashes it on extra.credit rather than cost_usd.
    assert agent_steps[0].metrics.cost_usd is None
    assert agent_steps[0].metrics.extra == {"credit": 0.5}
    print(f"Basic: {len(traj.steps)} steps, model={traj.agent.model_name}")


def test_topic_populates_extra(tmp_path: Path, parser: CodebuddyParser) -> None:
    """Topic events become traj.extra.topic."""
    main = tmp_path / "projects" / "p" / "sid-2.jsonl"
    _write_jsonl(
        main,
        [
            {
                "id": "u1", "timestamp": 1700000000000, "type": "message",
                "role": "user", "content": [{"type": "input_text", "text": "hi"}],
                "sessionId": "sid-2", "cwd": "/tmp",
            },
            {"timestamp": 1700000001000, "type": "topic", "topic": "Greeting"},
            {
                "id": "a1", "timestamp": 1700000002000, "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hello"}],
                "sessionId": "sid-2", "cwd": "/tmp",
                "providerData": {"messageId": "m1", "model": "x"},
            },
        ],
    )
    trajs = parser.parse(main)
    assert trajs[0].extra is not None
    assert trajs[0].extra["topic"] == "Greeting"
    print("topic captured")


def test_subagent_linkage_via_renderer_value(
    tmp_path: Path, parser: CodebuddyParser
) -> None:
    """Sub-agent linkage uses renderer.value JSON taskId; child file is loaded."""
    main = tmp_path / "projects" / "p" / "sid-3.jsonl"
    child = tmp_path / "projects" / "p" / "sid-3" / "subagents" / "agent-deadbeef.jsonl"

    _write_jsonl(
        main,
        [
            {
                "id": "u1", "timestamp": 1700000000000, "type": "message",
                "role": "user", "content": [{"type": "input_text", "text": "spawn"}],
                "sessionId": "sid-3", "cwd": "/tmp",
            },
            {
                "id": "a1", "timestamp": 1700000001000, "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Spawning agent."}],
                "sessionId": "sid-3", "cwd": "/tmp",
                "providerData": {"messageId": "m1", "model": "x"},
            },
            {
                "id": "fc1", "parentId": "a1", "timestamp": 1700000002000,
                "type": "function_call",
                "name": "Agent",
                "callId": "call_x",
                "arguments": '{"description": "explore"}',
                "sessionId": "sid-3", "cwd": "/tmp",
                "providerData": {"messageId": "m1", "model": "x", "agent": "cli"},
            },
            {
                "id": "fcr1", "parentId": "fc1", "timestamp": 1700000003000,
                "type": "function_call_result",
                "name": "Agent",
                "callId": "call_x",
                "status": "completed",
                "output": {
                    "type": "text",
                    "text": "Spawned successfully.\nagent_id: Explore-1\ntask_id: agent-deadbeef\n",
                },
                "providerData": {
                    "agent": "cli",
                    "toolResult": {
                        "renderer": {
                            "type": "team-member-spawned",
                            "value": json.dumps({
                                "name": "Explore-1",
                                "taskId": "agent-deadbeef",
                                "color": "blue",
                                "teamName": "_auto_sid-3",
                                "prompt": "Explore the codebase.",
                            }),
                        },
                    },
                },
                "sessionId": "sid-3", "cwd": "/tmp",
            },
        ],
    )
    _write_jsonl(
        child,
        [
            {
                "id": "cu1", "timestamp": 1700000004000, "type": "message",
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": (
                        '<teammate-message teammate_id="team-lead" '
                        'summary="Initial task">\nDo it.\n</teammate-message>'
                    ),
                }],
                "sessionId": "child-sid-uuid", "cwd": "/tmp",
            },
            {
                "id": "ca1", "timestamp": 1700000005000, "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Done."}],
                "sessionId": "child-sid-uuid", "cwd": "/tmp",
                "providerData": {"messageId": "cm1", "model": "y", "isSubAgent": True},
            },
        ],
    )

    trajs = parser.parse(main)
    assert len(trajs) == 2
    main_traj = next(t for t in trajs if t.parent_trajectory_ref is None)
    child_traj = next(t for t in trajs if t.parent_trajectory_ref is not None)
    assert child_traj.parent_trajectory_ref.session_id == "sid-3"
    assert child_traj.parent_trajectory_ref.tool_call_id == "call_x"
    spawn_step = next(s for s in main_traj.steps if s.tool_calls)
    assert spawn_step.observation is not None
    obs = spawn_step.observation.results[0]
    assert obs.subagent_trajectory_ref is not None
    assert obs.subagent_trajectory_ref[0].session_id == "child-sid-uuid"
    assert child_traj.extra is not None
    assert child_traj.extra.get("is_subagent") is True
    print(f"Sub-agent linkage: {main_traj.session_id} -> {child_traj.session_id}")


def test_subagent_linkage_via_regex_fallback(
    tmp_path: Path, parser: CodebuddyParser
) -> None:
    """When renderer.value is missing, regex on output.text recovers task_id."""
    main = tmp_path / "projects" / "p" / "sid-4.jsonl"
    child = tmp_path / "projects" / "p" / "sid-4" / "subagents" / "agent-cafe.jsonl"

    _write_jsonl(
        main,
        [
            {"id": "u1", "timestamp": 1700000000000, "type": "message",
             "role": "user", "content": [{"type": "input_text", "text": "go"}],
             "sessionId": "sid-4", "cwd": "/tmp"},
            {"id": "a1", "timestamp": 1700000001000, "type": "message",
             "role": "assistant",
             "content": [{"type": "output_text", "text": "spawning"}],
             "sessionId": "sid-4", "cwd": "/tmp",
             "providerData": {"messageId": "m1", "model": "x"}},
            {"id": "fc1", "timestamp": 1700000002000, "type": "function_call",
             "name": "Agent", "callId": "c1", "arguments": "{}",
             "sessionId": "sid-4", "cwd": "/tmp",
             "providerData": {"messageId": "m1"}},
            {"id": "fcr1", "timestamp": 1700000003000,
             "type": "function_call_result", "name": "Agent", "callId": "c1",
             "status": "completed",
             "output": {"type": "text",
                        "text": "Spawned.\ntask_id: agent-cafe\nDone."},
             "sessionId": "sid-4", "cwd": "/tmp"},
        ],
    )
    _write_jsonl(
        child,
        [
            {"id": "cu", "timestamp": 1700000004000, "type": "message",
             "role": "user",
             "content": [{"type": "input_text", "text": "child prompt"}],
             "sessionId": "child-cafe", "cwd": "/tmp"},
            {"id": "ca", "timestamp": 1700000005000, "type": "message",
             "role": "assistant",
             "content": [{"type": "output_text", "text": "ok"}],
             "sessionId": "child-cafe", "cwd": "/tmp",
             "providerData": {"messageId": "cm", "model": "y", "isSubAgent": True}},
        ],
    )
    trajs = parser.parse(main)
    child_traj = next(t for t in trajs if t.parent_trajectory_ref is not None)
    assert child_traj.session_id == "child-cafe"
    print("Regex fallback OK")


def test_teammate_message_first_message_detection(
    tmp_path: Path, parser: CodebuddyParser
) -> None:
    """Sub-agent's first user message — wrapped — appears in first_message."""
    sub = tmp_path / "projects" / "p" / "sid" / "subagents" / "agent-x.jsonl"
    _write_jsonl(
        sub,
        [
            {
                "id": "u", "timestamp": 1700000000000, "type": "message",
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": (
                        '<teammate-message teammate_id="lead" summary="task">'
                        "\nDo it\n</teammate-message>"
                    ),
                }],
                "sessionId": "sub-sid", "cwd": "/tmp",
            },
            {
                "id": "a", "timestamp": 1700000001000, "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ok"}],
                "sessionId": "sub-sid", "cwd": "/tmp",
                "providerData": {"messageId": "m", "model": "x", "isSubAgent": True},
            },
        ],
    )
    trajs = parser.parse(sub)
    assert "<teammate-message" in (trajs[0].first_message or "")
    user_step = next(s for s in trajs[0].steps if s.source == StepSource.USER)
    assert user_step.extra is not None
    assert user_step.extra.get("is_spawn_prompt") is True
    print("teammate-message wrapper detected as spawn prompt")


def test_malformed_jsonl_no_exception(tmp_path: Path, parser: CodebuddyParser) -> None:
    bad = tmp_path / "projects" / "p" / "bad.jsonl"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not json\n", encoding="utf-8")
    assert parser.parse(bad) == []
    print("Malformed input tolerated")


def test_discover_excludes_subagents(tmp_path: Path, parser: CodebuddyParser) -> None:
    main = tmp_path / "projects" / "p" / "sid.jsonl"
    sub = tmp_path / "projects" / "p" / "sid" / "subagents" / "agent-1.jsonl"
    main.parent.mkdir(parents=True, exist_ok=True)
    sub.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("{}\n", encoding="utf-8")
    sub.write_text("{}\n", encoding="utf-8")
    discovered = parser.discover_session_files(tmp_path)
    assert len(discovered) == 1
    assert discovered[0].name == "sid.jsonl"
    print("Discovery excludes subagents/")

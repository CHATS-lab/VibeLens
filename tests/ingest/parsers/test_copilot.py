"""Copilot parser tests."""

from pathlib import Path

import pytest

from vibelens.ingest.parsers.copilot import CopilotParser
from vibelens.models.enums import AgentType, StepSource


def _write_jsonl(path: Path, events: list[dict]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


@pytest.fixture
def parser() -> CopilotParser:
    return CopilotParser()


def test_basic_session(tmp_path: Path, parser: CopilotParser) -> None:
    """Session.start + user.message + assistant.message produces 2 steps."""
    events_jsonl = tmp_path / "session-state" / "abc-1" / "events.jsonl"
    _write_jsonl(
        events_jsonl,
        [
            {
                "type": "session.start",
                "data": {
                    "sessionId": "abc-1",
                    "version": 1,
                    "copilotVersion": "1.0.0",
                    "producer": "copilot-agent",
                    "context": {
                        "cwd": "/tmp/fixture",
                        "gitRoot": "/tmp/fixture",
                        "branch": "main",
                        "headCommit": "abc123",
                        "repository": "owner/repo",
                        "hostType": "github",
                        "repositoryHost": "github.com",
                    },
                },
                "id": "evt-1",
                "timestamp": "2026-04-22T15:00:00.000Z",
            },
            {
                "type": "session.model_change",
                "data": {"newModel": "gpt-5-mini", "reasoningEffort": "medium"},
                "id": "evt-2",
                "timestamp": "2026-04-22T15:00:01.000Z",
            },
            {
                "type": "user.message",
                "data": {"content": "Who are you?", "interactionId": "iid-1"},
                "id": "evt-3",
                "timestamp": "2026-04-22T15:00:02.000Z",
            },
            {
                "type": "assistant.message",
                "data": {
                    "messageId": "msg-1",
                    "content": "I'm Copilot.",
                    "outputTokens": 10,
                    "requestId": "req-1",
                    "interactionId": "iid-1",
                },
                "id": "evt-4",
                "timestamp": "2026-04-22T15:00:03.000Z",
            },
        ],
    )

    trajs = parser.parse(events_jsonl)
    assert len(trajs) == 1
    traj = trajs[0]
    assert traj.session_id == "abc-1"
    assert traj.agent.name == AgentType.COPILOT.value
    assert traj.agent.model_name == "gpt-5-mini"
    assert traj.project_path == "/tmp/fixture"
    assert traj.first_message == "Who are you?"
    assert traj.extra is not None
    assert traj.extra["head_commit"] == "abc123"
    assert traj.extra["repository"] == "owner/repo"
    assert traj.extra["cli_version"] == "1.0.0"
    user_steps = [s for s in traj.steps if s.source == StepSource.USER]
    agent_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
    assert len(user_steps) == 1
    assert len(agent_steps) == 1
    assert agent_steps[0].model_name == "gpt-5-mini"
    print(f"Trajectory built: {len(traj.steps)} steps, model={traj.agent.model_name}")


def test_tool_call_pairing(tmp_path: Path, parser: CopilotParser) -> None:
    """Tool execution start + complete produces ToolCall + ObservationResult."""
    events_jsonl = tmp_path / "session-state" / "tc-1" / "events.jsonl"
    _write_jsonl(
        events_jsonl,
        [
            {
                "type": "session.start",
                "data": {"sessionId": "tc-1", "version": 1, "copilotVersion": "1.0.0",
                         "producer": "copilot-agent", "context": {"cwd": "/tmp"}},
                "id": "e1",
                "timestamp": "2026-04-22T15:00:00.000Z",
            },
            {
                "type": "session.model_change",
                "data": {"newModel": "gpt-5-mini"},
                "id": "e2",
                "timestamp": "2026-04-22T15:00:01.000Z",
            },
            {
                "type": "user.message",
                "data": {"content": "List files"},
                "id": "e3",
                "timestamp": "2026-04-22T15:00:02.000Z",
            },
            {
                "type": "assistant.message",
                "data": {
                    "messageId": "m1",
                    "content": "Listing files",
                    "toolRequests": [
                        {
                            "toolCallId": "call_1",
                            "name": "view",
                            "arguments": {"path": "/tmp"},
                            "intentionSummary": "view directory contents",
                        },
                    ],
                    "outputTokens": 15,
                },
                "id": "e4",
                "timestamp": "2026-04-22T15:00:03.000Z",
            },
            {
                "type": "tool.execution_start",
                "data": {"toolCallId": "call_1", "toolName": "view",
                         "arguments": {"path": "/tmp"}},
                "id": "e5",
                "timestamp": "2026-04-22T15:00:03.500Z",
            },
            {
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "call_1",
                    "model": "gpt-5-mini",
                    "success": True,
                    "result": {"content": "file1.txt\nfile2.txt",
                               "detailedContent": "file1.txt\nfile2.txt"},
                },
                "id": "e6",
                "timestamp": "2026-04-22T15:00:04.000Z",
            },
        ],
    )

    trajs = parser.parse(events_jsonl)
    traj = trajs[0]
    agent_step = next(s for s in traj.steps if s.source == StepSource.AGENT)
    assert len(agent_step.tool_calls) == 1
    assert agent_step.tool_calls[0].function_name == "view"
    assert agent_step.tool_calls[0].extra is not None
    assert agent_step.tool_calls[0].extra["intention_summary"] == "view directory contents"
    assert agent_step.observation is not None
    assert len(agent_step.observation.results) == 1
    obs = agent_step.observation.results[0]
    assert obs.source_call_id == "call_1"
    assert obs.is_error is False
    assert "file1.txt" in (obs.content or "")
    name = agent_step.tool_calls[0].function_name
    snippet = (obs.content or "")[:30]
    print(f"Tool pairing OK: {name} -> {snippet!r}")


def test_inflight_tool_emits_synthetic_error(tmp_path: Path, parser: CopilotParser) -> None:
    """tool.execution_start without paired complete produces synthetic error."""
    events_jsonl = tmp_path / "session-state" / "if-1" / "events.jsonl"
    _write_jsonl(
        events_jsonl,
        [
            {
                "type": "session.start",
                "data": {"sessionId": "if-1", "version": 1, "copilotVersion": "1.0.0",
                         "producer": "copilot-agent", "context": {"cwd": "/tmp"}},
                "id": "e1",
                "timestamp": "2026-04-22T15:00:00.000Z",
            },
            {
                "type": "session.model_change",
                "data": {"newModel": "gpt-5-mini"},
                "id": "e2",
                "timestamp": "2026-04-22T15:00:01.000Z",
            },
            {
                "type": "user.message",
                "data": {"content": "do something"},
                "id": "e3",
                "timestamp": "2026-04-22T15:00:02.000Z",
            },
            {
                "type": "assistant.message",
                "data": {
                    "messageId": "m1",
                    "content": "Working on it",
                    "toolRequests": [
                        {"toolCallId": "stuck_call", "name": "shell",
                         "arguments": {"command": "sleep 9999"}},
                    ],
                    "outputTokens": 5,
                },
                "id": "e4",
                "timestamp": "2026-04-22T15:00:03.000Z",
            },
            {
                "type": "tool.execution_start",
                "data": {"toolCallId": "stuck_call", "toolName": "shell"},
                "id": "e5",
                "timestamp": "2026-04-22T15:00:03.500Z",
            },
            {
                "type": "session.shutdown",
                "data": {"shutdownType": "killed"},
                "id": "e6",
                "timestamp": "2026-04-22T20:00:00.000Z",
            },
        ],
    )

    trajs = parser.parse(events_jsonl)
    traj = trajs[0]
    agent_step = next(s for s in traj.steps if s.source == StepSource.AGENT)
    obs = agent_step.observation.results[0]
    assert obs.is_error is True
    assert obs.extra and obs.extra.get("in_flight") is True
    print(f"In-flight detection OK: is_error={obs.is_error}")


def test_session_with_no_events_jsonl_skipped(tmp_path: Path, parser: CopilotParser) -> None:
    """A session-state subdir with workspace.yaml but no events.jsonl is skipped."""
    (tmp_path / "session-state" / "empty").mkdir(parents=True)
    (tmp_path / "session-state" / "empty" / "workspace.yaml").write_text("id: empty\n")
    discovered = parser.discover_session_files(tmp_path)
    assert discovered == []
    print("Empty session correctly skipped")


def test_malformed_jsonl_no_exception(tmp_path: Path, parser: CopilotParser) -> None:
    """Malformed JSONL lines are recorded as diagnostics; parser doesn't raise."""
    events_jsonl = tmp_path / "session-state" / "bad" / "events.jsonl"
    events_jsonl.parent.mkdir(parents=True)
    events_jsonl.write_text("{not json\n", encoding="utf-8")
    trajs = parser.parse(events_jsonl)
    assert trajs == []
    print("Malformed input handled gracefully")

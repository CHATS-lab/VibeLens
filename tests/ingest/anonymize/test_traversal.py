"""Tests for the deep trajectory tree walker."""

from vibelens.ingest.anonymize.traversal import traverse_trajectory
from vibelens.models.trajectories import (
    Agent,
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
    TrajectoryRef,
)


def _make_trajectory(**overrides) -> Trajectory:
    """Build a minimal valid Trajectory with optional overrides."""
    defaults = {
        "session_id": "test-session-001",
        "agent": Agent(name="test-agent"),
        "steps": [
            Step(step_id="step-1", source="agent", message="hello world"),
        ],
    }
    defaults.update(overrides)
    return Trajectory(**defaults)


def test_project_path_transformed() -> None:
    t = _make_trajectory(project_path="/Users/alice/code")
    result = traverse_trajectory(t, str.upper)
    print(f"  project_path: {result.project_path}")
    assert result.project_path == "/USERS/ALICE/CODE"


def test_first_message_transformed() -> None:
    t = _make_trajectory(first_message="fix the bug")
    result = traverse_trajectory(t, str.upper)
    print(f"  first_message: {result.first_message}")
    assert result.first_message == "FIX THE BUG"


def test_step_message_string() -> None:
    t = _make_trajectory(steps=[
        Step(step_id="s1", source="agent", message="read the file"),
    ])
    result = traverse_trajectory(t, str.upper)
    print(f"  step message: {result.steps[0].message}")
    assert result.steps[0].message == "READ THE FILE"


def test_step_message_content_parts() -> None:
    t = _make_trajectory(steps=[
        Step(
            step_id="s1",
            source="agent",
            message=[
                {"type": "text", "text": "hello"},
                {"type": "image", "source": {"media_type": "image/png", "base64": "abc"}},
            ],
        ),
    ])
    result = traverse_trajectory(t, str.upper)
    parts = result.steps[0].message
    print(f"  content parts: {parts}")
    # After model_validate, parts are ContentPart objects
    assert parts[0].text == "HELLO"
    # Non-text part should be untouched
    assert parts[1].type == "image"


def test_reasoning_content() -> None:
    t = _make_trajectory(steps=[
        Step(step_id="s1", source="agent", message="msg", reasoning_content="think about it"),
    ])
    result = traverse_trajectory(t, str.upper)
    print(f"  reasoning_content: {result.steps[0].reasoning_content}")
    assert result.steps[0].reasoning_content == "THINK ABOUT IT"


def test_tool_call_arguments_dict() -> None:
    t = _make_trajectory(steps=[
        Step(
            step_id="s1",
            source="agent",
            message="",
            tool_calls=[
                ToolCall(
                    tool_call_id="tc1",
                    function_name="Read",
                    arguments={"file_path": "/Users/alice/code/main.py"},
                ),
            ],
            observation=Observation(results=[
                ObservationResult(source_call_id="tc1", content="ok"),
            ]),
        ),
    ])
    result = traverse_trajectory(t, str.upper)
    args = result.steps[0].tool_calls[0].arguments
    print(f"  tool call dict args: {args}")
    assert args["file_path"] == "/USERS/ALICE/CODE/MAIN.PY"


def test_tool_call_arguments_string() -> None:
    t = _make_trajectory(steps=[
        Step(
            step_id="s1",
            source="agent",
            message="",
            tool_calls=[
                ToolCall(tool_call_id="tc1", function_name="Bash", arguments="ls -la"),
            ],
            observation=Observation(results=[
                ObservationResult(source_call_id="tc1", content="output"),
            ]),
        ),
    ])
    result = traverse_trajectory(t, str.upper)
    args = result.steps[0].tool_calls[0].arguments
    print(f"  tool call string args: {args}")
    assert args == "LS -LA"


def test_observation_content() -> None:
    t = _make_trajectory(steps=[
        Step(
            step_id="s1",
            source="agent",
            message="",
            tool_calls=[
                ToolCall(tool_call_id="tc1", function_name="Read"),
            ],
            observation=Observation(results=[
                ObservationResult(source_call_id="tc1", content="file contents here"),
            ]),
        ),
    ])
    result = traverse_trajectory(t, str.upper)
    content = result.steps[0].observation.results[0].content
    print(f"  observation content: {content}")
    assert content == "FILE CONTENTS HERE"


def test_extra_dict_recursive() -> None:
    t = _make_trajectory(extra={"key": "value", "nested": {"inner": "deep"}})
    result = traverse_trajectory(t, str.upper)
    print(f"  extra: {result.extra}")
    assert result.extra["key"] == "VALUE"
    assert result.extra["nested"]["inner"] == "DEEP"


def test_trajectory_ref_path() -> None:
    t = _make_trajectory(
        prev_trajectory_ref=TrajectoryRef(
            session_id="prev-session",
            trajectory_path="/Users/alice/.claude/projects/test/abc.jsonl",
        ),
    )
    result = traverse_trajectory(t, str.upper)
    ref_path = result.prev_trajectory_ref.trajectory_path
    print(f"  trajectory_ref path: {ref_path}")
    assert ref_path == "/USERS/ALICE/.CLAUDE/PROJECTS/TEST/ABC.JSONL"


def test_subagent_ref_path() -> None:
    t = _make_trajectory(steps=[
        Step(
            step_id="s1",
            source="agent",
            message="",
            tool_calls=[
                ToolCall(tool_call_id="tc1", function_name="Agent"),
            ],
            observation=Observation(results=[
                ObservationResult(
                    source_call_id="tc1",
                    content="done",
                    subagent_trajectory_ref=[
                        TrajectoryRef(
                            session_id="sub-1",
                            trajectory_path="/Users/alice/.claude/subagents/agent-1.jsonl",
                        ),
                    ],
                ),
            ]),
        ),
    ])
    result = traverse_trajectory(t, str.upper)
    sub_ref = result.steps[0].observation.results[0].subagent_trajectory_ref[0]
    print(f"  subagent ref path: {sub_ref.trajectory_path}")
    assert sub_ref.trajectory_path == "/USERS/ALICE/.CLAUDE/SUBAGENTS/AGENT-1.JSONL"


def test_structural_fields_untouched() -> None:
    t = _make_trajectory(steps=[
        Step(
            step_id="step-001",
            source="agent",
            message="hello",
            tool_calls=[
                ToolCall(tool_call_id="tc-001", function_name="Read"),
            ],
            observation=Observation(results=[
                ObservationResult(source_call_id="tc-001", content="ok"),
            ]),
        ),
    ])
    result = traverse_trajectory(t, str.upper)
    # Structural fields must NOT be uppercased
    assert result.session_id == "test-session-001"
    assert result.steps[0].step_id == "step-001"
    assert result.steps[0].tool_calls[0].tool_call_id == "tc-001"
    assert result.steps[0].tool_calls[0].function_name == "Read"
    assert result.steps[0].source == "agent"
    print("  structural fields preserved correctly")


def test_none_fields_stay_none() -> None:
    t = _make_trajectory(
        project_path=None,
        first_message=None,
        prev_trajectory_ref=None,
    )
    result = traverse_trajectory(t, str.upper)
    assert result.project_path is None
    assert result.first_message is None
    assert result.prev_trajectory_ref is None
    print("  None fields remain None")

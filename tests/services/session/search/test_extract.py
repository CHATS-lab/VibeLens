"""Per-field extraction: user prompts, agent messages, tool calls."""

from tests.services.session.search._fixtures import (
    make_agent_step,
    make_tool_step,
    make_trajectory,
    make_user_step,
)
from vibelens.models.enums import ContentType, StepSource
from vibelens.models.trajectories import Step
from vibelens.models.trajectories.content import ContentPart
from vibelens.models.trajectories.observation import Observation
from vibelens.models.trajectories.observation_result import ObservationResult
from vibelens.models.trajectories.tool_call import ToolCall
from vibelens.services.session.search.index import (
    ARG_VALUE_MAX_LENGTH,
    OBSERVATION_MAX_LENGTH,
    _extract_agent_messages,
    _extract_message_text,
    _extract_readable_args,
    _extract_tool_calls,
    _extract_user_prompts,
)


def test_user_prompts_concatenates_all_user_steps():
    """Every USER step contributes to user_prompts, lowercased."""
    traj = make_trajectory(
        "sid-1",
        [
            make_user_step("First question", "u1"),
            make_agent_step("Answer", "s1"),
            make_user_step("Follow-up please", "u2"),
        ],
    )
    out = _extract_user_prompts([traj])
    print(f"user_prompts: {out!r}")
    assert "first question" in out
    assert "follow-up please" in out
    assert "answer" not in out


def test_agent_messages_excludes_tool_data():
    """Only AGENT text content is captured; tool_calls are a separate field."""
    traj = make_trajectory(
        "sid-1",
        [
            make_user_step("hi", "u1"),
            make_agent_step("Hello there", "s1"),
            make_tool_step("Read", {"file_path": "/tmp/x"}, "t1"),
        ],
    )
    out = _extract_agent_messages([traj])
    print(f"agent_messages: {out!r}")
    assert "hello there" in out
    assert "read" not in out
    assert "/tmp/x" not in out


def test_tool_calls_includes_name_and_string_args():
    """Tool calls field covers function name + string-valued args."""
    traj = make_trajectory(
        "sid-1",
        [
            make_user_step("hi", "u1"),
            make_tool_step("Grep", {"pattern": "authentication", "glob": "*.py"}, "t1"),
        ],
    )
    out = _extract_tool_calls([traj])
    print(f"tool_calls: {out!r}")
    assert "grep" in out
    assert "authentication" in out
    assert "*.py" in out


def test_tool_calls_truncates_long_args():
    """Args longer than ARG_VALUE_MAX_LENGTH are cut."""
    big = "x" * (ARG_VALUE_MAX_LENGTH + 100)
    traj = make_trajectory(
        "sid-1",
        [
            make_user_step("hi", "u1"),
            make_tool_step("Read", {"content": big}, "t1"),
        ],
    )
    out = _extract_tool_calls([traj])
    # The string of x's should be clipped: total output contains fewer
    # than ARG_VALUE_MAX_LENGTH + 100 consecutive x chars.
    x_run = max(len(chunk) for chunk in out.split(" ") if set(chunk) == {"x"})
    print(f"longest-x-run: {x_run}")
    assert x_run <= ARG_VALUE_MAX_LENGTH


def test_extractors_handle_empty_trajectory_list():
    """Empty input yields empty strings, not exceptions."""
    assert _extract_user_prompts([]) == ""
    assert _extract_agent_messages([]) == ""
    assert _extract_tool_calls([]) == ""


def test_observation_truncation_constant_is_sane():
    """Guard against an accidental change making tool_calls unbounded."""
    # Sanity: the cap is smaller than the arg cap so observations don't
    # dwarf arguments in the index.
    assert 0 < OBSERVATION_MAX_LENGTH <= ARG_VALUE_MAX_LENGTH


def test_tool_calls_includes_observation_text():
    """Observation content (string) is indexed alongside tool name and args."""
    tc = ToolCall(tool_call_id="tc-1", function_name="Read", arguments={"file_path": "/tmp/x"})
    obs = Observation(
        results=[
            ObservationResult(source_call_id="tc-1", content="Permission denied on /etc/shadow")
        ]
    )
    step = Step(step_id="s1", source=StepSource.AGENT, tool_calls=[tc], observation=obs)
    traj = make_trajectory("sid-1", [make_user_step("hi"), step])
    out = _extract_tool_calls([traj])
    print(f"tool_calls with observation: {out!r}")
    assert "read" in out
    assert "permission denied" in out


def test_tool_calls_truncates_long_observations():
    """Observations longer than OBSERVATION_MAX_LENGTH are cut."""
    long_obs = "y" * (OBSERVATION_MAX_LENGTH + 100)
    tc = ToolCall(tool_call_id="tc-1", function_name="Bash", arguments={"command": "ls"})
    obs = Observation(results=[ObservationResult(source_call_id="tc-1", content=long_obs)])
    step = Step(step_id="s1", source=StepSource.AGENT, tool_calls=[tc], observation=obs)
    traj = make_trajectory("sid-1", [make_user_step("hi"), step])
    out = _extract_tool_calls([traj])
    y_run = max(len(chunk) for chunk in out.split(" ") if set(chunk) == {"y"})
    print(f"longest-y-run: {y_run}")
    assert y_run <= OBSERVATION_MAX_LENGTH


def test_extract_message_text_handles_content_part_list():
    """ContentPart arrays (multimodal messages) yield text-parts joined."""
    parts = [
        ContentPart(type=ContentType.TEXT, text="Here is the analysis:"),
        ContentPart(type=ContentType.TEXT, text="The tokenizer works fine."),
    ]
    out = _extract_message_text(parts)
    print(f"content-part text: {out!r}")
    assert "here is the analysis:" in out.lower()
    assert "tokenizer works fine" in out.lower()


def test_extract_message_text_skips_non_text_parts():
    """Image ContentParts (no .text) contribute nothing to the extracted string."""
    # IMAGE parts have source but no text; the extractor must not raise.
    from vibelens.models.trajectories.content import Base64Source
    parts = [
        ContentPart(type=ContentType.TEXT, text="Look at this:"),
        ContentPart(
            type=ContentType.IMAGE,
            source=Base64Source(media_type="image/png", base64="abc"),
        ),
    ]
    out = _extract_message_text(parts)
    print(f"mixed content-part text: {out!r}")
    assert "look at this" in out.lower()
    # The base64 blob must not leak into the searchable text.
    assert "abc" not in out


def test_extract_message_text_handles_none_and_empty_string():
    """None and empty string both produce empty output with no exception."""
    assert _extract_message_text(None) == ""
    assert _extract_message_text("") == ""


def test_extract_readable_args_string_input():
    """A plain string argument blob passes through unchanged."""
    out = _extract_readable_args("make it faster")
    assert out == "make it faster"


def test_extract_readable_args_dict_keeps_only_strings():
    """Dict-shaped arguments keep string values; non-strings (nested dicts, numbers) are dropped.

    This matches today's conservative behavior — avoids dumping JSON
    repr of nested structures into the search index.
    """
    args = {
        "file_path": "/tmp/x.py",
        "pattern": "auth",
        "max_results": 10,  # int — dropped
        "options": {"case_sensitive": True},  # nested dict — dropped
    }
    out = _extract_readable_args(args)
    print(f"readable args: {out!r}")
    assert "/tmp/x.py" in out
    assert "auth" in out
    assert "10" not in out
    assert "case_sensitive" not in out


def test_extract_readable_args_none_returns_empty():
    """None yields an empty string rather than raising."""
    assert _extract_readable_args(None) == ""


def test_user_prompts_captures_content_part_message():
    """User messages delivered as ContentPart lists are extracted too."""
    parts_msg = [ContentPart(type=ContentType.TEXT, text="How do I write a migration?")]
    step = Step(step_id="u1", source=StepSource.USER, message=parts_msg)
    traj = make_trajectory("sid-1", [step])
    out = _extract_user_prompts([traj])
    print(f"content-part user_prompts: {out!r}")
    assert "migration" in out


def test_agent_messages_ignores_user_content_parts():
    """Source filtering holds even when the user step uses ContentPart."""
    user_parts = [ContentPart(type=ContentType.TEXT, text="USER SAID THIS")]
    user_step = Step(step_id="u1", source=StepSource.USER, message=user_parts)
    agent_step = Step(step_id="s1", source=StepSource.AGENT, message="agent response")
    traj = make_trajectory("sid-1", [user_step, agent_step])
    out = _extract_agent_messages([traj])
    print(f"agent_messages: {out!r}")
    assert "agent response" in out
    assert "user said this" not in out

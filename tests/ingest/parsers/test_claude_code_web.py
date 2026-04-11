"""Unit tests for vibelens.ingest.parsers.claude_code_web parser."""

import json
from pathlib import Path

from vibelens.ingest.parsers.claude_code_web import ClaudeCodeWebParser
from vibelens.models.enums import StepSource

_parser = ClaudeCodeWebParser()

DATASET_DIR_1 = Path("datasets/Claude Data Mar 29 2026")
DATASET_DIR_2 = Path("datasets/data-2026-03-29-19-48-24-batch-0000")


def _make_conversation(
    uuid: str = "conv-001", name: str = "Test Conversation", chat_messages: list | None = None
) -> dict:
    """Build a minimal conversation dict."""
    return {
        "uuid": uuid,
        "name": name,
        "summary": "",
        "created_at": "2025-10-24T19:39:14.000000Z",
        "updated_at": "2025-10-24T19:40:00.000000Z",
        "account": {},
        "chat_messages": chat_messages or [],
    }


def _human_msg(
    uuid: str = "msg-h1",
    text: str = "Hello",
    created_at: str = "2025-10-24T19:39:14.000000Z",
    attachments: list | None = None,
) -> dict:
    """Build a human chat_message."""
    return {
        "uuid": uuid,
        "sender": "human",
        "text": text,
        "created_at": created_at,
        "content": [{"type": "text", "text": text}],
        "attachments": attachments or [],
    }


def _assistant_msg(
    uuid: str = "msg-a1",
    content_blocks: list | None = None,
    created_at: str = "2025-10-24T19:39:16.000000Z",
) -> dict:
    """Build an assistant chat_message."""
    return {
        "uuid": uuid,
        "sender": "assistant",
        "text": "",
        "created_at": created_at,
        "content": content_blocks or [],
        "attachments": [],
    }


def test_parse_real_dataset_1():
    """Parse the first real dataset and verify trajectory count."""
    file_path = DATASET_DIR_1 / "conversations.json"
    if not file_path.exists():
        print(f"SKIP: {file_path} not found")
        return

    trajectories = _parser.parse_file(file_path)
    print(f"Dataset 1: {len(trajectories)} trajectories from {file_path}")

    # Count non-empty conversations in the source data
    with open(file_path) as f:
        data = json.load(f)
    non_empty = sum(1 for c in data if c.get("chat_messages"))
    print(f"  Non-empty conversations: {non_empty}")

    assert len(trajectories) > 0, "Should parse at least some trajectories"
    assert len(trajectories) == non_empty

    # Spot-check first trajectory
    first = trajectories[0]
    print(f"  First trajectory: session_id={first.session_id}, steps={len(first.steps)}")
    assert first.session_id
    assert len(first.steps) > 0

    # Spot-check last trajectory
    last = trajectories[-1]
    print(f"  Last trajectory: session_id={last.session_id}, steps={len(last.steps)}")
    assert last.session_id
    assert len(last.steps) > 0


def test_parse_real_dataset_2():
    """Parse the second real dataset and verify trajectory count."""
    file_path = DATASET_DIR_2 / "conversations.json"
    if not file_path.exists():
        print(f"SKIP: {file_path} not found")
        return

    trajectories = _parser.parse_file(file_path)
    print(f"Dataset 2: {len(trajectories)} trajectories from {file_path}")

    with open(file_path) as f:
        data = json.load(f)
    total = len(data)
    print(f"  Total conversations: {total}")

    # Some conversations have messages but all text fields are empty
    # (image-only or redacted), so trajectory count may be less than total
    assert len(trajectories) > 0
    assert len(trajectories) <= total


def test_parse_text_only_conversation():
    """Simple human/assistant text exchange."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(text="Tell me a joke"),
            _assistant_msg(
                content_blocks=[{"type": "text", "text": "Why did the chicken cross the road?"}]
            ),
        ]
    )
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    assert len(trajectories) == 1
    traj = trajectories[0]
    assert traj.session_id == "conv-001"
    assert len(traj.steps) == 2

    user_step = traj.steps[0]
    assert user_step.source == StepSource.USER
    assert user_step.message == "Tell me a joke"

    agent_step = traj.steps[1]
    assert agent_step.source == StepSource.AGENT
    assert "chicken" in agent_step.message
    assert not agent_step.tool_calls
    assert agent_step.observation is None

    print(f"Text-only: {len(traj.steps)} steps, first_message={traj.first_message!r}")


def test_parse_thinking_blocks():
    """Thinking content maps to reasoning_content."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(text="Explain quantum computing"),
            _assistant_msg(
                content_blocks=[
                    {"type": "thinking", "thinking": "Let me think about this carefully..."},
                    {"type": "text", "text": "Quantum computing uses qubits."},
                ]
            ),
        ]
    )
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    assert len(trajectories) == 1
    agent_step = trajectories[0].steps[1]
    assert agent_step.reasoning_content == "Let me think about this carefully..."
    assert "qubits" in agent_step.message
    preview = repr(agent_step.reasoning_content)[:60]
    print(f"Thinking: reasoning={preview}")


def test_parse_tool_pairing():
    """Tool use in assistant paired with inline tool result."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(text="Search for cats"),
            _assistant_msg(
                content_blocks=[
                    {"type": "text", "text": "Let me search for that."},
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "web_search",
                        "input": {"query": "cats"},
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_123",
                        "name": "web_search",
                        "is_error": False,
                        "content": [{"type": "text", "text": "Found 10 results about cats"}],
                    },
                    {"type": "text", "text": "Here are some results about cats."},
                ]
            ),
        ]
    )
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    assert len(trajectories) == 1
    agent_step = trajectories[0].steps[1]

    # Tool call
    assert len(agent_step.tool_calls) == 1
    tc = agent_step.tool_calls[0]
    assert tc.function_name == "web_search"
    assert tc.arguments == {"query": "cats"}

    # Observation
    assert agent_step.observation is not None
    assert len(agent_step.observation.results) == 1
    obs = agent_step.observation.results[0]
    assert obs.source_call_id == tc.tool_call_id
    assert "Found 10 results" in obs.content

    # Text includes both text blocks
    assert "Let me search" in agent_step.message
    assert "results about cats" in agent_step.message

    result_preview = repr(obs.content)[:60]
    print(f"Tool pairing: tool={tc.function_name}, result={result_preview}")


def test_parse_multiple_tools_positional():
    """N tool_use blocks paired with N tool_result blocks."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(text="Do two things"),
            _assistant_msg(
                content_blocks=[
                    {"type": "thinking", "thinking": "I need to use two tools"},
                    {
                        "type": "tool_use",
                        "id": "toolu_a",
                        "name": "tool_alpha",
                        "input": {"x": 1},
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_a",
                        "content": "result_alpha",
                    },
                    {"type": "thinking", "thinking": "Now the second tool"},
                    {
                        "type": "tool_use",
                        "id": "toolu_b",
                        "name": "tool_beta",
                        "input": {"y": 2},
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_b",
                        "content": "result_beta",
                    },
                    {"type": "text", "text": "Done with both."},
                ]
            ),
        ]
    )
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    assert len(trajectories) == 1
    agent_step = trajectories[0].steps[1]

    assert len(agent_step.tool_calls) == 2
    assert agent_step.tool_calls[0].function_name == "tool_alpha"
    assert agent_step.tool_calls[1].function_name == "tool_beta"

    assert agent_step.observation is not None
    assert len(agent_step.observation.results) == 2
    assert agent_step.observation.results[0].content == "result_alpha"
    assert agent_step.observation.results[1].content == "result_beta"

    # Verify source_call_id linkage
    assert agent_step.observation.results[0].source_call_id == agent_step.tool_calls[0].tool_call_id
    assert agent_step.observation.results[1].source_call_id == agent_step.tool_calls[1].tool_call_id

    # Reasoning from both thinking blocks
    assert "two tools" in agent_step.reasoning_content
    assert "second tool" in agent_step.reasoning_content

    call_count = len(agent_step.tool_calls)
    result_count = len(agent_step.observation.results)
    print(f"Multiple tools: {call_count} calls, {result_count} results")


def test_parse_tool_use_without_id():
    """Tool use/result blocks with None IDs (artifact tools) are still paired positionally."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(text="Create an artifact"),
            _assistant_msg(
                content_blocks=[
                    {"type": "text", "text": "Creating artifact."},
                    {
                        "type": "tool_use",
                        "id": None,
                        "name": "artifacts",
                        "input": {"title": "My doc"},
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": None,
                        "content": [{"type": "text", "text": "OK"}],
                    },
                ]
            ),
        ]
    )
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    agent_step = trajectories[0].steps[1]
    assert len(agent_step.tool_calls) == 1
    assert agent_step.tool_calls[0].function_name == "artifacts"

    assert agent_step.observation is not None
    assert len(agent_step.observation.results) == 1
    # Both have None native IDs, but the result should map to our generated ID
    assert agent_step.observation.results[0].source_call_id == agent_step.tool_calls[0].tool_call_id

    print("Tool without ID: paired successfully via None key")


def test_parse_orphaned_tool_use():
    """Tool use without a following result (e.g. last message interrupted)."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(text="Do something"),
            _assistant_msg(
                content_blocks=[
                    {
                        "type": "tool_use",
                        "id": "toolu_orphan",
                        "name": "web_fetch",
                        "input": {"url": "https://example.com"},
                    },
                ]
            ),
        ]
    )
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    agent_step = trajectories[0].steps[1]
    assert len(agent_step.tool_calls) == 1
    assert agent_step.tool_calls[0].function_name == "web_fetch"
    # No observation since there's no tool_result block
    assert agent_step.observation is None

    print("Orphaned tool_use: parsed with no observation")


def test_parse_attachments():
    """Attachments on human messages stored in step.extra."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(
                text="Here is a file",
                attachments=[
                    {
                        "file_name": "report.pdf",
                        "file_type": "pdf",
                        "file_size": 12345,
                        "extracted_content": "Some PDF content",
                    }
                ],
            ),
            _assistant_msg(content_blocks=[{"type": "text", "text": "I see your file."}]),
        ]
    )
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    user_step = trajectories[0].steps[0]
    assert user_step.extra is not None
    assert "attachments" in user_step.extra
    assert len(user_step.extra["attachments"]) == 1
    att = user_step.extra["attachments"][0]
    assert att["file_name"] == "report.pdf"
    assert att["file_type"] == "pdf"
    assert att["file_size"] == 12345
    # extracted_content is not stored (too large)
    assert "extracted_content" not in att

    print(f"Attachments: {att}")


def test_parse_empty_conversations():
    """Empty array returns empty list."""
    content = json.dumps([])
    trajectories = _parser.parse(content)
    assert trajectories == []
    print("Empty conversations: 0 trajectories")


def test_parse_no_messages():
    """Conversation with empty chat_messages is skipped."""
    conversation = _make_conversation(chat_messages=[])
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)
    assert trajectories == []
    print("No messages: skipped")


def test_deterministic_ids():
    """Parsing same content twice yields identical IDs."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(text="Hi"),
            _assistant_msg(
                content_blocks=[
                    {"type": "text", "text": "Hello!"},
                    {
                        "type": "tool_use",
                        "id": "toolu_det",
                        "name": "web_search",
                        "input": {"q": "test"},
                    },
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_det",
                        "content": "OK",
                    },
                ]
            ),
        ]
    )
    content = json.dumps([conversation])
    traj1 = _parser.parse(content)[0]
    traj2 = _parser.parse(content)[0]

    assert traj1.session_id == traj2.session_id
    for s1, s2 in zip(traj1.steps, traj2.steps, strict=True):
        assert s1.step_id == s2.step_id
        for tc1, tc2 in zip(s1.tool_calls, s2.tool_calls, strict=True):
            assert tc1.tool_call_id == tc2.tool_call_id

    print("Deterministic IDs: verified identical across two parses")


def test_discover_conversations_json(tmp_path: Path):
    """discover_session_files finds conversations.json files."""
    # Create nested structure mimicking an extracted zip
    subdir = tmp_path / "export"
    subdir.mkdir()
    (subdir / "conversations.json").write_text("[]")
    (subdir / "users.json").write_text("[]")

    files = _parser.discover_session_files(tmp_path)
    assert len(files) == 1
    assert files[0].name == "conversations.json"
    print(f"Discovery: found {files}")


def test_parse_conversation_name_in_extra():
    """Conversation name and summary stored in trajectory extra."""
    conversation = _make_conversation(
        name="My Important Chat",
        chat_messages=[
            _human_msg(text="Hello"),
            _assistant_msg(content_blocks=[{"type": "text", "text": "Hi there!"}]),
        ],
    )
    conversation["summary"] = "A friendly greeting"
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    traj = trajectories[0]
    assert traj.extra is not None
    assert traj.extra["conversation_name"] == "My Important Chat"
    assert traj.extra["summary"] == "A friendly greeting"
    print(f"Extra: {traj.extra}")


def test_parse_token_budget_skipped():
    """token_budget blocks are skipped without error."""
    conversation = _make_conversation(
        chat_messages=[
            _human_msg(text="Hi"),
            _assistant_msg(
                content_blocks=[
                    {"type": "text", "text": "Hello"},
                    {
                        "type": "token_budget",
                        "start_timestamp": "2025-10-24T19:39:16Z",
                        "stop_timestamp": "2025-10-24T19:39:17Z",
                        "flags": {},
                    },
                ]
            ),
        ]
    )
    content = json.dumps([conversation])
    trajectories = _parser.parse(content)

    assert len(trajectories) == 1
    agent_step = trajectories[0].steps[1]
    assert agent_step.message == "Hello"
    assert not agent_step.tool_calls
    print("token_budget: skipped correctly")


def test_agent_type_is_claude_code_web():
    """Parser AGENT_TYPE is set correctly."""
    from vibelens.models.enums import AgentType

    assert _parser.AGENT_TYPE == AgentType.CLAUDE_CODE_WEB

    trajectories = _parser.parse(
        json.dumps(
            [
                _make_conversation(
                    chat_messages=[
                        _human_msg(text="Hi"),
                        _assistant_msg(content_blocks=[{"type": "text", "text": "Hello"}]),
                    ]
                )
            ]
        )
    )
    assert trajectories[0].agent.name == "claude_code_web"
    print(f"Agent type: {trajectories[0].agent.name}")

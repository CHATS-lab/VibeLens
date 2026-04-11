"""Claude Code Web (claude.ai) export parser.

Parses the ``conversations.json`` file from claude.ai's **Settings > Export Data**
ZIP download. Each exported ZIP contains a JSON array of conversations with chat
messages, where each conversation maps to one ATIF Trajectory.

Unlike the local CLI parsers (claude_code, codex) where each file holds one
session, the web export packs **all conversations into a single JSON array**
— so ``parse`` returns multiple Trajectory objects from a single file.

Data format observations:
- Tool results appear **inline** in assistant messages (not in the next human
  message like the CLI format). Each ``tool_use`` block is followed by its
  ``tool_result`` block in the same message's content array.
- Most ``tool_use`` blocks have an ``id`` field and the matching
  ``tool_result`` has a ``tool_use_id`` field. Some pairs have ``None`` for
  both IDs (artifact tools), in which case positional pairing is used.
- ``thinking`` blocks contain extended thinking in a ``thinking`` field.
- ``token_budget`` blocks are metadata and skipped.
- Human messages only contain ``text`` blocks and optional ``attachments``.
"""

import json
from pathlib import Path

from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType, StepSource
from vibelens.models.trajectories import (
    Observation,
    ObservationResult,
    Step,
    ToolCall,
    Trajectory,
)
from vibelens.utils import deterministic_id, get_logger, parse_iso_timestamp

logger = get_logger(__name__)

# The single JSON file containing all conversations in a claude.ai export ZIP
CONVERSATIONS_FILENAME = "conversations.json"

# Content block types to skip during parsing
SKIP_BLOCK_TYPES = {"token_budget"}


class ClaudeCodeWebParser(BaseParser):
    """Parser for claude.ai web export datasets."""

    AGENT_TYPE = AgentType.CLAUDE_CODE_WEB
    LOCAL_DATA_DIR = None

    def discover_session_files(self, data_dir: Path) -> list[Path]:
        """Find conversations.json files in the given directory.

        Args:
            data_dir: Directory to scan.

        Returns:
            List of paths to conversations.json files.
        """
        return sorted(data_dir.rglob(CONVERSATIONS_FILENAME))

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse a conversations.json array into Trajectory objects.

        Args:
            content: Raw JSON content (array of conversation objects).
            source_path: Original file path for logging.

        Returns:
            List of Trajectory objects, one per non-empty conversation.
        """
        try:
            conversations = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in %s: %s", source_path, exc)
            return []

        if not isinstance(conversations, list):
            actual_type = type(conversations).__name__
            logger.warning("Expected JSON array in %s, got %s", source_path, actual_type)
            return []

        trajectories: list[Trajectory] = []
        for conversation in conversations:
            trajectory = _parse_conversation(self, conversation)
            if trajectory:
                trajectories.append(trajectory)

        logger.info(
            "Parsed %d trajectories from %s (%d conversations total)",
            len(trajectories),
            source_path or "unknown",
            len(conversations),
        )
        return trajectories


def _parse_conversation(parser: ClaudeCodeWebParser, conversation: dict) -> Trajectory | None:
    """Convert one conversation dict to a Trajectory.

    Args:
        parser: Parser instance for calling assemble_trajectory.
        conversation: Single conversation object from conversations.json.

    Returns:
        Trajectory, or None if the conversation has no messages.
    """
    session_id = conversation.get("uuid", "")
    if not session_id:
        return None

    chat_messages = conversation.get("chat_messages", [])
    if not chat_messages:
        return None

    steps = _build_steps(chat_messages, session_id)
    if not steps:
        return None

    extra: dict = {}
    conversation_name = conversation.get("name")
    if conversation_name:
        extra["conversation_name"] = conversation_name
    summary = conversation.get("summary")
    if summary:
        extra["summary"] = summary

    agent = parser.build_agent()
    return parser.assemble_trajectory(
        session_id=session_id, agent=agent, steps=steps, extra=extra or None
    )


def _build_steps(chat_messages: list, session_id: str) -> list[Step]:
    """Convert chat messages into Step objects.

    Human messages become USER steps. Assistant messages become AGENT steps
    with tool calls and observations extracted from inline content blocks.

    Args:
        chat_messages: List of chat_message dicts from the conversation.
        session_id: Parent conversation UUID for deterministic ID generation.

    Returns:
        List of Step objects.
    """
    steps: list[Step] = []
    for idx, msg in enumerate(chat_messages):
        if not isinstance(msg, dict):
            continue

        sender = msg.get("sender", "")
        if sender == "human":
            step = _build_human_step(msg, session_id, idx)
        elif sender == "assistant":
            step = _build_assistant_step(msg, session_id, idx)
        else:
            continue

        if step:
            steps.append(step)

    return steps


def _build_human_step(msg: dict, session_id: str, msg_idx: int) -> Step | None:
    """Build a USER step from a human message.

    Args:
        msg: Chat message dict with sender="human".
        session_id: Parent conversation UUID.
        msg_idx: Message index for deterministic ID.

    Returns:
        Step, or None if the message has no content.
    """
    text, attachments = _extract_user_content(msg)
    if not text:
        return None

    step_id = msg.get("uuid") or deterministic_id("msg", session_id, str(msg_idx), "human")
    timestamp = parse_iso_timestamp(msg.get("created_at"))

    extra: dict | None = None
    if attachments:
        extra = {"attachments": attachments}

    return Step(
        step_id=step_id, source=StepSource.USER, message=text, timestamp=timestamp, extra=extra
    )


def _build_assistant_step(msg: dict, session_id: str, msg_idx: int) -> Step | None:
    """Build an AGENT step from an assistant message.

    Decomposes the content blocks into text, reasoning, tool calls, and
    observations (tool results).

    Args:
        msg: Chat message dict with sender="assistant".
        session_id: Parent conversation UUID.
        msg_idx: Message index for deterministic ID.

    Returns:
        Step, or None if the message has no meaningful content.
    """
    content_blocks = msg.get("content", [])
    if not isinstance(content_blocks, list):
        content_blocks = []

    text_parts, reasoning_parts, tool_calls, observation_results = _decompose_assistant_content(
        content_blocks, session_id, msg_idx
    )

    message = "\n\n".join(text_parts).strip()
    reasoning = "\n\n".join(reasoning_parts).strip() or None

    if not message and not tool_calls and not reasoning:
        return None

    step_id = msg.get("uuid") or deterministic_id("msg", session_id, str(msg_idx), "assistant")
    timestamp = parse_iso_timestamp(msg.get("created_at"))

    observation: Observation | None = None
    if observation_results:
        observation = Observation(results=observation_results)

    return Step(
        step_id=step_id,
        source=StepSource.AGENT,
        message=message,
        reasoning_content=reasoning,
        timestamp=timestamp,
        tool_calls=tool_calls,
        observation=observation,
    )


def _decompose_assistant_content(
    content_blocks: list, session_id: str, msg_idx: int
) -> tuple[list[str], list[str], list[ToolCall], list[ObservationResult]]:
    """Extract structured data from assistant message content blocks.

    Processes blocks in order. Each ``tool_use`` block is converted to a
    ToolCall, and the matching ``tool_result`` block (which follows it
    inline) is converted to an ObservationResult.

    Args:
        content_blocks: List of content block dicts from the assistant message.
        session_id: Parent conversation UUID.
        msg_idx: Message index for deterministic ID generation.

    Returns:
        Tuple of (text_parts, reasoning_parts, tool_calls, observation_results).
    """
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    observation_results: list[ObservationResult] = []

    # Track tool_use blocks for pairing with tool_result blocks
    # Maps tool_use.id -> tool_call_id (our generated ID)
    tool_id_map: dict[str | None, str] = {}
    tool_use_counter = 0

    for block in content_blocks:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")

        if block_type in SKIP_BLOCK_TYPES:
            continue

        if block_type == "text":
            text = block.get("text", "")
            if text and text.strip():
                text_parts.append(text.strip())

        elif block_type == "thinking":
            thinking = block.get("thinking", "")
            if thinking and thinking.strip():
                reasoning_parts.append(thinking.strip())

        elif block_type == "tool_use":
            tool_name = block.get("name", "unknown")
            native_id = block.get("id")
            tool_call_id = deterministic_id(
                "tc", session_id, str(msg_idx), tool_name, str(tool_use_counter)
            )
            tool_id_map[native_id] = tool_call_id
            tool_use_counter += 1

            tool_calls.append(
                ToolCall(
                    tool_call_id=tool_call_id, function_name=tool_name, arguments=block.get("input")
                )
            )

        elif block_type == "tool_result":
            result_content = _extract_tool_result_content(block)
            native_tool_use_id = block.get("tool_use_id")
            source_call_id = tool_id_map.get(native_tool_use_id)

            observation_results.append(
                ObservationResult(source_call_id=source_call_id, content=result_content)
            )

    return text_parts, reasoning_parts, tool_calls, observation_results


def _extract_tool_result_content(block: dict) -> str | None:
    """Extract text content from a tool_result block.

    The content field can be a string, a list of sub-blocks (each with
    type/text), or None.

    Args:
        block: A tool_result content block.

    Returns:
        Concatenated text content, or None if empty.
    """
    raw_content = block.get("content")
    if raw_content is None:
        return None

    if isinstance(raw_content, str):
        return raw_content or None

    if isinstance(raw_content, list):
        parts = []
        for sub in raw_content:
            if isinstance(sub, dict) and sub.get("type") == "text":
                text = sub.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts) if parts else None

    return None


def _extract_user_content(msg: dict) -> tuple[str, list[dict]]:
    """Extract text and attachments from a human message.

    Tries the ``content`` blocks array first, falling back to
    the top-level ``text`` field.

    Args:
        msg: Chat message dict with sender="human".

    Returns:
        Tuple of (text, attachments_list).
    """
    content_blocks = msg.get("content", [])
    text_parts: list[str] = []

    if isinstance(content_blocks, list):
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text and text.strip():
                    text_parts.append(text.strip())

    text = "\n\n".join(text_parts).strip()

    # Fall back to top-level text field if content blocks yielded nothing
    if not text:
        text = (msg.get("text") or "").strip()

    attachments: list[dict] = []
    for att in msg.get("attachments", []):
        if isinstance(att, dict):
            attachments.append(
                {
                    "file_name": att.get("file_name", ""),
                    "file_type": att.get("file_type", ""),
                    "file_size": att.get("file_size", 0),
                }
            )

    return text, attachments

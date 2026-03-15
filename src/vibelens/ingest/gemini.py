"""Gemini CLI session JSON format parser.

Parses ~/.gemini/tmp/{project}/chats/session-*.json files containing
Gemini CLI session data with user and gemini message types.

Gemini CLI stores each session as a single JSON file (not JSONL), so the
entire conversation is loaded at once.  Key design differences from
Claude Code and Codex:

  - Tool calls and their results are **embedded** in the same ``gemini``
    message object (``toolCalls[].result``), so no cross-message pairing
    is needed.
  - Thinking is a structured ``thoughts`` array with ``subject`` /
    ``description`` pairs, not raw text.
  - The assistant role is recorded as ``type: "gemini"``; we normalise
    it to ``role: "assistant"`` for the unified model.
  - Sub-agent sessions share the same ``sessionId`` but live in separate
    files with ``kind: "subagent"``.
"""

import json
from pathlib import Path

from vibelens.ingest.base import BaseParser
from vibelens.ingest.diagnostics import DiagnosticsCollector
from vibelens.models.message import Message, TokenUsage, ToolCall
from vibelens.models.session import DataSourceType, SessionSummary
from vibelens.utils import (
    coerce_to_string,
    deterministic_id,
    get_logger,
    load_json_file,
    parse_iso_timestamp,
)

logger = get_logger(__name__)

# Gemini CLI uses "gemini" instead of "assistant" for model responses.
RELEVANT_TYPES = {"user", "gemini"}


class GeminiParser(BaseParser):
    """Parser for Gemini CLI's native session JSON format.

    Handles session JSON files with user and gemini messages,
    embedded tool calls, and structured thinking process.
    """

    def parse_file(self, file_path: Path) -> list[tuple[SessionSummary, list[Message]]]:
        """Parse a Gemini CLI session JSON file.

        Args:
            file_path: Path to a session-*.json file.

        Returns:
            Single-element list of (SessionSummary, messages), or empty list.
        """
        if not file_path.exists():
            logger.warning("Session file not found: %s", file_path)
            return []

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read session file: %s", file_path)
            return []

        session_id = data.get("sessionId", "")
        if not session_id:
            return []

        collector = DiagnosticsCollector()
        raw_messages = data.get("messages", [])
        collector.total_lines = len(raw_messages) if isinstance(raw_messages, list) else 0
        messages = _build_messages(raw_messages, session_id)
        collector.parsed_lines = len(messages)
        if not messages:
            return []
        self.enrich_tool_calls(messages)

        # Gemini stores main vs sub-agent sessions in separate files
        # distinguished by "kind".  Mark all messages so analytics can
        # filter orchestrated sub-tasks from primary user interaction.
        is_subagent = data.get("kind") == "subagent"
        if is_subagent:
            for msg in messages:
                msg.is_sidechain = True

        start_time = parse_iso_timestamp(data.get("startTime"))
        # Gemini provides explicit lastUpdated rather than requiring us to
        # derive duration from individual message timestamps.
        last_updated = parse_iso_timestamp(data.get("lastUpdated"))
        first_message = self.find_first_user_text(messages)
        models = {m.model for m in messages if m.model}
        tool_call_count = sum(len(m.tool_calls) for m in messages)

        duration = 0
        if start_time and last_updated:
            duration = int((last_updated - start_time).total_seconds())

        # Resolve project hash directory to a human-readable project path.
        # Gemini stores sessions under ~/.gemini/tmp/{sha256-hash}/chats/.
        hash_dir = ""
        gemini_dir = None
        if file_path.parts:
            chats_parent = file_path.parent.parent
            if chats_parent.name and file_path.parent.name == "chats":
                hash_dir = chats_parent.name
                gemini_dir = chats_parent.parent.parent

        project_path = ""
        if hash_dir and gemini_dir:
            project_path = resolve_project_path(hash_dir, gemini_dir, messages)

        summary = SessionSummary(
            session_id=session_id,
            project_id=self.encode_project_path(project_path) if project_path else "",
            project_name=self.extract_project_name(project_path) if project_path else "",
            timestamp=start_time,
            duration=duration,
            message_count=len(messages),
            tool_call_count=tool_call_count,
            models=sorted(models),
            first_message=first_message,
            source_type=DataSourceType.LOCAL,
            diagnostics=collector.to_diagnostics(),
        )

        return [(summary, messages)]


_PATH_ARG_KEYS = {"file_path", "path", "filename", "directory"}

# Avoid interpreting root-level paths like "/" or "/Users" as projects.
_MIN_PATH_DEPTH = 3


def resolve_project_path(
    hash_dir: str, gemini_dir: Path, messages: list[Message] | None = None
) -> str:
    """Resolve a Gemini SHA-256 hash directory to the original project path.

    Uses four strategies in order of speed:
    1. Check ``~/.gemini/tmp/{hash_dir}/.project_root`` file (fast path)
    2. Check ``~/.gemini/projects.json`` reverse lookup (medium path)
    3. Infer from tool call arguments in messages (slow path)
    4. Fall back to the hash string as-is

    Args:
        hash_dir: SHA-256 hash directory name.
        gemini_dir: Path to the ``~/.gemini`` directory.
        messages: Optional parsed messages for tool-arg inference.

    Returns:
        Resolved project path, or the hash string if unresolvable.
    """
    # Fast path: .project_root file inside the hash directory
    project_root_file = gemini_dir / "tmp" / hash_dir / ".project_root"
    try:
        if project_root_file.is_file():
            content = project_root_file.read_text(encoding="utf-8").strip()
            if content:
                return content
    except OSError:
        pass

    # Medium path: projects.json reverse lookup
    projects_file = gemini_dir / "projects.json"
    projects_data = load_json_file(projects_file)
    if isinstance(projects_data, dict):
        for project_path, info in projects_data.items():
            if isinstance(info, dict) and info.get("hash") == hash_dir:
                return project_path

    # Slow path: infer from tool call arguments
    if messages:
        inferred = _infer_project_from_tool_args(messages)
        if inferred:
            return inferred

    return hash_dir


def _infer_project_from_tool_args(messages: list[Message]) -> str:
    """Infer the project directory from absolute paths in tool call inputs.

    Collects absolute paths from tool call arguments, finds the longest
    common prefix, and returns the most frequent candidate that appears
    in at least 2 tool calls.

    Args:
        messages: Parsed messages with tool_calls.

    Returns:
        Inferred project path, or empty string if insufficient data.
    """
    absolute_paths: list[str] = []
    for msg in messages:
        for tc in msg.tool_calls:
            if not isinstance(tc.input, dict):
                continue
            for key in _PATH_ARG_KEYS:
                value = tc.input.get(key, "")
                if isinstance(value, str) and value.startswith("/"):
                    absolute_paths.append(value)

    if len(absolute_paths) < 2:
        return ""

    from collections import Counter
    from os.path import commonpath, dirname

    directories = [dirname(p) if not p.endswith("/") else p.rstrip("/") for p in absolute_paths]
    dir_counts: Counter[str] = Counter()
    for directory in directories:
        parts = directory.split("/")
        if len(parts) >= _MIN_PATH_DEPTH:
            dir_counts[directory] += 1

    if not dir_counts:
        return ""

    try:
        prefix = commonpath(absolute_paths)
    except ValueError:
        return ""

    prefix_parts = prefix.split("/")
    if len(prefix_parts) < _MIN_PATH_DEPTH:
        most_common = dir_counts.most_common(1)[0]
        if most_common[1] >= 2:
            return most_common[0]
        return ""

    return prefix


def _build_messages(raw_messages: list, session_id: str) -> list[Message]:
    """Convert Gemini CLI messages into Message objects.

    Args:
        raw_messages: Raw message dicts from session JSON.
        session_id: Session identifier.

    Returns:
        Ordered list of Message objects.
    """
    messages = []
    for idx, raw in enumerate(raw_messages):
        if not isinstance(raw, dict):
            continue
        msg_type = raw.get("type", "")
        if msg_type not in RELEVANT_TYPES:
            continue

        uuid = raw.get("id") or deterministic_id("msg", session_id, str(idx), msg_type)
        timestamp = parse_iso_timestamp(raw.get("timestamp"))

        if msg_type == "user":
            messages.append(
                Message(
                    uuid=uuid,
                    session_id=session_id,
                    role="user",
                    type="user",
                    content=_extract_user_content(raw),
                    timestamp=timestamp,
                )
            )
        elif msg_type == "gemini":
            messages.append(
                Message(
                    uuid=uuid,
                    session_id=session_id,
                    role="assistant",
                    type="gemini",
                    content=raw.get("content", ""),
                    thinking=_extract_thinking(raw),
                    model=raw.get("model", ""),
                    timestamp=timestamp,
                    usage=_parse_gemini_tokens(raw.get("tokens")),
                    tool_calls=_build_tool_calls(
                        raw.get("toolCalls", []), session_id, idx
                    ),
                )
            )

    return messages


def _extract_user_content(raw: dict) -> str:
    """Extract plain text from a user message's content array."""
    return coerce_to_string(raw.get("content", []))


def _extract_thinking(raw: dict) -> str | None:
    """Extract concatenated thinking text from thoughts array.

    Gemini structures thinking as ``{subject, description, timestamp}``
    objects — richer than Claude's raw text blocks.  We flatten them into
    a single string with ``[Subject] description`` formatting to match
    the unified model's ``thinking`` field, preserving the subject tags
    so downstream analysis can still segment by reasoning step.
    """
    thoughts = raw.get("thoughts", [])
    if not thoughts:
        return None
    parts = []
    for thought in thoughts:
        if not isinstance(thought, dict):
            continue
        subject = thought.get("subject", "")
        description = thought.get("description", "")
        if subject and description:
            parts.append(f"[{subject}] {description}")
        elif description:
            parts.append(description)
    return "\n".join(parts) if parts else None


def _parse_gemini_tokens(tokens: dict | None) -> TokenUsage | None:
    """Parse Gemini CLI token statistics into TokenUsage.

    Gemini uses a flat structure with short keys (``input``, ``output``,
    ``cached``, ``thoughts``, ``tool``, ``total``) — simpler than the
    nested Anthropic/OpenAI formats.  ``thoughts`` and ``tool`` counts
    have no equivalent in our unified TokenUsage model and are dropped.
    """
    if not tokens:
        return None
    return TokenUsage(
        input_tokens=tokens.get("input", 0),
        output_tokens=tokens.get("output", 0),
        cache_read_tokens=tokens.get("cached", 0),
    )


def _build_tool_calls(
    raw_tool_calls: list, session_id: str, msg_idx: int
) -> list[ToolCall]:
    """Convert Gemini CLI toolCalls into ToolCall objects.

    Unlike Claude Code (which splits tool_use and tool_result across two
    messages) and Codex (which uses separate response_item entries),
    Gemini embeds the result directly inside each toolCall object.
    This makes parsing simpler — no cross-entry pairing needed.
    """
    calls = []
    for tc_idx, tool in enumerate(raw_tool_calls):
        if not isinstance(tool, dict):
            continue
        tool_name = tool.get("name", "unknown")
        tc_id = tool.get("id") or deterministic_id(
            "tc", session_id, tool_name, str(msg_idx), str(tc_idx)
        )
        calls.append(
            ToolCall(
                id=tc_id,
                name=tool_name,
                input=tool.get("args"),
                output=_extract_tool_output(tool.get("result", [])),
                is_error=tool.get("status") == "error",
            )
        )
    return calls


def _extract_tool_output(result: list) -> str | None:
    """Extract output text from a Gemini toolCall result array.

    Results are wrapped in a ``functionResponse`` envelope following the
    Google function-calling protocol: ``[{functionResponse: {id, name,
    response: {output: "..."}}}]``.  We unwrap to get the plain output.
    """
    if not result:
        return None
    parts = []
    for item in result:
        if not isinstance(item, dict):
            continue
        response = item.get("functionResponse", {}).get("response", {})
        output = response.get("output", "")
        if output:
            parts.append(output)
    return "\n".join(parts) if parts else None

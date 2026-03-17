"""VibeLens Export v1 serializer.

Produces a clean, re-importable JSON format for session export/download.
Separate from the MongoDB serializer which has its own consumers and
structural conventions (flat messages with agent_id discriminator, _id
fields, etc.).
"""

from vibelens.models.message import Message
from vibelens.models.session import SessionDetail, SessionSummary, SubAgentSession
from vibelens.utils.timestamps import format_isoformat

VIBELENS_EXPORT_VERSION = 1

# Known agent formats for heuristic fallback when agent_format is unset.
_MODEL_PREFIX_HINTS: dict[str, str] = {
    "claude": "claude_code",
    "gpt": "codex",
    "gemini": "gemini",
}


def serialize_export(detail: SessionDetail) -> dict:
    """Serialize a SessionDetail into VibeLens Export v1 format.

    Args:
        detail: Full session data to serialize.

    Returns:
        Dictionary with vibelens_version, agent_format, session, messages,
        and sub_sessions suitable for JSON export and re-import.
    """
    agent_format = _resolve_agent_format(detail.summary)
    return {
        "vibelens_version": VIBELENS_EXPORT_VERSION,
        "agent_format": agent_format,
        "session": _serialize_session_metadata(detail.summary),
        "messages": [_serialize_export_message(msg) for msg in detail.messages],
        "sub_sessions": [_serialize_sub_session(sub) for sub in detail.sub_sessions],
    }


def _serialize_session_metadata(summary: SessionSummary) -> dict:
    """Serialize session metadata without MongoDB artifacts.

    Args:
        summary: Session summary to serialize.

    Returns:
        Dictionary with session-level metadata (no _id).
    """
    source_type = (
        summary.source_type.value if hasattr(summary.source_type, "value") else summary.source_type
    )
    return {
        "session_id": summary.session_id,
        "project_id": summary.project_id,
        "project_name": summary.project_name,
        "timestamp": format_isoformat(summary.timestamp),
        "duration": summary.duration,
        "message_count": summary.message_count,
        "tool_call_count": summary.tool_call_count,
        "models": summary.models,
        "first_message": summary.first_message,
        "source_type": source_type,
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
        "total_cache_read": summary.total_cache_read,
        "total_cache_write": summary.total_cache_write,
        "diagnostics": summary.diagnostics.model_dump() if summary.diagnostics else None,
    }


def _serialize_export_message(msg: Message) -> dict:
    """Serialize a message with role-aware field omission.

    User messages omit thinking, tool_calls, usage, and model.
    Assistant messages omit fields that are None or empty.

    Args:
        msg: Message to serialize.

    Returns:
        Dictionary with only relevant fields present.
    """
    if isinstance(msg.content, str):
        content = msg.content
    else:
        content = [block.model_dump() for block in msg.content]

    doc: dict = {
        "uuid": msg.uuid,
        "role": msg.role,
        "content": content,
        "timestamp": format_isoformat(msg.timestamp),
    }

    if msg.parent_uuid:
        doc["parent_uuid"] = msg.parent_uuid

    if msg.role == "assistant":
        if msg.model:
            doc["model"] = msg.model
        if msg.thinking:
            doc["thinking"] = msg.thinking
        if msg.usage:
            doc["usage"] = msg.usage.model_dump()
        if msg.tool_calls:
            doc["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]

    return doc


def _serialize_sub_session(sub: SubAgentSession) -> dict:
    """Serialize a sub-agent session with hierarchical structure.

    Args:
        sub: Sub-agent session to serialize.

    Returns:
        Dictionary with agent metadata, messages, and nested sub-sessions.
    """
    return {
        "agent_id": sub.agent_id,
        "spawn_index": sub.spawn_index,
        "spawn_tool_call_id": sub.spawn_tool_call_id,
        "messages": [_serialize_export_message(msg) for msg in sub.messages],
        "sub_sessions": [_serialize_sub_session(nested) for nested in sub.sub_sessions],
    }


def _resolve_agent_format(summary: SessionSummary) -> str:
    """Determine the agent format, with heuristic fallback for old data.

    Checks the agent_format field first. If empty, infers from model names.

    Args:
        summary: Session summary to inspect.

    Returns:
        Agent format string (e.g. "claude_code", "codex", "gemini").
    """
    if summary.agent_format:
        return summary.agent_format
    # Heuristic fallback: infer from model name prefixes
    for model in summary.models:
        model_lower = model.lower()
        for prefix, fmt in _MODEL_PREFIX_HINTS.items():
            if model_lower.startswith(prefix):
                return fmt
    return "unknown"

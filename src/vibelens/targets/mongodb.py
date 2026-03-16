"""MongoDB data target for pushing session data."""

import logging

from motor.motor_asyncio import AsyncIOMotorClient

from vibelens.models.message import Message
from vibelens.models.requests import PushResult
from vibelens.models.session import MAIN_AGENT_ID, SessionDetail, SubAgentSession
from vibelens.utils.timestamps import format_isoformat

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


class MongoDBTarget:
    """Push parsed session data to a MongoDB instance.

    Uses a two-collection design (sessions + messages) to avoid the
    16 MB BSON document limit and enable efficient message pagination.
    """

    def __init__(self, uri: str, db_name: str = "vibelens") -> None:
        """Initialize MongoDB connection.

        Args:
            uri: MongoDB connection URI.
            db_name: Database name to use.
        """
        self._client = AsyncIOMotorClient(uri)
        self._db = self._client[db_name]
        self.sessions = self._db["sessions"]
        self.messages = self._db["messages"]

    @property
    def target_type(self) -> str:
        return "mongodb"

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient querying."""
        await self.sessions.create_index("source_type")
        await self.sessions.create_index("project_name")
        await self.sessions.create_index([("timestamp", -1)])

        await self.messages.create_index([("session_id", 1), ("timestamp", 1)])
        await self.messages.create_index([("session_id", 1), ("agent_id", 1)])

    async def push_sessions(self, sessions: list[SessionDetail]) -> PushResult:
        """Push session data to MongoDB.

        Args:
            sessions: List of SessionDetail objects to upload.

        Returns:
            PushResult with upload statistics.
        """
        uploaded = 0
        skipped = 0
        errors: list[dict] = []

        for detail in sessions:
            session_id = detail.summary.session_id
            try:
                existing = await self.sessions.find_one({"_id": session_id}, {"_id": 1})
                if existing:
                    skipped += 1
                    continue

                session_doc = serialize_session(detail)
                await self.sessions.insert_one(session_doc)

                message_docs = flatten_messages(detail)
                if message_docs:
                    for batch_start in range(0, len(message_docs), BATCH_SIZE):
                        batch = message_docs[batch_start : batch_start + BATCH_SIZE]
                        await self.messages.insert_many(batch, ordered=False)

                uploaded += 1
                logger.info("Pushed session %s (%d messages)", session_id, len(message_docs))

            except Exception as exc:
                logger.error("Failed to push session %s: %s", session_id, exc)
                errors.append({"session_id": session_id, "error": str(exc)})

        return PushResult(total=len(sessions), uploaded=uploaded, skipped=skipped, errors=errors)

    async def close(self) -> None:
        """Close the MongoDB client connection."""
        self._client.close()


def serialize_session(detail: SessionDetail) -> dict:
    """Convert a SessionDetail into a MongoDB session document.

    Args:
        detail: Full session data to serialize.

    Returns:
        Dictionary suitable for MongoDB insertion.
    """
    summary = detail.summary
    source_type = (
        summary.source_type.value if hasattr(summary.source_type, "value") else summary.source_type
    )
    return {
        "_id": summary.session_id,
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
        "source_name": summary.source_name,
        "source_host": summary.source_host,
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
        "total_cache_read": summary.total_cache_read,
        "total_cache_write": summary.total_cache_write,
        "diagnostics": summary.diagnostics.model_dump() if summary.diagnostics else None,
        "sub_sessions": [_extract_sub_session_metadata(sub) for sub in detail.sub_sessions],
    }


def _extract_sub_session_metadata(sub: SubAgentSession) -> dict:
    """Extract metadata from a SubAgentSession including message stats.

    Args:
        sub: Sub-agent session to extract metadata from.

    Returns:
        Dictionary with agent_id, spawn info, message count, and nested sub-session metadata.
    """
    tool_count = sum(len(m.tool_calls) for m in sub.messages)
    models = sorted({m.model for m in sub.messages if m.model})
    first_msg = ""
    for m in sub.messages:
        if m.role == "user" and isinstance(m.content, str) and m.content.strip():
            first_msg = m.content[:120]
            break

    return {
        "agent_id": sub.agent_id,
        "spawn_index": sub.spawn_index,
        "spawn_tool_call_id": sub.spawn_tool_call_id,
        "message_count": len(sub.messages),
        "tool_call_count": tool_count,
        "models": models,
        "first_message": first_msg,
        "sub_sessions": [_extract_sub_session_metadata(nested) for nested in sub.sub_sessions],
    }


def _serialize_message(msg: Message, agent_id: str) -> dict:
    """Convert a Message into a MongoDB message document.

    Args:
        msg: Message to serialize.
        agent_id: Agent identifier ("" for main session).

    Returns:
        Dictionary suitable for MongoDB insertion.
    """
    if isinstance(msg.content, str):
        content = msg.content
    else:
        content = [block.model_dump() for block in msg.content]

    return {
        "_id": msg.uuid,
        "session_id": msg.session_id,
        "agent_id": agent_id,
        "parent_uuid": msg.parent_uuid,
        "role": msg.role,
        "type": msg.type,
        "content": content,
        "thinking": msg.thinking,
        "model": msg.model,
        "timestamp": format_isoformat(msg.timestamp),
        "is_sidechain": msg.is_sidechain,
        "usage": msg.usage.model_dump() if msg.usage else None,
        "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
    }


def flatten_messages(detail: SessionDetail) -> list[dict]:
    """Recursively collect all messages from main session and sub-sessions.

    MongoDB stores all messages in a single flat collection. Each message
    carries an ``agent_id`` discriminator so queries can reconstruct the
    tree: main session messages use MAIN_AGENT_ID (""), sub-agent messages
    use their agent file stem (e.g. "agent-abc123").

    Args:
        detail: Full session data containing messages and sub-sessions.

    Returns:
        Flat list of message documents with correct agent_id discriminator.
    """
    docs: list[dict] = []
    for msg in detail.messages:
        docs.append(_serialize_message(msg, MAIN_AGENT_ID))
    for sub in detail.sub_sessions:
        _collect_sub_messages(sub, docs)
    return docs


def _collect_sub_messages(sub: SubAgentSession, docs: list[dict]) -> None:
    """Recursively collect messages from a sub-agent session tree.

    Args:
        sub: Sub-agent session to collect from.
        docs: Accumulator list to append message documents to.
    """
    for msg in sub.messages:
        docs.append(_serialize_message(msg, sub.agent_id))
    for nested in sub.sub_sessions:
        _collect_sub_messages(nested, docs)

"""MongoDB data source for querying session data."""

import logging
from collections import defaultdict

from motor.motor_asyncio import AsyncIOMotorClient

from vibelens.models.message import Message
from vibelens.models.requests import RemoteSessionsQuery
from vibelens.models.session import (
    MAIN_AGENT_ID,
    SessionDetail,
    SessionSummary,
    SubAgentSession,
)

logger = logging.getLogger(__name__)


class MongoDBSource:
    """Query sessions from a remote MongoDB instance."""

    def __init__(self, uri: str, db_name: str = "vibelens") -> None:
        """Initialize MongoDB connection.

        Args:
            uri: MongoDB connection URI.
            db_name: Database name to query.
        """
        self._client = AsyncIOMotorClient(uri)
        self._db = self._client[db_name]
        self.sessions = self._db["sessions"]
        self.messages = self._db["messages"]

    @property
    def source_type(self) -> str:
        return "mongodb"

    @property
    def display_name(self) -> str:
        return "MongoDB"

    async def list_sessions(self, query: RemoteSessionsQuery) -> list[SessionSummary]:
        """Query session summaries with optional filters.

        Args:
            query: Filtering and pagination parameters.

        Returns:
            List of SessionSummary objects.
        """
        mongo_filter: dict = {}
        if query.source_type:
            mongo_filter["source_type"] = query.source_type.value
        if query.project_id:
            mongo_filter["project_name"] = query.project_id

        cursor = (
            self.sessions.find(mongo_filter)
            .sort("timestamp", -1)
            .skip(query.offset)
            .limit(query.limit)
        )

        summaries = []
        async for doc in cursor:
            summaries.append(_deserialize_session(doc))
        return summaries

    async def get_session(self, session_id: str) -> SessionDetail | None:
        """Fetch a full session with messages and sub-agent hierarchy.

        Args:
            session_id: The session to retrieve.

        Returns:
            SessionDetail with reconstructed sub-sessions, or None if not found.
        """
        session_doc = await self.sessions.find_one({"_id": session_id})
        if not session_doc:
            return None

        summary = _deserialize_session(session_doc)

        # Messages are stored flat in MongoDB with agent_id as discriminator.
        # Group by agent_id, then use the sub_sessions metadata tree from the
        # session document to reconstruct the nested SubAgentSession hierarchy.
        cursor = self.messages.find({"session_id": session_id}).sort("timestamp", 1)
        messages_by_agent: dict[str, list[Message]] = defaultdict(list)
        async for doc in cursor:
            agent_id = doc.get("agent_id", MAIN_AGENT_ID)
            messages_by_agent[agent_id].append(_deserialize_message(doc))

        main_messages = messages_by_agent.pop(MAIN_AGENT_ID, [])
        sub_meta = session_doc.get("sub_sessions", [])
        sub_sessions = _reconstruct_sub_sessions(sub_meta, messages_by_agent)

        return SessionDetail(
            summary=summary,
            messages=main_messages,
            sub_sessions=sub_sessions,
        )

    async def list_projects(self) -> list[str]:
        """Return distinct project names from stored sessions.

        Returns:
            Sorted list of project name strings.
        """
        projects = await self.sessions.distinct("project_name", {"project_name": {"$ne": ""}})
        return sorted(projects)

    async def close(self) -> None:
        """Close the MongoDB client connection."""
        self._client.close()


def _deserialize_session(doc: dict) -> SessionSummary:
    """Convert a MongoDB session document to a SessionSummary.

    Args:
        doc: MongoDB document from the sessions collection.

    Returns:
        Populated SessionSummary instance.
    """
    diagnostics_raw = doc.get("diagnostics")
    return SessionSummary(
        session_id=doc["_id"],
        project_id=doc.get("project_id", ""),
        project_name=doc.get("project_name", ""),
        timestamp=doc.get("timestamp"),
        duration=doc.get("duration", 0),
        message_count=doc.get("message_count", 0),
        tool_call_count=doc.get("tool_call_count", 0),
        models=doc.get("models", []),
        first_message=doc.get("first_message", ""),
        source_type=doc.get("source_type", "mongodb"),
        source_name=doc.get("source_name", ""),
        source_host=doc.get("source_host", ""),
        total_input_tokens=doc.get("total_input_tokens", 0),
        total_output_tokens=doc.get("total_output_tokens", 0),
        total_cache_read=doc.get("total_cache_read", 0),
        total_cache_write=doc.get("total_cache_write", 0),
        diagnostics=diagnostics_raw,
    )


def _deserialize_message(doc: dict) -> Message:
    """Convert a MongoDB message document to a Message.

    Args:
        doc: MongoDB document from the messages collection.

    Returns:
        Populated Message instance.
    """
    return Message(
        uuid=doc["_id"],
        session_id=doc.get("session_id", ""),
        parent_uuid=doc.get("parent_uuid", ""),
        role=doc.get("role", ""),
        type=doc.get("type", ""),
        content=doc.get("content", ""),
        thinking=doc.get("thinking"),
        model=doc.get("model", ""),
        timestamp=doc.get("timestamp"),
        is_sidechain=doc.get("is_sidechain", False),
        usage=doc.get("usage"),
        tool_calls=doc.get("tool_calls", []),
    )


def _reconstruct_sub_sessions(
    sub_meta: list[dict], messages_by_agent: dict[str, list[Message]]
) -> list[SubAgentSession]:
    """Recursively reconstruct SubAgentSession hierarchy from metadata and messages.

    Args:
        sub_meta: Sub-session metadata from the session document.
        messages_by_agent: Messages grouped by agent_id.

    Returns:
        List of SubAgentSession objects with messages attached.
    """
    result = []
    for meta in sub_meta:
        agent_id = meta["agent_id"]
        nested_meta = meta.get("sub_sessions", [])
        # pop() rather than get() so each agent's messages are consumed
        # exactly once — prevents duplicate attachment if metadata has
        # overlapping agent_ids across nesting levels.
        sub = SubAgentSession(
            agent_id=agent_id,
            spawn_index=meta.get("spawn_index"),
            spawn_tool_call_id=meta.get("spawn_tool_call_id", ""),
            messages=messages_by_agent.pop(agent_id, []),
            sub_sessions=_reconstruct_sub_sessions(nested_meta, messages_by_agent),
        )
        result.append(sub)
    return result

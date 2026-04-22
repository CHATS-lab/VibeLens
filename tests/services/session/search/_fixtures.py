"""Synthetic session fixtures for search tests.

Builds minimal ATIF ``Trajectory`` objects and a prebuilt index so tests
never touch disk. Keeps the catalog small enough to reason about but
large enough that BM25 IDF math produces sensible numbers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Agent, Step, Trajectory
from vibelens.models.trajectories.tool_call import ToolCall
from vibelens.services.search import InvertedIndex, tokenize
from vibelens.services.session.search.index import (
    FIELD_WEIGHTS,
    SessionSearchIndex,
    _build_entry,
)
from vibelens.services.session.search.index import _SessionEntry as _EntryType  # re-export

# Re-export so tests can import from one place.
SessionEntry = _EntryType  # noqa: N816 -- alias for a private dataclass
FIELDS_UNDER_TEST = tuple(FIELD_WEIGHTS.keys())

# Base timestamp; fixtures offset per session so tie-breakers are deterministic.
_BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_agent_step(text: str, step_id: str = "s1") -> Step:
    """One agent step with text content."""
    return Step(step_id=step_id, source=StepSource.AGENT, message=text)


def make_user_step(text: str, step_id: str = "u1") -> Step:
    """One user step with text content."""
    return Step(step_id=step_id, source=StepSource.USER, message=text)


def make_tool_step(name: str, args: dict, step_id: str = "t1") -> Step:
    """Agent step whose only content is a tool call."""
    tc = ToolCall(
        tool_call_id=f"tc-{step_id}",
        function_name=name,
        arguments=args,
    )
    return Step(
        step_id=step_id,
        source=StepSource.AGENT,
        message="",
        tool_calls=[tc],
    )


def make_trajectory(session_id: str, steps: list[Step]) -> Trajectory:
    """Wrap a list of steps into a minimal Trajectory."""
    return Trajectory(
        session_id=session_id,
        agent=Agent(name="claude"),
        steps=steps,
        timestamp=_BASE_TS,
    )


def make_synthetic_entry(
    session_id: str,
    user_text: str = "",
    agent_text: str = "",
    tool_text: str = "",
    offset_days: int = 0,
) -> SessionEntry:
    """Build an index-ready entry directly, bypassing the store loader.

    The three text fields are stored pre-lowercased and the tokenization
    matches what ``_build_entry`` produces on real data.
    """
    sid_lower = session_id.lower()
    tokens = {
        "session_id": tokenize(sid_lower.replace("-", " ")),
        "user_prompts": tokenize(user_text),
        "agent_messages": tokenize(agent_text),
        "tool_calls": tokenize(tool_text),
    }
    return SessionEntry(
        session_id=session_id,
        session_id_lower=sid_lower,
        user_prompts=user_text.lower(),
        agent_messages=agent_text.lower(),
        tool_calls=tool_text.lower(),
        tokens_per_field=tokens,
        timestamp=_BASE_TS + timedelta(days=offset_days),
    )


def build_index_from_entries(entries: list[SessionEntry]) -> SessionSearchIndex:
    """Install a precomputed entry set into a fresh index."""
    idx = SessionSearchIndex()
    entries_by_sid = {e.session_id: e for e in entries}
    idx._swap_in_full(entries_by_sid)  # noqa: SLF001 -- exposed for tests
    return idx


__all__ = [
    "FIELDS_UNDER_TEST",
    "InvertedIndex",
    "SessionEntry",
    "build_index_from_entries",
    "make_agent_step",
    "make_synthetic_entry",
    "make_tool_step",
    "make_trajectory",
    "make_user_step",
    "_build_entry",
    "tokenize",
]

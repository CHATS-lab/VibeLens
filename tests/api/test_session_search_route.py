"""HTTP-level tests for GET /api/sessions/search.

Exercise the endpoint's ranked-response contract and the fallback to
Tier 1 when Tier 2 is not yet built.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from vibelens.app import create_app
from vibelens.services.session.search import (
    ScoredSession,
    SessionSearchIndex,
    invalidate_search_index,
)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """Minimal FastAPI TestClient with search.enabled forced True.

    Search defaults to disabled (settings.search.enabled=False) to keep
    the base memory footprint low; these tests exercise the endpoint
    contract so they need it on.
    """
    from vibelens.deps import get_settings

    monkeypatch.setattr(get_settings().search, "enabled", True)
    return TestClient(create_app())


def _fake_index(with_full: bool) -> SessionSearchIndex:
    """Build a SessionSearchIndex populated in-memory without hitting disk."""
    # Minimal monkeypatch-style setup via the fixtures module so tests stay
    # isolated from the real on-disk catalog.
    from tests.services.session.search._fixtures import (
        build_index_from_entries,
        make_synthetic_entry,
    )

    entries = [
        make_synthetic_entry("alpha-1", user_text="fastapi dependency injection"),
        make_synthetic_entry("beta-2", user_text="react state hooks"),
        make_synthetic_entry("gamma-3", user_text="python pytest fixtures"),
        # Padding so BM25 IDF is stable.
        make_synthetic_entry("fill-a", user_text="go channel deadlock"),
        make_synthetic_entry("fill-b", user_text="rust tokio runtime"),
        make_synthetic_entry("fill-c", user_text="docker multi-stage build"),
    ]
    if with_full:
        return build_index_from_entries(entries)
    # Tier-2-less index: only metadata entries populated.
    idx = SessionSearchIndex()
    from vibelens.services.session.search.index import _SessionEntry

    for e in entries:
        idx._metadata_entries[e.session_id] = _SessionEntry(  # noqa: SLF001
            session_id=e.session_id,
            session_id_lower=e.session_id,
            user_prompts=e.user_prompts,
            agent_messages="",
            tool_calls="",
        )
    return idx


def test_empty_query_returns_empty_list(client):
    """An empty ``q`` short-circuits to [] without invoking the index."""
    resp = client.get("/api/sessions/search?q=")
    assert resp.status_code == 200
    assert resp.json() == []


def test_query_returns_ranked_json_shape(client):
    """Results come back as [{session_id, score}, ...] in rank order."""
    fake = _fake_index(with_full=True)
    with patch("vibelens.services.session.search._index", fake):
        resp = client.get("/api/sessions/search?q=fastapi")
    assert resp.status_code == 200
    body = resp.json()
    print(f"ranked body: {body}")
    assert isinstance(body, list)
    assert body, "fastapi should hit at least one session"
    first = body[0]
    assert set(first.keys()) == {"session_id", "score"}
    assert isinstance(first["session_id"], str)
    assert isinstance(first["score"], (int, float))
    # The alpha-1 session is the only one that says 'fastapi'.
    assert body[0]["session_id"] == "alpha-1"


def test_tier1_fallback_returns_zero_scores(client):
    """Before Tier 2 is built, metadata substring match returns score=0."""
    fake = _fake_index(with_full=False)
    with patch("vibelens.services.session.search._index", fake):
        resp = client.get("/api/sessions/search?q=fastapi")
    assert resp.status_code == 200
    body = resp.json()
    print(f"tier1 body: {body}")
    assert body, "Tier-1 should still match the user_prompts preview"
    assert all(entry["score"] == 0.0 for entry in body)
    assert {entry["session_id"] for entry in body} == {"alpha-1"}


def test_unranked_endpoint_honors_session_token_header(client):
    """The x-session-token header is forwarded down to the search function."""
    captured = {}

    def fake_search(query, session_token=None, top_k=None):
        captured["query"] = query
        captured["token"] = session_token
        return [ScoredSession(session_id="abc", composite_score=1.0)]

    with patch("vibelens.api.sessions.search_sessions", fake_search):
        resp = client.get(
            "/api/sessions/search?q=hello",
            headers={"x-session-token": "tab-xyz"},
        )

    assert resp.status_code == 200
    assert resp.json() == [{"session_id": "abc", "score": 1.0}]
    print(f"captured: {captured}")
    assert captured["token"] == "tab-xyz"
    assert captured["query"] == "hello"


@pytest.fixture(autouse=True)
def _reset_index_singleton():
    """Make sure no test leaks state via the module-level _index singleton."""
    yield
    invalidate_search_index()

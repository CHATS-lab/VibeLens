"""Scorer tests: session_id tier, AND semantics, BM25F composite."""

from tests.services.session.search._fixtures import (
    build_index_from_entries,
    make_synthetic_entry,
)


def _mini_catalog():
    """Ten synthetic sessions covering the ranking scenarios we test.

    Small enough to reason about but large enough that BM25 IDF stays
    well-behaved.
    """
    return [
        make_synthetic_entry(
            "abc-1",
            user_text="react component library question",
            agent_text="use the useState hook",
            tool_text="Read src/App.tsx Grep useState",
            offset_days=1,
        ),
        make_synthetic_entry(
            "def-2",
            user_text="python testing with pytest fixtures",
            agent_text="pytest fixtures can scope to module",
            tool_text="Bash pytest -v tests/",
            offset_days=2,
        ),
        make_synthetic_entry(
            "ghi-3",
            user_text="fastapi dependency injection",
            agent_text="Depends() is the idiom",
            tool_text="Read main.py",
            offset_days=3,
        ),
        make_synthetic_entry(
            "jkl-4",
            user_text="rust async await tokio",
            agent_text="spawn with tokio spawn",
            tool_text="Bash cargo test",
            offset_days=4,
        ),
        make_synthetic_entry(
            "mno-5",
            user_text="migration from sqlalchemy 1.4 to 2.0",
            agent_text="Use the new select() style",
            tool_text="Read models.py Edit models.py",
            offset_days=5,
        ),
        make_synthetic_entry(
            "pqr-6",
            user_text="authentication bug with jwt tokens",
            agent_text="check iss claim and expiry",
            tool_text="Grep jwt",
            offset_days=6,
        ),
        make_synthetic_entry(
            "stu-7",
            user_text="react native ios build fails",
            agent_text="pod install usually fixes it",
            tool_text="Bash cd ios && pod install",
            offset_days=7,
        ),
        make_synthetic_entry(
            "vwx-8",
            user_text="python asyncio event loop",
            agent_text="get_running_loop beats get_event_loop",
            tool_text="Read loop.py",
            offset_days=8,
        ),
        make_synthetic_entry(
            "yz0-9",
            user_text="docker multi-stage build optimization",
            agent_text="Use cache mounts in RUN",
            tool_text="Edit Dockerfile",
            offset_days=9,
        ),
        make_synthetic_entry(
            "abc-10",  # shares prefix with abc-1, for prefix-tier tests
            user_text="unrelated sql index optimization",
            agent_text="run EXPLAIN ANALYZE",
            tool_text="Bash psql -c EXPLAIN",
            offset_days=10,
        ),
    ]


def test_exact_session_id_wins():
    """Exact session_id match ranks 1 regardless of text content."""
    entries = _mini_catalog()
    idx = build_index_from_entries(entries)
    out = idx.search_full("ghi-3")
    print(f"exact sid hits: {out[:3]}")
    assert out[0][0] == "ghi-3"


def test_sid_prefix_tier_outranks_content_match():
    """A first-segment prefix match beats a pure content match."""
    entries = _mini_catalog()
    idx = build_index_from_entries(entries)
    # "abc" matches abc-1 and abc-10 via the prefix band, beats any
    # content-only hit in the rest of the catalog.
    out = idx.search_full("abc")
    top2 = {sid for sid, _ in out[:2]}
    print(f"abc prefix top2: {top2}")
    assert top2 == {"abc-1", "abc-10"}


def test_mid_sid_does_not_prefix_match():
    """Query 'def' only matches sids whose FIRST segment is 'def'.

    Guard against regressing to substring-prefix: sessions like
    "fed-def-9" (which don't exist in this catalog) would wrongly match
    if we ever used plain substring instead of leading-segment prefix.
    """
    entries = _mini_catalog()
    idx = build_index_from_entries(entries)
    out = idx.search_full("def")
    sids = [sid for sid, _ in out]
    print(f"'def' results: {sids}")
    # def-2's leading segment is 'def'; content doesn't mention 'def'.
    # The result must contain exactly one session: def-2.
    assert sids == ["def-2"]


def test_multi_token_and_semantics():
    """Both 'python' and 'testing' must appear for the doc to match."""
    entries = _mini_catalog()
    idx = build_index_from_entries(entries)
    out = idx.search_full("python testing")
    sids = [sid for sid, _ in out]
    print(f"'python testing' sids: {sids}")
    # def-2 mentions both.
    assert "def-2" in sids
    # vwx-8 mentions python but not testing — must not match under AND.
    assert "vwx-8" not in sids


def test_single_token_content_match():
    """A unique token finds exactly one session."""
    entries = _mini_catalog()
    idx = build_index_from_entries(entries)
    out = idx.search_full("jwt")
    sids = [sid for sid, _ in out]
    print(f"'jwt' sids: {sids}")
    assert sids[0] == "pqr-6"


def test_nonsense_query_returns_empty():
    """A query matching nothing anywhere returns an empty list."""
    entries = _mini_catalog()
    idx = build_index_from_entries(entries)
    out = idx.search_full("xyzqqqq")
    print(f"nonsense: {out}")
    assert out == []


def test_recency_tiebreaker_within_same_score():
    """When two sessions score equally, the newer one ranks first."""
    # Two sessions with identical content differ only in timestamp.
    entries = [
        make_synthetic_entry(
            "aaa-old", user_text="gpu memory leak", offset_days=0,
        ),
        make_synthetic_entry(
            "aaa-new", user_text="gpu memory leak", offset_days=30,
        ),
        # Padding so BM25 IDF doesn't collapse.
        make_synthetic_entry("bbb", user_text="unrelated"),
        make_synthetic_entry("ccc", user_text="more unrelated"),
        make_synthetic_entry("ddd", user_text="still unrelated"),
    ]
    idx = build_index_from_entries(entries)
    out = idx.search_full("gpu memory leak")
    sids = [sid for sid, _ in out[:2]]
    print(f"tiebreak top2: {sids}")
    # Both aaa-old and aaa-new also match the "aaa" first-segment prefix
    # tier (since the query doesn't share that prefix, tiers tie at 0),
    # so recency alone breaks the tie.
    assert sids == ["aaa-new", "aaa-old"]

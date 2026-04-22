"""Lifecycle tests: build, incremental add, refresh, invalidate."""

from unittest.mock import patch

from tests.services.session.search._fixtures import (
    build_index_from_entries,
    make_agent_step,
    make_synthetic_entry,
    make_trajectory,
    make_user_step,
)
from vibelens.services.session.search import (
    ScoredSession,
    SessionSearchIndex,
    search_sessions,
)


def test_has_full_flips_after_swap_in():
    """Empty index reports not ready until entries are installed."""
    idx = SessionSearchIndex()
    assert not idx.has_full()
    entries = [make_synthetic_entry("a", user_text="foo bar baz")]
    idx = build_index_from_entries(entries)
    assert idx.has_full()


def test_search_full_returns_none_on_empty_query():
    """Empty query short-circuits to None so caller can skip."""
    idx = build_index_from_entries([make_synthetic_entry("a", user_text="foo")])
    assert idx.search_full("") is None
    assert idx.search_full("   ") is None


def test_search_metadata_covers_session_id_and_first_message():
    """Tier 1 substring works against session_id and user_prompts fields."""
    idx = SessionSearchIndex()
    # Inject metadata entries directly — bypasses list_all_metadata().
    from vibelens.services.session.search.index import _SessionEntry
    idx._metadata_entries = {  # noqa: SLF001 -- test fixture
        "alpha-1": _SessionEntry(
            session_id="alpha-1",
            session_id_lower="alpha-1",
            user_prompts="deploy staging today",
            agent_messages="",
            tool_calls="",
        ),
        "beta-2": _SessionEntry(
            session_id="beta-2",
            session_id_lower="beta-2",
            user_prompts="hello",
            agent_messages="",
            tool_calls="",
        ),
    }
    hits_by_sid = {sid for sid, _ in idx.search_metadata("alpha")}
    hits_by_body = {sid for sid, _ in idx.search_metadata("staging")}
    print(f"by_sid={hits_by_sid} by_body={hits_by_body}")
    assert hits_by_sid == {"alpha-1"}
    assert hits_by_body == {"alpha-1"}


def test_search_sessions_returns_scored_session():
    """Public API returns a list of ScoredSession with float scores."""
    entries = [
        make_synthetic_entry("a", user_text="fastapi dependency injection", offset_days=0),
        make_synthetic_entry("b", user_text="unrelated", offset_days=1),
        make_synthetic_entry("c", user_text="other", offset_days=2),
    ]
    idx = build_index_from_entries(entries)

    with patch("vibelens.services.session.search._index", idx):
        hits = search_sessions("fastapi")
    print(f"hits: {hits}")
    assert all(isinstance(h, ScoredSession) for h in hits)
    assert hits[0].session_id == "a"
    assert hits[0].composite_score >= 0.0


def test_search_sessions_empty_query_returns_empty_list():
    """The public entry point never crashes on empty input."""
    assert search_sessions("") == []
    assert search_sessions("   ") == []


def test_build_full_uses_loaded_trajectories():
    """build_full calls load_from_stores for each metadata entry."""
    idx = SessionSearchIndex()

    # BM25 IDF behaves oddly on very small corpora; pad with a handful of
    # unrelated sessions so the "react" token carries real discriminating
    # weight.
    target = "sess-target"
    trajs = {target: [make_trajectory(target, [
        make_user_step("hi"),
        make_agent_step("react components are cool"),
    ])]}
    meta = [{"session_id": target, "first_message": "hi", "timestamp": None}]
    filler_text = [
        "postgres index optimization",
        "docker multi-stage build",
        "rust async tokio deadlock",
        "pytest fixture scope module",
        "kubernetes helm values yaml",
        "golang channel select default",
        "pytorch training loss plateau",
        "aws lambda cold start python",
    ]
    for i, text in enumerate(filler_text):
        sid = f"filler-{i}"
        trajs[sid] = [make_trajectory(sid, [make_user_step(text)])]
        meta.append({"session_id": sid, "first_message": text, "timestamp": None})

    def fake_list_all_metadata(_token):
        return meta

    def fake_load_from_stores(sid, _token):
        return trajs.get(sid)

    with patch(
        "vibelens.services.session.search.index.list_all_metadata", fake_list_all_metadata
    ), patch(
        "vibelens.services.session.search.index.load_from_stores", fake_load_from_stores
    ):
        idx.build_full(None)

    assert idx.has_full()
    hits = dict(idx.search_full("react"))
    print(f"react hits: {hits}")
    assert target in hits
    assert not any(sid.startswith("filler-") for sid in hits)


def test_invalidate_preserves_tier1_and_clears_tier2():
    """invalidate() drops full entries but keeps the metadata layer."""
    idx = build_index_from_entries([make_synthetic_entry("a", user_text="foo bar")])
    # Also inject a Tier-1 entry by hand.
    from vibelens.services.session.search.index import _SessionEntry
    idx._metadata_entries["a"] = _SessionEntry(  # noqa: SLF001
        session_id="a", session_id_lower="a", user_prompts="foo", agent_messages="", tool_calls=""
    )
    assert idx.has_full()
    idx.invalidate()
    assert not idx.has_full()
    # Metadata survived.
    assert idx.search_metadata("foo")


def _make_meta(sid: str, first_message: str = "") -> dict:
    """Minimal metadata-summary shape used by list_all_metadata callers."""
    return {"session_id": sid, "first_message": first_message, "timestamp": None}


def _filler_pair(prefix: str) -> tuple[list[dict], dict]:
    """Eight filler sessions so BM25 IDF is stable."""
    texts = [
        "postgres index optimization",
        "docker multi-stage build",
        "rust async tokio deadlock",
        "pytest fixture scope module",
        "kubernetes helm values yaml",
        "golang channel select default",
        "pytorch training loss plateau",
        "aws lambda cold start python",
    ]
    meta = []
    trajs: dict[str, list] = {}
    for i, text in enumerate(texts):
        sid = f"{prefix}-filler-{i}"
        meta.append(_make_meta(sid, text))
        trajs[sid] = [make_trajectory(sid, [make_user_step(text)])]
    return meta, trajs


def test_add_sessions_inserts_into_live_index():
    """add_sessions parses each new id, extracts, and makes it searchable."""
    idx = SessionSearchIndex()
    base_meta, base_trajs = _filler_pair("base")

    def list_meta_call_1(_token):
        return base_meta

    def load_stores(sid, _token):
        return base_trajs.get(sid) or new_trajs.get(sid)

    with patch(
        "vibelens.services.session.search.index.list_all_metadata", list_meta_call_1
    ), patch(
        "vibelens.services.session.search.index.load_from_stores", load_stores
    ):
        idx.build_full(None)

    assert idx.has_full()
    pre_sids = {sid for sid, _ in idx.search_full("postgres")}
    print(f"pre-add postgres: {pre_sids}")

    # Add two brand-new sessions.
    new_sid_a = "newly-uploaded-a"
    new_sid_b = "newly-uploaded-b"
    new_trajs = {
        new_sid_a: [make_trajectory(new_sid_a, [make_user_step("graphql dataloader n+1")])],
        new_sid_b: [make_trajectory(new_sid_b, [make_user_step("elixir phoenix liveview")])],
    }
    extended_meta = base_meta + [
        _make_meta(new_sid_a, "graphql dataloader"),
        _make_meta(new_sid_b, "elixir phoenix"),
    ]

    def list_meta_call_2(_token):
        return extended_meta

    with patch(
        "vibelens.services.session.search.index.list_all_metadata", list_meta_call_2
    ), patch(
        "vibelens.services.session.search.index.load_from_stores", load_stores
    ):
        idx.add_sessions([new_sid_a, new_sid_b], None)

    post_graphql = {sid for sid, _ in idx.search_full("graphql")}
    post_elixir = {sid for sid, _ in idx.search_full("phoenix")}
    print(f"post-add graphql={post_graphql} phoenix={post_elixir}")
    assert new_sid_a in post_graphql
    assert new_sid_b in post_elixir
    # Old entries survive the rebuild.
    assert idx.search_full("postgres")


def test_refresh_adds_new_and_removes_stale():
    """refresh() diffs metadata: adds new sessions, drops missing ones."""
    idx = SessionSearchIndex()
    base_meta, base_trajs = _filler_pair("base")

    def load_stores(sid, _token):
        return base_trajs.get(sid) or new_trajs.get(sid)

    with patch(
        "vibelens.services.session.search.index.list_all_metadata", lambda _t: base_meta
    ), patch(
        "vibelens.services.session.search.index.load_from_stores", load_stores
    ):
        idx.build_full(None)

    # Simulate the on-disk state changing: one of the base sessions is gone,
    # and two new ones have appeared.
    dropped_sid = base_meta[0]["session_id"]
    new_sid_a = "refresh-new-a"
    new_sid_b = "refresh-new-b"
    new_trajs = {
        new_sid_a: [make_trajectory(new_sid_a, [make_user_step("svelte kit routing")])],
        new_sid_b: [make_trajectory(new_sid_b, [make_user_step("prisma schema migrate")])],
    }
    refreshed_meta = [m for m in base_meta if m["session_id"] != dropped_sid] + [
        _make_meta(new_sid_a, "svelte kit"),
        _make_meta(new_sid_b, "prisma"),
    ]

    with patch(
        "vibelens.services.session.search.index.list_all_metadata", lambda _t: refreshed_meta
    ), patch(
        "vibelens.services.session.search.index.load_from_stores", load_stores
    ):
        idx.refresh(None)

    full_sids = set(idx._full_entries.keys())  # noqa: SLF001 -- test inspection
    print(f"full_sids after refresh: {full_sids}")
    assert dropped_sid not in full_sids
    assert new_sid_a in full_sids
    assert new_sid_b in full_sids
    # New sessions are searchable.
    assert new_sid_a in {sid for sid, _ in idx.search_full("svelte")}


def test_refresh_is_noop_when_nothing_changed():
    """refresh() with identical metadata leaves the index alone."""
    idx = SessionSearchIndex()
    base_meta, base_trajs = _filler_pair("noop")

    def load_stores(sid, _token):
        return base_trajs.get(sid)

    with patch(
        "vibelens.services.session.search.index.list_all_metadata", lambda _t: base_meta
    ), patch(
        "vibelens.services.session.search.index.load_from_stores", load_stores
    ):
        idx.build_full(None)
        before = dict(idx._full_entries)  # noqa: SLF001 -- test inspection
        idx.refresh(None)
        after = dict(idx._full_entries)  # noqa: SLF001 -- test inspection

    # Same set of session_ids, same objects (no rebuild churn).
    assert set(before.keys()) == set(after.keys())


def test_build_search_index_populates_tier1_only():
    """build_search_index (public wrapper) populates only Tier 1."""
    from vibelens.services.session.search import build_search_index, get_session_index

    meta = [_make_meta("tier1-a", "hi there"), _make_meta("tier1-b", "deploy staging")]
    with patch(
        "vibelens.services.session.search.index.list_all_metadata", lambda _t: meta
    ):
        build_search_index(None)

    idx = get_session_index()
    assert not idx.has_full(), "Tier-2 must not be touched by build_search_index"
    assert idx.search_metadata("staging"), "Tier-1 metadata match should work"
    # Reset so we don't leak state into other tests that use the singleton.
    idx.invalidate()
    idx._metadata_entries.clear()  # noqa: SLF001 -- test cleanup

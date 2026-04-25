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


def test_phrase_bonus_full_query():
    """Verbatim substring in user_prompts ranks above token-only matches."""
    entries = [
        # Source: contains the exact verbatim phrase in user_prompts.
        make_synthetic_entry(
            "src-1",
            user_text="Read docs/paper-nips and explore the codebase",
            offset_days=1,
        ),
        # Distractors share tokens but not the verbatim phrase.
        make_synthetic_entry(
            "dst-2",
            user_text="codebase exploration tips and reading documentation",
            offset_days=2,
        ),
        make_synthetic_entry(
            "dst-3",
            user_text="paper review on coding agents",
            agent_text="explore the related work",
            offset_days=3,
        ),
        make_synthetic_entry("pad-4", user_text="unrelated", offset_days=4),
        make_synthetic_entry("pad-5", user_text="more unrelated", offset_days=5),
    ]
    idx = build_index_from_entries(entries)
    out = idx.search_full("Read docs/paper-nips and explore the codebase")
    sids = [sid for sid, _ in out]
    print(f"phrase-bonus sids: {sids}")
    print(f"phrase-bonus full: {out}")
    assert sids[0] == "src-1"
    # The phrase-matching doc's final score should be at least 2x the
    # next doc's, reflecting the (1 + 1.5) user_prompts bonus.
    if len(out) > 1:
        assert out[0][1] >= 2.0 * out[1][1]


def test_phrase_bonus_mid_typing_fallback():
    """An incomplete trailing word still earns a bonus for the truncated phrase."""
    entries = [
        make_synthetic_entry(
            "src-1",
            user_text="Read docs/paper-nips and explore the codebase",
            offset_days=1,
        ),
        make_synthetic_entry(
            "dst-2",
            user_text="codebase reading and paper exploration",
            offset_days=2,
        ),
        make_synthetic_entry("pad-3", user_text="unrelated", offset_days=3),
        make_synthetic_entry("pad-4", user_text="still unrelated", offset_days=4),
    ]
    idx = build_index_from_entries(entries)
    # User stopped mid-word: "explc" doesn't appear in any doc.
    # The full-query phrase fails; truncation to "Read docs/paper-nips and"
    # still matches src-1.
    out = idx.search_full("Read docs/paper-nips and explc")
    sids = [sid for sid, _ in out]
    print(f"mid-typing sids: {sids}")
    print(f"mid-typing scores: {out}")
    assert sids[0] == "src-1"


def test_phrase_bonus_fallback_gate_skips_single_word():
    """A two-word query whose truncated form is single-word gets no phrase bonus.

    The mid-typing BM25 fallback retries with the truncated query so the
    user sees results during typing. The phrase fallback gate, however,
    must NOT fire on a single-word truncation — otherwise any doc
    containing that word gets a spurious bonus.
    """
    # Padding ensures BM25 IDF for "implement" is non-zero — without
    # enough non-matching docs, IDF degenerates and the score is zero.
    entries = [
        # Strong match for "implement" with one occurrence.
        make_synthetic_entry(
            "src-1",
            user_text="implement the following plan in detail",
            offset_days=1,
        ),
        # Trap doc: "implement" appears many times, so BM25 TF would put
        # it at the top under a single-token query. If the phrase
        # fallback gate failed (single-word fallback fired), trap-2 would
        # also receive a bonus and stay on top.
        make_synthetic_entry(
            "trap-2",
            user_text="implement implement implement everywhere",
            offset_days=2,
        ),
    ]
    for i in range(8):
        entries.append(
            make_synthetic_entry(
                f"pad-{i:02d}",
                user_text=f"unrelated padding content number {i}",
                offset_days=10 + i,
            )
        )
    idx = build_index_from_entries(entries)
    # Query "implement pl" — initial BM25 call fails (no doc has "pl").
    # Mid-typing BM25 fallback retries with "implement" and matches.
    # Phrase fallback gate must skip single-word truncation, so neither
    # src-1 nor trap-2 receives a phrase bonus.
    out = idx.search_full("implement pl")
    print(f"fallback-gate full: {out}")
    sids = [sid for sid, _ in out]
    assert "src-1" in sids
    # If the gate worked, the ordering reflects raw BM25 (no bonus).
    # We don't assert an exact order — the point is that BOTH docs appear
    # with no gigantic 2.5x multiplier on either, i.e. final scores are
    # all in the BM25 [0, 1] range.
    for _, score in out:
        assert score <= 1.5, (
            f"final score {score} suggests phrase bonus fired despite "
            f"single-word truncation gate"
        )


def test_composite_floor_trims_long_tail():
    """Tier-0 docs below FLOOR_FRAC * top are dropped; tier-0 top is kept."""
    # Build a corpus where one doc is a strong match and many docs are weak
    # token co-occurrences — exactly the long-tail case the floor exists for.
    entries = [
        # Strong match: token "friction" occurs in user_prompts.
        make_synthetic_entry(
            "strong-1",
            user_text="friction friction friction friction friction friction",
            offset_days=1,
        ),
    ]
    # 12 weak matches: token mentioned once in tool_calls (low weight field).
    for i in range(12):
        entries.append(
            make_synthetic_entry(
                f"weak-{i:02d}",
                user_text="completely unrelated content",
                tool_text="friction",
                offset_days=10 + i,
            )
        )
    idx = build_index_from_entries(entries)
    out = idx.search_full("friction")
    sids = [sid for sid, _ in out]
    print(f"floor sids ({len(sids)}): {sids}")
    print(f"floor scores: {out}")
    assert sids[0] == "strong-1"
    # Floor must trim at least some weak matches.
    assert len(sids) < 13, f"floor failed to trim long tail: {len(sids)} hits"


def test_composite_floor_keeps_solo_match():
    """The single highest tier-0 doc survives even when it would be 'below' itself."""
    # A solitary tier-0 match must not be filtered out — there's nothing to
    # rank it relative to, so the top-1 guarantee keeps it.
    entries = [
        make_synthetic_entry("solo-1", user_text="uniqueterm", offset_days=1),
        make_synthetic_entry("pad-2", user_text="unrelated", offset_days=2),
        make_synthetic_entry("pad-3", user_text="still unrelated", offset_days=3),
        make_synthetic_entry("pad-4", user_text="more unrelated", offset_days=4),
    ]
    idx = build_index_from_entries(entries)
    out = idx.search_full("uniqueterm")
    sids = [sid for sid, _ in out]
    print(f"solo result: {out}")
    assert sids == ["solo-1"]


def test_composite_floor_exempts_sid_prefix_tier():
    """Tier-1 (sid prefix) docs survive the floor even with weak BM25 composite.

    The floor is composite-relative on tier-0 docs only; sid matches are
    high-confidence promotions and shouldn't be filtered by BM25 strength.
    """
    entries = [
        # Tier-1 candidate: sid leading segment matches the query, but
        # there's no content match.
        make_synthetic_entry("zzz-1", user_text="completely unrelated", offset_days=1),
        # Tier-0 strong match on a token that happens to exist.
        make_synthetic_entry(
            "tier0-strong",
            user_text="zzz zzz zzz zzz zzz zzz",
            offset_days=2,
        ),
    ]
    # Tier-0 weak matches.
    for i in range(5):
        entries.append(
            make_synthetic_entry(
                f"tier0-weak-{i}",
                user_text="zzz padding text",
                offset_days=10 + i,
            )
        )
    idx = build_index_from_entries(entries)
    out = idx.search_full("zzz")
    sids = [sid for sid, _ in out]
    print(f"sid-tier-exempt sids: {sids}")
    # zzz-1 has tier-1 (leading segment "zzz" matches the query) and must
    # appear in the result regardless of its composite.
    assert "zzz-1" in sids


def test_soft_and_admits_one_missing_token():
    """A doc missing exactly one of N>=3 query tokens still ranks #1 if it has the phrase.

    Real-world case: user types "date frontend: beautify the friction"
    while the session text is "Update frontend: beautify the friction".
    Strict AND fails on "date", but soft-AND admits the doc to the phrase
    candidate set and the leading-truncation phrase fallback rescues it.
    """
    entries = [
        # Source: matches 4 of 5 tokens (missing "date"), has the phrase
        # "frontend beautify friction" verbatim in user_prompts.
        make_synthetic_entry(
            "src-1",
            user_text="Update frontend: beautify the friction copy all button",
            offset_days=1,
        ),
        # Trap: contains "date" but doesn't have the phrase. Strict AND
        # admits this doc; soft-AND admits both. Phrase test must reject
        # the trap (no contiguous phrase substring) and rescue src-1.
        make_synthetic_entry(
            "trap-2",
            user_text="date frontend friction beautify scattered tokens",
            offset_days=2,
        ),
    ]
    for i in range(8):
        entries.append(
            make_synthetic_entry(
                f"pad-{i:02d}",
                user_text=f"unrelated padding content number {i}",
                offset_days=10 + i,
            )
        )
    idx = build_index_from_entries(entries)
    out = idx.search_full("date frontend: beautify the friction")
    sids = [sid for sid, _ in out]
    print(f"soft-AND sids: {sids}")
    print(f"soft-AND scores: {out[:3]}")
    assert sids[0] == "src-1", (
        f"expected src-1 first via leading-phrase rescue, got {sids[:3]}"
    )


def test_phrase_bonus_leading_truncation():
    """Phrase fallback drops the FIRST word, not just the last.

    Distinguishes the leading-truncation path from the trailing-truncation
    path. Setup: source has "<rest of phrase>" but not "<first word>".
    Trailing truncation alone wouldn't help — both ends would still
    contain the wrong first word.
    """
    entries = [
        # Source has "frontend beautify friction" but not "wrongword".
        make_synthetic_entry(
            "src-1",
            user_text="frontend beautify friction in the app today",
            offset_days=1,
        ),
        # Padding so BM25 IDF stays meaningful.
        make_synthetic_entry("pad-2", user_text="unrelated content", offset_days=2),
        make_synthetic_entry("pad-3", user_text="more unrelated", offset_days=3),
    ]
    for i in range(6):
        entries.append(
            make_synthetic_entry(
                f"noise-{i:02d}",
                user_text=f"random padding text {i}",
                offset_days=10 + i,
            )
        )
    idx = build_index_from_entries(entries)
    # The leading "wrongword" is not in any doc, so:
    # 1. Strict AND fails (no doc has "wrongword").
    # 2. Mid-typing trailing fallback retries "wrongword frontend beautify"
    #    — still fails (no doc has "wrongword").
    # 3. Phrase full-query test fails (no doc has full string).
    # 4. Phrase trailing-truncation "wrongword frontend beautify the" fails.
    # 5. Phrase leading-truncation "frontend beautify friction" matches src-1.
    out = idx.search_full("wrongword frontend beautify friction")
    sids = [sid for sid, _ in out]
    print(f"leading-truncation sids: {sids}")
    print(f"leading-truncation scores: {out[:3]}")
    assert "src-1" in sids
    assert sids[0] == "src-1"


def test_recency_decay_demotes_older_among_equal_content():
    """When two docs have identical content, the more recent ranks first.

    Same intent as test_recency_tiebreaker_within_same_score but exercises
    the recency *multiplier* (not just the lexsort tiebreaker), so it
    holds even when scores would otherwise be exactly equal.
    """
    entries = [
        make_synthetic_entry("aaa-old", user_text="distinctive memory leak debug", offset_days=0),
        make_synthetic_entry("aaa-new", user_text="distinctive memory leak debug", offset_days=30),
        make_synthetic_entry("pad-1", user_text="unrelated", offset_days=1),
        make_synthetic_entry("pad-2", user_text="more unrelated", offset_days=2),
        make_synthetic_entry("pad-3", user_text="still unrelated", offset_days=3),
    ]
    idx = build_index_from_entries(entries)
    out = idx.search_full("distinctive memory leak")
    sids = [sid for sid, _ in out[:2]]
    print(f"recency-decay top2: {sids}, scores: {out[:2]}")
    assert sids == ["aaa-new", "aaa-old"]


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

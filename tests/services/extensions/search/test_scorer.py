"""Scorer tests: mode weights, missing-input redistribution, tiebreakers."""

from tests.services.extensions.search._fixtures import make_item
from vibelens.services.extensions.search.index import CatalogSearchIndex
from vibelens.services.extensions.search.query import SortMode
from vibelens.services.extensions.search.scorer import (
    WEIGHTS_BY_MODE,
    _effective_weights,
    rank_extensions,
)


def test_weight_rows_sum_to_one():
    """Every mode's weight row is a valid probability distribution."""
    for mode, weights in WEIGHTS_BY_MODE.items():
        total = sum(weights.values())
        print(f"{mode}: {total}")
        assert abs(total - 1.0) < 1e-9


def test_effective_weights_redistributes_empty_text():
    """Zeroing `text` rescales the rest to sum to 1."""
    present = {"profile", "quality", "popularity", "recency"}  # no "text"
    weights = _effective_weights(WEIGHTS_BY_MODE[SortMode.PERSONALIZED], present)
    print(f"weights={weights}")
    assert weights["text"] == 0.0
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    # profile was 0.5 of 0.80, should now be 0.5/0.8 = 0.625
    assert abs(weights["profile"] - 0.625) < 1e-9


def test_effective_weights_redistributes_missing_profile():
    """Zeroing `profile` rescales the rest."""
    present = {"text", "quality", "popularity", "recency"}  # no "profile"
    weights = _effective_weights(WEIGHTS_BY_MODE[SortMode.DEFAULT], present)
    print(f"weights={weights}")
    assert weights["profile"] == 0.0
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_name_sort_is_alphabetical():
    """SortMode.NAME returns pure alphabetical order regardless of scores."""
    items = [
        make_item("zebra", quality=100.0),
        make_item("alpha", quality=10.0),
        make_item("mango", quality=50.0),
    ]
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "", [], SortMode.NAME)
    names = [r.extension_id.split("/")[-1] for r in ranked]
    print(f"sorted names: {names}")
    assert names == ["alpha", "mango", "zebra"]


def test_name_sort_with_query_filters_and_still_alphabetizes():
    """SortMode.NAME + search text: filter by match, still sort A→Z.

    Regression for the bug where NAME mode produced no results when a
    query was typed — it was skipping text scoring entirely, and the
    downstream filter dropped everything.
    """
    items = [
        make_item("alpha-paper", description="paper writing", topics=["writing"]),
        make_item("bravo-unrelated", description="database", topics=["sql"]),
        make_item("zebra-paper", description="academic paper", topics=["writing"]),
        make_item("charlie-other", description="misc", topics=["other"]),
        # Fillers so BM25 IDF is well-behaved.
        make_item("delta-filler", description="filler one", topics=["filler"]),
        make_item("echo-filler", description="filler two", topics=["filler"]),
        make_item("foxtrot-filler", description="filler three", topics=["filler"]),
        make_item("golf-filler", description="filler four", topics=["filler"]),
        make_item("hotel-filler", description="filler five", topics=["filler"]),
        make_item("india-filler", description="filler six", topics=["filler"]),
    ]
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "paper", [], SortMode.NAME)
    names = [r.extension_id.split("/")[-1] for r in ranked]
    print(f"NAME + 'paper': {names}")
    # Two items mention paper; they must both appear, in alphabetical order.
    assert "alpha-paper" in names
    assert "zebra-paper" in names
    assert names.index("alpha-paper") < names.index("zebra-paper")
    # An unrelated item must not appear.
    assert "bravo-unrelated" not in names


def test_quality_sort_respects_quality_score():
    """SortMode.QUALITY puts highest quality_score first when no text."""
    items = [
        make_item("low", quality=10.0),
        make_item("high", quality=90.0),
        make_item("mid", quality=50.0),
    ]
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "", [], SortMode.QUALITY)
    names = [r.extension_id.split("/")[-1] for r in ranked]
    print(f"quality order: {names}")
    assert names == ["high", "mid", "low"]


def test_text_query_ranks_name_match_first():
    """A query matching an item's name outranks description-only matches."""
    items = [
        make_item("testgen", description="generate tests"),
        make_item("other", description="mentions testgen but not in name"),
        make_item("unrelated", description="other stuff"),
    ]
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "testgen", [], SortMode.DEFAULT)
    names = [r.extension_id.split("/")[-1] for r in ranked]
    print(f"text-query order: {names}")
    assert names[0] == "testgen"


def test_profile_signal_boosts_matching_items():
    """When profile keywords match an item, it ranks higher.

    Uses an 11-item corpus so BM25 IDF is well-behaved. Tiny corpora
    (2-3 items) can invert rankings because Okapi IDF goes negative
    for terms present in most documents — real catalog sizes (28K
    items) do not hit this.
    """
    items = [
        make_item("react-helper", description="react component patterns"),
        make_item("python-helper", description="python scripting"),
        make_item("java-helper", description="java enterprise"),
        make_item("rust-helper", description="rust systems"),
        make_item("go-helper", description="go concurrency"),
        make_item("bash-helper", description="bash scripts"),
        make_item("sql-helper", description="sql queries"),
        make_item("api-helper", description="api design"),
        make_item("data-helper", description="data pipelines"),
        make_item("ml-helper", description="machine learning"),
        make_item("ui-helper", description="ui design"),
    ]
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "", ["react", "component"], SortMode.PERSONALIZED)
    top2 = [r.extension_id.split("/")[-1] for r in ranked[:2]]
    print(f"profile-boost top2: {top2}")
    assert "react-helper" in top2


def test_ranking_is_deterministic_on_ties():
    """Two identical items sort deterministically (by name asc)."""
    items = [
        make_item("bravo", quality=50.0, popularity=0.5, updated_at="2026-04-01T00:00:00Z"),
        make_item("alpha", quality=50.0, popularity=0.5, updated_at="2026-04-01T00:00:00Z"),
    ]
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "", [], SortMode.DEFAULT)
    names = [r.extension_id.split("/")[-1] for r in ranked]
    print(f"tie order: {names}")
    assert names == ["alpha", "bravo"]


def test_composite_includes_all_nonzero_weight_signals():
    """Breakdown keys include every signal the mode weights."""
    items = [make_item("x", description="y", quality=60, popularity=0.4)]
    idx = CatalogSearchIndex(items)
    ranked = rank_extensions(idx, "x", [], SortMode.DEFAULT)
    print(f"breakdown: {ranked[0].signal_breakdown}")
    for key in ("text", "profile", "quality", "popularity", "recency"):
        assert key in ranked[0].signal_breakdown


def test_empty_catalog_returns_empty():
    """Zero-item index returns an empty ranking."""
    idx = CatalogSearchIndex([])
    assert rank_extensions(idx, "anything", [], SortMode.DEFAULT) == []

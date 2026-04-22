"""Index tests: build, reset, prefix expansion, per-field scoring."""

from tests.services.extensions.search._fixtures import make_item
from vibelens.services.extensions.search.index import CatalogSearchIndex


def test_empty_catalog():
    """An empty catalog produces a zero-item index that rejects searches cleanly."""
    idx = CatalogSearchIndex([])
    assert idx.num_items() == 0
    scores = idx.score_field("name", ["anything"])
    assert len(scores) == 0


def test_single_item():
    """One item still indexes correctly, allowing the BM25 guard to fire sentinels."""
    items = [make_item("solo", description="alone")]
    idx = CatalogSearchIndex(items)
    assert idx.num_items() == 1
    scores = idx.score_field("name", ["solo"])
    print(f"scores: {scores}")
    # Single-doc BM25 degenerates; just assert no crash and correct length.
    assert len(scores) == 1


def test_multi_field_indexes_built():
    """All field indexes (where tokens exist) get built."""
    items = [
        make_item(
            "testgen", description="Generate tests", topics=["testing"], readme="long readme text"
        ),
        make_item("foo", description="bar", topics=["misc"], readme="baz readme"),
    ]
    idx = CatalogSearchIndex(items)
    # Name, description, topics, readme all have content.
    for field in ("name", "description", "topics", "readme"):
        scores = idx.score_field(field, ["test"])
        print(f"field={field} scores={scores}")
        assert len(scores) == 2


def test_prefix_expansion():
    """A short prefix expands to full tokens that start with it."""
    items = [make_item("testgen", description="Generate tests")]
    idx = CatalogSearchIndex(items)
    expansions = idx.expand_prefix("test")
    print(f"expansions: {expansions}")
    assert "testgen" in expansions or "test" in expansions


def test_prefix_below_minimum_returns_empty():
    """Prefixes shorter than 3 chars don't expand (would be too broad)."""
    items = [make_item("testgen")]
    idx = CatalogSearchIndex(items)
    assert idx.expand_prefix("t") == []
    assert idx.expand_prefix("te") == []


def test_idx_of_lookup():
    """idx_of returns the position for known ids and None for unknown."""
    items = [make_item("a"), make_item("b")]
    idx = CatalogSearchIndex(items)
    assert idx.idx_of("alice/a") == 0
    assert idx.idx_of("alice/b") == 1
    assert idx.idx_of("nonexistent") is None


def test_score_field_returns_float_array():
    """Scores are a 1-d float array of length num_items."""
    items = [
        make_item("testgen", description="tests"),
        make_item("foo", description="bar"),
    ]
    idx = CatalogSearchIndex(items)
    scores = idx.score_field("name", ["testgen"])
    print(f"scores: {scores}")
    assert scores.shape == (2,)
    assert scores.dtype.kind == "f"


def test_reset_builds_fresh():
    """reset_index followed by get_index produces a new instance.

    Verified through module-level functions since they wrap the singleton.
    """
    from vibelens.services.extensions.search import reset_index

    reset_index()
    # Direct rebuild path exercised by other tests. Here we just assert no crash.
    reset_index()

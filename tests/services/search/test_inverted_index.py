"""Direct unit tests for the generic InvertedIndex.

Separate from the domain-specific extension and session tests so a
breaking change to the core shows up here first with a clear failure.
"""

import numpy as np

from vibelens.services.search import InvertedIndex, tokenize


def _corpus() -> list[dict[str, list[str]]]:
    """Small but non-trivial per-field tokenized corpus.

    Three documents across two fields. Kept tiny so behavior is
    auditable by eye; BM25 IDF on three docs is still meaningful
    because the term frequencies differ.
    """
    return [
        {
            "title": tokenize("python testing fixtures"),
            "body": tokenize("pytest makes testing easy"),
        },
        {
            "title": tokenize("react components"),
            "body": tokenize("useState hook for form state"),
        },
        {
            "title": tokenize("rust tokio async"),
            "body": tokenize("spawn with tokio spawn join handle"),
        },
    ]


def _weights() -> dict[str, float]:
    return {"title": 3.0, "body": 1.0}


def test_num_docs_and_field_weights_expose_build_state():
    """Constructor stores doc count and a copy of the weight dict."""
    idx = InvertedIndex(_corpus(), _weights())
    print(f"n={idx.num_docs} weights={idx.field_weights}")
    assert idx.num_docs == 3
    assert idx.field_weights == _weights()
    # ``field_weights`` must return a copy, not the internal dict.
    idx.field_weights["title"] = 99.0
    assert idx.field_weights["title"] == 3.0


def test_empty_corpus_stays_consistent():
    """Zero docs is a valid (degenerate) state, not a crash."""
    idx = InvertedIndex([], _weights())
    assert idx.num_docs == 0
    assert idx.score_field("title", ["python"]).shape == (0,)
    assert idx.per_field_has_token("title", "python").shape == (0,)
    assert idx.posting_indices("title", "python").shape == (0,)
    assert idx.expand_prefix("pyt") == []
    assert idx.token_in_any_vocab("python") is False


def test_score_field_returns_positive_scores_for_matching_tokens():
    """BM25 scores are non-negative and assign more weight to rarer terms."""
    idx = InvertedIndex(_corpus(), _weights())
    # 'tokio' appears only in doc 2 -> high IDF; it should dominate.
    scores = idx.score_field("title", ["tokio"])
    print(f"tokio title scores: {scores.tolist()}")
    assert scores.shape == (3,)
    assert scores[2] > scores[0]
    assert scores[2] > scores[1]


def test_score_field_unknown_token_scores_zero_or_lt_zero():
    """Unknown tokens produce zero contribution (BM25 skips the term)."""
    idx = InvertedIndex(_corpus(), _weights())
    scores = idx.score_field("title", ["xyzqqqq"])
    print(f"unknown token scores: {scores.tolist()}")
    # Either zero (not in vocab) or uniformly same value; never picks one doc.
    assert scores.shape == (3,)
    assert len(set(scores.tolist())) == 1


def test_score_field_zero_weight_field_is_unindexed():
    """Fields with weight=0 at build time aren't scored even if queried."""
    weights = {"title": 1.0, "body": 0.0}
    idx = InvertedIndex(_corpus(), weights)
    body_scores = idx.score_field("body", ["pytest"])
    print(f"body scores (zero-weight): {body_scores.tolist()}")
    # Unbuilt field -> all zeros.
    assert np.all(body_scores == 0)


def test_per_field_has_token_and_posting_indices_agree():
    """The boolean mask and the int32 index array describe the same docs."""
    idx = InvertedIndex(_corpus(), _weights())
    mask = idx.per_field_has_token("body", "tokio")
    posting = idx.posting_indices("body", "tokio")
    print(f"mask={mask.tolist()} posting={posting.tolist()}")
    # The mask has True exactly at the indices the posting lists.
    assert mask.sum() == len(posting)
    for i in posting:
        assert mask[int(i)]


def test_per_field_has_token_for_missing_token_is_all_false():
    """A token absent from the field returns an all-False mask of length n."""
    idx = InvertedIndex(_corpus(), _weights())
    mask = idx.per_field_has_token("title", "graphql")
    assert mask.shape == (3,)
    assert not mask.any()


def test_expand_prefix_returns_matching_tokens():
    """Prefix expansion finds every indexed token starting with the prefix."""
    idx = InvertedIndex(_corpus(), _weights())
    expansions = set(idx.expand_prefix("tok"))
    print(f"tok expansions: {expansions}")
    # ``tokio`` is in the vocab (via the title of doc 2).
    assert "tokio" in expansions


def test_expand_prefix_respects_minimum_length():
    """Very short prefixes (<3 chars) return empty to avoid combinatorial blowups."""
    idx = InvertedIndex(_corpus(), _weights())
    assert idx.expand_prefix("t") == []
    assert idx.expand_prefix("to") == []
    assert idx.expand_prefix("tok") != []  # boundary hit


def test_token_in_any_vocab_true_for_indexed_tokens():
    """``token_in_any_vocab`` answers the 'should we prefix-expand?' question."""
    idx = InvertedIndex(_corpus(), _weights())
    assert idx.token_in_any_vocab("tokio") is True
    assert idx.token_in_any_vocab("pytest") is True
    assert idx.token_in_any_vocab("xyzqqqq") is False

"""Direct unit tests for the shared ranking helpers.

Exercise ``score_text_query``, ``and_match_mask``, ``or_match_mask``,
``split_required_and_prefix``, and ``effective_weights`` without going
through a domain wrapper.
"""

import numpy as np

from vibelens.services.search import (
    InvertedIndex,
    and_match_mask,
    effective_weights,
    or_match_mask,
    score_text_query,
    split_required_and_prefix,
    tokenize,
)


def _three_doc_index() -> InvertedIndex:
    corpus = [
        {"title": tokenize("python testing"), "body": tokenize("pytest fixtures module")},
        {"title": tokenize("react state"), "body": tokenize("useState hook form")},
        {"title": tokenize("rust tokio"), "body": tokenize("spawn async join handle")},
    ]
    return InvertedIndex(corpus, {"title": 3.0, "body": 1.0})


def test_and_match_mask_requires_every_token():
    """An item matches only when every token appears in at least one field."""
    idx = _three_doc_index()
    mask = and_match_mask(idx, ["pytest", "fixture"], n=3)
    print(f"pytest+fixture mask: {mask.tolist()}")
    # Only doc 0 has both (fixtures -> fixture after stemming).
    assert mask.tolist() == [True, False, False]


def test_and_match_mask_all_absent_returns_all_false():
    """If one token is absent from every doc, the whole mask is False."""
    idx = _three_doc_index()
    mask = and_match_mask(idx, ["python", "graphql"], n=3)
    assert not mask.any()


def test_or_match_mask_is_true_if_any_token_hits():
    """Any token present anywhere in any field flips the mask."""
    idx = _three_doc_index()
    mask = or_match_mask(idx, ["pytest", "tokio"], n=3)
    print(f"pytest|tokio mask: {mask.tolist()}")
    # Doc 0 hits pytest; doc 2 hits tokio; doc 1 has neither.
    assert mask.tolist() == [True, False, True]


def test_split_required_and_prefix_keeps_vocab_tokens_required():
    """If the last token is a known vocab term, no prefix-expansion happens."""
    idx = _three_doc_index()
    req, opt = split_required_and_prefix(
        idx, "python pytest", ["python", "pytest"], expand_last_as_prefix=True
    )
    print(f"required={req} optional={opt}")
    assert req == ["python", "pytest"]
    assert opt == []


def test_split_required_and_prefix_expands_unknown_last_token():
    """An unknown last token gets prefix-expanded into OR alternatives."""
    idx = _three_doc_index()
    req, opt = split_required_and_prefix(
        idx, "python tok", ["python", "tok"], expand_last_as_prefix=True
    )
    print(f"required={req} optional={opt}")
    # 'tok' isn't in any vocab, so it becomes optional prefix expansions.
    assert req == ["python"]
    assert "tokio" in opt


def test_split_required_and_prefix_trailing_space_means_finished_typing():
    """Trailing whitespace signals 'token finished'; no prefix expansion."""
    idx = _three_doc_index()
    req, opt = split_required_and_prefix(
        idx, "python tok ", ["python", "tok"], expand_last_as_prefix=True
    )
    assert req == ["python", "tok"]
    assert opt == []


def test_split_required_and_prefix_no_expansion_when_flag_false():
    """``expand_last_as_prefix=False`` short-circuits immediately."""
    idx = _three_doc_index()
    req, opt = split_required_and_prefix(
        idx, "python tok", ["python", "tok"], expand_last_as_prefix=False
    )
    assert req == ["python", "tok"]
    assert opt == []


def test_score_text_query_returns_zero_when_empty_or_no_match():
    """No tokens / no matches -> all zeros of length ``num_docs``."""
    idx = _three_doc_index()
    assert np.all(score_text_query(idx, "", expand_last_as_prefix=True) == 0)
    assert np.all(score_text_query(idx, "xyzqqqq", expand_last_as_prefix=True) == 0)


def test_score_text_query_is_normalized_to_unit_max():
    """The returned scores are normalized so the best-matching doc is 1.0."""
    idx = _three_doc_index()
    scores = score_text_query(idx, "pytest fixture", expand_last_as_prefix=True)
    print(f"scores: {scores.tolist()}")
    assert float(scores.max()) == 1.0
    # Non-matching docs are zeroed by the AND mask.
    assert float(scores.min()) == 0.0


def test_score_text_query_respects_and_semantics_even_with_prefix():
    """Prefix-expanded tokens are OR'd but required tokens still AND-gate.

    Setup: ``python`` is a known token in doc 0. ``zzzunk`` is not a
    prefix of anything in the vocab, so prefix expansion yields nothing
    and ``zzzunk`` remains a required token that no doc satisfies.
    """
    idx = _three_doc_index()
    scores = score_text_query(idx, "python zzzunk", expand_last_as_prefix=True)
    print(f"python zzzunk scores: {scores.tolist()}")
    assert np.all(scores == 0)


def test_score_text_query_prefix_expansion_finds_partial_typing():
    """An unknown last token with a valid prefix gets expanded and contributes OR."""
    idx = _three_doc_index()
    # 'tok' is not a whole-word vocab term but expands to 'tokio'.
    scores = score_text_query(idx, "tok", expand_last_as_prefix=True)
    print(f"tok prefix scores: {scores.tolist()}")
    # Doc 2 ('rust tokio async') must be the winner.
    assert float(scores[2]) == 1.0
    assert float(scores[0]) == 0.0
    assert float(scores[1]) == 0.0


def test_effective_weights_renormalizes_when_present_signals_shrink():
    """Missing signals get zeroed and the rest scale to sum 1.0."""
    mode = {"text": 0.5, "profile": 0.3, "quality": 0.2}
    out = effective_weights(mode, present_signals={"text", "quality"})
    print(f"effective: {out}")
    assert out["profile"] == 0.0
    assert abs(sum(out.values()) - 1.0) < 1e-9
    # text was 0.5 / (0.5 + 0.2) = 0.714...
    assert abs(out["text"] - 0.5 / 0.7) < 1e-9


def test_effective_weights_no_filter_keeps_input_normalized():
    """``present_signals=None`` leaves each weight alone, just normalizes."""
    mode = {"a": 1.0, "b": 3.0}
    out = effective_weights(mode, present_signals=None)
    print(f"no-filter: {out}")
    assert abs(sum(out.values()) - 1.0) < 1e-9
    assert abs(out["a"] - 0.25) < 1e-9
    assert abs(out["b"] - 0.75) < 1e-9


def test_effective_weights_all_zero_falls_back_to_uniform():
    """If every signal is absent, degrade to a uniform distribution."""
    mode = {"a": 0.0, "b": 0.0}
    out = effective_weights(mode, present_signals=set())
    assert out == {"a": 0.5, "b": 0.5}

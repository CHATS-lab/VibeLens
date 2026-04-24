"""Tests for the recommendation engine orchestrator."""

import inspect

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import AgentExtensionItem
from vibelens.services.recommendation.engine import (
    RATIONALE_MAX_RESULTS,
    RATIONALE_MAX_RESULTS_LIMIT,
    RATIONALE_MIN_RELEVANCE,
    SCORING_TOP_K,
    _build_rationale_candidates,
)


def _mock_item(*, name: str, description: str | None) -> AgentExtensionItem:
    return AgentExtensionItem(
        extension_id=f"test:{name}",
        extension_type=AgentExtensionType.SKILL,
        name=name,
        description=description,
        source_url=f"https://github.com/acme/{name}/tree/main",
        repo_full_name=f"acme/{name}",
        discovery_source="seed",
        topics=[],
        quality_score=70.0,
        popularity=0.5,
        stars=10,
        forks=0,
    )


def test_engine_constants():
    """Engine constants are defined with expected values."""
    assert SCORING_TOP_K == 100
    assert RATIONALE_MAX_RESULTS == 15
    assert RATIONALE_MAX_RESULTS_LIMIT == 50
    assert RATIONALE_MIN_RELEVANCE == 0.6


def test_engine_importable():
    """Engine entry points are importable."""
    from vibelens.services.recommendation.engine import (
        analyze_recommendation,
        estimate_recommendation,
    )

    assert callable(analyze_recommendation)
    assert callable(estimate_recommendation)


def test_engine_exports_lightweight_path():
    """Engine accepts empty session_ids for lightweight extraction."""
    from vibelens.services.recommendation.engine import _run_pipeline

    # Verify the function signature accepts empty session_ids
    sig = inspect.signature(_run_pipeline)
    params = list(sig.parameters.keys())
    assert "session_ids" in params


def test_analyze_recommendation_signature():
    """analyze_recommendation accepts optional session_ids and top_n."""
    from vibelens.services.recommendation.engine import analyze_recommendation

    sig = inspect.signature(analyze_recommendation)
    session_ids_param = sig.parameters["session_ids"]
    assert session_ids_param.default is not inspect.Parameter.empty

    top_n_param = sig.parameters["top_n"]
    assert top_n_param.default == RATIONALE_MAX_RESULTS


def test_build_rationale_candidates_handles_null_description():
    """Regression: catalog items may have description=None; the L4 template
    builder must coerce to empty string instead of crashing in truncate().
    """
    scored = [
        (_mock_item(name="no-desc", description=None), 0.82),
        (_mock_item(name="with-desc", description="a real skill"), 0.71),
    ]

    out = _build_rationale_candidates(scored)

    assert len(out) == 2
    assert out[0] == {"item_id": "test:no-desc", "name": "no-desc", "description": ""}
    assert out[1]["description"] == "a real skill"
    print(f"built candidates: {out}")


def test_build_rationale_candidates_truncates_long_description():
    """Descriptions longer than DESCRIPTION_MAX_CHARS get an ellipsis suffix."""
    from vibelens.services.recommendation.engine import DESCRIPTION_MAX_CHARS

    long_text = "word " * (DESCRIPTION_MAX_CHARS // 4)
    scored = [(_mock_item(name="long", description=long_text), 0.9)]

    out = _build_rationale_candidates(scored)

    assert out[0]["description"].endswith("...")
    assert len(out[0]["description"]) <= DESCRIPTION_MAX_CHARS + 3

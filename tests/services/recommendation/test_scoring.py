"""Tests for the multi-signal recommendation scoring pipeline."""

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import AgentExtensionItem
from vibelens.models.personalization.recommendation import UserProfile
from vibelens.services.recommendation import scoring
from vibelens.services.recommendation.scoring import score_candidates


def _make_item(
    name: str, quality: float = 50.0, platforms: list[str] | None = None
) -> AgentExtensionItem:
    return AgentExtensionItem(
        extension_id=f"test/{name}",
        extension_type=AgentExtensionType.SKILL,
        name=name,
        description=f"A {name} tool",
        topics=[],
        platforms=platforms,
        quality_score=quality,
        popularity=0.5,
        updated_at="2026-04-01T00:00:00Z",
        source_url=f"https://github.com/test/{name}",
        repo_full_name=f"test/{name}",
        discovery_source="seed",
        stars=10,
        forks=0,
    )


def _make_profile() -> UserProfile:
    return UserProfile(
        domains=["web-dev"],
        languages=["python"],
        frameworks=["fastapi"],
        agent_platforms=["claude-code"],
        bottlenecks=["slow tests"],
        workflow_style="iterative debugger",
        search_keywords=["testing", "fastapi"],
    )


def test_weights_sum_to_one():
    total = (
        scoring.WEIGHT_RELEVANCE
        + scoring.WEIGHT_QUALITY
        + scoring.WEIGHT_PLATFORM_MATCH
        + scoring.WEIGHT_POPULARITY
        + scoring.WEIGHT_COMPOSABILITY
    )
    assert abs(total - 1.0) < 1e-9
    assert scoring.WEIGHT_PLATFORM_MATCH == 0.0
    print(
        f"weights ok: rel={scoring.WEIGHT_RELEVANCE} "
        f"qual={scoring.WEIGHT_QUALITY} "
        f"plat={scoring.WEIGHT_PLATFORM_MATCH} "
        f"pop={scoring.WEIGHT_POPULARITY} "
        f"comp={scoring.WEIGHT_COMPOSABILITY}"
    )


def test_score_candidates_returns_sorted():
    """score_candidates returns results sorted by score descending."""
    candidates = [
        (_make_item("low-quality", quality=10.0), 0.3),
        (_make_item("high-quality", quality=90.0), 0.8),
        (_make_item("mid-quality", quality=50.0), 0.5),
    ]
    profile = _make_profile()
    results = score_candidates(candidates, profile, top_k=3)
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
    print(f"Scores: {[(item.name, round(s, 3)) for item, s in results]}")


def test_platform_match_does_not_boost_when_weight_zero():
    """Platform-match weight is zero this release; matched/unmatched score equally."""
    matched = _make_item("matched", platforms=["claude-code"])
    unmatched = _make_item("unmatched", platforms=["cursor"])
    candidates = [(matched, 0.5), (unmatched, 0.5)]
    profile = _make_profile()
    results = score_candidates(candidates, profile, top_k=2)
    matched_score = next(s for item, s in results if item.name == "matched")
    unmatched_score = next(s for item, s in results if item.name == "unmatched")
    assert matched_score == unmatched_score


def test_platform_match_handles_none_platforms():
    """Items with platforms=None (the catalog default) don't crash scoring."""
    item = _make_item("orphan", platforms=None)
    candidates = [(item, 0.5)]
    profile = _make_profile()
    results = score_candidates(candidates, profile, top_k=1)
    assert len(results) == 1
    print(f"orphan ok: score={results[0][1]:.3f}")


def test_top_k_limit():
    """score_candidates respects top_k."""
    candidates = [(_make_item(f"item-{i}"), 0.5) for i in range(20)]
    results = score_candidates(candidates, _make_profile(), top_k=5)
    assert len(results) <= 5

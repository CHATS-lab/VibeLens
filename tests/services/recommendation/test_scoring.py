"""Tests for the multi-signal recommendation scoring pipeline."""

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import ExtensionItem
from vibelens.models.personalization.recommendation import UserProfile
from vibelens.services.recommendation.scoring import score_candidates


def _make_item(
    name: str, quality: float = 50.0, platforms: list[str] | None = None
) -> ExtensionItem:
    return ExtensionItem(
        extension_id=f"test/{name}",
        extension_type=AgentExtensionType.SKILL,
        name=name,
        description=f"A {name} tool",
        tags=[],
        category="testing",
        platforms=platforms or ["claude-code"],
        quality_score=quality,
        popularity=0.5,
        updated_at="2026-04-01T00:00:00Z",
        source_url=f"https://github.com/test/{name}",
        repo_full_name=f"test/{name}",
        install_method="skill_file",
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


def test_platform_match_boosts_score():
    """Items matching user's agent platform score higher."""
    matched = _make_item("matched", platforms=["claude-code"])
    unmatched = _make_item("unmatched", platforms=["cursor"])
    candidates = [(matched, 0.5), (unmatched, 0.5)]
    profile = _make_profile()
    results = score_candidates(candidates, profile, top_k=2)
    matched_score = next(s for item, s in results if item.name == "matched")
    unmatched_score = next(s for item, s in results if item.name == "unmatched")
    assert matched_score > unmatched_score


def test_top_k_limit():
    """score_candidates respects top_k."""
    candidates = [(_make_item(f"item-{i}"), 0.5) for i in range(20)]
    results = score_candidates(candidates, _make_profile(), top_k=5)
    assert len(results) <= 5

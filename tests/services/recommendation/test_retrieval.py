"""Tests for TF-IDF keyword retrieval backend."""
from vibelens.models.recommendation.catalog import CatalogItem, ItemType
from vibelens.services.recommendation.retrieval import KeywordRetrieval


def _make_item(name: str, description: str, tags: list[str] | None = None) -> CatalogItem:
    """Build a minimal CatalogItem for testing."""
    return CatalogItem(
        item_id=f"test/{name}",
        item_type=ItemType.SKILL,
        name=name,
        description=description,
        tags=tags or [],
        category="testing",
        platforms=["claude-code"],
        quality_score=75.0,
        popularity=0.5,
        updated_at="2026-04-01T00:00:00Z",
        source_url=f"https://github.com/test/{name}",
        repo_full_name=f"test/{name}",
        install_method="skill_file",
    )


def test_keyword_retrieval_basic():
    """KeywordRetrieval finds items matching query keywords."""
    items = [
        _make_item("test-runner", "Runs pytest and reports results", ["testing", "pytest"]),
        _make_item("docker-deploy", "Deploy containers to production", ["docker", "deploy"]),
        _make_item("code-review", "Automated code review", ["review", "quality"]),
    ]
    backend = KeywordRetrieval()
    backend.build_index(items)

    results = backend.search("pytest testing runner", top_k=2)
    assert len(results) > 0
    names = [item.name for item, _ in results]
    assert "test-runner" in names
    print(f"Search results: {[(item.name, round(score, 3)) for item, score in results]}")


def test_keyword_retrieval_empty_query():
    """Empty query returns empty results."""
    backend = KeywordRetrieval()
    backend.build_index([_make_item("test", "A test skill")])
    results = backend.search("", top_k=5)
    assert len(results) == 0


def test_keyword_retrieval_top_k():
    """Results respect top_k limit."""
    items = [_make_item(f"skill-{i}", f"Description {i}") for i in range(20)]
    backend = KeywordRetrieval()
    backend.build_index(items)
    results = backend.search("description skill", top_k=5)
    assert len(results) <= 5


def test_keyword_retrieval_scores_normalized():
    """Scores are between 0.0 and 1.0."""
    items = [
        _make_item("exact-match", "python testing automation pytest"),
        _make_item("partial", "some other tool"),
    ]
    backend = KeywordRetrieval()
    backend.build_index(items)
    results = backend.search("python testing pytest", top_k=10)
    for _, score in results:
        assert 0.0 <= score <= 1.0

"""Tests for recommendation API endpoints."""


def test_recommendation_schemas_importable():
    """Recommendation schemas are importable."""
    from vibelens.schemas.recommendation import (
        CatalogStatusResponse,
        RecommendationAnalyzeRequest,
    )
    req = RecommendationAnalyzeRequest(session_ids=["s1", "s2"])
    assert len(req.session_ids) == 2

    status = CatalogStatusResponse(version="2026-04-13", item_count=100, schema_version=1)
    assert status.item_count == 100


def test_recommendation_router_importable():
    """Recommendation API router is importable."""
    from vibelens.api.recommendation import router
    routes = [r.path for r in router.routes]
    assert "/recommendation" in routes, f"Expected /recommendation in {routes}"
    print(f"Recommendation routes: {routes}")

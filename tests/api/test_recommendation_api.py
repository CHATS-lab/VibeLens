"""Tests for recommendation API endpoints."""


def test_recommendation_schemas_importable():
    """Personalization schemas are importable."""
    from vibelens.schemas.personalization import PersonalizationRequest

    req = PersonalizationRequest(session_ids=["s1", "s2"])
    assert len(req.session_ids) == 2


def test_recommendation_router_importable():
    """Recommendation API router is importable."""
    from vibelens.api.recommendation import router

    routes = [r.path for r in router.routes]
    assert "/recommendation" in routes, f"Expected /recommendation in {routes}"
    print(f"Recommendation routes: {routes}")

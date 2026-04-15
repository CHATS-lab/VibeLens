"""Tests for recommendation store."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from vibelens.models.enums import AgentExtensionType
from vibelens.models.llm.inference import BackendType
from vibelens.models.personalization.enums import PersonalizationMode
from vibelens.models.personalization.recommendation import (
    RankedRecommendationItem,
    RecommendationItem,
    UserProfile,
)
from vibelens.models.personalization.results import PersonalizationResult
from vibelens.models.trajectories.final_metrics import FinalMetrics
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.personalization.store import PersonalizationStore


def _build_test_result(session_ids: list[str]) -> PersonalizationResult:
    """Build a minimal PersonalizationResult for recommendation store tests."""
    return PersonalizationResult(
        id="test-rec-001",
        mode=PersonalizationMode.RECOMMENDATION,
        session_ids=session_ids,
        skipped_session_ids=[],
        title="Test recommendations",
        user_profile=UserProfile(
            domains=["web-dev"],
            languages=["python"],
            frameworks=["fastapi"],
            agent_platforms=["claude-code"],
            bottlenecks=["slow tests"],
            workflow_style="iterative",
            search_keywords=["testing", "python"],
        ),
        recommendations=[
            RankedRecommendationItem(
                item=RecommendationItem(
                    extension_id="test/skill",
                    extension_type=AgentExtensionType.SKILL,
                    name="test-skill",
                    description="A test skill.",
                    tags=["testing"],
                    updated_at="2025-01-01T00:00:00Z",
                    source_url="https://example.com",
                    repo_name="test/repo",
                ),
                rationale="Matches test patterns.",
                scores={"relevance": 0.9, "quality": 80.0, "composite": 0.85},
            ),
        ],
        backend=BackendType.MOCK,
        model="mock-model",
        created_at=datetime.now(timezone.utc).isoformat(),
        batch_count=2,
        batch_metrics=[
            Metrics(cost_usd=0.005),
            Metrics(cost_usd=0.005),
        ],
        final_metrics=FinalMetrics(total_cost_usd=0.01),
    )


def test_recommendation_store_save_and_load():
    """PersonalizationStore saves and loads results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = PersonalizationStore(Path(tmpdir))
        result = _build_test_result(["session-1", "session-2"])
        store.save(result, "test-analysis-001")
        loaded = store.load("test-analysis-001")
        assert loaded is not None
        assert loaded.id == "test-rec-001"
        assert len(loaded.recommendations) > 0
        print(f"Saved and loaded {len(loaded.recommendations)} recommendations")


def test_recommendation_store_list():
    """PersonalizationStore lists analyses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = PersonalizationStore(Path(tmpdir))
        result = _build_test_result(["s1"])
        store.save(result, "test-001")
        analyses = store.list_analyses()
        assert len(analyses) == 1
        assert analyses[0].id == "test-001"

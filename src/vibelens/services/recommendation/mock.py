"""Mock recommendation data for demo and test modes."""

from datetime import datetime, timezone

from vibelens.models.llm.inference import BackendType
from vibelens.models.recommendation.catalog import ITEM_TYPE_LABELS, ItemType
from vibelens.models.recommendation.profile import UserProfile
from vibelens.models.recommendation.results import (
    CatalogRecommendation,
    RecommendationResult,
)
from vibelens.models.trajectories.metrics import Metrics


def build_mock_recommendation_result(session_ids: list[str]) -> RecommendationResult:
    """Build a realistic mock recommendation result for demo/test mode.

    Args:
        session_ids: Session IDs to include in the result.

    Returns:
        RecommendationResult with sample recommendations.
    """
    profile = UserProfile(
        domains=["web-dev", "api-development"],
        languages=["python", "typescript"],
        frameworks=["fastapi", "react", "docker"],
        agent_platforms=["claude-code"],
        bottlenecks=["repeated test failures", "slow CI feedback"],
        workflow_style="iterative debugger, prefers small commits",
        search_keywords=[
            "testing",
            "pytest",
            "fastapi",
            "react",
            "docker",
            "code-review",
            "refactoring",
            "debugging",
            "linting",
            "type-checking",
            "documentation",
            "ci-cd",
            "deployment",
        ],
    )

    recommendations = [
        CatalogRecommendation(
            item_id="anthropics/skills/test-runner",
            item_type=ItemType.SKILL,
            user_label=ITEM_TYPE_LABELS[ItemType.SKILL],
            name="test-runner",
            description="Automatically runs tests after code changes and reports results.",
            rationale=(
                "Catches test failures early in your workflow.\n"
                "- Runs after every edit\n"
                "- Shows only failing tests"
            ),
            confidence=0.92,
            quality_score=85.0,
            score=0.88,
            install_method="skill_file",
            install_command=None,
            has_content=True,
            source_url="https://github.com/anthropics/skills/tree/main/skills/test-runner",
        ),
        CatalogRecommendation(
            item_id="anthropics/skills/code-review",
            item_type=ItemType.SKILL,
            user_label=ITEM_TYPE_LABELS[ItemType.SKILL],
            name="code-review",
            description="Reviews code changes for bugs, style issues, and best practices.",
            rationale=(
                "Catches issues before they reach your tests.\n"
                "- Reviews diffs automatically\n"
                "- Suggests improvements inline"
            ),
            confidence=0.85,
            quality_score=80.0,
            score=0.82,
            install_method="skill_file",
            install_command=None,
            has_content=True,
            source_url="https://github.com/anthropics/skills/tree/main/skills/code-review",
        ),
        CatalogRecommendation(
            item_id="modelcontextprotocol/servers/postgres",
            item_type=ItemType.REPO,
            user_label=ITEM_TYPE_LABELS[ItemType.REPO],
            name="postgres-mcp",
            description="MCP server for PostgreSQL database access and querying.",
            rationale=(
                "Lets your agent query your database directly.\n"
                "- No manual SQL copying\n"
                "- Schema-aware queries"
            ),
            confidence=0.78,
            quality_score=90.0,
            score=0.76,
            install_method="mcp_config",
            install_command=None,
            has_content=False,
            source_url="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
        ),
    ]

    return RecommendationResult(
        analysis_id="mock-recommendation-001",
        session_ids=session_ids,
        skipped_session_ids=[],
        title=f"Found {len(recommendations)} tools for your workflow",
        summary="Based on your web-dev and API work with Python and TypeScript.",
        user_profile=profile,
        recommendations=recommendations,
        backend_id=BackendType.MOCK,
        model="mock-model",
        created_at=datetime.now(timezone.utc).isoformat(),
        metrics=Metrics(cost_usd=0.05),
        duration_seconds=2.5,
        catalog_version="2026-04-10",
        is_example=True,
    )

"""Tests for recommendation prompt definitions."""
from vibelens.prompts.recommendation import (
    RECOMMENDATION_PROFILE_PROMPT,
    RECOMMENDATION_RATIONALE_PROMPT,
)


def test_profile_prompt_renders():
    """L2 profile prompt renders system and user templates."""
    system = RECOMMENDATION_PROFILE_PROMPT.render_system(
        output_schema="{}", backend_rules=""
    )
    assert "profile" in system.lower() or "workflow" in system.lower()
    print(f"Profile system prompt: {len(system)} chars")

    user = RECOMMENDATION_PROFILE_PROMPT.render_user(
        session_count=5,
        session_digest="User asked about Python testing...",
    )
    assert "5" in user
    print(f"Profile user prompt: {len(user)} chars")


def test_rationale_prompt_renders():
    """L4 rationale prompt renders system and user templates."""
    system = RECOMMENDATION_RATIONALE_PROMPT.render_system(
        output_schema="{}", backend_rules=""
    )
    assert "rationale" in system.lower() or "recommend" in system.lower()

    user = RECOMMENDATION_RATIONALE_PROMPT.render_user(
        user_profile={"domains": ["web-dev"], "languages": ["python"]},
        candidates=[{"name": "test-runner", "description": "Runs tests"}],
    )
    assert "test-runner" in user
    print(f"Rationale user prompt: {len(user)} chars")


def test_profile_prompt_task_id():
    """Profile prompt has correct task_id."""
    assert RECOMMENDATION_PROFILE_PROMPT.task_id == "recommendation_profile"


def test_rationale_prompt_task_id():
    """Rationale prompt has correct task_id."""
    assert RECOMMENDATION_RATIONALE_PROMPT.task_id == "recommendation_rationale"


def test_recommendation_prompts_in_registry():
    """Recommendation prompts are registered in PROMPT_REGISTRY."""
    from vibelens.prompts import PROMPT_REGISTRY
    assert "recommendation_profile" in PROMPT_REGISTRY

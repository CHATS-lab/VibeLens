"""Skill-related services — analysis, persistence, and digest formatting."""

from vibelens.llm.cost_estimator import CostEstimate
from vibelens.models.skill import SkillAnalysisResult, SkillMode
from vibelens.services.skill.store import SkillAnalysisStore

__all__ = [
    "SkillAnalysisStore",
    "analyze_skills",
    "estimate_skill_analysis",
]


async def analyze_skills(
    session_ids: list[str],
    mode: SkillMode,
    session_token: str | None = None,
    skill_names: list[str] | None = None,
) -> SkillAnalysisResult:
    """Dispatch skill analysis to the appropriate mode handler."""
    if mode == SkillMode.RETRIEVAL:
        from vibelens.services.skill.retrieval import analyze_skill_retrieval

        return await analyze_skill_retrieval(session_ids, session_token)
    elif mode == SkillMode.CREATION:
        from vibelens.services.skill.creation import analyze_skill_creation

        return await analyze_skill_creation(session_ids, session_token)
    else:
        from vibelens.services.skill.evolution import analyze_skill_evolution

        return await analyze_skill_evolution(session_ids, session_token, skill_names)


def estimate_skill_analysis(
    session_ids: list[str],
    mode: SkillMode,
    session_token: str | None = None,
    skill_names: list[str] | None = None,
) -> CostEstimate:
    """Pre-flight cost estimate dispatched to the appropriate mode handler."""
    if mode == SkillMode.RETRIEVAL:
        from vibelens.services.skill.retrieval import estimate_skill_retrieval

        return estimate_skill_retrieval(session_ids, session_token)
    elif mode == SkillMode.CREATION:
        from vibelens.services.skill.creation import estimate_skill_creation

        return estimate_skill_creation(session_ids, session_token)
    else:
        from vibelens.services.skill.evolution import estimate_skill_evolution

        return estimate_skill_evolution(session_ids, session_token, skill_names)

"""Skill-related services — analysis, persistence, and digest formatting."""

from vibelens.models.skill import (
    SkillAnalysisResult,
    SkillCreation,
    SkillCreationProposalResult,
    SkillMode,
)
from vibelens.services.skill.store import SkillAnalysisStore

__all__ = [
    "SkillAnalysisStore",
    "analyze_skill_creation_proposals",
    "analyze_skills",
    "infer_skill_creation",
]


async def analyze_skills(
    session_ids: list[str], mode: SkillMode, session_token: str | None = None
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

        return await analyze_skill_evolution(session_ids, session_token)


async def analyze_skill_creation_proposals(
    session_ids: list[str], session_token: str | None = None
) -> SkillCreationProposalResult:
    """Generate lightweight skill proposals from session analysis."""
    from vibelens.services.skill.creation import (
        _infer_skill_creation_proposals,
    )

    return await _infer_skill_creation_proposals(session_ids, session_token)


async def infer_skill_creation(
    proposal_name: str,
    proposal_description: str,
    proposal_rationale: str,
    addressed_patterns: list[str],
    session_ids: list[str],
    session_token: str | None = None,
) -> SkillCreation:
    """Generate full SKILL.md content for one approved proposal."""
    from vibelens.services.skill.creation import (
        _infer_skill_creation as _infer,
    )

    return await _infer(
        proposal_name,
        proposal_description,
        proposal_rationale,
        addressed_patterns,
        session_ids,
        session_token,
    )

"""Analysis prompt registry.

Central lookup for all available AnalysisPrompt instances.
"""

from vibelens.llm.prompts.friction_analysis import FRICTION_ANALYSIS_PROMPT
from vibelens.llm.prompts.skill_evolution import SKILL_EVOLUTION_PROPOSAL_PROMPT
from vibelens.llm.prompts.skill_retrieval import SKILL_RETRIEVAL_PROMPT
from vibelens.models.llm.prompts import AnalysisPrompt

PROMPT_REGISTRY: dict[str, AnalysisPrompt] = {
    FRICTION_ANALYSIS_PROMPT.task_id: FRICTION_ANALYSIS_PROMPT,
    SKILL_RETRIEVAL_PROMPT.task_id: SKILL_RETRIEVAL_PROMPT,
    SKILL_EVOLUTION_PROPOSAL_PROMPT.task_id: SKILL_EVOLUTION_PROPOSAL_PROMPT,
}


def get_prompt(task_id: str) -> AnalysisPrompt | None:
    """Look up a registered analysis prompt by task ID.

    Args:
        task_id: Unique prompt identifier (e.g. 'friction_analysis').

    Returns:
        AnalysisPrompt instance, or None if not found.
    """
    return PROMPT_REGISTRY.get(task_id)

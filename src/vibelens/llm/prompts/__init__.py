"""Analysis prompt registry.

Central lookup for all available AnalysisPrompt instances.
New analysis types register here for discovery by the insight service.
"""

from vibelens.llm.prompts.friction_analysis import FRICTION_ANALYSIS_PROMPT
from vibelens.llm.prompts.insights import FRICTION_PROMPT, HIGHLIGHTS_PROMPT
from vibelens.llm.prompts.skill_creation import SKILL_CREATION_PROMPT
from vibelens.llm.prompts.skill_evolution import SKILL_EVOLUTION_PROMPT
from vibelens.llm.prompts.skill_retrieval import SKILL_RETRIEVAL_PROMPT
from vibelens.models.analysis.prompts import AnalysisPrompt

PROMPT_REGISTRY: dict[str, AnalysisPrompt] = {
    HIGHLIGHTS_PROMPT.task_id: HIGHLIGHTS_PROMPT,
    FRICTION_PROMPT.task_id: FRICTION_PROMPT,
    FRICTION_ANALYSIS_PROMPT.task_id: FRICTION_ANALYSIS_PROMPT,
    SKILL_RETRIEVAL_PROMPT.task_id: SKILL_RETRIEVAL_PROMPT,
    SKILL_CREATION_PROMPT.task_id: SKILL_CREATION_PROMPT,
    SKILL_EVOLUTION_PROMPT.task_id: SKILL_EVOLUTION_PROMPT,
}


def get_prompt(task_id: str) -> AnalysisPrompt | None:
    """Look up a registered analysis prompt by task ID.

    Args:
        task_id: Unique prompt identifier (e.g. 'highlights', 'friction').

    Returns:
        AnalysisPrompt instance, or None if not found.
    """
    return PROMPT_REGISTRY.get(task_id)

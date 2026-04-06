"""Prompts for skill retrieval analysis and cross-batch synthesis.

Detects workflow patterns from session transcripts and recommends
existing skills from a pre-built candidate list. Synthesis merges
batch-level results when multiple batches are used.
"""

from vibelens.models.llm.prompts import AnalysisPrompt, load_template
from vibelens.models.skill import SkillRetrievalOutput

SKILL_RETRIEVAL_PROMPT = AnalysisPrompt(
    task_id="skill_retrieval",
    system_template=load_template("skill/retrieval_system.j2"),
    user_template=load_template("skill/retrieval_user.j2"),
    output_model=SkillRetrievalOutput,
)

SKILL_RETRIEVAL_SYNTHESIS_PROMPT = AnalysisPrompt(
    task_id="skill_retrieval_synthesis",
    system_template=load_template("skill/retrieval_synthesis_system.j2"),
    user_template=load_template("skill/retrieval_synthesis_user.j2"),
    output_model=SkillRetrievalOutput,
)

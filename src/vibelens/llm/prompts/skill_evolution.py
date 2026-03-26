"""Prompt for skill evolution analysis.

Detects workflow patterns and suggests granular edits to existing
installed skills. Uses SkillLLMOutput as the output model.
"""

from vibelens.models.analysis.prompts import AnalysisPrompt, load_template
from vibelens.models.analysis.skills import SkillLLMOutput

SKILL_EVOLUTION_PROMPT = AnalysisPrompt(
    task_id="skill_evolution",
    system_template=load_template("skill_evolution_system.j2"),
    user_template=load_template("skill_evolution_user.j2"),
    output_model=SkillLLMOutput,
)

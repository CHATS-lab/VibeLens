"""Prompt for skill creation analysis.

Detects workflow patterns from session transcripts and generates
new SKILL.md definitions. Uses SkillLLMOutput as the output model.
"""

from vibelens.models.analysis.prompts import AnalysisPrompt, load_template
from vibelens.models.analysis.skills import SkillLLMOutput

SKILL_CREATION_PROMPT = AnalysisPrompt(
    task_id="skill_creation",
    system_template=load_template("skill_creation_system.j2"),
    user_template=load_template("skill_creation_user.j2"),
    output_model=SkillLLMOutput,
)

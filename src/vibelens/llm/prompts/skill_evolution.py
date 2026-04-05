"""Prompts for skill evolution: proposals, synthesis, and editing.

Two-step pipeline:
1. Proposals: detect patterns and propose improvements to existing skills
2. Editing: generate granular edits for each approved proposal
"""

from vibelens.models.prompts import AnalysisPrompt, load_template
from vibelens.models.skill import SkillEvolution, SkillEvolutionProposalOutput

SKILL_EVOLUTION_PROPOSAL_PROMPT = AnalysisPrompt(
    task_id="skill_evolution_proposal",
    system_template=load_template("skill/evolution_proposal_system.j2"),
    user_template=load_template("skill/evolution_proposal_user.j2"),
    output_model=SkillEvolutionProposalOutput,
)

SKILL_EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT = AnalysisPrompt(
    task_id="skill_evolution_proposal_synthesis",
    system_template=load_template("skill/evolution_proposal_synthesis_system.j2"),
    user_template=load_template("skill/evolution_proposal_synthesis_user.j2"),
    output_model=SkillEvolutionProposalOutput,
)

SKILL_EVOLUTION_EDIT_PROMPT = AnalysisPrompt(
    task_id="skill_evolution_edit",
    system_template=load_template("skill/evolution_system.j2"),
    user_template=load_template("skill/evolution_user.j2"),
    output_model=SkillEvolution,
)

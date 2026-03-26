"""Prompts for multi-session friction analysis.

Two-phase pipeline:
1. FRICTION_ANALYSIS_PROMPT: Per-batch friction detection (events + batch summary).
2. FRICTION_SYNTHESIS_PROMPT: Post-batch synthesis (title + cohesive summary + type descriptions).
"""

from vibelens.models.analysis.friction import FrictionLLMBatchOutput, FrictionSynthesisOutput
from vibelens.models.analysis.prompts import AnalysisPrompt, load_template

FRICTION_ANALYSIS_PROMPT = AnalysisPrompt(
    task_id="friction_analysis",
    system_template=load_template("friction_analysis_system.j2"),
    user_template=load_template("friction_analysis_user.j2"),
    output_model=FrictionLLMBatchOutput,
)

FRICTION_SYNTHESIS_PROMPT = AnalysisPrompt(
    task_id="friction_synthesis",
    system_template=load_template("friction_synthesis_system.j2"),
    user_template=load_template("friction_synthesis_user.j2"),
    output_model=FrictionSynthesisOutput,
)

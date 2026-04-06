"""Prompts for multi-session friction analysis.

Two-phase pipeline:
1. FRICTION_ANALYSIS_PROMPT: Per-batch friction detection (events + summary + mitigations).
2. FRICTION_SYNTHESIS_PROMPT: Post-batch synthesis (merged title + summary + events + mitigations).
"""

from vibelens.models.analysis.friction import FrictionAnalysisOutput
from vibelens.models.llm.prompts import AnalysisPrompt, load_template

FRICTION_ANALYSIS_PROMPT = AnalysisPrompt(
    task_id="friction_analysis",
    system_template=load_template("friction/analysis_system.j2"),
    user_template=load_template("friction/analysis_user.j2"),
    output_model=FrictionAnalysisOutput,
)

FRICTION_SYNTHESIS_PROMPT = AnalysisPrompt(
    task_id="friction_synthesis",
    system_template=load_template("friction/synthesis_system.j2"),
    user_template=load_template("friction/synthesis_user.j2"),
    output_model=FrictionAnalysisOutput,
)

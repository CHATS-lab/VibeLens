"""Prompt for multi-session friction analysis.

Distinct from the single-session friction prompt in insights.py.
Uses session_count and session_digest variables instead of
trajectory_digest, and outputs FrictionLLMOutput instead of FrictionReport.
"""

from vibelens.models.analysis.friction import FrictionLLMOutput
from vibelens.models.analysis.prompts import AnalysisPrompt, load_template

FRICTION_ANALYSIS_PROMPT = AnalysisPrompt(
    task_id="friction_analysis",
    system_template=load_template("friction_analysis_system.j2"),
    user_template=load_template("friction_analysis_user.j2"),
    output_model=FrictionLLMOutput,
)

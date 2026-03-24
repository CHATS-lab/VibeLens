"""Prompt instances for session highlights and friction analysis."""

from vibelens.models.analysis.insights import FrictionReport, SessionHighlights
from vibelens.models.analysis.prompts import AnalysisPrompt, load_template

HIGHLIGHTS_PROMPT = AnalysisPrompt(
    task_id="highlights",
    system_template=load_template("highlights_system.j2"),
    user_template=load_template("highlights_user.j2"),
    output_model=SessionHighlights,
)

FRICTION_PROMPT = AnalysisPrompt(
    task_id="friction",
    system_template=load_template("friction_system.j2"),
    user_template=load_template("friction_user.j2"),
    output_model=FrictionReport,
)

"""Prompts for the recommendation pipeline: profile generation and rationale.

Two LLM calls:
1. L2 Profile: Extract structured user profile from session transcripts
2. L4 Rationale: Generate personalized rationale for top-scoring candidates
"""

from vibelens.models.llm.prompts import AnalysisPrompt, load_template
from vibelens.models.recommendation.profile import UserProfile
from vibelens.models.recommendation.results import RationaleOutput

# L2: Profile generation from session transcripts
RECOMMENDATION_PROFILE_PROMPT = AnalysisPrompt(
    task_id="recommendation_profile",
    system_template=load_template("recommendation/profile_system.j2"),
    user_template=load_template("recommendation/profile_user.j2"),
    output_model=UserProfile,
)

# L4: Rationale generation for top candidates
RECOMMENDATION_RATIONALE_PROMPT = AnalysisPrompt(
    task_id="recommendation_rationale",
    system_template=load_template("recommendation/rationale_system.j2"),
    user_template=load_template("recommendation/rationale_user.j2"),
    output_model=RationaleOutput,
)

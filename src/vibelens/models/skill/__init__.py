"""Skill domain models."""

from vibelens.models.creation import (
    ElementCreation,
    ElementCreationProposal,
    ElementCreationProposalOutput,
    ElementCreationProposalResult,
)
from vibelens.models.evolution import (
    ElementEdit,
    ElementEvolution,
    ElementEvolutionProposal,
    ElementEvolutionProposalOutput,
    ElementEvolutionProposalResult,
)
from vibelens.models.skill.info import VALID_SKILL_NAME, SkillInfo
from vibelens.models.skill.patterns import SkillMode, WorkflowPattern
from vibelens.models.skill.results import SkillAnalysisResult
from vibelens.models.skill.retrieval import SkillRecommendation, SkillRetrievalOutput
from vibelens.models.skill.source import SkillSource, SkillSourceType

# Backward-compat aliases: old Skill* names map to new Element* names.
SkillCreation = ElementCreation
SkillCreationProposal = ElementCreationProposal
SkillCreationProposalOutput = ElementCreationProposalOutput
SkillCreationProposalResult = ElementCreationProposalResult
SkillEdit = ElementEdit
SkillEvolution = ElementEvolution
SkillEvolutionProposal = ElementEvolutionProposal
SkillEvolutionProposalOutput = ElementEvolutionProposalOutput
SkillEvolutionProposalResult = ElementEvolutionProposalResult

__all__ = [
    # New Element* names
    "ElementCreation",
    "ElementCreationProposal",
    "ElementCreationProposalOutput",
    "ElementCreationProposalResult",
    "ElementEdit",
    "ElementEvolution",
    "ElementEvolutionProposal",
    "ElementEvolutionProposalOutput",
    "ElementEvolutionProposalResult",
    # Backward-compat Skill* aliases
    "SkillAnalysisResult",
    "SkillCreation",
    "SkillCreationProposal",
    "SkillCreationProposalOutput",
    "SkillCreationProposalResult",
    "SkillEdit",
    "SkillEvolution",
    "SkillEvolutionProposal",
    "SkillEvolutionProposalOutput",
    "SkillEvolutionProposalResult",
    "SkillInfo",
    "SkillMode",
    "SkillRecommendation",
    "SkillRetrievalOutput",
    "SkillSource",
    "SkillSourceType",
    "VALID_SKILL_NAME",
    "WorkflowPattern",
]

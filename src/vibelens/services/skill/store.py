"""Skill analysis result persistence.

Thin subclass of AnalysisStore with skill-specific meta building.
"""

from pathlib import Path

from vibelens.models.skill import SkillAnalysisResult
from vibelens.schemas.skills import SkillAnalysisMeta
from vibelens.services.analysis_store import AnalysisStore


def _build_meta(analysis_id: str, result: SkillAnalysisResult) -> SkillAnalysisMeta:
    """Build lightweight metadata from a full skill analysis result."""
    return SkillAnalysisMeta(
        analysis_id=analysis_id,
        mode=result.mode,
        title=result.title,
        session_ids=result.session_ids,
        created_at=result.created_at,
        model=result.model,
        cost_usd=result.cost_usd,
        duration_seconds=result.duration_seconds,
    )


class SkillAnalysisStore(AnalysisStore[SkillAnalysisResult, SkillAnalysisMeta]):
    """Manages persisted skill analysis results on disk."""

    def __init__(self, store_dir: Path):
        super().__init__(store_dir, SkillAnalysisResult, SkillAnalysisMeta, _build_meta)

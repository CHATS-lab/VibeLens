"""Friction analysis result persistence.

Thin subclass of AnalysisStore with friction-specific meta building.
"""

from pathlib import Path

from vibelens.models.analysis.friction import FrictionAnalysisResult
from vibelens.schemas.friction import FrictionMeta
from vibelens.services.analysis_store import AnalysisStore


def _build_meta(analysis_id: str, result: FrictionAnalysisResult) -> FrictionMeta:
    """Build lightweight metadata from a full friction analysis result."""
    return FrictionMeta(
        analysis_id=analysis_id,
        title=result.title,
        session_ids=result.session_ids,
        created_at=result.created_at,
        model=result.model,
        cost_usd=result.metrics.cost_usd,
        batch_count=result.batch_count,
        duration_seconds=result.duration_seconds,
    )


class FrictionStore(AnalysisStore[FrictionAnalysisResult, FrictionMeta]):
    """Manages persisted friction analysis results on disk."""

    def __init__(self, friction_dir: Path):
        super().__init__(friction_dir, FrictionAnalysisResult, FrictionMeta, _build_meta)

"""Creation analysis result persistence.

Thin subclass of AnalysisStore with creation-specific meta building.
"""

from pathlib import Path

from vibelens.models.creation import CreationAnalysisResult
from vibelens.schemas.creation import CreationAnalysisMeta
from vibelens.services.analysis_store import AnalysisStore


def _build_meta(analysis_id: str, result: CreationAnalysisResult) -> CreationAnalysisMeta:
    """Build lightweight metadata from a full creation analysis result."""
    return CreationAnalysisMeta(
        analysis_id=analysis_id,
        title=result.title,
        session_ids=result.session_ids,
        created_at=result.created_at,
        model=result.model,
        cost_usd=result.metrics.cost_usd,
        duration_seconds=result.duration_seconds,
        is_example=result.is_example,
    )


class CreationAnalysisStore(AnalysisStore[CreationAnalysisResult, CreationAnalysisMeta]):
    """Manages persisted creation analysis results on disk."""

    def __init__(self, store_dir: Path):
        super().__init__(store_dir, CreationAnalysisResult, CreationAnalysisMeta, _build_meta)

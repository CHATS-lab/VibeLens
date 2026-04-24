"""Friction analysis result persistence.

Thin subclass of AnalysisStore with friction-specific meta building.
"""

from pathlib import Path

from vibelens.models.friction import FrictionAnalysisResult
from vibelens.schemas.friction import FrictionMeta
from vibelens.services.analysis_store import AnalysisStore
from vibelens.utils.identifiers import generate_timestamped_id
from vibelens.utils.json import locked_jsonl_append, locked_jsonl_remove
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


def _build_meta(analysis_id: str, result: FrictionAnalysisResult) -> FrictionMeta:
    """Build lightweight metadata from a full friction analysis result."""
    return FrictionMeta(
        id=analysis_id,
        title=result.title,
        session_count=len(result.session_ids),
        item_count=len(result.friction_types),
        backend=result.backend,
        model=result.model,
        created_at=result.created_at,
        batch_count=result.batch_count,
        final_metrics=result.final_metrics,
        is_example=result.is_example,
    )


class FrictionStore(AnalysisStore[FrictionAnalysisResult, FrictionMeta]):
    """Manages persisted friction analysis results on disk."""

    def __init__(self, friction_dir: Path):
        super().__init__(friction_dir, FrictionAnalysisResult, FrictionMeta, _build_meta)

    def save(
        self, result: FrictionAnalysisResult, analysis_id: str | None = None
    ) -> FrictionMeta:
        """Persist a result and append metadata to the JSONL index."""
        if analysis_id is None:
            analysis_id = generate_timestamped_id()
        result.id = analysis_id

        self._data_path(analysis_id).write_text(result.model_dump_json(indent=2), encoding="utf-8")

        meta = self._build_meta(analysis_id, result)
        locked_jsonl_append(self._index_path, meta.model_dump(mode="json"))

        logger.info("Saved analysis %s to %s", analysis_id, self._dir.name)
        return meta

    def delete(self, analysis_id: str) -> bool:
        """Delete an analysis result and remove its entry from the index."""
        data_path = self._data_path(analysis_id)
        if not data_path.exists():
            return False
        data_path.unlink(missing_ok=True)
        locked_jsonl_remove(self._index_path, "id", analysis_id)
        logger.info("Deleted analysis %s from %s", analysis_id, self._dir.name)
        return True

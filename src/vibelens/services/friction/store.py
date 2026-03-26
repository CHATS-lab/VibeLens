"""Friction store — persistence for friction analysis results."""

import json
import secrets
from pathlib import Path

from vibelens.models.analysis.friction import FrictionAnalysisResult
from vibelens.schemas.friction import FrictionMeta
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

TOKEN_BYTES = 12
SUMMARY_PREVIEW_LENGTH = 120


class FrictionStore:
    """Manages persisted friction analysis results on disk.

    Each analysis produces two files under ``friction_dir``:
    - ``{analysis_id}.json``      — full FrictionAnalysisResult
    - ``{analysis_id}.meta.json`` — lightweight FrictionMeta for listing
    """

    def __init__(self, friction_dir: Path):
        self._dir = friction_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _data_path(self, analysis_id: str) -> Path:
        return self._dir / f"{analysis_id}.json"

    def _meta_path(self, analysis_id: str) -> Path:
        return self._dir / f"{analysis_id}.meta.json"

    def save(self, result: FrictionAnalysisResult) -> FrictionMeta:
        """Persist a friction analysis result and return its metadata.

        Args:
            result: Complete friction analysis result to persist.

        Returns:
            FrictionMeta with the generated analysis_id.
        """
        analysis_id = secrets.token_urlsafe(TOKEN_BYTES)
        result.analysis_id = analysis_id

        self._data_path(analysis_id).write_text(result.model_dump_json(indent=2), encoding="utf-8")

        meta = _build_meta(analysis_id, result)
        self._meta_path(analysis_id).write_text(meta.model_dump_json(indent=2), encoding="utf-8")

        logger.info("Saved friction analysis %s (%d events)", analysis_id, len(result.events))
        return meta

    def load(self, analysis_id: str) -> FrictionAnalysisResult | None:
        """Load a full friction analysis result by ID.

        Args:
            analysis_id: Unique analysis identifier.

        Returns:
            FrictionAnalysisResult, or None if not found.
        """
        path = self._data_path(analysis_id)
        if not path.exists():
            return None
        return FrictionAnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))

    def load_meta(self, analysis_id: str) -> FrictionMeta | None:
        """Load friction metadata by ID.

        Args:
            analysis_id: Unique analysis identifier.

        Returns:
            FrictionMeta, or None if not found.
        """
        path = self._meta_path(analysis_id)
        if not path.exists():
            return None
        return FrictionMeta.model_validate_json(path.read_text(encoding="utf-8"))

    def list_analyses(self) -> list[FrictionMeta]:
        """List all persisted analyses sorted by created_at descending.

        Returns:
            List of FrictionMeta objects.
        """
        analyses: list[FrictionMeta] = []
        for meta_path in self._dir.glob("*.meta.json"):
            try:
                meta = FrictionMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
                analyses.append(meta)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Skipping corrupt friction metadata: %s", meta_path)
        analyses.sort(key=lambda m: m.created_at, reverse=True)
        return analyses

    def delete(self, analysis_id: str) -> bool:
        """Remove a persisted friction analysis.

        Args:
            analysis_id: Unique analysis identifier.

        Returns:
            True if files were deleted, False if not found.
        """
        data_path = self._data_path(analysis_id)
        meta_path = self._meta_path(analysis_id)
        if not data_path.exists() and not meta_path.exists():
            return False
        data_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        logger.info("Deleted friction analysis %s", analysis_id)
        return True


def _build_meta(analysis_id: str, result: FrictionAnalysisResult) -> FrictionMeta:
    """Build lightweight metadata from a full analysis result.

    Args:
        analysis_id: Unique analysis identifier.
        result: Complete friction analysis result.

    Returns:
        FrictionMeta summarizing the result.
    """
    preview = result.summary[:SUMMARY_PREVIEW_LENGTH]
    if len(result.summary) > SUMMARY_PREVIEW_LENGTH:
        preview += "..."

    return FrictionMeta(
        analysis_id=analysis_id,
        session_ids=result.session_ids,
        event_count=len(result.events),
        summary_preview=preview,
        created_at=result.created_at,
        model=result.model,
        cost_usd=result.cost_usd,
        batch_count=result.batch_count,
    )

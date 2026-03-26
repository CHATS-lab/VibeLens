"""Friction store — persistence for friction analysis results.

Uses a single ``meta.jsonl`` file for lightweight listing and individual
``{analysis_id}.json`` files for full results.
"""

import json
import secrets
from pathlib import Path

from vibelens.models.analysis.friction import FrictionAnalysisResult
from vibelens.schemas.friction import FrictionMeta
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

TOKEN_BYTES = 12
SUMMARY_PREVIEW_LENGTH = 120
META_FILENAME = "meta.jsonl"


class FrictionStore:
    """Manages persisted friction analysis results on disk.

    Each analysis produces one line in ``meta.jsonl`` (append-only) and
    one ``{analysis_id}.json`` file containing the full result.
    """

    def __init__(self, friction_dir: Path):
        self._dir = friction_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def _meta_path(self) -> Path:
        return self._dir / META_FILENAME

    def _data_path(self, analysis_id: str) -> Path:
        return self._dir / f"{analysis_id}.json"

    def save(self, result: FrictionAnalysisResult) -> FrictionMeta:
        """Persist a friction analysis result and append metadata.

        Args:
            result: Complete friction analysis result to persist.

        Returns:
            FrictionMeta with the generated analysis_id.
        """
        analysis_id = secrets.token_urlsafe(TOKEN_BYTES)
        result.analysis_id = analysis_id

        self._data_path(analysis_id).write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )

        meta = _build_meta(analysis_id, result)
        with self._meta_path.open("a", encoding="utf-8") as fh:
            fh.write(meta.model_dump_json() + "\n")

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

    def list_analyses(self) -> list[FrictionMeta]:
        """List all persisted analyses sorted by created_at descending.

        Returns:
            List of FrictionMeta objects.
        """
        if not self._meta_path.exists():
            return []

        analyses: list[FrictionMeta] = []
        for line in self._meta_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                analyses.append(FrictionMeta.model_validate_json(stripped))
            except (json.JSONDecodeError, ValueError):
                logger.warning("Skipping corrupt meta line: %s", stripped[:80])

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
        if not data_path.exists():
            return False
        data_path.unlink(missing_ok=True)
        self._rewrite_meta_without(analysis_id)
        logger.info("Deleted friction analysis %s", analysis_id)
        return True

    def _rewrite_meta_without(self, analysis_id: str) -> None:
        """Remove a single entry from the meta JSONL by rewriting.

        Args:
            analysis_id: ID to remove from meta.jsonl.
        """
        if not self._meta_path.exists():
            return
        lines = self._meta_path.read_text(encoding="utf-8").splitlines()
        kept = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("analysis_id") == analysis_id:
                    continue
            except json.JSONDecodeError:
                pass
            kept.append(stripped)
        self._meta_path.write_text("\n".join(kept) + "\n" if kept else "", encoding="utf-8")


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
        title=result.title,
        session_ids=result.session_ids,
        event_count=len(result.events),
        summary_preview=preview,
        created_at=result.created_at,
        model=result.model,
        cost_usd=result.cost_usd,
        batch_count=result.batch_count,
    )

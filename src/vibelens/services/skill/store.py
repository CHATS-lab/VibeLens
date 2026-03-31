"""Skill analysis result persistence.

Uses a single JSONL index file for metadata (fast listing) and
individual JSON files for full results (lazy loading).
"""

import json
import secrets
from pathlib import Path

from vibelens.models.skill.skills import SkillAnalysisResult
from vibelens.schemas.skills import SkillAnalysisMeta
from vibelens.utils.json_helpers import locked_jsonl_append, locked_jsonl_remove
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

TOKEN_BYTES = 12
SUMMARY_PREVIEW_LENGTH = 120
META_FILENAME = "index.jsonl"


class SkillAnalysisStore:
    """Manages persisted skill analysis results on disk.

    Metadata is stored in a single JSONL index file for efficient listing.
    Full results are stored in individual JSON files for lazy loading.
    """

    def __init__(self, store_dir: Path):
        self._dir = store_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._meta_path = self._dir / META_FILENAME
        self._migrate_legacy_meta_files()

    def _data_path(self, analysis_id: str) -> Path:
        return self._dir / f"{analysis_id}.json"

    def save(self, result: SkillAnalysisResult) -> SkillAnalysisMeta:
        """Persist an analysis result and append metadata to the JSONL index."""
        analysis_id = secrets.token_urlsafe(TOKEN_BYTES)
        result.analysis_id = analysis_id

        self._data_path(analysis_id).write_text(result.model_dump_json(indent=2), encoding="utf-8")

        meta = _build_meta(analysis_id, result)
        self._append_meta(meta)

        logger.info(
            "Saved skill analysis %s (mode=%s, %d patterns)",
            analysis_id,
            result.mode,
            len(result.workflow_patterns),
        )
        return meta

    def load(self, analysis_id: str) -> SkillAnalysisResult | None:
        """Load a full analysis result by ID."""
        path = self._data_path(analysis_id)
        if not path.exists():
            return None
        return SkillAnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))

    def list_analyses(self) -> list[SkillAnalysisMeta]:
        """List all analyses from the JSONL index, newest first."""
        if not self._meta_path.exists():
            return []
        analyses: list[SkillAnalysisMeta] = []
        for line in self._meta_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                meta = SkillAnalysisMeta.model_validate_json(line)
                analyses.append(meta)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Skipping corrupt meta line in %s", self._meta_path)
        analyses.sort(key=lambda m: m.created_at, reverse=True)
        return analyses

    def delete(self, analysis_id: str) -> bool:
        """Delete an analysis result and remove its entry from the JSONL index."""
        data_path = self._data_path(analysis_id)
        if not data_path.exists():
            return False
        data_path.unlink(missing_ok=True)
        self._remove_meta(analysis_id)
        logger.info("Deleted skill analysis %s", analysis_id)
        return True

    def _append_meta(self, meta: SkillAnalysisMeta) -> None:
        """Append one metadata record to the JSONL index."""
        locked_jsonl_append(self._meta_path, meta.model_dump(mode="json"))

    def _remove_meta(self, analysis_id: str) -> None:
        """Remove one entry from the JSONL index by rewriting without it."""
        locked_jsonl_remove(self._meta_path, "analysis_id", analysis_id)

    def _migrate_legacy_meta_files(self) -> None:
        """Migrate old per-analysis .meta.json files into the single JSONL index."""
        legacy_files = list(self._dir.glob("*.meta.json"))
        if not legacy_files:
            return
        for meta_file in legacy_files:
            try:
                meta = SkillAnalysisMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                self._append_meta(meta)
                meta_file.unlink()
            except (json.JSONDecodeError, ValueError):
                logger.warning("Skipping corrupt legacy meta file: %s", meta_file)
                meta_file.unlink(missing_ok=True)
        if legacy_files:
            logger.info("Migrated %d legacy .meta.json files to JSONL index", len(legacy_files))


def _build_meta(analysis_id: str, result: SkillAnalysisResult) -> SkillAnalysisMeta:
    """Build lightweight metadata from a full analysis result."""
    preview = result.summary[:SUMMARY_PREVIEW_LENGTH]
    if len(result.summary) > SUMMARY_PREVIEW_LENGTH:
        preview += "..."

    return SkillAnalysisMeta(
        analysis_id=analysis_id,
        mode=result.mode,
        session_ids=result.session_ids,
        pattern_count=len(result.workflow_patterns),
        summary_preview=preview,
        created_at=result.created_at,
        model=result.model,
        cost_usd=result.cost_usd,
    )

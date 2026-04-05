"""Generic JSONL-indexed analysis store.

Provides a reusable base class for persisting analysis results on disk:
a JSONL index file for fast metadata listing, and individual JSON files
for lazy-loading full results.
"""

import json
import secrets
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from vibelens.utils.json_helpers import locked_jsonl_append, locked_jsonl_remove
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

TOKEN_BYTES = 12
INDEX_FILENAME = "index.jsonl"


class AnalysisStore[ResultT: BaseModel, MetaT: BaseModel]:
    """Generic JSONL-indexed analysis store.

    Uses a single JSONL index file for metadata (fast listing) and
    individual JSON files for full results (lazy loading).

    Args:
        store_dir: Directory for persisted files. Created if missing.
        result_type: Pydantic model class for full results.
        meta_type: Pydantic model class for lightweight metadata.
        build_meta_fn: Callable(analysis_id, result) -> MetaT.
    """

    def __init__(
        self,
        store_dir: Path,
        result_type: type[ResultT],
        meta_type: type[MetaT],
        build_meta_fn: Callable[[str, ResultT], MetaT],
    ):
        self._dir = store_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._result_type = result_type
        self._meta_type = meta_type
        self._build_meta = build_meta_fn
        self._index_path = self._dir / INDEX_FILENAME

    def _data_path(self, analysis_id: str) -> Path:
        return self._dir / f"{analysis_id}.json"

    def save(self, result: ResultT) -> MetaT:
        """Persist a result and append metadata to the JSONL index."""
        analysis_id = secrets.token_urlsafe(TOKEN_BYTES)
        result.analysis_id = analysis_id  # type: ignore[attr-defined]

        self._data_path(analysis_id).write_text(result.model_dump_json(indent=2), encoding="utf-8")

        meta = self._build_meta(analysis_id, result)
        locked_jsonl_append(self._index_path, meta.model_dump(mode="json"))

        logger.info("Saved analysis %s to %s", analysis_id, self._dir.name)
        return meta

    def load(self, analysis_id: str) -> ResultT | None:
        """Load a full analysis result by ID."""
        path = self._data_path(analysis_id)
        if not path.exists():
            return None
        return self._result_type.model_validate_json(path.read_text(encoding="utf-8"))

    def list_analyses(self) -> list[MetaT]:
        """List all analyses from the JSONL index, newest first."""
        if not self._index_path.exists():
            return []
        analyses: list[MetaT] = []
        for line in self._index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                meta = self._meta_type.model_validate_json(line)
                analyses.append(meta)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Skipping corrupt meta line in %s", self._index_path)
        analyses.sort(key=lambda m: m.created_at, reverse=True)  # type: ignore[attr-defined]
        return analyses

    def delete(self, analysis_id: str) -> bool:
        """Delete an analysis result and remove its entry from the index."""
        data_path = self._data_path(analysis_id)
        if not data_path.exists():
            return False
        data_path.unlink(missing_ok=True)
        locked_jsonl_remove(self._index_path, "analysis_id", analysis_id)
        logger.info("Deleted analysis %s from %s", analysis_id, self._dir.name)
        return True

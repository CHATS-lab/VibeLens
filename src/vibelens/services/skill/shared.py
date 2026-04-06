"""Shared utilities for skill analysis services.

Constants, caching, skill gathering, pattern validation, and generic LLM
output parsing used by retrieval, creation, and evolvement modules.
"""

import hashlib
import json
from enum import Enum
from pathlib import Path

from cachetools import TTLCache
from pydantic import BaseModel, ValidationError

from vibelens.deps import get_central_skill_store
from vibelens.llm.backend import InferenceError
from vibelens.models.context import SessionContextBatch
from vibelens.models.skill import SkillMode, WorkflowPattern
from vibelens.services.analysis_shared import CACHE_MAXSIZE, CACHE_TTL_SECONDS
from vibelens.utils.json_extract import extract_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

SKILL_LOG_DIR = Path("logs/skill")

_cache: TTLCache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)


class SkillDetailLevel(Enum):
    """How much detail to include when gathering installed skills."""

    METADATA = "metadata"
    FULL = "full"


def skill_cache_key(session_ids: list[str], mode: SkillMode) -> str:
    """Generate a cache key from sorted session IDs and mode."""
    sorted_ids = ",".join(sorted(session_ids))
    raw = f"skill:{mode}:{sorted_ids}"
    return f"skill:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def gather_installed_skills(
    detail_level: SkillDetailLevel = SkillDetailLevel.METADATA,
) -> list[dict]:
    """Collect installed skill info from the central store.

    Args:
        detail_level: METADATA returns name+description only.
            FULL additionally loads the SKILL.md content for each skill.

    Returns:
        List of dicts with skill info at the requested detail level.
    """
    managed_store = get_central_skill_store()
    skills = managed_store.get_cached()

    if detail_level == SkillDetailLevel.METADATA:
        return [{"name": s.name, "description": s.description} for s in skills]

    return [
        {
            "name": s.name,
            "description": s.description,
            "content": managed_store.read_content(s.name) or "",
        }
        for s in skills
    ]


def validate_patterns(
    patterns: list[WorkflowPattern], context_set: SessionContextBatch
) -> list[WorkflowPattern]:
    """Resolve and validate workflow pattern step references against trajectories.

    Resolves 0-indexed step indices from LLM output to real UUIDs, then
    validates each ref against known trajectory steps.

    Args:
        patterns: Workflow patterns from LLM output.
        context_set: SessionContextBatch with step index maps and trajectory data.

    Returns:
        Patterns with resolved and validated example_refs.
    """
    validated: list[WorkflowPattern] = []
    for pattern in patterns:
        resolved_refs = [
            r
            for r in (context_set.resolve_step_ref(ref) for ref in pattern.example_refs)
            if r is not None
        ]
        pattern.example_refs = resolved_refs
        validated.append(pattern)
    return validated


def merge_batch_refs(
    synthesis_patterns: list[WorkflowPattern],
    batch_patterns_list: list[list[WorkflowPattern]],
) -> None:
    """Recover example_refs the synthesis LLM dropped.

    The synthesis LLM merges workflow patterns from multiple batches but
    typically returns empty example_refs. This function propagates refs
    from the original batch outputs into the synthesis patterns by matching
    on normalized title.

    Mutates synthesis_patterns in place. Only fills patterns whose
    example_refs are empty (preserves any refs the LLM did produce).

    Args:
        synthesis_patterns: Workflow patterns from synthesis output.
        batch_patterns_list: Per-batch workflow pattern lists with refs intact.
    """
    refs_by_title: dict[str, list] = {}
    for batch_patterns in batch_patterns_list:
        for pattern in batch_patterns:
            if not pattern.example_refs:
                continue
            key = pattern.title.strip().lower()
            refs_by_title.setdefault(key, []).extend(pattern.example_refs)

    merged_count = 0
    for pattern in synthesis_patterns:
        if pattern.example_refs:
            continue
        key = pattern.title.strip().lower()
        refs = refs_by_title.get(key)
        if refs:
            pattern.example_refs = list(refs)
            merged_count += 1

    if merged_count:
        logger.info(
            "Merged example_refs into %d/%d synthesis patterns",
            merged_count,
            len(synthesis_patterns),
        )


def parse_llm_output[ModelT: BaseModel](text: str, model_class: type[ModelT], label: str) -> ModelT:
    """Parse raw LLM text into a Pydantic model.

    Extracts JSON from the text, validates against the model schema,
    and raises InferenceError with a descriptive message on failure.

    Args:
        text: Raw LLM output text.
        model_class: Pydantic model class to validate against.
        label: Human-readable label for error messages (e.g. "retrieval").

    Returns:
        Validated model instance.

    Raises:
        InferenceError: If text is empty, not valid JSON, or fails validation.
    """
    if not text or not text.strip():
        raise InferenceError(f"LLM returned empty response for {label}.")

    json_str = extract_json(text)
    try:
        data = json.loads(json_str)
        return model_class.model_validate(data)
    except json.JSONDecodeError as exc:
        preview = json_str[:500] if len(json_str) > 500 else json_str
        raise InferenceError(
            f"{label} output is not valid JSON. Preview: {preview!r}. Error: {exc}"
        ) from exc
    except ValidationError as exc:
        raise InferenceError(
            f"{label} JSON does not match {model_class.__name__} schema: {exc}"
        ) from exc

"""Shared utilities for skill analysis services.

Constants, caching, skill gathering, pattern validation, and generic LLM
output parsing used by retrieval, creation, and evolvement modules.
"""

import hashlib
import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ValidationError

from vibelens.deps import get_central_skill_store
from vibelens.llm.backend import InferenceError
from vibelens.models.skill import SkillMode, WorkflowPattern
from vibelens.models.trajectories import Trajectory
from vibelens.services.analysis_shared import make_ttl_cache
from vibelens.utils.json_extract import extract_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

SKILL_LOG_DIR = Path("logs/skill")

_cache = make_ttl_cache()


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
    patterns: list[WorkflowPattern], trajectories: list[Trajectory]
) -> list[WorkflowPattern]:
    """Validate workflow pattern step references against loaded trajectories."""
    valid_step_ids = {step.step_id for t in trajectories for step in t.steps}
    validated: list[WorkflowPattern] = []
    for pattern in patterns:
        filtered_refs = [
            ref
            for ref in pattern.example_refs
            if ref.start_step_id in valid_step_ids
            and (ref.end_step_id is None or ref.end_step_id in valid_step_ids)
        ]
        pattern.example_refs = filtered_refs
        validated.append(pattern)
    return validated


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

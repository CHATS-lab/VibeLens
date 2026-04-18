"""Shared utilities for personalization services.

Constants, caching, skill gathering, pattern validation, and generic LLM
output parsing used by creation and evolvement modules.
"""

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

from cachetools import TTLCache
from pydantic import BaseModel, ValidationError

from vibelens.deps import get_skill_service
from vibelens.llm.backend import InferenceError
from vibelens.models.context import SessionContextBatch
from vibelens.models.personalization.enums import PersonalizationMode
from vibelens.models.session.patterns import WorkflowPattern
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.inference_shared import CACHE_MAXSIZE, CACHE_TTL_SECONDS
from vibelens.utils.json import extract_json_from_llm_output
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

# Shared TTL cache for personalization analysis results (keyed by session IDs + mode).
# Consumed by creation and evolution services to avoid re-running identical analyses.
_cache: TTLCache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)

_VALID_JSON_ESCAPES = set('"\\/bfnrtu')
_INVALID_ESCAPE_RE = re.compile(r"\\(.)")


def _repair_json_escapes(json_str: str) -> str:
    """Escape stray backslashes that LLMs sometimes emit inside JSON strings.

    LLMs (especially when generating SKILL.md content containing code, LaTeX,
    or regex patterns) often produce invalid escapes like ``\\_`` or ``\\&``
    that make ``json.loads`` fail. This helper scans for ``\\X`` sequences
    where X is not a recognised JSON escape character and doubles the
    backslash to ``\\\\X``, letting the parser accept the text.

    Args:
        json_str: JSON text that failed strict parsing.

    Returns:
        JSON text with invalid escapes repaired to literal backslashes.
    """

    def _fix(match: re.Match) -> str:
        char = match.group(1)
        if char in _VALID_JSON_ESCAPES:
            return match.group(0)
        return "\\\\" + char

    return _INVALID_ESCAPE_RE.sub(_fix, json_str)


class SkillDetailLevel(Enum):
    """How much detail to include when gathering installed skills."""

    METADATA = "metadata"
    FULL = "full"


def personalization_cache_key(session_ids: list[str], mode: PersonalizationMode) -> str:
    """Generate a cache key from sorted session IDs and mode."""
    sorted_ids = ",".join(sorted(session_ids))
    raw = f"personalization:{mode}:{sorted_ids}"
    return f"personalization:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _canonical_session_id(raw_id: str) -> str:
    """Strip the ``__partN`` suffix used when a session is split across digests."""
    base, sep, _ = raw_id.partition("__")
    return base if sep else raw_id


def resolve_proposal_session_ids(
    proposal_session_ids: list[str], loaded_session_ids: list[str]
) -> list[str]:
    """Map a proposal's cited UUIDs back to the loaded session set.

    Canonicalizes ``uuid__partN`` suffixes on both sides, then intersects
    with the loaded set to drop any hallucinated or unknown IDs. Falls
    back to the full loaded set when the proposal cites none or every
    cited ID is unknown.

    Args:
        proposal_session_ids: UUIDs cited by the proposal LLM.
        loaded_session_ids: UUIDs successfully loaded for analysis.

    Returns:
        Deduplicated list of canonical UUIDs that exist in the loaded set.
    """
    if not proposal_session_ids:
        return list(loaded_session_ids)

    loaded_canonical = {_canonical_session_id(sid) for sid in loaded_session_ids}
    seen: set[str] = set()
    relevant: list[str] = []
    for raw_id in proposal_session_ids:
        canonical = _canonical_session_id(raw_id)
        if canonical in seen or canonical not in loaded_canonical:
            continue
        seen.add(canonical)
        relevant.append(canonical)

    if not relevant:
        logger.warning(
            "Proposal session_ids %s do not match any loaded session; "
            "falling back to all loaded sessions.",
            proposal_session_ids,
        )
        return list(loaded_session_ids)
    return relevant


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
    service = get_skill_service()
    skills, _ = service.list_items(page_size=9999)

    if detail_level == SkillDetailLevel.METADATA:
        return [{"name": s.name, "description": s.description} for s in skills]

    result: list[dict] = []
    for s in skills:
        try:
            content = service.get_item_content(s.name)
        except FileNotFoundError:
            content = ""
        result.append({"name": s.name, "description": s.description, "content": content})
    return result


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


async def reduce_batch_results(
    batch_results: list[tuple[ModelT, Metrics]],
    synthesize: Callable[[list[tuple[ModelT, Metrics]]], Awaitable[tuple[ModelT, Metrics]]],
) -> tuple[ModelT, list[Metrics]]:
    """Collapse per-batch outputs into one: return single directly, else synthesize.

    Shared post-inference reducer for creation/evolution proposal flows.
    When batches > 1 the synthesis call is delegated to the caller so each
    service can pass its own prompt, output model, and any extra context
    (e.g. installed_skills). After synthesis, ``merge_batch_refs`` is applied
    to recover ``example_refs`` the synthesis LLM typically drops.

    Args:
        batch_results: Per-batch outputs and metrics. Must be non-empty.
        synthesize: Async callable that merges multi-batch outputs. Invoked
            only when more than one batch succeeded.

    Returns:
        Tuple of (final output, cumulative metrics list). The list contains
        one entry per batch, plus the synthesis metrics when synthesized.
    """
    all_metrics: list[Metrics] = [m for _, m in batch_results]
    if len(batch_results) == 1:
        return batch_results[0][0], all_metrics

    merged_output, syn_metrics = await synthesize(batch_results)
    all_metrics.append(syn_metrics)
    merge_batch_refs(
        merged_output.workflow_patterns,
        [output.workflow_patterns for output, _ in batch_results],
    )
    return merged_output, all_metrics


def merge_batch_refs(
    synthesis_patterns: list[WorkflowPattern], batch_patterns_list: list[list[WorkflowPattern]]
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


def parse_llm_output(
    text: str,
    model_class: type[ModelT],
    label: str,
    field_fallbacks: dict[str, object] | None = None,
) -> ModelT:
    """Parse raw LLM text into a Pydantic model.

    Extracts JSON from the text, validates against the model schema,
    and raises InferenceError with a descriptive message on failure.

    Args:
        text: Raw LLM output text.
        model_class: Pydantic model class to validate against.
        label: Human-readable label for error messages (e.g. "retrieval").
        field_fallbacks: Optional mapping of field names to fallback values
            applied only when that key is missing from the parsed JSON.
            Used to recover from LLMs that occasionally drop required fields.

    Returns:
        Validated model instance.

    Raises:
        InferenceError: If text is empty, not valid JSON, or fails validation.
    """
    if not text or not text.strip():
        raise InferenceError(f"LLM returned empty response for {label}.")

    json_str = extract_json_from_llm_output(text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed for %s at %s; retrying with escape repair", label, exc)
        try:
            data = json.loads(_repair_json_escapes(json_str))
        except json.JSONDecodeError as retry_exc:
            preview = json_str[:500] if len(json_str) > 500 else json_str
            raise InferenceError(
                f"{label} output is not valid JSON (even after escape repair). "
                f"Preview: {preview!r}. Error: {retry_exc}"
            ) from retry_exc

    if field_fallbacks and isinstance(data, dict):
        for key, fallback in field_fallbacks.items():
            if key not in data:
                logger.warning("LLM omitted %s in %s output; filling with fallback", key, label)
                data[key] = fallback

    try:
        return model_class.model_validate(data)
    except ValidationError as exc:
        raise InferenceError(
            f"{label} JSON does not match {model_class.__name__} schema: {exc}"
        ) from exc

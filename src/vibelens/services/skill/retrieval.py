"""Skill retrieval mode — recommend existing skills from the featured catalog.

Contains shared infrastructure (caching, session loading, parsing, validation)
used by all three skill analysis modes.
"""

import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from vibelens.deps import (
    get_central_skill_store,
    get_inference_backend,
    get_skill_analysis_store,
)
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.prompts.skill_retrieval import SKILL_RETRIEVAL_PROMPT
from vibelens.models.inference import InferenceRequest
from vibelens.models.prompts import AnalysisPrompt
from vibelens.models.skill.skills import (
    SkillAnalysisResult,
    SkillLLMOutput,
    SkillMode,
    WorkflowPattern,
)
from vibelens.models.trajectories import Trajectory
from vibelens.services.friction.signals import build_step_signals
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    load_from_stores,
)
from vibelens.services.skill.digest import digest_step_signals_for_skills
from vibelens.utils.json_extract import extract_json as _extract_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 3600
FEATURED_SKILLS_PATH = Path(__file__).resolve().parents[4] / "featured-skills.json"
CANDIDATE_PREFILTER_THRESHOLD = 200
PREFILTER_TOP_K = 100
SKILL_LOG_DIR = Path("logs/skill")

_cache: dict[str, tuple[float, BaseModel]] = {}


async def analyze_retrieval(
    session_ids: list[str], session_token: str | None = None
) -> SkillAnalysisResult:
    """Run retrieval-mode skill analysis: recommend existing skills from catalog."""
    cache_key = _skill_cache_key(session_ids, SkillMode.RETRIEVAL)
    cached = _get_cached(cache_key)
    if cached:
        return cached

    backend = _require_backend()
    loaded_trajectories, loaded_ids, skipped_ids = _load_sessions(session_ids, session_token)

    if not loaded_trajectories:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    signals = build_step_signals(loaded_trajectories)
    digest = digest_step_signals_for_skills(signals)

    prompt = SKILL_RETRIEVAL_PROMPT
    installed_skills = _gather_installed_skills()
    user_prompt = _render_retrieval_prompt(prompt, digest, len(loaded_ids), installed_skills)

    system_prompt = prompt.render_system()
    request = InferenceRequest(
        system=system_prompt, user=user_prompt, json_schema=prompt.output_model.model_json_schema()
    )
    _log_prompt(system_prompt, user_prompt, loaded_ids, SkillMode.RETRIEVAL)

    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = SKILL_LOG_DIR / run_timestamp
    _save_skill_log(log_dir, "retrieval_system.txt", system_prompt)
    _save_skill_log(log_dir, "retrieval_user.txt", user_prompt)

    result = await backend.generate(request)
    _log_response(result.text, loaded_ids, SkillMode.RETRIEVAL)
    _save_skill_log(log_dir, "retrieval_output.txt", result.text)

    llm_output = _parse_llm_output(result.text)
    validated_patterns = _validate_patterns(llm_output.workflow_patterns, loaded_trajectories)

    skill_result = _build_result(
        SkillMode.RETRIEVAL,
        validated_patterns,
        llm_output,
        loaded_ids,
        skipped_ids,
        backend,
        result.cost_usd,
    )
    get_skill_analysis_store().save(skill_result)

    _cache[cache_key] = (time.monotonic(), skill_result)
    return skill_result


def _render_retrieval_prompt(
    prompt: AnalysisPrompt, digest: str, session_count: int, installed_skills: list[dict]
) -> str:
    """Render retrieval-specific user prompt with skill candidates."""
    output_schema = json.dumps(prompt.output_model.model_json_schema(), indent=2)
    skill_candidates = _load_skill_candidates()
    if len(skill_candidates) > CANDIDATE_PREFILTER_THRESHOLD:
        skill_candidates = _prefilter_candidates(skill_candidates, digest)
    return prompt.render_user(
        session_count=session_count,
        session_digest=digest,
        output_schema=output_schema,
        installed_skills=installed_skills if installed_skills else None,
        skill_candidates=skill_candidates if skill_candidates else None,
    )


def _load_skill_candidates() -> list[dict]:
    """Load skill candidates from the featured skills catalog.

    Returns a list of dicts with name, summary, and tags for each candidate.
    The LLM picks from these candidates when recommending skills.
    """
    if not FEATURED_SKILLS_PATH.is_file():
        return []
    try:
        raw = FEATURED_SKILLS_PATH.read_text(encoding="utf-8")
        catalog = json.loads(raw)
        return [
            {
                "name": entry.get("slug", entry.get("name", "")),
                "summary": entry.get("summary", ""),
                "tags": entry.get("tags", []),
            }
            for entry in catalog.get("skills", [])
            if entry.get("summary")
        ]
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load featured skills catalog for retrieval candidates")
        return []


def _prefilter_candidates(candidates: list[dict], digest: str) -> list[dict]:
    """Keyword-based pre-filtering for large skill catalogs.

    Extracts keywords from the digest (tool names, user topics, alpha tokens)
    and scores each candidate by keyword overlap in name + summary + tags.

    Args:
        candidates: Full list of skill candidate dicts.
        digest: Session digest text used for keyword extraction.

    Returns:
        Top PREFILTER_TOP_K candidates sorted by relevance score.
    """
    keywords = _extract_digest_keywords(digest)
    if not keywords:
        return candidates[:PREFILTER_TOP_K]

    scored: list[tuple[int, dict]] = []
    for candidate in candidates:
        searchable = " ".join(
            [
                candidate.get("name", ""),
                candidate.get("summary", ""),
                " ".join(candidate.get("tags", [])),
            ]
        ).lower()
        score = sum(1 for kw in keywords if kw in searchable)
        scored.append((score, candidate))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in scored[:PREFILTER_TOP_K]]


def _extract_digest_keywords(digest: str) -> set[str]:
    """Extract keywords from a session digest for candidate matching.

    Pulls tool names from "TOOL FREQUENCY:" blocks, user topics,
    and alpha tokens longer than 3 characters.

    Args:
        digest: Session digest text.

    Returns:
        Set of lowercase keywords.
    """
    keywords: set[str] = set()

    # Extract tool names from TOOL FREQUENCY lines (e.g. "  Edit: 15")
    for match in re.finditer(r"^\s+(\w+):\s+\d+", digest, re.MULTILINE):
        keywords.add(match.group(1).lower())

    # Extract user topics from USER TOPICS lines
    topic_match = re.search(r"USER TOPICS:\s*(.+)", digest)
    if topic_match:
        topic_text = topic_match.group(1)
        for token in re.findall(r"[a-zA-Z]{4,}", topic_text):
            keywords.add(token.lower())

    # Extract general alpha tokens from fn= tool calls
    for match in re.finditer(r"fn=(\w+)", digest):
        keywords.add(match.group(1).lower())

    return keywords


# Shared infrastructure used by all modes
def _skill_cache_key(session_ids: list[str], mode: SkillMode) -> str:
    sorted_ids = ",".join(sorted(session_ids))
    raw = f"skill:{mode}:{sorted_ids}"
    return f"skill:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _require_backend() -> InferenceBackend:
    backend = get_inference_backend()
    if not backend:
        raise ValueError("No inference backend configured. Set llm.backend in config.")
    return backend


def _load_sessions(
    session_ids: list[str], session_token: str | None
) -> tuple[list[Trajectory], list[str], list[str]]:
    loaded_trajectories: list[Trajectory] = []
    loaded_ids: list[str] = []
    skipped_ids: list[str] = []
    for sid in session_ids:
        if get_metadata_from_stores(sid, session_token) is None:
            skipped_ids.append(sid)
            continue
        trajectories = load_from_stores(sid, session_token)
        if not trajectories:
            skipped_ids.append(sid)
            continue
        loaded_trajectories.extend(trajectories)
        loaded_ids.append(sid)
    return loaded_trajectories, loaded_ids, skipped_ids


def _gather_installed_skills() -> list[dict]:
    """Collect installed skill metadata from the central store."""
    managed_store = get_central_skill_store()
    skills = managed_store.get_cached()
    return [
        {
            "name": s.name,
            "description": s.description,
            "skill_targets": [target.value for target in s.skill_targets],
            "sources": [
                {"source_type": source.source_type.value, "source_path": source.source_path}
                for source in s.sources
            ],
        }
        for s in skills
    ]


def _parse_llm_output(text: str) -> SkillLLMOutput:
    if not text or not text.strip():
        raise InferenceError(
            "LLM returned empty response. Check logs for the prompt that was sent."
        )

    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
        return SkillLLMOutput.model_validate(data)
    except json.JSONDecodeError as exc:
        preview = json_str[:500] if len(json_str) > 500 else json_str
        raise InferenceError(
            f"LLM output is not valid JSON. Preview: {preview!r}. Error: {exc}"
        ) from exc
    except ValidationError as exc:
        raise InferenceError(f"LLM JSON does not match SkillLLMOutput schema: {exc}") from exc


def _validate_patterns(
    patterns: list[WorkflowPattern], trajectories: list[Trajectory]
) -> list[WorkflowPattern]:
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


def _build_result(
    mode: SkillMode,
    validated_patterns: list[WorkflowPattern],
    llm_output: SkillLLMOutput,
    loaded_ids: list[str],
    skipped_ids: list[str],
    backend: InferenceBackend,
    cost_usd: float | None,
) -> SkillAnalysisResult:
    """Build a SkillAnalysisResult from common fields."""
    return SkillAnalysisResult(
        mode=mode,
        workflow_patterns=validated_patterns,
        recommendations=llm_output.recommendations,
        generated_skills=llm_output.generated_skills,
        evolution_suggestions=llm_output.evolution_suggestions,
        summary=llm_output.summary,
        user_profile=llm_output.user_profile,
        session_ids=loaded_ids,
        sessions_skipped=skipped_ids,
        backend_id=backend.backend_id,
        model=backend.model,
        cost_usd=cost_usd,
        created_at=datetime.now(UTC).isoformat(),
    )


def _log_prompt(system: str, user: str, session_ids: list[str], mode: SkillMode) -> None:
    logger.debug(
        "Skill analysis prompt mode=%s sessions=%s system=%r user=%r",
        mode,
        session_ids,
        system,
        user,
    )


def _log_response(text: str, session_ids: list[str], mode: SkillMode) -> None:
    logger.debug("Skill analysis response mode=%s sessions=%s text=%r", mode, session_ids, text)


def _save_skill_log(log_dir: Path, filename: str, content: str) -> None:
    """Save skill analysis log to a timestamped directory.

    Args:
        log_dir: Target directory.
        filename: File name within the directory.
        content: Text content to write.
    """
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / filename).write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to save skill log %s/%s: %s", log_dir, filename, exc)


def _get_cached(cache_key: str) -> SkillAnalysisResult | None:
    entry = _cache.get(cache_key)
    if not entry:
        return None
    cached_at, result = entry
    if time.monotonic() - cached_at > CACHE_TTL_SECONDS:
        del _cache[cache_key]
        return None
    return result if isinstance(result, SkillAnalysisResult) else None

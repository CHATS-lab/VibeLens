"""Skill analysis service — LLM-powered workflow pattern detection and skill recommendations.

Pipeline: load sessions -> build signals -> digest -> gather context ->
select prompt by mode -> infer -> validate -> persist -> cache.
"""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from vibelens.analysis.step_signals import build_step_signals
from vibelens.deps import (
    get_central_skill_store,
    get_inference_backend,
    get_skill_analysis_store,
    get_store,
    is_demo_mode,
)
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.prompts.skill_creation import SKILL_CREATION_PROMPT
from vibelens.llm.prompts.skill_evolution import SKILL_EVOLUTION_PROMPT
from vibelens.llm.prompts.skill_retrieval import SKILL_RETRIEVAL_PROMPT
from vibelens.models.analysis.prompts import AnalysisPrompt
from vibelens.models.analysis.skills import (
    SkillAnalysisResult,
    SkillLLMOutput,
    SkillMode,
    WorkflowPattern,
)
from vibelens.models.inference import InferenceRequest
from vibelens.models.trajectories import Trajectory
from vibelens.services.skill.digest import digest_step_signals_for_skills
from vibelens.services.upload_visibility import is_session_visible
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 3600
FEATURED_SKILLS_PATH = Path(__file__).resolve().parents[3] / "featured-skills.json"

_cache: dict[str, tuple[float, BaseModel]] = {}

PROMPT_BY_MODE: dict[SkillMode, AnalysisPrompt] = {
    SkillMode.RETRIEVAL: SKILL_RETRIEVAL_PROMPT,
    SkillMode.CREATION: SKILL_CREATION_PROMPT,
    SkillMode.EVOLUTION: SKILL_EVOLUTION_PROMPT,
}


async def analyze_skills(
    session_ids: list[str], mode: SkillMode, session_token: str | None = None
) -> SkillAnalysisResult:
    """Run LLM-powered skill analysis across specified sessions."""
    cache_key = _skill_cache_key(session_ids, mode)
    cached = _get_cached(cache_key)
    if cached:
        return cached

    backend = _require_backend()
    loaded_trajectories, loaded_ids, skipped_ids = _load_sessions(session_ids, session_token)

    if not loaded_trajectories:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    signals = build_step_signals(loaded_trajectories)
    digest = digest_step_signals_for_skills(signals)

    prompt = PROMPT_BY_MODE[mode]
    installed_skills = _gather_installed_skills()
    user_prompt = _render_user_prompt(prompt, digest, len(loaded_ids), installed_skills, mode)

    system_prompt = prompt.render_system()
    request = InferenceRequest(system=system_prompt, user=user_prompt)
    _log_prompt(system_prompt, user_prompt, loaded_ids, mode)

    result = await backend.generate(request)
    _log_response(result.text, loaded_ids, mode)

    llm_output = _parse_llm_output(result.text)
    validated_patterns = _validate_patterns(llm_output.workflow_patterns, loaded_trajectories)

    skill_result = SkillAnalysisResult(
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
        model=_get_backend_model(backend),
        cost_usd=result.cost_usd,
        created_at=datetime.now(UTC).isoformat(),
    )
    get_skill_analysis_store().save(skill_result)

    _cache[cache_key] = (time.monotonic(), skill_result)
    return skill_result


def _skill_cache_key(session_ids: list[str], mode: SkillMode) -> str:
    sorted_ids = ",".join(sorted(session_ids))
    raw = f"skill:{mode}:{sorted_ids}"
    return f"skill:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _require_backend() -> InferenceBackend:
    backend = get_inference_backend()
    if not backend:
        raise ValueError("No inference backend configured. Set llm.backend in config.")
    return backend


def _get_backend_model(backend: InferenceBackend) -> str:
    """Extract model name from a backend instance."""
    if hasattr(backend, "_model"):
        return backend._model or "unknown"
    return "unknown"


def _load_sessions(
    session_ids: list[str], session_token: str | None
) -> tuple[list[Trajectory], list[str], list[str]]:
    store = get_store()
    demo = is_demo_mode()
    loaded_trajectories: list[Trajectory] = []
    loaded_ids: list[str] = []
    skipped_ids: list[str] = []
    for sid in session_ids:
        if demo and not is_session_visible(store.get_metadata(sid), session_token):
            skipped_ids.append(sid)
            continue
        trajectories = store.load(sid)
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


def _gather_installed_skill_contents() -> list[dict]:
    """Collect installed skills with full SKILL.md content for evolution mode."""
    managed_store = get_central_skill_store()
    skills = managed_store.get_cached()
    result = []
    for skill_info in skills:
        content = managed_store.read_content(skill_info.name)
        result.append({
            "name": skill_info.name,
            "description": skill_info.description,
            "content": content or "",
        })
    return result


def _load_skill_candidates() -> list[dict]:
    """Load skill candidates from the featured skills catalog for retrieval mode.

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


def _render_user_prompt(
    prompt: AnalysisPrompt,
    digest: str,
    session_count: int,
    installed_skills: list[dict],
    mode: SkillMode,
) -> str:
    """Render the user prompt with mode-specific template variables."""
    output_schema = json.dumps(prompt.output_model.model_json_schema(), indent=2)

    if mode == SkillMode.RETRIEVAL:
        skill_candidates = _load_skill_candidates()
        return prompt.render_user(
            session_count=session_count,
            session_digest=digest,
            output_schema=output_schema,
            installed_skills=installed_skills if installed_skills else None,
            skill_candidates=skill_candidates if skill_candidates else None,
        )

    if mode == SkillMode.EVOLUTION:
        # Evolution needs full skill content to suggest granular edits
        skill_contents = _gather_installed_skill_contents()
        return prompt.render_user(
            session_count=session_count,
            session_digest=digest,
            output_schema=output_schema,
            installed_skills=skill_contents,
        )

    # Creation mode: only needs installed skill names to avoid duplicates
    return prompt.render_user(
        session_count=session_count,
        session_digest=digest,
        output_schema=output_schema,
        installed_skills=installed_skills if installed_skills else None,
    )


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


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        start = 1
        end = len(lines) - 1
        while end > start and not lines[end].strip().startswith("```"):
            end -= 1
        return "\n".join(lines[start:end])
    return stripped


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


def _get_cached(cache_key: str) -> SkillAnalysisResult | None:
    entry = _cache.get(cache_key)
    if not entry:
        return None
    cached_at, result = entry
    if time.monotonic() - cached_at > CACHE_TTL_SECONDS:
        del _cache[cache_key]
        return None
    return result if isinstance(result, SkillAnalysisResult) else None

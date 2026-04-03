"""Skill evolvement mode — suggest improvements to existing installed skills."""

import json
import time
from datetime import UTC, datetime

from vibelens.deps import get_central_skill_store, get_skill_analysis_store
from vibelens.llm.prompts.skill_evolution import SKILL_EVOLUTION_PROMPT
from vibelens.models.inference import InferenceRequest
from vibelens.models.prompts import AnalysisPrompt
from vibelens.models.skill.skills import SkillAnalysisResult, SkillMode
from vibelens.services.friction.signals import build_step_signals
from vibelens.services.skill.digest import digest_step_signals_for_skills
from vibelens.services.skill.retrieval import (
    SKILL_LOG_DIR,
    _build_result,
    _cache,
    _get_cached,
    _load_sessions,
    _log_prompt,
    _log_response,
    _parse_llm_output,
    _require_backend,
    _save_skill_log,
    _skill_cache_key,
    _validate_patterns,
)


async def analyze_evolvement(
    session_ids: list[str], session_token: str | None = None
) -> SkillAnalysisResult:
    """Run evolvement-mode skill analysis: suggest improvements to installed skills."""
    cache_key = _skill_cache_key(session_ids, SkillMode.EVOLUTION)
    cached = _get_cached(cache_key)
    if cached:
        return cached

    backend = _require_backend()
    loaded_trajectories, loaded_ids, skipped_ids = _load_sessions(session_ids, session_token)

    if not loaded_trajectories:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    signals = build_step_signals(loaded_trajectories)
    digest = digest_step_signals_for_skills(signals)

    prompt = SKILL_EVOLUTION_PROMPT
    skill_contents = _gather_installed_skill_contents()
    user_prompt = _render_evolvement_prompt(prompt, digest, len(loaded_ids), skill_contents)

    system_prompt = prompt.render_system()
    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        json_schema=prompt.output_model.model_json_schema(),
    )
    _log_prompt(system_prompt, user_prompt, loaded_ids, SkillMode.EVOLUTION)

    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = SKILL_LOG_DIR / run_timestamp
    _save_skill_log(log_dir, "evolvement_system.txt", system_prompt)
    _save_skill_log(log_dir, "evolvement_user.txt", user_prompt)

    result = await backend.generate(request)
    _log_response(result.text, loaded_ids, SkillMode.EVOLUTION)
    _save_skill_log(log_dir, "evolvement_output.txt", result.text)

    llm_output = _parse_llm_output(result.text)
    validated_patterns = _validate_patterns(llm_output.workflow_patterns, loaded_trajectories)

    skill_result = _build_result(
        SkillMode.EVOLUTION,
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


def _gather_installed_skill_contents() -> list[dict]:
    """Collect installed skills with full SKILL.md content for evolution mode."""
    managed_store = get_central_skill_store()
    skills = managed_store.get_cached()
    result = []
    for skill_info in skills:
        content = managed_store.read_content(skill_info.name)
        result.append(
            {
                "name": skill_info.name,
                "description": skill_info.description,
                "content": content or "",
            }
        )
    return result


def _render_evolvement_prompt(
    prompt: AnalysisPrompt, digest: str, session_count: int, installed_skills: list[dict]
) -> str:
    """Render evolvement-specific user prompt with full skill content."""
    output_schema = json.dumps(prompt.output_model.model_json_schema(), indent=2)
    return prompt.render_user(
        session_count=session_count,
        session_digest=digest,
        output_schema=output_schema,
        installed_skills=installed_skills,
    )

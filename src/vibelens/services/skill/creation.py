"""Skill creation mode — two-step pipeline: proposals then deep creation.

Pipeline:
1. analyze_proposals: load sessions → extract contexts → batch → concurrent
   LLM proposal calls → optional synthesis → SkillProposalResult
2. deep_create_skill: single LLM call per approved proposal → SkillCreation
3. analyze_creation: backward-compat wrapper calling both steps
"""

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from vibelens.deps import get_skill_analysis_store
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.prompts.skill_deep_creation import SKILL_DEEP_CREATION_PROMPT
from vibelens.llm.prompts.skill_proposal import (
    SKILL_PROPOSAL_PROMPT,
    SKILL_PROPOSAL_SYNTHESIS_PROMPT,
)
from vibelens.models.inference import InferenceRequest
from vibelens.models.skill.skills import (
    SkillAnalysisResult,
    SkillCreation,
    SkillDeepCreationOutput,
    SkillMode,
    SkillProposalOutput,
    SkillProposalResult,
)
from vibelens.services.context_extraction import SessionContext, extract_session_context
from vibelens.services.friction.digest import format_batch_digest
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    load_from_stores,
)
from vibelens.services.session_batcher import SessionBatch, build_batches
from vibelens.services.skill.retrieval import (
    SKILL_LOG_DIR,
    _cache,
    _gather_installed_skills,
    _get_cached,
    _require_backend,
    _save_skill_log,
    _skill_cache_key,
    _validate_patterns,
)
from vibelens.utils.json_extract import extract_json as _extract_json
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

PROPOSAL_OUTPUT_TOKENS = 4096
PROPOSAL_TIMEOUT_SECONDS = 300
PROPOSAL_SYNTHESIS_OUTPUT_TOKENS = 8192
PROPOSAL_SYNTHESIS_TIMEOUT_SECONDS = 120
PROPOSAL_CACHE_TTL_SECONDS = 3600
DEEP_CREATION_OUTPUT_TOKENS = 4096
DEEP_CREATION_TIMEOUT_SECONDS = 120

# Proposal pipeline internals
_proposal_cache: dict[str, tuple[float, SkillProposalResult]] = {}


async def analyze_creation(
    session_ids: list[str], session_token: str | None = None
) -> SkillAnalysisResult:
    """Backward-compatible creation: proposals then deep creation for each.

    Preserves the existing POST /skills/analysis endpoint with mode=creation.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        SkillAnalysisResult with generated_skills populated.
    """
    cache_key = _skill_cache_key(session_ids, SkillMode.CREATION)
    cached = _get_cached(cache_key)
    if cached:
        return cached

    # Step 1: Generate proposals
    proposal_result = await analyze_proposals(session_ids, session_token)

    # Step 2: Deep create each proposal concurrently
    creation_tasks = [
        deep_create_skill(
            proposal_name=p.name,
            proposal_description=p.description,
            proposal_rationale=p.rationale,
            addressed_patterns=p.addressed_patterns,
            session_ids=session_ids,
            session_token=session_token,
        )
        for p in proposal_result.proposals
    ]

    generated_skills: list[SkillCreation] = []
    creation_warnings: list[str] = list(proposal_result.warnings)
    if creation_tasks:
        results = await asyncio.gather(*creation_tasks, return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, SkillCreation):
                generated_skills.append(result)
            else:
                name = proposal_result.proposals[idx].name
                creation_warnings.append(f"Deep creation failed for '{name}': {result}")
                logger.warning("Deep creation failed for proposal '%s': %s", name, result)

    skill_result = SkillAnalysisResult(
        mode=SkillMode.CREATION,
        workflow_patterns=proposal_result.workflow_patterns,
        generated_skills=generated_skills,
        summary=proposal_result.summary,
        user_profile=proposal_result.user_profile,
        session_ids=proposal_result.session_ids,
        sessions_skipped=proposal_result.sessions_skipped,
        warnings=creation_warnings,
        backend_id=proposal_result.backend_id,
        model=proposal_result.model,
        cost_usd=proposal_result.cost_usd,
        created_at=datetime.now(UTC).isoformat(),
    )
    get_skill_analysis_store().save(skill_result)

    _cache[cache_key] = (time.monotonic(), skill_result)
    return skill_result


async def analyze_proposals(
    session_ids: list[str], session_token: str | None = None
) -> SkillProposalResult:
    """Run the proposal step: detect patterns and generate lightweight proposals.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        SkillProposalResult with proposals and metadata.

    Raises:
        ValueError: If no sessions could be loaded or no backend configured.
        InferenceError: If LLM backend fails.
    """
    cache_key = _skill_cache_key(session_ids, SkillMode.CREATION) + ":proposals"
    cached = _get_cached_proposals(cache_key)
    if cached:
        return cached

    backend = _require_backend()
    contexts, loaded_ids, skipped_ids = _extract_all_contexts(session_ids, session_token)

    if not contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    batches = build_batches(contexts)
    logger.info("Skill proposals: %d sessions → %d batch(es)", len(loaded_ids), len(batches))

    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = SKILL_LOG_DIR / run_timestamp

    installed_skills = _gather_installed_skills()

    batch_results, batch_warnings = await _run_proposal_batches(
        backend, batches, installed_skills, log_dir
    )

    total_cost = sum(cost for _, cost in batch_results)

    # Single batch: use directly; multiple batches: synthesize
    if len(batch_results) == 1:
        proposal_output = batch_results[0][0]
    else:
        proposal_output, syn_cost = await _synthesize_proposals(
            backend, batch_results, len(loaded_ids), log_dir
        )
        total_cost += syn_cost

    # Collect all trajectories for pattern validation
    all_trajectories = []
    for ctx in contexts:
        all_trajectories.extend(ctx.trajectory_group)

    validated_patterns = _validate_patterns(proposal_output.workflow_patterns, all_trajectories)

    result = SkillProposalResult(
        session_ids=loaded_ids,
        workflow_patterns=validated_patterns,
        proposals=proposal_output.proposals,
        summary=proposal_output.summary,
        user_profile=proposal_output.user_profile,
        sessions_skipped=skipped_ids,
        warnings=batch_warnings,
        backend_id=backend.backend_id,
        model=backend.model,
        cost_usd=total_cost if total_cost > 0 else None,
        batch_count=len(batches),
        created_at=datetime.now(UTC).isoformat(),
    )

    _proposal_cache[cache_key] = (time.monotonic(), result)
    return result


async def deep_create_skill(
    proposal_name: str,
    proposal_description: str,
    proposal_rationale: str,
    addressed_patterns: list[str],
    session_ids: list[str],
    session_token: str | None = None,
) -> SkillCreation:
    """Generate full SKILL.md content for one approved proposal.

    Args:
        proposal_name: Kebab-case skill name.
        proposal_description: One-line trigger description.
        proposal_rationale: Why this skill would improve workflow.
        addressed_patterns: Pattern titles this proposal addresses.
        session_ids: Sessions to use as evidence.
        session_token: Browser tab token for upload scoping.

    Returns:
        SkillCreation with full SKILL.md content.

    Raises:
        ValueError: If no sessions could be loaded or no backend configured.
        InferenceError: If LLM backend fails.
    """
    backend = _require_backend()
    contexts, loaded_ids, skipped_ids = _extract_all_contexts(session_ids, session_token)

    if not contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    # Build digest from all contexts (no batching needed for single-skill creation)
    digest = _build_digest_from_contexts(contexts)
    installed_skills = _gather_installed_skills()

    output_schema = json.dumps(
        SKILL_DEEP_CREATION_PROMPT.output_model.model_json_schema(), indent=2
    )
    system_prompt = SKILL_DEEP_CREATION_PROMPT.render_system()
    user_prompt = SKILL_DEEP_CREATION_PROMPT.render_user(
        proposal_name=proposal_name,
        proposal_description=proposal_description,
        proposal_rationale=proposal_rationale,
        addressed_patterns=addressed_patterns,
        session_digest=digest,
        installed_skills=installed_skills if installed_skills else None,
        output_schema=output_schema,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=DEEP_CREATION_OUTPUT_TOKENS,
        timeout=DEEP_CREATION_TIMEOUT_SECONDS,
        json_schema=SKILL_DEEP_CREATION_PROMPT.output_model.model_json_schema(),
    )

    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = SKILL_LOG_DIR / run_timestamp
    _save_skill_log(log_dir, "deep_creation_system.txt", system_prompt)
    _save_skill_log(log_dir, "deep_creation_user.txt", user_prompt)

    result = await backend.generate(request)
    _save_skill_log(log_dir, "deep_creation_output.txt", result.text)

    deep_output = _parse_deep_creation_output(result.text)

    return SkillCreation(
        name=deep_output.name,
        description=deep_output.description,
        skill_md_content=deep_output.skill_md_content,
        rationale=deep_output.rationale,
    )


def _get_cached_proposals(cache_key: str) -> SkillProposalResult | None:
    """Return cached proposal result if still valid."""
    entry = _proposal_cache.get(cache_key)
    if not entry:
        return None
    cached_at, result = entry
    if time.monotonic() - cached_at > PROPOSAL_CACHE_TTL_SECONDS:
        del _proposal_cache[cache_key]
        return None
    return result


def _extract_all_contexts(
    session_ids: list[str], session_token: str | None
) -> tuple[list[SessionContext], list[str], list[str]]:
    """Load sessions and extract compressed contexts.

    Args:
        session_ids: Sessions to load.
        session_token: Browser tab token for upload scoping.

    Returns:
        Tuple of (session_contexts, loaded_ids, skipped_ids).
    """
    contexts: list[SessionContext] = []
    loaded_ids: list[str] = []
    skipped_ids: list[str] = []

    for sid in session_ids:
        if get_metadata_from_stores(sid, session_token) is None:
            skipped_ids.append(sid)
            continue
        try:
            trajectories = load_from_stores(sid, session_token)
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Failed to load session %s, skipping: %s", sid, exc)
            skipped_ids.append(sid)
            continue
        if not trajectories:
            skipped_ids.append(sid)
            continue

        ctx = extract_session_context(trajectories)
        contexts.append(ctx)
        loaded_ids.append(sid)

    return contexts, loaded_ids, skipped_ids


async def _infer_proposal_batch(
    backend: InferenceBackend,
    batch: SessionBatch,
    installed_skills: list[dict],
    log_dir: Path,
    batch_index: int,
) -> tuple[SkillProposalOutput, float]:
    """Run LLM inference for one proposal batch.

    Args:
        backend: Configured inference backend.
        batch: Session batch with pre-extracted contexts.
        installed_skills: Already-installed skills to avoid duplicates.
        log_dir: Timestamped directory for saving prompts and outputs.
        batch_index: Zero-based batch index for file naming.

    Returns:
        Tuple of (parsed proposal output, cost in USD).
    """
    digest = format_batch_digest(batch)
    session_count = len(batch.session_contexts)
    output_schema = json.dumps(SKILL_PROPOSAL_PROMPT.output_model.model_json_schema(), indent=2)

    system_prompt = SKILL_PROPOSAL_PROMPT.render_system()
    user_prompt = SKILL_PROPOSAL_PROMPT.render_user(
        session_count=session_count,
        session_digest=digest,
        output_schema=output_schema,
        installed_skills=installed_skills if installed_skills else None,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=PROPOSAL_OUTPUT_TOKENS,
        timeout=PROPOSAL_TIMEOUT_SECONDS,
        json_schema=SKILL_PROPOSAL_PROMPT.output_model.model_json_schema(),
    )

    if batch_index == 0:
        _save_skill_log(log_dir, "proposal_system.txt", system_prompt)
    _save_skill_log(log_dir, f"proposal_user_{batch_index}.txt", user_prompt)

    result = await backend.generate(request)
    _save_skill_log(log_dir, f"proposal_output_{batch_index}.txt", result.text)

    proposal_output = _parse_proposal_output(result.text)
    cost = result.cost_usd or 0.0
    return proposal_output, cost


async def _run_proposal_batches(
    backend: InferenceBackend,
    batches: list[SessionBatch],
    installed_skills: list[dict],
    log_dir: Path,
) -> tuple[list[tuple[SkillProposalOutput, float]], list[str]]:
    """Run all proposal batches concurrently, tolerating individual failures.

    Args:
        backend: Configured inference backend.
        batches: List of session batches.
        installed_skills: Already-installed skills.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (successful results, warning messages).

    Raises:
        InferenceError: If every batch fails.
    """
    tasks = [
        _infer_proposal_batch(backend, batch, installed_skills, log_dir, idx)
        for idx, batch in enumerate(batches)
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    successes: list[tuple[SkillProposalOutput, float]] = []
    warnings: list[str] = []
    for idx, result in enumerate(raw_results):
        if isinstance(result, BaseException):
            warnings.append(f"Batch {idx + 1}/{len(batches)} failed: {result}")
            logger.warning("Proposal batch %d failed: %s", idx, result)
        else:
            successes.append(result)

    if not successes:
        raise InferenceError(
            f"All {len(batches)} proposal batch(es) failed. Last error: {raw_results[-1]}"
        )

    return successes, warnings


async def _synthesize_proposals(
    backend: InferenceBackend,
    batch_results: list[tuple[SkillProposalOutput, float]],
    session_count: int,
    log_dir: Path,
) -> tuple[SkillProposalOutput, float]:
    """Merge proposals from multiple batches via LLM synthesis.

    Args:
        backend: Configured inference backend.
        batch_results: Per-batch proposal outputs and costs.
        session_count: Total number of sessions analyzed.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (merged SkillProposalOutput, synthesis cost in USD).
    """
    batch_data = [
        {
            "summary": output.summary,
            "user_profile": output.user_profile,
            "workflow_patterns": [
                {"title": p.title, "description": p.description, "pain_point": p.pain_point}
                for p in output.workflow_patterns
            ],
            "proposals": [
                {
                    "name": p.name,
                    "description": p.description,
                    "rationale": p.rationale,
                    "addressed_patterns": p.addressed_patterns,
                }
                for p in output.proposals
            ],
        }
        for output, _ in batch_results
    ]

    output_schema = json.dumps(
        SKILL_PROPOSAL_SYNTHESIS_PROMPT.output_model.model_json_schema(), indent=2
    )
    system_prompt = SKILL_PROPOSAL_SYNTHESIS_PROMPT.render_system()
    user_prompt = SKILL_PROPOSAL_SYNTHESIS_PROMPT.render_user(
        batch_count=len(batch_results),
        session_count=session_count,
        batch_results=batch_data,
        output_schema=output_schema,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=PROPOSAL_SYNTHESIS_OUTPUT_TOKENS,
        timeout=PROPOSAL_SYNTHESIS_TIMEOUT_SECONDS,
        json_schema=SKILL_PROPOSAL_SYNTHESIS_PROMPT.output_model.model_json_schema(),
    )

    _save_skill_log(log_dir, "proposal_synthesis_system.txt", system_prompt)
    _save_skill_log(log_dir, "proposal_synthesis_user.txt", user_prompt)

    result = await backend.generate(request)
    _save_skill_log(log_dir, "proposal_synthesis_output.txt", result.text)

    synthesis_output = _parse_proposal_output(result.text)
    cost = result.cost_usd or 0.0
    return synthesis_output, cost


def _build_digest_from_contexts(contexts: list[SessionContext]) -> str:
    """Build a single digest string from session contexts.

    Args:
        contexts: Extracted session contexts.

    Returns:
        Concatenated context text.
    """
    if not contexts:
        return "[no sessions]"
    return "\n\n".join(ctx.context_text for ctx in contexts)


def _parse_proposal_output(text: str) -> SkillProposalOutput:
    """Parse LLM output text into SkillProposalOutput.

    Args:
        text: Raw LLM output text.

    Returns:
        Validated SkillProposalOutput instance.

    Raises:
        InferenceError: If parsing or validation fails.
    """
    if not text or not text.strip():
        raise InferenceError("LLM returned empty response for skill proposals.")

    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
        return SkillProposalOutput.model_validate(data)
    except json.JSONDecodeError as exc:
        preview = json_str[:500] if len(json_str) > 500 else json_str
        raise InferenceError(
            f"Proposal output is not valid JSON. Preview: {preview!r}. Error: {exc}"
        ) from exc
    except ValidationError as exc:
        raise InferenceError(
            f"Proposal JSON does not match SkillProposalOutput schema: {exc}"
        ) from exc


def _parse_deep_creation_output(text: str) -> SkillDeepCreationOutput:
    """Parse LLM output text into SkillDeepCreationOutput.

    Args:
        text: Raw LLM output text.

    Returns:
        Validated SkillDeepCreationOutput instance.

    Raises:
        InferenceError: If parsing or validation fails.
    """
    if not text or not text.strip():
        raise InferenceError("LLM returned empty response for deep skill creation.")

    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
        return SkillDeepCreationOutput.model_validate(data)
    except json.JSONDecodeError as exc:
        preview = json_str[:500] if len(json_str) > 500 else json_str
        raise InferenceError(
            f"Deep creation output is not valid JSON. Preview: {preview!r}. Error: {exc}"
        ) from exc
    except ValidationError as exc:
        raise InferenceError(
            f"Deep creation JSON does not match SkillDeepCreationOutput schema: {exc}"
        ) from exc



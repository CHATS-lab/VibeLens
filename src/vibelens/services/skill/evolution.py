"""Skill evolution mode — propose improvements then edit existing skills.

Two-step pipeline (mirrors creation):
1. _infer_skill_evolution_proposals: batch → concurrent LLM proposal calls
   → optional synthesis → SkillEvolutionProposalOutput
2. _infer_skill_evolution: single LLM call per proposal → SkillEvolution
3. analyze_skill_evolution: orchestrator calling both steps
"""

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

from vibelens.deps import get_skill_analysis_store
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.prompts.skill_evolution import (
    SKILL_EVOLUTION_EDIT_PROMPT,
    SKILL_EVOLUTION_PROPOSAL_PROMPT,
    SKILL_EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT,
)
from vibelens.models.inference import InferenceRequest
from vibelens.models.skill import (
    SkillAnalysisResult,
    SkillEvolution,
    SkillEvolutionProposalOutput,
    SkillEvolutionProposalResult,
    SkillMode,
)
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.analysis_shared import (
    build_digest_from_contexts,
    build_system_kwargs,
    extract_all_contexts,
    require_backend,
    run_batches_concurrent,
    save_analysis_log,
    truncate_digest_to_fit,
)
from vibelens.services.context_params import PRESET_MEDIUM
from vibelens.services.friction.digest import format_batch_digest
from vibelens.services.session_batcher import SessionBatch, build_batches
from vibelens.services.skill.shared import (
    SKILL_LOG_DIR,
    SkillDetailLevel,
    _cache,
    gather_installed_skills,
    parse_llm_output,
    skill_cache_key,
    validate_patterns,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

SKILL_EVOLUTION_PROPOSAL_OUTPUT_TOKENS = 4096
SKILL_EVOLUTION_PROPOSAL_TIMEOUT_SECONDS = 300
SKILL_EVOLUTION_SYNTHESIS_OUTPUT_TOKENS = 8192
SKILL_EVOLUTION_SYNTHESIS_TIMEOUT_SECONDS = 300
SKILL_EVOLUTION_EDIT_OUTPUT_TOKENS = 8192
SKILL_EVOLUTION_EDIT_TIMEOUT_SECONDS = 300


async def analyze_skill_evolution(
    session_ids: list[str], session_token: str | None = None
) -> SkillAnalysisResult:
    """Run evolvement-mode skill analysis: propose then deep-edit installed skills.

    Two-step pipeline:
    1. Generate evolution proposals (batched, with optional synthesis)
    2. Deep-edit each proposed skill concurrently (full SKILL.md + evidence)

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        SkillAnalysisResult with evolutions populated.
    """
    cache_key = skill_cache_key(session_ids, SkillMode.EVOLUTION)
    if cache_key in _cache:
        return _cache[cache_key]

    start_time = time.monotonic()
    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = SKILL_LOG_DIR / run_timestamp

    # Step 1: Generate proposals
    proposal_result = await _infer_skill_evolution_proposals(session_ids, session_token, log_dir)

    proposal_names = [p.skill_name for p in proposal_result.proposal_output.proposals]
    logger.info("Evolution proposals: %s", proposal_names)

    # Step 2: Deep-edit each proposal concurrently
    edit_tasks = [
        _infer_skill_evolution(
            skill_name=p.skill_name,
            rationale=p.rationale,
            suggested_changes=p.suggested_changes,
            session_ids=session_ids,
            session_token=session_token,
            proposal_confidence=p.confidence,
            log_dir=log_dir,
            proposal_index=idx,
        )
        for idx, p in enumerate(proposal_result.proposal_output.proposals)
    ]

    evolutions: list[SkillEvolution] = []
    edit_warnings: list[str] = list(proposal_result.warnings)
    total_cost = proposal_result.metrics.cost_usd or 0.0

    if edit_tasks:
        results = await asyncio.gather(*edit_tasks, return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, tuple):
                evolution, cost = result
                evolutions.append(evolution)
                total_cost += cost
            else:
                name = proposal_result.proposal_output.proposals[idx].skill_name
                edit_warnings.append(f"Deep edit failed for '{name}': {result}")
                logger.warning("Deep edit failed for proposal '%s': %s", name, result)

    duration = round(time.monotonic() - start_time, 2)
    proposal_output = proposal_result.proposal_output
    skill_result = SkillAnalysisResult(
        mode=SkillMode.EVOLUTION,
        title=proposal_output.title,
        workflow_patterns=proposal_output.workflow_patterns,
        evolutions=evolutions,
        summary=proposal_output.summary,
        user_profile=proposal_output.user_profile,
        session_ids=proposal_result.session_ids,
        skipped_session_ids=proposal_result.skipped_session_ids,
        warnings=edit_warnings,
        backend_id=proposal_result.backend_id,
        model=proposal_result.model,
        metrics=Metrics(cost_usd=total_cost if total_cost > 0 else None),
        duration_seconds=duration,
        batch_count=proposal_result.batch_count,
        created_at=datetime.now(UTC).isoformat(),
    )
    get_skill_analysis_store().save(skill_result)

    _cache[cache_key] = skill_result
    return skill_result


async def _infer_skill_evolution_proposals(
    session_ids: list[str], session_token: str | None, log_dir: Path
) -> SkillEvolutionProposalResult:
    """Execute the proposal step: load sessions, batch, infer, validate.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.
        log_dir: Shared log directory for saving prompts and outputs.

    Returns:
        SkillEvolutionProposalResult with nested proposal_output and metadata.

    Raises:
        ValueError: If no sessions could be loaded or no installed skills found.
        InferenceError: If LLM backend fails.
    """
    backend = require_backend()
    contexts, loaded_ids, skipped_ids = extract_all_contexts(
        session_ids, session_token, PRESET_MEDIUM
    )

    if not contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    installed_skills = gather_installed_skills()
    if not installed_skills:
        raise ValueError("No installed skills found for evolution analysis.")

    batches = build_batches(contexts)
    logger.info("Evolution proposals: %d sessions → %d batch(es)", len(loaded_ids), len(batches))

    tasks = [
        _infer_skill_evolution_proposal_batch(backend, batch, installed_skills, log_dir, idx)
        for idx, batch in enumerate(batches)
    ]
    batch_results, batch_warnings = await run_batches_concurrent(tasks, "evolution_proposal")

    total_cost = sum(cost for _, cost in batch_results)

    # Single batch: use directly; multiple batches: synthesize
    if len(batch_results) == 1:
        proposal_output = batch_results[0][0]
    else:
        proposal_output, syn_cost = await _synthesize_skill_evolution_proposals(
            backend, batch_results, len(loaded_ids), log_dir
        )
        total_cost += syn_cost

    # Validate pattern refs against real step IDs
    all_trajectories = []
    for ctx in contexts:
        all_trajectories.extend(ctx.trajectory_group)
    validated_patterns = validate_patterns(proposal_output.workflow_patterns, all_trajectories)

    final_output = SkillEvolutionProposalOutput(
        title=proposal_output.title,
        user_profile=proposal_output.user_profile,
        workflow_patterns=validated_patterns,
        summary=proposal_output.summary,
        proposals=proposal_output.proposals,
    )

    return SkillEvolutionProposalResult(
        session_ids=loaded_ids,
        skipped_session_ids=skipped_ids,
        warnings=batch_warnings,
        backend_id=backend.backend_id,
        model=backend.model,
        metrics=Metrics(cost_usd=total_cost if total_cost > 0 else None),
        batch_count=len(batches),
        created_at=datetime.now(UTC).isoformat(),
        proposal_output=final_output,
    )


async def _infer_skill_evolution(
    skill_name: str,
    rationale: str,
    suggested_changes: str,
    session_ids: list[str],
    session_token: str | None = None,
    proposal_confidence: float = 0.0,
    log_dir: Path | None = None,
    proposal_index: int | None = None,
) -> tuple[SkillEvolution, float]:
    """Generate granular edits for one existing skill.

    Args:
        skill_name: Name of the installed skill to evolve.
        rationale: Why this skill should be evolved.
        suggested_changes: High-level description of proposed changes.
        session_ids: Sessions to use as evidence.
        session_token: Browser tab token for upload scoping.
        proposal_confidence: Confidence from proposal step (0.0-1.0).
        log_dir: Shared log directory. Created if None.
        proposal_index: Index for log file naming.

    Returns:
        Tuple of (SkillEvolution, cost in USD).
    """
    backend = require_backend()
    contexts, loaded_ids, skipped_ids = extract_all_contexts(
        session_ids, session_token, PRESET_MEDIUM
    )

    if not contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    # Load full SKILL.md content for the target skill
    all_skills = gather_installed_skills(SkillDetailLevel.FULL)
    target_skill = next((s for s in all_skills if s["name"] == skill_name), None)
    if not target_skill:
        raise ValueError(f"Skill '{skill_name}' not found in installed skills.")

    digest = build_digest_from_contexts(contexts)

    system_kwargs = build_system_kwargs(SKILL_EVOLUTION_EDIT_PROMPT.output_model, backend)
    system_prompt = SKILL_EVOLUTION_EDIT_PROMPT.render_system(**system_kwargs)

    # Truncate digest to fit context budget
    non_digest_overhead = SKILL_EVOLUTION_EDIT_PROMPT.render_user(
        skill_name=skill_name,
        rationale=rationale,
        suggested_changes=suggested_changes,
        skill_content=target_skill["content"],
        session_digest="",
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = SKILL_EVOLUTION_EDIT_PROMPT.render_user(
        skill_name=skill_name,
        rationale=rationale,
        suggested_changes=suggested_changes,
        skill_content=target_skill["content"],
        session_digest=digest,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_EVOLUTION_EDIT_OUTPUT_TOKENS,
        timeout=SKILL_EVOLUTION_EDIT_TIMEOUT_SECONDS,
        json_schema=SKILL_EVOLUTION_EDIT_PROMPT.output_model.model_json_schema(),
    )

    if log_dir is None:
        run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        log_dir = SKILL_LOG_DIR / run_timestamp

    suffix = f"_{proposal_index}" if proposal_index is not None else ""
    save_analysis_log(log_dir, f"deep_edit{suffix}_system.txt", system_prompt)
    save_analysis_log(log_dir, f"deep_edit{suffix}_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, f"deep_edit{suffix}_output.txt", result.text)

    evolution = parse_llm_output(result.text, SkillEvolution, "deep edit")
    evolution.confidence = proposal_confidence
    cost = result.cost_usd or 0.0
    return evolution, cost


async def _infer_skill_evolution_proposal_batch(
    backend: InferenceBackend,
    batch: SessionBatch,
    installed_skills: list[dict],
    log_dir: Path,
    batch_index: int,
) -> tuple[SkillEvolutionProposalOutput, float]:
    """Run LLM inference for one evolution proposal batch.

    Args:
        backend: Configured inference backend.
        batch: Session batch with pre-extracted contexts.
        installed_skills: Installed skill metadata (name + description).
        log_dir: Timestamped directory for saving prompts and outputs.
        batch_index: Zero-based batch index for file naming.

    Returns:
        Tuple of (parsed proposal output, cost in USD).
    """
    digest = format_batch_digest(batch)
    session_count = len(batch.session_contexts)

    prompt = SKILL_EVOLUTION_PROPOSAL_PROMPT
    system_kwargs = build_system_kwargs(prompt.output_model, backend)
    system_prompt = prompt.render_system(**system_kwargs)

    # Truncate digest to fit context budget
    non_digest_overhead = prompt.render_user(
        session_count=session_count,
        session_digest="",
        installed_skills=installed_skills,
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = prompt.render_user(
        session_count=session_count,
        session_digest=digest,
        installed_skills=installed_skills,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_EVOLUTION_PROPOSAL_OUTPUT_TOKENS,
        timeout=SKILL_EVOLUTION_PROPOSAL_TIMEOUT_SECONDS,
        json_schema=prompt.output_model.model_json_schema(),
    )

    if batch_index == 0:
        save_analysis_log(log_dir, "evolution_proposal_system.txt", system_prompt)
    save_analysis_log(log_dir, f"evolution_proposal_user_{batch_index}.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, f"evolution_proposal_output_{batch_index}.txt", result.text)

    proposal_output = parse_llm_output(
        result.text, SkillEvolutionProposalOutput, "evolution proposal"
    )
    cost = result.cost_usd or 0.0
    return proposal_output, cost


async def _synthesize_skill_evolution_proposals(
    backend: InferenceBackend,
    batch_results: list[tuple[SkillEvolutionProposalOutput, float]],
    session_count: int,
    log_dir: Path,
) -> tuple[SkillEvolutionProposalOutput, float]:
    """Merge evolution proposals from multiple batches via LLM synthesis.

    Args:
        backend: Configured inference backend.
        batch_results: Per-batch proposal outputs and costs.
        session_count: Total number of sessions analyzed.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (merged SkillEvolutionProposalOutput, synthesis cost in USD).
    """
    batch_data = [
        {
            "title": output.title,
            "summary": output.summary,
            "user_profile": output.user_profile,
            "workflow_patterns": [
                {
                    "title": p.title,
                    "description": p.description,
                    "gap": p.gap,
                    "example_refs": [ref.model_dump(exclude_none=True) for ref in p.example_refs],
                }
                for p in output.workflow_patterns
            ],
            "proposals": [
                {
                    "skill_name": p.skill_name,
                    "rationale": p.rationale,
                    "suggested_changes": p.suggested_changes,
                    "addressed_patterns": p.addressed_patterns,
                }
                for p in output.proposals
            ],
        }
        for output, _ in batch_results
    ]

    prompt = SKILL_EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT
    system_kwargs = build_system_kwargs(prompt.output_model, backend)
    system_prompt = prompt.render_system(**system_kwargs)
    user_prompt = prompt.render_user(
        batch_count=len(batch_results),
        session_count=session_count,
        batch_results=batch_data,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_EVOLUTION_SYNTHESIS_OUTPUT_TOKENS,
        timeout=SKILL_EVOLUTION_SYNTHESIS_TIMEOUT_SECONDS,
        json_schema=prompt.output_model.model_json_schema(),
    )

    save_analysis_log(log_dir, "evolution_proposal_synthesis_system.txt", system_prompt)
    save_analysis_log(log_dir, "evolution_proposal_synthesis_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, "evolution_proposal_synthesis_output.txt", result.text)

    synthesis_output = parse_llm_output(
        result.text, SkillEvolutionProposalOutput, "evolution proposal synthesis"
    )
    cost = result.cost_usd or 0.0
    return synthesis_output, cost

"""Skill evolution mode — propose improvements then evolve existing skills.

Two-step pipeline (mirrors creation):
1. _infer_evolution_proposals: batch → concurrent LLM proposal calls
   → optional synthesis → EvolutionProposalBatch
2. _infer_skill_evolution: single LLM call per proposal → PersonalizationEvolution
3. analyze_skill_evolution: orchestrator calling both steps
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from vibelens.context import DetailExtractor, SummaryExtractor, build_batches
from vibelens.deps import get_personalization_store, get_settings
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContextBatch
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.personalization.enums import PersonalizationMode
from vibelens.models.personalization.evolution import (
    EvolutionProposalBatch,
    EvolutionProposalResult,
    PersonalizationEvolution,
)
from vibelens.models.personalization.results import PersonalizationResult
from vibelens.models.trajectories.final_metrics import FinalMetrics
from vibelens.prompts.evolution import (
    EVOLUTION_PROMPT,
    EVOLUTION_PROPOSAL_PROMPT,
    EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT,
)
from vibelens.services.analysis_store import generate_analysis_id
from vibelens.services.inference_shared import (
    build_system_kwargs,
    extract_all_contexts,
    format_context_batch,
    log_inference_summary,
    require_backend,
    run_batches_concurrent,
    save_inference_log,
    truncate_digest_to_fit,
)
from vibelens.services.personalization.shared import (
    PERSONALIZATION_LOG_DIR,
    SkillDetailLevel,
    _cache,
    gather_installed_skills,
    merge_batch_refs,
    parse_llm_output,
    personalization_cache_key,
    validate_patterns,
)
from vibelens.utils.log import clear_analysis_id, get_logger, set_analysis_id

logger = get_logger(__name__)

# LLM inference limits for each step of the skill evolution pipeline
EVOLUTION_PROPOSAL_OUTPUT_TOKENS = 4096
EVOLUTION_PROPOSAL_TIMEOUT_SECONDS = 300
EVOLUTION_SYNTHESIS_OUTPUT_TOKENS = 8192
EVOLUTION_SYNTHESIS_TIMEOUT_SECONDS = 300
EVOLUTION_OUTPUT_TOKENS = 8192
EVOLUTION_TIMEOUT_SECONDS = 300
# Number of sequential LLM calls in the full pipeline (proposal → synthesis → evolution)
EXPECTED_EVOLUTION_CALLS = 3


def _filter_skills(
    skills: list[dict[str, str]], skill_names: list[str] | None
) -> list[dict[str, str]]:
    """Filter installed skills to only those the user selected.

    Args:
        skills: All installed skills (dicts with 'name' key).
        skill_names: User-selected names. None means keep all.

    Returns:
        Filtered skill list.
    """
    if not skill_names:
        return skills
    allowed = set(skill_names)
    return [s for s in skills if s["name"] in allowed]


def estimate_skill_evolution(
    session_ids: list[str], session_token: str | None = None, skill_names: list[str] | None = None
) -> CostEstimate:
    """Pre-flight cost estimate for skill evolution analysis.

    Estimates the full pipeline: proposal batches + synthesis + evolution
    for an expected number of proposals.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.
        skill_names: Skill names to target. None means all installed skills.

    Returns:
        CostEstimate with projected cost range.

    Raises:
        ValueError: If no sessions could be loaded or no installed skills.
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, extractor=SummaryExtractor()
    )
    if not context_set:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    installed_skills = _filter_skills(gather_installed_skills(), skill_names)
    if not installed_skills:
        raise ValueError("No installed skills found for evolution analysis.")

    max_input = get_settings().inference.max_input_tokens
    batches = build_batches(context_set.contexts, max_batch_tokens=max_input)

    # Proposal phase tokens
    proposal_system = EVOLUTION_PROPOSAL_PROMPT.render_system(
        **build_system_kwargs(EVOLUTION_PROPOSAL_PROMPT, backend)
    )
    batch_token_counts = [count_tokens(format_context_batch(batch)) for batch in batches]

    # Evolution phase tokens (estimated per-call)
    evolution_kwargs = build_system_kwargs(EVOLUTION_PROMPT, backend)
    evolution_system = EVOLUTION_PROMPT.render_system(**evolution_kwargs)
    digest = format_context_batch(context_set)
    deep_input_tokens = count_tokens(evolution_system) + count_tokens(digest)
    extra_calls = [
        (deep_input_tokens, EVOLUTION_OUTPUT_TOKENS) for _ in range(EXPECTED_EVOLUTION_CALLS)
    ]

    return estimate_analysis_cost(
        batch_token_counts=batch_token_counts,
        system_prompt=proposal_system,
        model=backend.model,
        max_output_tokens=EVOLUTION_PROPOSAL_OUTPUT_TOKENS,
        synthesis_output_tokens=EVOLUTION_SYNTHESIS_OUTPUT_TOKENS,
        synthesis_threshold=1,
        extra_calls=extra_calls,
    )


async def analyze_skill_evolution(
    session_ids: list[str], session_token: str | None = None, skill_names: list[str] | None = None
) -> PersonalizationResult:
    """Run evolvement-mode skill analysis: propose then evolve installed skills.

    Two-step pipeline:
    1. Generate evolution proposals (batched, with optional synthesis)
    2. Evolve each proposed skill concurrently (full SKILL.md + evidence)

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.
        skill_names: Skill names to target. None means all installed skills.

    Returns:
        PersonalizationResult with evolutions populated.
    """
    cache_key = personalization_cache_key(session_ids, PersonalizationMode.EVOLUTION)
    if cache_key in _cache:
        return _cache[cache_key]

    analysis_id = generate_analysis_id()
    set_analysis_id(analysis_id)

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = PERSONALIZATION_LOG_DIR / run_timestamp

    # Step 1: Generate proposals (filtered to user-selected skills)
    proposal_result = await _infer_evolution_proposals(
        session_ids, session_token, log_dir, skill_names
    )

    # Deduplicate: keep only the first proposal per element_name
    seen_skills: set[str] = set()
    unique_proposals = []
    for p in proposal_result.proposal_batch.proposals:
        if p.element_name in seen_skills:
            logger.warning("Dropping duplicate proposal for skill '%s'", p.element_name)
            continue
        seen_skills.add(p.element_name)
        unique_proposals.append(p)
    proposal_result.proposal_batch.proposals = unique_proposals

    proposal_names = [p.element_name for p in unique_proposals]
    logger.info("Evolution proposals: %s", proposal_names)

    # Step 2: Generate evolutions concurrently
    evolution_tasks = []
    for idx, p in enumerate(unique_proposals):
        # Filter to only relevant sessions when indices are specified
        if p.session_indices:
            relevant_ids = [
                proposal_result.session_ids[i]
                for i in p.session_indices
                if i < len(proposal_result.session_ids)
            ]
        else:
            relevant_ids = session_ids
        evolution_tasks.append(
            _infer_evolution(
                skill_name=p.element_name,
                rationale=p.rationale,
                suggested_changes=p.rationale,
                addressed_patterns=p.addressed_patterns,
                session_ids=relevant_ids,
                session_token=session_token,
                proposal_confidence=p.confidence,
                log_dir=log_dir,
                proposal_index=idx,
            )
        )

    evolutions: list[PersonalizationEvolution] = []
    warnings: list[str] = list(proposal_result.warnings)
    total_cost = proposal_result.final_metrics.total_cost_usd or 0.0

    if evolution_tasks:
        results = await asyncio.gather(*evolution_tasks, return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, tuple):
                evolution, cost = result
                evolutions.append(evolution)
                total_cost += cost
            else:
                name = proposal_result.proposal_batch.proposals[idx].element_name
                warnings.append(f"Evolution failed for '{name}': {result}")
                logger.warning("Evolution failed for proposal '%s': %s", name, result)

    proposal_output = proposal_result.proposal_batch
    skill_result = PersonalizationResult(
        id=analysis_id,
        mode=PersonalizationMode.EVOLUTION,
        title=proposal_output.title,
        workflow_patterns=proposal_output.workflow_patterns,
        evolutions=evolutions,
        session_ids=proposal_result.session_ids,
        skipped_session_ids=proposal_result.skipped_session_ids,
        warnings=warnings,
        backend=proposal_result.backend,
        model=proposal_result.model,
        final_metrics=FinalMetrics(total_cost_usd=total_cost if total_cost > 0 else None),
        batch_count=proposal_result.batch_count,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    get_personalization_store().save(skill_result, analysis_id)
    clear_analysis_id()

    _cache[cache_key] = skill_result
    return skill_result


async def _infer_evolution_proposals(
    session_ids: list[str],
    session_token: str | None,
    log_dir: Path,
    skill_names: list[str] | None = None,
) -> EvolutionProposalResult:
    """Execute the proposal step: load sessions, batch, infer, validate.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.
        log_dir: Shared log directory for saving prompts and outputs.
        skill_names: Skill names to target. None means all installed skills.

    Returns:
        EvolutionProposalResult with nested proposal_batch and metadata.

    Raises:
        ValueError: If no sessions could be loaded or no installed skills found.
        InferenceError: If LLM backend fails.
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, extractor=SummaryExtractor()
    )

    if not context_set:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    installed_skills = _filter_skills(gather_installed_skills(), skill_names)
    if not installed_skills:
        raise ValueError("No installed skills found for evolution analysis.")

    max_input = get_settings().inference.max_input_tokens
    batches = build_batches(context_set.contexts, max_batch_tokens=max_input)
    logger.info(
        "Evolution proposals: %d sessions → %d batch(es)",
        len(context_set.session_ids),
        len(batches),
    )
    log_inference_summary(context_set, batches, backend)

    tasks = [
        _infer_evolution_proposal_batch(backend, batch, installed_skills, log_dir, idx)
        for idx, batch in enumerate(batches)
    ]
    batch_results, batch_warnings = await run_batches_concurrent(tasks, "evolution_proposal")

    total_cost = sum(cost for _, cost in batch_results)

    # Single batch: use directly; multiple batches: synthesize
    if len(batch_results) == 1:
        proposal_output = batch_results[0][0]
    else:
        proposal_output, syn_cost = await _synthesize_evolution_proposals(
            backend, batch_results, len(context_set.session_ids), log_dir
        )
        total_cost += syn_cost
        # Synthesis LLM drops example_refs; recover from batch outputs
        merge_batch_refs(
            proposal_output.workflow_patterns,
            [output.workflow_patterns for output, _ in batch_results],
        )

    validated_patterns = validate_patterns(proposal_output.workflow_patterns, context_set)

    final_output = EvolutionProposalBatch(
        title=proposal_output.title,
        workflow_patterns=validated_patterns,
        proposals=proposal_output.proposals,
    )

    return EvolutionProposalResult(
        session_ids=context_set.session_ids,
        skipped_session_ids=context_set.skipped_session_ids,
        warnings=batch_warnings,
        backend=backend.backend_id,
        model=backend.model,
        final_metrics=FinalMetrics(total_cost_usd=total_cost if total_cost > 0 else None),
        batch_count=len(batches),
        created_at=datetime.now(timezone.utc).isoformat(),
        proposal_batch=final_output,
    )


async def _infer_evolution(
    skill_name: str,
    rationale: str,
    suggested_changes: str,
    addressed_patterns: list[str],
    session_ids: list[str],
    session_token: str | None = None,
    proposal_confidence: float = 0.0,
    log_dir: Path | None = None,
    proposal_index: int | None = None,
) -> tuple[PersonalizationEvolution, float]:
    """Generate granular evolutions for one existing skill.

    Args:
        skill_name: Name of the installed skill to evolve.
        rationale: Why this skill should be evolved.
        suggested_changes: High-level description of proposed changes.
        addressed_patterns: Pattern titles this evolution addresses.
        session_ids: Sessions to use as evidence.
        session_token: Browser tab token for upload scoping.
        proposal_confidence: Confidence from proposal step (0.0-1.0).
        log_dir: Shared log directory. Created if None.
        proposal_index: Index for log file naming.

    Returns:
        Tuple of (PersonalizationEvolution, cost in USD).
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, extractor=DetailExtractor()
    )

    if not context_set:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    # Load full SKILL.md content for the target skill
    all_skills = gather_installed_skills(SkillDetailLevel.FULL)
    target_skill = next((s for s in all_skills if s["name"] == skill_name), None)
    if not target_skill:
        raise ValueError(f"Skill '{skill_name}' not found in installed skills.")

    digest = format_context_batch(context_set)

    system_kwargs = build_system_kwargs(EVOLUTION_PROMPT, backend)
    system_prompt = EVOLUTION_PROMPT.render_system(**system_kwargs)

    # Truncate digest to fit context budget
    non_digest_overhead = EVOLUTION_PROMPT.render_user(
        skill_name=skill_name,
        rationale=rationale,
        suggested_changes=suggested_changes,
        skill_content=target_skill["content"],
        session_digest="",
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = EVOLUTION_PROMPT.render_user(
        skill_name=skill_name,
        rationale=rationale,
        suggested_changes=suggested_changes,
        skill_content=target_skill["content"],
        session_digest=digest,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=EVOLUTION_OUTPUT_TOKENS,
        timeout=EVOLUTION_TIMEOUT_SECONDS,
        json_schema=EVOLUTION_PROMPT.output_json_schema(),
    )

    if log_dir is None:
        run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_dir = PERSONALIZATION_LOG_DIR / run_timestamp

    suffix = f"_{proposal_index}" if proposal_index is not None else ""
    save_inference_log(log_dir, f"skill_evolution{suffix}_system.txt", system_prompt)
    save_inference_log(log_dir, f"skill_evolution{suffix}_user.txt", user_prompt)

    result = await backend.generate(request)
    save_inference_log(log_dir, f"skill_evolution{suffix}_output.txt", result.text)

    evolution = parse_llm_output(result.text, PersonalizationEvolution, "evolution")
    evolution.confidence = proposal_confidence
    evolution.addressed_patterns = addressed_patterns
    cost = result.cost_usd or 0.0
    return evolution, cost


async def _infer_evolution_proposal_batch(
    backend: InferenceBackend,
    batch: SessionContextBatch,
    installed_skills: list[dict],
    log_dir: Path,
    batch_index: int,
) -> tuple[EvolutionProposalBatch, float]:
    """Run LLM inference for one evolution proposal batch.

    Args:
        backend: Configured inference backend.
        batch: Session batch with pre-extracted contexts.
        installed_skills: Installed skill metadata (name + description).
        log_dir: Timestamped directory for saving prompts and outputs.
        batch_index: Zero-based batch index for file naming.

    Returns:
        Tuple of (parsed proposal batch, cost in USD).
    """
    digest = format_context_batch(batch)
    session_count = len(batch.contexts)

    prompt = EVOLUTION_PROPOSAL_PROMPT
    system_kwargs = build_system_kwargs(prompt, backend)
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
        max_tokens=EVOLUTION_PROPOSAL_OUTPUT_TOKENS,
        timeout=EVOLUTION_PROPOSAL_TIMEOUT_SECONDS,
        json_schema=prompt.output_json_schema(),
    )

    if batch_index == 0:
        save_inference_log(log_dir, "skill_evolution_proposal_system.txt", system_prompt)
    save_inference_log(log_dir, f"skill_evolution_proposal_user_{batch_index}.txt", user_prompt)

    result = await backend.generate(request)
    save_inference_log(log_dir, f"skill_evolution_proposal_output_{batch_index}.txt", result.text)

    proposal_output = parse_llm_output(result.text, EvolutionProposalBatch, "evolution proposal")
    cost = result.cost_usd or 0.0
    return proposal_output, cost


async def _synthesize_evolution_proposals(
    backend: InferenceBackend,
    batch_results: list[tuple[EvolutionProposalBatch, float]],
    session_count: int,
    log_dir: Path,
) -> tuple[EvolutionProposalBatch, float]:
    """Merge evolution proposals from multiple batches via LLM synthesis.

    Args:
        backend: Configured inference backend.
        batch_results: Per-batch proposal outputs and costs.
        session_count: Total number of sessions analyzed.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (merged EvolutionProposalBatch, synthesis cost in USD).
    """
    batch_data = [
        {
            "title": output.title,
            "workflow_patterns": [
                {
                    "title": p.title,
                    "description": p.description,
                    "example_refs": [ref.model_dump(exclude_none=True) for ref in p.example_refs],
                }
                for p in output.workflow_patterns
            ],
            "proposals": [
                {
                    "element_name": p.element_name,
                    "rationale": p.rationale,
                    "addressed_patterns": p.addressed_patterns,
                }
                for p in output.proposals
            ],
        }
        for output, _ in batch_results
    ]

    prompt = EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT
    system_kwargs = build_system_kwargs(prompt, backend)
    system_prompt = prompt.render_system(**system_kwargs)
    user_prompt = prompt.render_user(
        batch_count=len(batch_results), session_count=session_count, batch_results=batch_data
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=EVOLUTION_SYNTHESIS_OUTPUT_TOKENS,
        timeout=EVOLUTION_SYNTHESIS_TIMEOUT_SECONDS,
        json_schema=prompt.output_json_schema(),
    )

    save_inference_log(log_dir, "skill_evolution_proposal_synthesis_system.txt", system_prompt)
    save_inference_log(log_dir, "skill_evolution_proposal_synthesis_user.txt", user_prompt)

    result = await backend.generate(request)
    save_inference_log(log_dir, "skill_evolution_proposal_synthesis_output.txt", result.text)

    synthesis_output = parse_llm_output(
        result.text, EvolutionProposalBatch, "evolution proposal synthesis"
    )
    cost = result.cost_usd or 0.0
    return synthesis_output, cost

"""Skill evolution mode — propose improvements then evolve existing skills.

Two-step pipeline (mirrors creation):
1. _infer_evolution_proposals: batch → concurrent LLM proposal calls
   → optional synthesis → EvolutionProposalBatch
2. _infer_skill_evolution: single LLM call per proposal → PersonalizationEvolution
3. analyze_skill_evolution: orchestrator calling both steps
"""

import asyncio
import time
from datetime import datetime, timezone

from vibelens.context import (
    DetailExtractor,
    SummaryExtractor,
    build_batches,
    format_context_batch,
    truncate_digest_to_fit,
)
from vibelens.deps import get_evolution_store, get_settings
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.backends.cli_base import EVOLUTION_CWD
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContextBatch
from vibelens.models.enums import AgentExtensionType
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.personalization.enums import PersonalizationMode
from vibelens.models.personalization.evolution import (
    EvolutionProposalBatch,
    EvolutionProposalResult,
    PersonalizationEvolution,
)
from vibelens.models.personalization.results import PersonalizationResult
from vibelens.models.trajectories.metrics import Metrics
from vibelens.prompts.evolution import (
    EVOLUTION_PROMPT,
    EVOLUTION_PROPOSAL_PROMPT,
    EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT,
)
from vibelens.services.inference_log import (
    InferenceCallContext,
    InferenceLogWriter,
    analysis_log_dir,
    log_inference_summary,
    run_inference,
)
from vibelens.services.inference_shared import (
    MAX_PROPOSALS,
    MAX_WORKFLOW_PATTERNS,
    aggregate_final_metrics,
    extract_all_contexts,
    parse_llm_output,
    render_system_for,
    require_backend,
    run_batches_concurrent,
    run_synthesis,
)
from vibelens.services.personalization.shared import (
    SkillDetailLevel,
    _cache,
    gather_installed_skills,
    personalization_cache_key,
    reduce_batch_results,
    resolve_proposal_session_ids,
    validate_patterns,
)
from vibelens.utils.collections import truncate_to_cap
from vibelens.utils.identifiers import generate_timestamped_id
from vibelens.utils.log import clear_analysis_id, get_logger, set_analysis_id

logger = get_logger(__name__)

# Number of sequential LLM calls in the full pipeline (proposal → synthesis → evolution)
EXPECTED_EVOLUTION_CALLS = 3
# Canonical title when no evolution proposals survive filtering.
EVOLUTION_EMPTY_STATE_TITLE = "Your installed skills do not match your recent work"


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
    if skill_names is None:
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
    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    installed_skills = _filter_skills(gather_installed_skills(), skill_names)
    if not installed_skills:
        raise ValueError("No installed skills found for evolution analysis.")

    inference_cfg = get_settings().inference
    max_input = inference_cfg.max_input_tokens
    max_output = inference_cfg.max_output_tokens
    batches = build_batches(context_set.contexts, max_batch_tokens=max_input)

    # Proposal phase tokens
    proposal_system = render_system_for(EVOLUTION_PROPOSAL_PROMPT, backend)
    batch_token_counts = [count_tokens(format_context_batch(batch)) for batch in batches]

    # Evolution phase tokens (estimated per-call)
    evolution_system = render_system_for(EVOLUTION_PROMPT, backend)
    digest = format_context_batch(context_set)
    deep_input_tokens = count_tokens(evolution_system) + count_tokens(digest)
    extra_calls = [
        (deep_input_tokens, max_output) for _ in range(EXPECTED_EVOLUTION_CALLS)
    ]

    return estimate_analysis_cost(
        batch_token_counts=batch_token_counts,
        system_prompt=proposal_system,
        model=backend.model,
        max_output_tokens=max_output,
        synthesis_output_tokens=max_output,
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

    analysis_id = generate_timestamped_id()
    set_analysis_id(analysis_id)

    start_time = time.monotonic()
    log_dir = analysis_log_dir("evolution") / analysis_id
    writer = InferenceLogWriter(
        log_dir, analysis_id, mode="evolution", config=get_settings().inference
    )

    # Step 1: Generate proposals (filtered to user-selected skills)
    proposal_result = await _infer_evolution_proposals(
        session_ids, session_token, writer, skill_names
    )

    # Drop hallucinated proposals whose name is not in the installed-skill list.
    allowed_names = skill_names or [s["name"] for s in gather_installed_skills()]
    installed_set = set(allowed_names)
    filtered_proposals = []
    for p in proposal_result.proposal_batch.proposals:
        if p.element_name not in installed_set:
            logger.warning(
                "Dropping hallucinated evolution proposal '%s' (not installed)",
                p.element_name,
            )
            continue
        filtered_proposals.append(p)

    # Deduplicate: keep only the first proposal per element_name
    seen_skills: set[str] = set()
    unique_proposals = []
    for p in filtered_proposals:
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
        relevant_ids = resolve_proposal_session_ids(
            proposal_session_ids=p.session_ids, loaded_session_ids=proposal_result.session_ids
        )
        evolution_tasks.append(
            _infer_evolution(
                skill_name=p.element_name,
                rationale=p.rationale,
                addressed_patterns=p.addressed_patterns,
                session_ids=relevant_ids,
                session_token=session_token,
                proposal_confidence=p.confidence,
                writer=writer,
                proposal_index=idx,
            )
        )

    evolutions: list[PersonalizationEvolution] = []
    warnings: list[str] = list(proposal_result.warnings)
    all_metrics: list[Metrics] = list(proposal_result.batch_metrics)

    if evolution_tasks:
        results = await asyncio.gather(*evolution_tasks, return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, tuple):
                evolution, step_metrics = result
                evolutions.append(evolution)
                all_metrics.append(step_metrics)
            else:
                name = proposal_result.proposal_batch.proposals[idx].element_name
                warnings.append(f"Evolution failed for '{name}': {result}")
                logger.warning("Evolution failed for proposal '%s': %s", name, result)

    duration = int(time.monotonic() - start_time)
    proposal_output = proposal_result.proposal_batch
    result_title = (
        EVOLUTION_EMPTY_STATE_TITLE if len(unique_proposals) == 0 else proposal_output.title
    )
    skill_result = PersonalizationResult(
        id=analysis_id,
        mode=PersonalizationMode.EVOLUTION,
        title=result_title,
        workflow_patterns=proposal_output.workflow_patterns,
        evolutions=evolutions,
        session_ids=proposal_result.session_ids,
        skipped_session_ids=proposal_result.skipped_session_ids,
        warnings=warnings,
        backend=proposal_result.backend,
        model=proposal_result.model,
        batch_metrics=all_metrics,
        final_metrics=aggregate_final_metrics(all_metrics, duration_seconds=duration),
        batch_count=proposal_result.batch_count,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    get_evolution_store().save(skill_result, analysis_id)
    clear_analysis_id()

    _cache[cache_key] = skill_result
    return skill_result


async def _infer_evolution_proposals(
    session_ids: list[str],
    session_token: str | None,
    writer: InferenceLogWriter,
    skill_names: list[str] | None = None,
) -> EvolutionProposalResult:
    """Execute the proposal step: load sessions, batch, infer, validate.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.
        writer: Log writer for this analysis run.
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

    if not context_set.contexts:
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
        _infer_evolution_proposal_batch(backend, batch, installed_skills, writer, idx)
        for idx, batch in enumerate(batches)
    ]
    batch_results, batch_warnings = await run_batches_concurrent(tasks, "evolution_proposal")

    session_count = len(context_set.session_ids)

    async def _synthesize(
        results: list[tuple[EvolutionProposalBatch, Metrics]],
    ) -> tuple[EvolutionProposalBatch, Metrics]:
        return await _synthesize_evolution_proposals(
            backend, results, session_count, installed_skills, writer
        )

    proposal_output, all_metrics = await reduce_batch_results(
        batch_results, synthesize=_synthesize
    )

    validated_patterns = validate_patterns(proposal_output.workflow_patterns, context_set)

    # Enforce count caps deterministically — LLMs regularly exceed
    # prompt-stated "at most N" instructions.
    pre_patterns = len(validated_patterns)
    truncate_to_cap(validated_patterns, MAX_WORKFLOW_PATTERNS)
    if pre_patterns > len(validated_patterns):
        logger.info("Capped workflow_patterns: %d -> %d", pre_patterns, len(validated_patterns))

    pre_proposals = len(proposal_output.proposals)
    truncate_to_cap(proposal_output.proposals, MAX_PROPOSALS)
    if pre_proposals > len(proposal_output.proposals):
        logger.info("Capped proposals: %d -> %d", pre_proposals, len(proposal_output.proposals))

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
        batch_metrics=all_metrics,
        final_metrics=aggregate_final_metrics(all_metrics),
        batch_count=len(batches),
        created_at=datetime.now(timezone.utc).isoformat(),
        proposal_batch=final_output,
    )


async def _infer_evolution(
    skill_name: str,
    rationale: str,
    addressed_patterns: list[str],
    session_ids: list[str],
    writer: InferenceLogWriter,
    session_token: str | None = None,
    proposal_confidence: float = 0.0,
    proposal_index: int | None = None,
) -> tuple[PersonalizationEvolution, Metrics]:
    """Generate granular evolutions for one existing skill.

    Args:
        skill_name: Name of the installed skill to evolve.
        rationale: Why this skill should be evolved and what to change.
        addressed_patterns: Pattern titles this evolution addresses.
        session_ids: Sessions to use as evidence.
        writer: Log writer for this analysis run.
        session_token: Browser tab token for upload scoping.
        proposal_confidence: Confidence from proposal step (0.0-1.0).
        proposal_index: Index for log file naming.

    Returns:
        Tuple of (PersonalizationEvolution, per-call metrics).
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, extractor=DetailExtractor()
    )

    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    # Load full SKILL.md content for the target skill
    all_skills = gather_installed_skills(SkillDetailLevel.FULL)
    target_skill = next((s for s in all_skills if s["name"] == skill_name), None)
    if not target_skill:
        raise ValueError(f"Skill '{skill_name}' not found in installed skills.")

    digest = format_context_batch(context_set)

    system_prompt = render_system_for(EVOLUTION_PROMPT, backend)

    # Truncate digest to fit context budget
    non_digest_overhead = EVOLUTION_PROMPT.render_user(
        skill_name=skill_name,
        rationale=rationale,
        skill_content=target_skill["content"],
        session_digest="",
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = EVOLUTION_PROMPT.render_user(
        skill_name=skill_name,
        rationale=rationale,
        skill_content=target_skill["content"],
        session_digest=digest,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        json_schema=EVOLUTION_PROMPT.output_json_schema(),
        workspace_dir=EVOLUTION_CWD,
    )

    suffix = f"_{proposal_index}" if proposal_index is not None else ""
    system_file = f"skill_evolution{suffix}_system.txt"
    user_file = f"skill_evolution{suffix}_user.txt"
    writer.log_prompt_file(system_file, system_prompt)
    writer.log_prompt_file(user_file, user_prompt)

    context = InferenceCallContext(
        task_id=f"skill_evolution{suffix}", system_file=system_file, user_file=user_file
    )
    result = await run_inference(backend, request, writer, context)

    evolution = parse_llm_output(
        result.text,
        PersonalizationEvolution,
        "evolution",
        field_fallbacks={"rationale": rationale, "element_name": skill_name},
    )
    evolution.element_type = AgentExtensionType.SKILL
    evolution.confidence = proposal_confidence
    evolution.addressed_patterns = addressed_patterns
    return evolution, result.metrics


async def _infer_evolution_proposal_batch(
    backend: InferenceBackend,
    batch: SessionContextBatch,
    installed_skills: list[dict],
    writer: InferenceLogWriter,
    batch_index: int,
) -> tuple[EvolutionProposalBatch, Metrics]:
    """Run LLM inference for one evolution proposal batch.

    Args:
        backend: Configured inference backend.
        batch: Session batch with pre-extracted contexts.
        installed_skills: Installed skill metadata (name + description).
        writer: Log writer for this analysis run.
        batch_index: Zero-based batch index for file naming.

    Returns:
        Tuple of (parsed proposal batch, per-call metrics).
    """
    digest = format_context_batch(batch)
    session_count = len(batch.contexts)

    prompt = EVOLUTION_PROPOSAL_PROMPT
    system_prompt = render_system_for(prompt, backend)

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
        json_schema=prompt.output_json_schema(),
        workspace_dir=EVOLUTION_CWD,
    )

    system_file = "skill_evolution_proposal_system.txt"
    user_file = f"skill_evolution_proposal_user_{batch_index}.txt"
    if batch_index == 0:
        writer.log_prompt_file(system_file, system_prompt)
    writer.log_prompt_file(user_file, user_prompt)

    context = InferenceCallContext(
        task_id=f"skill_evolution_proposal_{batch_index}",
        system_file=system_file,
        user_file=user_file,
    )
    result = await run_inference(backend, request, writer, context)

    proposal_output = parse_llm_output(result.text, EvolutionProposalBatch, "evolution proposal")
    return proposal_output, result.metrics


async def _synthesize_evolution_proposals(
    backend: InferenceBackend,
    batch_results: list[tuple[EvolutionProposalBatch, Metrics]],
    session_count: int,
    installed_skills: list[dict],
    writer: InferenceLogWriter,
) -> tuple[EvolutionProposalBatch, Metrics]:
    """Merge evolution proposals from multiple batches via LLM synthesis.

    Args:
        backend: Configured inference backend.
        batch_results: Per-batch proposal outputs and metrics.
        session_count: Total number of sessions analyzed.
        installed_skills: Installed skills the synthesis is allowed to propose.
        writer: Log writer for this analysis run.

    Returns:
        Tuple of (merged EvolutionProposalBatch, synthesis call metrics).
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
                    "element_type": p.element_type,
                    "element_name": p.element_name,
                    "rationale": p.rationale,
                    "addressed_patterns": p.addressed_patterns,
                    "session_ids": p.session_ids,
                }
                for p in output.proposals
            ],
        }
        for output, _ in batch_results
    ]

    return await run_synthesis(
        backend=backend,
        prompt=EVOLUTION_PROPOSAL_SYNTHESIS_PROMPT,
        output_model=EvolutionProposalBatch,
        batch_data=batch_data,
        session_count=session_count,
        writer=writer,
        workspace_dir=EVOLUTION_CWD,
        extra_user_kwargs={"installed_skills": installed_skills},
    )

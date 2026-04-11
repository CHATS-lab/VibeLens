"""Skill creation mode — two-step pipeline: proposals then generation.

Pipeline:
1. _infer_skill_creation_proposals: batch → concurrent LLM proposal calls
   → optional synthesis → SkillCreationProposalResult
2. _infer_skill_creation: single LLM call per approved proposal → SkillCreation
3. analyze_skill_creation: orchestrator calling both steps
"""

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

from cachetools import TTLCache

from vibelens.deps import get_skill_analysis_store
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.prompts.skill_creation import (
    SKILL_CREATION_GENERATE_PROMPT,
    SKILL_CREATION_PROPOSAL_PROMPT,
    SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT,
)
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContextBatch
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.skill import (
    SkillAnalysisResult,
    SkillCreation,
    SkillCreationProposalOutput,
    SkillCreationProposalResult,
    SkillMode,
)
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.analysis_shared import (
    CACHE_TTL_SECONDS,
    build_digest_from_contexts,
    build_system_kwargs,
    extract_all_contexts,
    format_batch_digest,
    log_analysis_summary,
    require_backend,
    run_batches_concurrent,
    save_analysis_log,
    truncate_digest_to_fit,
)
from vibelens.services.analysis_store import generate_analysis_id
from vibelens.services.context_params import PRESET_DETAIL, PRESET_MEDIUM
from vibelens.services.session_batcher import build_batches
from vibelens.services.skill.shared import (
    SKILL_LOG_DIR,
    _cache,
    gather_installed_skills,
    merge_batch_refs,
    parse_llm_output,
    skill_cache_key,
    validate_patterns,
)
from vibelens.utils.log import clear_analysis_id, get_logger, set_analysis_id

logger = get_logger(__name__)

# LLM inference limits for each step of the skill creation pipeline
SKILL_CREATION_PROPOSAL_OUTPUT_TOKENS = 4096
SKILL_CREATION_PROPOSAL_TIMEOUT_SECONDS = 300
SKILL_CREATION_SYNTHESIS_OUTPUT_TOKENS = 8192
SKILL_CREATION_SYNTHESIS_TIMEOUT_SECONDS = 300
SKILL_CREATION_GENERATE_OUTPUT_TOKENS = 4096
SKILL_CREATION_GENERATE_TIMEOUT_SECONDS = 300
# Number of sequential LLM calls in the full pipeline (proposal → synthesis → generate)
EXPECTED_DEEP_CALLS = 3

_proposal_cache: TTLCache = TTLCache(maxsize=32, ttl=CACHE_TTL_SECONDS)


def estimate_skill_creation(
    session_ids: list[str], session_token: str | None = None
) -> CostEstimate:
    """Pre-flight cost estimate for skill creation analysis.

    Estimates the full pipeline: proposal batches + synthesis + deep generation
    for an expected number of proposals.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        CostEstimate with projected cost range.

    Raises:
        ValueError: If no sessions could be loaded.
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, params=PRESET_MEDIUM
    )
    if not context_set:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    batches = build_batches(context_set.contexts)

    # Proposal phase tokens
    proposal_system = SKILL_CREATION_PROPOSAL_PROMPT.render_system(
        **build_system_kwargs(SKILL_CREATION_PROPOSAL_PROMPT, backend)
    )
    batch_token_counts = [count_tokens(format_batch_digest(batch)) for batch in batches]

    # Deep generation phase tokens (estimated per-call)
    generate_system = SKILL_CREATION_GENERATE_PROMPT.render_system(
        **build_system_kwargs(SKILL_CREATION_GENERATE_PROMPT, backend)
    )
    digest = build_digest_from_contexts(context_set)
    deep_input_tokens = count_tokens(generate_system) + count_tokens(digest)
    extra_calls = [
        (deep_input_tokens, SKILL_CREATION_GENERATE_OUTPUT_TOKENS)
        for _ in range(EXPECTED_DEEP_CALLS)
    ]

    return estimate_analysis_cost(
        batch_token_counts=batch_token_counts,
        system_prompt=proposal_system,
        model=backend.model,
        max_output_tokens=SKILL_CREATION_PROPOSAL_OUTPUT_TOKENS,
        synthesis_output_tokens=SKILL_CREATION_SYNTHESIS_OUTPUT_TOKENS,
        synthesis_threshold=1,
        extra_calls=extra_calls,
    )


async def analyze_skill_creation(
    session_ids: list[str], session_token: str | None = None
) -> SkillAnalysisResult:
    """Backward-compatible creation: proposals then deep creation for each.

    Preserves the existing POST /skills/analysis endpoint with mode=creation.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        SkillAnalysisResult with creations populated.
    """
    cache_key = skill_cache_key(session_ids, SkillMode.CREATION)
    if cache_key in _cache:
        return _cache[cache_key]

    start_time = time.monotonic()
    analysis_id = generate_analysis_id()
    set_analysis_id(analysis_id)

    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = SKILL_LOG_DIR / run_timestamp

    # Step 1: Generate proposals
    proposal_result = await _infer_skill_creation_proposals(
        session_ids, session_token, log_dir=log_dir
    )

    proposal_names = [p.skill_name for p in proposal_result.proposal_output.proposals]
    logger.info("Creation proposals: %s", proposal_names)

    # Step 2: Deep create each proposal concurrently
    creation_tasks = []
    for idx, p in enumerate(proposal_result.proposal_output.proposals):
        # Filter to only relevant sessions when indices are specified
        if p.relevant_session_indices:
            relevant_ids = [
                proposal_result.session_ids[i]
                for i in p.relevant_session_indices
                if i < len(proposal_result.session_ids)
            ]
        else:
            relevant_ids = session_ids
        creation_tasks.append(
            _infer_skill_creation(
                proposal_name=p.skill_name,
                proposal_description=p.description,
                proposal_rationale=p.rationale,
                addressed_patterns=p.addressed_patterns,
                session_ids=relevant_ids,
                session_token=session_token,
                proposal_confidence=p.confidence,
                log_dir=log_dir,
                proposal_index=idx,
            )
        )

    creations: list[SkillCreation] = []
    creation_warnings: list[str] = list(proposal_result.warnings)
    total_cost = proposal_result.metrics.cost_usd or 0.0
    if creation_tasks:
        results = await asyncio.gather(*creation_tasks, return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, tuple):
                creation, cost = result
                creations.append(creation)
                total_cost += cost
            else:
                skill_name = proposal_result.proposal_output.proposals[idx].skill_name
                creation_warnings.append(f"Deep creation failed for '{skill_name}': {result}")
                logger.warning("Deep creation failed for proposal '%s': %s", skill_name, result)

    duration = round(time.monotonic() - start_time, 2)
    proposal_output = proposal_result.proposal_output
    skill_result = SkillAnalysisResult(
        mode=SkillMode.CREATION,
        title=proposal_output.title,
        workflow_patterns=proposal_output.workflow_patterns,
        creations=creations,
        session_ids=proposal_result.session_ids,
        skipped_session_ids=proposal_result.skipped_session_ids,
        warnings=creation_warnings,
        backend_id=proposal_result.backend_id,
        model=proposal_result.model,
        metrics=Metrics(cost_usd=total_cost if total_cost > 0 else None),
        duration_seconds=duration,
        created_at=datetime.now(UTC).isoformat(),
    )
    get_skill_analysis_store().save(skill_result, analysis_id)
    clear_analysis_id()

    _cache[cache_key] = skill_result
    return skill_result


async def _infer_skill_creation_proposals(
    session_ids: list[str], session_token: str | None = None, log_dir: Path | None = None
) -> SkillCreationProposalResult:
    """Run the proposal step: detect patterns and generate lightweight proposals.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.
        log_dir: Shared log directory. Created if None.

    Returns:
        SkillCreationProposalResult with nested proposal_output and metadata.

    Raises:
        ValueError: If no sessions could be loaded or no backend configured.
        InferenceError: If LLM backend fails.
    """
    cache_key = skill_cache_key(session_ids, SkillMode.CREATION) + ":proposals"
    if cache_key in _proposal_cache:
        return _proposal_cache[cache_key]

    backend = require_backend()
    context_set = extract_all_contexts(session_ids, session_token, PRESET_MEDIUM)

    if not context_set:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    batches = build_batches(context_set.contexts)
    logger.info(
        "Skill proposals: %d sessions → %d batch(es)",
        len(context_set.session_ids),
        len(batches),
    )
    log_analysis_summary(context_set, batches, backend)

    if log_dir is None:
        run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        log_dir = SKILL_LOG_DIR / run_timestamp

    installed_skills = gather_installed_skills()

    tasks = [
        _infer_skill_creation_proposal_batch(backend, batch, installed_skills, log_dir, idx)
        for idx, batch in enumerate(batches)
    ]
    batch_results, batch_warnings = await run_batches_concurrent(tasks, "proposal")

    total_cost = sum(cost for _, cost in batch_results)

    # Single batch: use directly; multiple batches: synthesize
    if len(batch_results) == 1:
        proposal_output = batch_results[0][0]
    else:
        proposal_output, syn_cost = await _synthesize_skill_creation_proposals(
            backend, batch_results, len(context_set.session_ids), log_dir
        )
        total_cost += syn_cost
        # Synthesis LLM drops example_refs; recover from batch outputs
        merge_batch_refs(
            proposal_output.workflow_patterns,
            [output.workflow_patterns for output, _ in batch_results],
        )

    validated_patterns = validate_patterns(proposal_output.workflow_patterns, context_set)

    final_output = SkillCreationProposalOutput(
        title=proposal_output.title,
        workflow_patterns=validated_patterns,
        proposals=proposal_output.proposals,
    )

    result = SkillCreationProposalResult(
        session_ids=context_set.session_ids,
        skipped_session_ids=context_set.skipped_session_ids,
        warnings=batch_warnings,
        backend_id=backend.backend_id,
        model=backend.model,
        metrics=Metrics(cost_usd=total_cost if total_cost > 0 else None),
        batch_count=len(batches),
        created_at=datetime.now(UTC).isoformat(),
        proposal_output=final_output,
    )

    _proposal_cache[cache_key] = result
    return result


async def _infer_skill_creation(
    proposal_name: str,
    proposal_description: str,
    proposal_rationale: str,
    addressed_patterns: list[str],
    session_ids: list[str],
    session_token: str | None = None,
    proposal_confidence: float = 0.0,
    log_dir: Path | None = None,
    proposal_index: int | None = None,
) -> tuple[SkillCreation, float]:
    """Generate full SKILL.md content for one approved proposal.

    Args:
        proposal_name: Kebab-case skill name.
        proposal_description: One-line trigger description.
        proposal_rationale: Why this skill would improve workflow.
        addressed_patterns: Pattern titles this proposal addresses.
        session_ids: Sessions to use as evidence.
        session_token: Browser tab token for upload scoping.
        proposal_confidence: Confidence from proposal step (0.0-1.0).
        log_dir: Shared log directory. Created if None.
        proposal_index: Index for log file naming when called from analyze_skill_creation.

    Returns:
        Tuple of (SkillCreation with full SKILL.md content, cost in USD).

    Raises:
        ValueError: If no sessions could be loaded or no backend configured.
        InferenceError: If LLM backend fails.
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, params=PRESET_DETAIL
    )

    if not context_set:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    # Build digest from all contexts (no batching needed for single-skill creation)
    digest = build_digest_from_contexts(context_set)
    installed_skills = gather_installed_skills()

    system_kwargs = build_system_kwargs(SKILL_CREATION_GENERATE_PROMPT, backend)
    system_prompt = SKILL_CREATION_GENERATE_PROMPT.render_system(**system_kwargs)

    # Truncate digest to fit context budget
    non_digest_overhead = SKILL_CREATION_GENERATE_PROMPT.render_user(
        proposal_name=proposal_name,
        proposal_description=proposal_description,
        proposal_rationale=proposal_rationale,
        addressed_patterns=addressed_patterns,
        session_digest="",
        installed_skills=installed_skills if installed_skills else None,
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = SKILL_CREATION_GENERATE_PROMPT.render_user(
        proposal_name=proposal_name,
        proposal_description=proposal_description,
        proposal_rationale=proposal_rationale,
        addressed_patterns=addressed_patterns,
        session_digest=digest,
        installed_skills=installed_skills if installed_skills else None,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_CREATION_GENERATE_OUTPUT_TOKENS,
        timeout=SKILL_CREATION_GENERATE_TIMEOUT_SECONDS,
        json_schema=SKILL_CREATION_GENERATE_PROMPT.output_json_schema(),
    )

    if log_dir is None:
        run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        log_dir = SKILL_LOG_DIR / run_timestamp

    suffix = f"_{proposal_index}" if proposal_index is not None else ""
    save_analysis_log(log_dir, f"skill_creation{suffix}_system.txt", system_prompt)
    save_analysis_log(log_dir, f"skill_creation{suffix}_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, f"skill_creation{suffix}_output.txt", result.text)

    creation = parse_llm_output(result.text, SkillCreation, "deep creation")
    creation.confidence = proposal_confidence
    creation.addressed_patterns = addressed_patterns
    cost = result.cost_usd or 0.0
    return creation, cost


async def _infer_skill_creation_proposal_batch(
    backend: InferenceBackend,
    batch: SessionContextBatch,
    installed_skills: list[dict],
    log_dir: Path,
    batch_index: int,
) -> tuple[SkillCreationProposalOutput, float]:
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
    session_count = len(batch.contexts)

    system_kwargs = build_system_kwargs(SKILL_CREATION_PROPOSAL_PROMPT, backend)
    system_prompt = SKILL_CREATION_PROPOSAL_PROMPT.render_system(**system_kwargs)

    # Truncate digest to fit context budget
    non_digest_overhead = SKILL_CREATION_PROPOSAL_PROMPT.render_user(
        session_count=session_count,
        session_digest="",
        installed_skills=installed_skills if installed_skills else None,
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = SKILL_CREATION_PROPOSAL_PROMPT.render_user(
        session_count=session_count,
        session_digest=digest,
        installed_skills=installed_skills if installed_skills else None,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_CREATION_PROPOSAL_OUTPUT_TOKENS,
        timeout=SKILL_CREATION_PROPOSAL_TIMEOUT_SECONDS,
        json_schema=SKILL_CREATION_PROPOSAL_PROMPT.output_json_schema(),
    )

    if batch_index == 0:
        save_analysis_log(log_dir, "skill_creation_proposal_system.txt", system_prompt)
    save_analysis_log(log_dir, f"skill_creation_proposal_user_{batch_index}.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, f"skill_creation_proposal_output_{batch_index}.txt", result.text)

    proposal_output = parse_llm_output(result.text, SkillCreationProposalOutput, "proposal")
    cost = result.cost_usd or 0.0
    return proposal_output, cost


async def _synthesize_skill_creation_proposals(
    backend: InferenceBackend,
    batch_results: list[tuple[SkillCreationProposalOutput, float]],
    session_count: int,
    log_dir: Path,
) -> tuple[SkillCreationProposalOutput, float]:
    """Merge proposals from multiple batches via LLM synthesis.

    Args:
        backend: Configured inference backend.
        batch_results: Per-batch proposal outputs and costs.
        session_count: Total number of sessions analyzed.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (merged SkillCreationProposalOutput, synthesis cost in USD).
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
                    "skill_name": p.skill_name,
                    "description": p.description,
                    "rationale": p.rationale,
                    "addressed_patterns": p.addressed_patterns,
                }
                for p in output.proposals
            ],
        }
        for output, _ in batch_results
    ]

    synthesis_prompt = SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT
    system_kwargs = build_system_kwargs(synthesis_prompt, backend)
    system_prompt = synthesis_prompt.render_system(**system_kwargs)
    user_prompt = synthesis_prompt.render_user(
        batch_count=len(batch_results), session_count=session_count, batch_results=batch_data
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_CREATION_SYNTHESIS_OUTPUT_TOKENS,
        timeout=SKILL_CREATION_SYNTHESIS_TIMEOUT_SECONDS,
        json_schema=synthesis_prompt.output_json_schema(),
    )

    save_analysis_log(log_dir, "skill_creation_proposal_synthesis_system.txt", system_prompt)
    save_analysis_log(log_dir, "skill_creation_proposal_synthesis_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, "skill_creation_proposal_synthesis_output.txt", result.text)

    synthesis_output = parse_llm_output(
        result.text, SkillCreationProposalOutput, "proposal synthesis"
    )
    cost = result.cost_usd or 0.0
    return synthesis_output, cost

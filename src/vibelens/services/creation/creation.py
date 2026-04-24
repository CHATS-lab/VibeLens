"""Skill creation mode — two-step pipeline: proposals then generation.

Pipeline:
1. _infer_creation_proposals: batch → concurrent LLM proposal calls
   → optional synthesis → CreationProposalResult
2. _infer_skill_creation: single LLM call per approved proposal → PersonalizationCreation
3. analyze_skill_creation: orchestrator calling both steps
"""

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

from cachetools import TTLCache

from vibelens.context import DetailExtractor, SummaryExtractor, build_batches
from vibelens.deps import get_creation_store, get_settings
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.backends.cli_base import CREATION_CWD
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContextBatch
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.personalization.creation import (
    CreationProposalBatch,
    CreationProposalResult,
    PersonalizationCreation,
)
from vibelens.models.personalization.enums import PersonalizationMode
from vibelens.models.personalization.results import PersonalizationResult
from vibelens.models.trajectories.metrics import Metrics
from vibelens.prompts.creation import (
    CREATION_PROMPT,
    CREATION_PROPOSAL_PROMPT,
    CREATION_PROPOSAL_SYNTHESIS_PROMPT,
)
from vibelens.services.inference_shared import (
    CACHE_TTL_SECONDS,
    aggregate_final_metrics,
    analysis_log_dir,
    extract_all_contexts,
    format_context_batch,
    log_inference_summary,
    metrics_from_result,
    render_system_for,
    require_backend,
    run_batches_concurrent,
    run_synthesis,
    save_inference_log,
    truncate_digest_to_fit,
)
from vibelens.services.personalization.shared import (
    _cache,
    gather_installed_skills,
    parse_llm_output,
    personalization_cache_key,
    reduce_batch_results,
    resolve_proposal_session_ids,
    validate_patterns,
)
from vibelens.utils.identifiers import generate_timestamped_id
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
        session_ids=session_ids, session_token=session_token, extractor=SummaryExtractor()
    )
    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    max_input = get_settings().inference.max_input_tokens
    batches = build_batches(context_set.contexts, max_batch_tokens=max_input)

    # Proposal phase tokens
    proposal_system = render_system_for(CREATION_PROPOSAL_PROMPT, backend)
    batch_token_counts = [count_tokens(format_context_batch(batch)) for batch in batches]

    # Deep generation phase tokens (estimated per-call)
    generate_system = render_system_for(CREATION_PROMPT, backend)
    digest = format_context_batch(context_set)
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
) -> PersonalizationResult:
    """Backward-compatible creation: proposals then deep creation for each.

    Preserves the existing POST /skills/analysis endpoint with mode=creation.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        PersonalizationResult with creations populated.
    """
    cache_key = personalization_cache_key(session_ids, PersonalizationMode.CREATION)
    if cache_key in _cache:
        return _cache[cache_key]

    analysis_id = generate_timestamped_id()
    set_analysis_id(analysis_id)

    start_time = time.monotonic()
    log_dir = analysis_log_dir("creation") / analysis_id

    # Step 1: Generate proposals
    proposal_result = await _infer_creation_proposals(
        session_ids, log_dir=log_dir, session_token=session_token
    )

    proposal_names = [p.element_name for p in proposal_result.proposal_batch.proposals]
    logger.info("Creation proposals: %s", proposal_names)

    # Step 2: Create each proposal concurrently
    creation_tasks = []
    for idx, p in enumerate(proposal_result.proposal_batch.proposals):
        relevant_ids = resolve_proposal_session_ids(
            proposal_session_ids=p.session_ids, loaded_session_ids=proposal_result.session_ids
        )
        creation_tasks.append(
            _infer_skill_creation(
                proposal_name=p.element_name,
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

    creations: list[PersonalizationCreation] = []
    creation_warnings: list[str] = list(proposal_result.warnings)
    all_metrics: list[Metrics] = list(proposal_result.batch_metrics)
    if creation_tasks:
        results = await asyncio.gather(*creation_tasks, return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, tuple):
                creation, step_metrics = result
                creations.append(creation)
                all_metrics.append(step_metrics)
            else:
                element_name = proposal_result.proposal_batch.proposals[idx].element_name
                creation_warnings.append(f"Creation failed for '{element_name}': {result}")
                logger.warning("Creation failed for proposal '%s': %s", element_name, result)

    duration = int(time.monotonic() - start_time)
    proposal_output = proposal_result.proposal_batch
    skill_result = PersonalizationResult(
        id=analysis_id,
        mode=PersonalizationMode.CREATION,
        title=proposal_output.title,
        workflow_patterns=proposal_output.workflow_patterns,
        creations=creations,
        session_ids=proposal_result.session_ids,
        skipped_session_ids=proposal_result.skipped_session_ids,
        warnings=creation_warnings,
        backend=proposal_result.backend,
        model=proposal_result.model,
        batch_metrics=all_metrics,
        final_metrics=aggregate_final_metrics(all_metrics, duration_seconds=duration),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    get_creation_store().save(skill_result, analysis_id)
    clear_analysis_id()

    _cache[cache_key] = skill_result
    return skill_result


async def _infer_creation_proposals(
    session_ids: list[str], log_dir: Path, session_token: str | None = None
) -> CreationProposalResult:
    """Run the proposal step: detect patterns and generate lightweight proposals.

    Args:
        session_ids: Sessions to analyze.
        log_dir: Per-run log directory under ``logs/personalization/creation/``.
        session_token: Browser tab token for upload scoping.

    Returns:
        CreationProposalResult with nested proposal_output and metadata.

    Raises:
        ValueError: If no sessions could be loaded or no backend configured.
        InferenceError: If LLM backend fails.
    """
    cache_key = personalization_cache_key(session_ids, PersonalizationMode.CREATION) + ":proposals"
    if cache_key in _proposal_cache:
        return _proposal_cache[cache_key]

    backend = require_backend()
    context_set = extract_all_contexts(session_ids, session_token, extractor=SummaryExtractor())

    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    max_input = get_settings().inference.max_input_tokens
    batches = build_batches(context_set.contexts, max_batch_tokens=max_input)
    logger.info(
        "Skill proposals: %d sessions → %d batch(es)",
        len(context_set.session_ids),
        len(batches),
    )
    log_inference_summary(context_set, batches, backend)

    installed_skills = gather_installed_skills()

    tasks = [
        _infer_skill_creation_proposal_batch(backend, batch, installed_skills, log_dir, idx)
        for idx, batch in enumerate(batches)
    ]
    batch_results, batch_warnings = await run_batches_concurrent(tasks, "proposal")

    session_count = len(context_set.session_ids)

    async def _synthesize(
        results: list[tuple[CreationProposalBatch, Metrics]],
    ) -> tuple[CreationProposalBatch, Metrics]:
        return await _synthesize_creation_proposals(backend, results, session_count, log_dir)

    proposal_output, all_metrics = await reduce_batch_results(batch_results, synthesize=_synthesize)

    validated_patterns = validate_patterns(proposal_output.workflow_patterns, context_set)

    final_output = CreationProposalBatch(
        title=proposal_output.title,
        workflow_patterns=validated_patterns,
        proposals=proposal_output.proposals,
    )

    result = CreationProposalResult(
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

    _proposal_cache[cache_key] = result
    return result


async def _infer_skill_creation(
    proposal_name: str,
    proposal_description: str,
    proposal_rationale: str,
    addressed_patterns: list[str],
    session_ids: list[str],
    log_dir: Path,
    session_token: str | None = None,
    proposal_confidence: float = 0.0,
    proposal_index: int | None = None,
) -> tuple[PersonalizationCreation, Metrics]:
    """Generate full SKILL.md content for one approved proposal.

    Args:
        proposal_name: Kebab-case skill name.
        proposal_description: One-line trigger description.
        proposal_rationale: Why this skill would improve workflow.
        addressed_patterns: Pattern titles this proposal addresses.
        session_ids: Sessions to use as evidence.
        log_dir: Shared per-run log directory.
        session_token: Browser tab token for upload scoping.
        proposal_confidence: Confidence from proposal step (0.0-1.0).
        proposal_index: Index for log file naming when called from analyze_skill_creation.

    Returns:
        Tuple of (PersonalizationCreation with full SKILL.md content, per-call metrics).

    Raises:
        ValueError: If no sessions could be loaded or no backend configured.
        InferenceError: If LLM backend fails.
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, extractor=DetailExtractor()
    )

    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    # Build digest from all contexts (no batching needed for single-skill creation)
    digest = format_context_batch(context_set)
    installed_skills = gather_installed_skills()

    system_prompt = render_system_for(CREATION_PROMPT, backend)

    # Truncate digest to fit context budget
    non_digest_overhead = CREATION_PROMPT.render_user(
        proposal_name=proposal_name,
        proposal_description=proposal_description,
        proposal_rationale=proposal_rationale,
        addressed_patterns=addressed_patterns,
        session_digest="",
        installed_skills=installed_skills if installed_skills else None,
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = CREATION_PROMPT.render_user(
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
        json_schema=CREATION_PROMPT.output_json_schema(),
        analysis_cwd=CREATION_CWD,
    )

    suffix = f"_{proposal_index}" if proposal_index is not None else ""
    save_inference_log(log_dir, f"skill_creation{suffix}_system.txt", system_prompt)
    save_inference_log(log_dir, f"skill_creation{suffix}_user.txt", user_prompt)

    result = await backend.generate(request)
    save_inference_log(log_dir, f"skill_creation{suffix}_output.txt", result.text)

    creation = parse_llm_output(
        result.text,
        PersonalizationCreation,
        "deep creation",
        field_fallbacks={"rationale": proposal_rationale},
    )
    creation.confidence = proposal_confidence
    creation.addressed_patterns = addressed_patterns
    return creation, metrics_from_result(result)


async def _infer_skill_creation_proposal_batch(
    backend: InferenceBackend,
    batch: SessionContextBatch,
    installed_skills: list[dict],
    log_dir: Path,
    batch_index: int,
) -> tuple[CreationProposalBatch, Metrics]:
    """Run LLM inference for one proposal batch.

    Args:
        backend: Configured inference backend.
        batch: Session batch with pre-extracted contexts.
        installed_skills: Already-installed skills to avoid duplicates.
        log_dir: Timestamped directory for saving prompts and outputs.
        batch_index: Zero-based batch index for file naming.

    Returns:
        Tuple of (parsed proposal output, per-call metrics).
    """
    digest = format_context_batch(batch)
    session_count = len(batch.contexts)

    system_prompt = render_system_for(CREATION_PROPOSAL_PROMPT, backend)

    # Truncate digest to fit context budget
    non_digest_overhead = CREATION_PROPOSAL_PROMPT.render_user(
        session_count=session_count,
        session_digest="",
        installed_skills=installed_skills if installed_skills else None,
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = CREATION_PROPOSAL_PROMPT.render_user(
        session_count=session_count,
        session_digest=digest,
        installed_skills=installed_skills if installed_skills else None,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_CREATION_PROPOSAL_OUTPUT_TOKENS,
        timeout=SKILL_CREATION_PROPOSAL_TIMEOUT_SECONDS,
        json_schema=CREATION_PROPOSAL_PROMPT.output_json_schema(),
        analysis_cwd=CREATION_CWD,
    )

    if batch_index == 0:
        save_inference_log(log_dir, "skill_creation_proposal_system.txt", system_prompt)
    save_inference_log(log_dir, f"skill_creation_proposal_user_{batch_index}.txt", user_prompt)

    result = await backend.generate(request)
    save_inference_log(log_dir, f"skill_creation_proposal_output_{batch_index}.txt", result.text)

    proposal_output = parse_llm_output(result.text, CreationProposalBatch, "proposal")
    return proposal_output, metrics_from_result(result)


async def _synthesize_creation_proposals(
    backend: InferenceBackend,
    batch_results: list[tuple[CreationProposalBatch, Metrics]],
    session_count: int,
    log_dir: Path,
) -> tuple[CreationProposalBatch, Metrics]:
    """Merge proposals from multiple batches via LLM synthesis.

    Args:
        backend: Configured inference backend.
        batch_results: Per-batch proposal outputs and metrics.
        session_count: Total number of sessions analyzed.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (merged CreationProposalBatch, synthesis call metrics).
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
                    "description": p.description,
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
        prompt=CREATION_PROPOSAL_SYNTHESIS_PROMPT,
        output_model=CreationProposalBatch,
        batch_data=batch_data,
        session_count=session_count,
        log_dir=log_dir,
        max_output_tokens=SKILL_CREATION_SYNTHESIS_OUTPUT_TOKENS,
        timeout_seconds=SKILL_CREATION_SYNTHESIS_TIMEOUT_SECONDS,
        analysis_cwd=CREATION_CWD,
    )

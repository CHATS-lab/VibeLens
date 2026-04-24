"""Recommendation engine — L1-L4 orchestrator.

Pipeline:
  L1: Context extraction (no LLM) — load sessions, compress to digest
  L2: LLM profile generation (1 call) — extract UserProfile from digest
  L3: Unified catalog search (no LLM) — retrieve + rank candidates
  L4: LLM rationale generation (1 call) — personalize top candidates
"""

import hashlib
import time
from datetime import datetime, timezone

from cachetools import TTLCache

from vibelens.context import (
    MetadataExtractor,
    format_context_batch,
    sample_contexts,
    truncate_digest_to_fit,
)
from vibelens.deps import get_recommendation_store, get_settings
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.backends.cli_base import RECOMMENDATION_CWD
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.extension import AgentExtensionItem
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.personalization.enums import PersonalizationMode
from vibelens.models.personalization.recommendation import (
    RankedRecommendationItem,
    RationaleOutput,
    RecommendationItem,
    UserProfile,
)
from vibelens.models.personalization.results import PersonalizationResult
from vibelens.models.trajectories.metrics import Metrics
from vibelens.prompts.recommendation import (
    RECOMMENDATION_PROFILE_PROMPT,
    RECOMMENDATION_RATIONALE_PROMPT,
)
from vibelens.services.extensions.search import ExtensionQuery, SortMode, rank_catalog
from vibelens.services.inference_log import (
    InferenceCallContext,
    InferenceLogWriter,
    analysis_log_dir,
    run_inference,
)
from vibelens.services.inference_shared import (
    CACHE_MAXSIZE,
    CACHE_TTL_SECONDS,
    aggregate_final_metrics,
    extract_all_contexts,
    parse_llm_output,
    render_system_for,
    require_backend,
)
from vibelens.services.session.store_resolver import list_all_metadata
from vibelens.storage.extension.catalog import CatalogSnapshot, load_catalog
from vibelens.utils.content import truncate
from vibelens.utils.identifiers import generate_timestamped_id
from vibelens.utils.log import clear_analysis_id, get_logger, set_analysis_id

logger = get_logger(__name__)

# L3 ranking: how many candidates survive ranking for L4 input.
SCORING_TOP_K = 100
# L4: maximum recommendations to return (CLI --top-n can override, capped here)
RATIONALE_MAX_RESULTS = 15
# Absolute upper bound for top_n
RATIONALE_MAX_RESULTS_LIMIT = 50
# L4: minimum relevance for inclusion
RATIONALE_MIN_RELEVANCE = 0.6
# Max chars for candidate descriptions sent to L4
DESCRIPTION_MAX_CHARS = 150
_cache: TTLCache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL_SECONDS)


def estimate_recommendation(
    session_ids: list[str], session_token: str | None = None
) -> CostEstimate:
    """Pre-flight cost estimate for recommendation analysis.

    Extracts contexts and estimates LLM cost for the two calls
    (L2 profile + L4 rationale) without running inference.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        CostEstimate with projected cost range.

    Raises:
        ValueError: If no sessions could be loaded or no catalog available.
    """
    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, extractor=MetadataExtractor()
    )
    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    catalog = load_catalog()
    if not catalog or not catalog.items:
        raise ValueError("No catalog available for recommendations.")

    digest = format_context_batch(context_set)
    profile_system = render_system_for(RECOMMENDATION_PROFILE_PROMPT, backend)
    digest_tokens = count_tokens(digest)

    # L2 profile call: system + user (digest)
    # L4 rationale call: estimated as extra_call
    rationale_system = render_system_for(
        RECOMMENDATION_RATIONALE_PROMPT,
        backend,
        max_results=RATIONALE_MAX_RESULTS,
        min_relevance=RATIONALE_MIN_RELEVANCE,
    )
    rationale_input_estimate = count_tokens(rationale_system) + 2000  # profile + candidates
    max_output = get_settings().inference.max_output_tokens

    return estimate_analysis_cost(
        batch_token_counts=[digest_tokens],
        system_prompt=profile_system,
        model=backend.model,
        max_output_tokens=max_output,
        synthesis_output_tokens=0,
        synthesis_threshold=999,
        extra_calls=[(rationale_input_estimate, max_output)],
    )


async def analyze_recommendation(
    session_ids: list[str] | None = None,
    session_token: str | None = None,
    top_n: int = RATIONALE_MAX_RESULTS,
) -> PersonalizationResult:
    """Run the full L1-L4 recommendation pipeline.

    L1: Extract session contexts (no LLM)
    L2: Generate user profile via LLM (1 call)
    L3: Unified catalog search, profile-weighted (no LLM)
    L4: Generate personalized rationales via LLM (1 call)

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.
        top_n: Maximum recommendations to return (capped at RATIONALE_MAX_RESULTS_LIMIT).

    Returns:
        PersonalizationResult with ranked, rationalized recommendations.

    Raises:
        ValueError: If no sessions loaded or no catalog available.
        InferenceError: If LLM backend fails.
    """
    top_n = min(max(top_n, 1), RATIONALE_MAX_RESULTS_LIMIT)

    cache_key = _recommendation_cache_key(session_ids)
    if cache_key in _cache:
        return _cache[cache_key]

    analysis_id = generate_timestamped_id()
    set_analysis_id(analysis_id)

    try:
        result = await _run_pipeline(session_ids, session_token, analysis_id, top_n=top_n)
    finally:
        clear_analysis_id()

    get_recommendation_store().save(result, analysis_id)
    _cache[cache_key] = result
    return result


async def _run_pipeline(
    session_ids: list[str] | None,
    session_token: str | None,
    analysis_id: str,
    top_n: int = RATIONALE_MAX_RESULTS,
) -> PersonalizationResult:
    """Execute L1-L4 pipeline steps.

    Separated from analyze_recommendation for clean try/finally in caller.

    Args:
        session_ids: Sessions to analyze. None discovers all local sessions.
        session_token: Browser tab token.
        analysis_id: Pre-generated analysis ID for log correlation.
        top_n: Maximum recommendations for L4 to return.

    Returns:
        PersonalizationResult with all pipeline outputs.
    """
    start_time = time.monotonic()
    backend = require_backend()

    # L1: Context extraction
    if not session_ids:
        # CLI path: discover all local sessions
        all_metadata = list_all_metadata(session_token)
        if not all_metadata:
            raise ValueError("No sessions found in local stores.")
        session_ids = [m.get("session_id", "") for m in all_metadata if m.get("session_id")]

    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, extractor=MetadataExtractor()
    )
    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from {len(session_ids)} session IDs")
    loaded_session_ids = context_set.session_ids
    skipped_session_ids = context_set.skipped_session_ids

    # Smart sampling: select diverse, recent sessions within token budget
    context_set = sample_contexts(context_set)
    digest = format_context_batch(context_set)

    catalog = load_catalog()
    if not catalog or not catalog.items:
        return _build_empty_result(
            analysis_id=analysis_id,
            session_ids=loaded_session_ids,
            skipped_session_ids=skipped_session_ids,
            backend=backend,
            reason="No catalog available",
        )

    log_dir = analysis_log_dir("recommendation") / analysis_id
    writer = InferenceLogWriter(
        log_dir, analysis_id, mode="recommendation", config=get_settings().inference
    )

    logger.info(
        "Recommendation pipeline: %d sessions, %d catalog items",
        len(loaded_session_ids),
        len(catalog.items),
    )

    # L2: Profile generation (1 LLM call)
    profile, profile_metrics = await _generate_profile(backend, digest, loaded_session_ids, writer)

    # L3: Retrieval + scoring (no LLM)
    scored_candidates = _retrieve_and_score(catalog, profile)
    if not scored_candidates:
        return _build_empty_result(
            analysis_id=analysis_id,
            session_ids=loaded_session_ids,
            skipped_session_ids=skipped_session_ids,
            backend=backend,
            reason="No matching catalog items found",
        )

    # L4: Rationale generation (1 LLM call)
    rationale_output, rationale_metrics = await _generate_rationales(
        backend, profile, scored_candidates, writer, top_n=top_n
    )

    ranked_items = _merge_and_rank(scored_candidates, rationale_output)

    title = f"Top {len(ranked_items)} recommendations for your workflow"
    if len(ranked_items) == 1:
        title = "1 recommendation for your workflow"

    duration = int(time.monotonic() - start_time)
    batch_metrics = [profile_metrics, rationale_metrics]

    return PersonalizationResult(
        id=analysis_id,
        mode=PersonalizationMode.RECOMMENDATION,
        session_ids=loaded_session_ids,
        skipped_session_ids=skipped_session_ids,
        title=title,
        user_profile=profile,
        recommendations=ranked_items,
        backend=backend.backend_id,
        model=backend.model,
        created_at=datetime.now(timezone.utc).isoformat(),
        batch_count=2,
        batch_metrics=batch_metrics,
        final_metrics=aggregate_final_metrics(batch_metrics, duration_seconds=duration),
    )


async def _generate_profile(
    backend: InferenceBackend,
    digest: str,
    session_ids: list[str],
    writer: InferenceLogWriter,
) -> tuple[UserProfile, Metrics]:
    """L2: Generate user profile from session digest.

    Args:
        backend: Configured inference backend.
        digest: Concatenated session context text.
        session_ids: IDs of loaded sessions (for template).
        writer: Log writer for this analysis run.

    Returns:
        Tuple of (parsed UserProfile, step metrics).
    """
    system_prompt = render_system_for(RECOMMENDATION_PROFILE_PROMPT, backend)

    non_digest_overhead = RECOMMENDATION_PROFILE_PROMPT.render_user(
        session_count=len(session_ids), session_digest=""
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = RECOMMENDATION_PROFILE_PROMPT.render_user(
        session_count=len(session_ids), session_digest=digest
    )

    system_file = "profile_system.txt"
    user_file = "profile_user.txt"
    writer.log_prompt_file(system_file, system_prompt)
    writer.log_prompt_file(user_file, user_prompt)

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        json_schema=RECOMMENDATION_PROFILE_PROMPT.output_json_schema(),
        workspace_dir=RECOMMENDATION_CWD,
    )
    context = InferenceCallContext(
        task_id="recommendation_profile", system_file=system_file, user_file=user_file
    )
    result = await run_inference(backend, request, writer, context)

    profile = parse_llm_output(result.text, UserProfile, "recommendation profile")
    metrics = result.metrics
    logger.info(
        "L2 profile: %d domains, %d languages, %d keywords",
        len(profile.domains),
        len(profile.languages),
        len(profile.search_keywords),
    )
    return profile, metrics


def _retrieve_and_score(
    catalog: CatalogSnapshot, profile: UserProfile
) -> list[tuple[AgentExtensionItem, float]]:
    """L3: Rank catalog via unified search with ``PERSONALIZED`` weights.

    Delegates to :func:`services.extensions.search.search`. The resulting
    ranked list is truncated to ``SCORING_TOP_K`` candidates before
    handing off to L4 rationale generation.

    Args:
        catalog: Loaded catalog snapshot (used to hydrate items by id).
        profile: User profile from L2.

    Returns:
        Top-k (ExtensionItem, composite_score) pairs for L4 input.
    """
    extension_query = ExtensionQuery(profile=profile, sort=SortMode.PERSONALIZED)
    ranked = rank_catalog(extension_query, top_k=SCORING_TOP_K)
    logger.info(
        "L3 ranking: %d candidates from %d search_keywords",
        len(ranked),
        len(profile.search_keywords),
    )
    results: list[tuple[AgentExtensionItem, float]] = []
    for scored in ranked:
        item = catalog.get_full(scored.extension_id) or catalog.get_item(scored.extension_id)
        if item is not None:
            results.append((item, scored.composite_score))
    return results


def _build_rationale_candidates(
    scored_candidates: list[tuple[AgentExtensionItem, float]],
) -> list[dict[str, str]]:
    """Shape the L4 prompt's candidate block.

    Catalog items can have ``description=None``; coerce to empty string
    before truncating so the template renders cleanly.
    """
    return [
        {
            "item_id": item.extension_id,
            "name": item.name,
            "description": truncate(item.description or "", max_chars=DESCRIPTION_MAX_CHARS),
        }
        for item, _ in scored_candidates
    ]


async def _generate_rationales(
    backend: InferenceBackend,
    profile: UserProfile,
    scored_candidates: list[tuple[AgentExtensionItem, float]],
    writer: InferenceLogWriter,
    top_n: int = RATIONALE_MAX_RESULTS,
) -> tuple[RationaleOutput, Metrics]:
    """L4: Generate personalized rationales for top candidates.

    Args:
        backend: Configured inference backend.
        profile: User profile from L2.
        scored_candidates: Scored (ExtensionItem, score) pairs from L3.
        writer: Log writer for this analysis run.
        top_n: Maximum recommendations for L4 to return.

    Returns:
        Tuple of (RationaleOutput, step metrics).
    """
    candidates_for_template = _build_rationale_candidates(scored_candidates)

    system_prompt = render_system_for(
        RECOMMENDATION_RATIONALE_PROMPT,
        backend,
        max_results=top_n,
        min_relevance=RATIONALE_MIN_RELEVANCE,
    )
    user_prompt = RECOMMENDATION_RATIONALE_PROMPT.render_user(
        user_profile=profile.model_dump(), candidates=candidates_for_template
    )

    system_file = "rationale_system.txt"
    user_file = "rationale_user.txt"
    writer.log_prompt_file(system_file, system_prompt)
    writer.log_prompt_file(user_file, user_prompt)

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        json_schema=RECOMMENDATION_RATIONALE_PROMPT.output_json_schema(),
        workspace_dir=RECOMMENDATION_CWD,
    )
    context = InferenceCallContext(
        task_id="recommendation_rationale", system_file=system_file, user_file=user_file
    )
    result = await run_inference(backend, request, writer, context)

    rationale_output = parse_llm_output(result.text, RationaleOutput, "recommendation rationale")
    metrics = result.metrics
    logger.info("L4 rationale: %d rationales generated", len(rationale_output.rationales))
    return rationale_output, metrics


def _merge_and_rank(
    scored_candidates: list[tuple[AgentExtensionItem, float]], rationale_output: RationaleOutput
) -> list[RankedRecommendationItem]:
    """Combine L3 scores with L4 ranked rationales into final recommendations.

    L4 list order determines final ranking (first = best).
    Items in the rationale output that don't match a scored candidate are skipped.

    Args:
        scored_candidates: Ranked (ExtensionItem, score) pairs from L3.
        rationale_output: LLM rationales from L4 (ordered by rank).

    Returns:
        Ordered list of RankedRecommendationItem.
    """
    score_map = {item.extension_id: score for item, score in scored_candidates}
    quality_map = {item.extension_id: item.quality_score for item, _ in scored_candidates}
    item_map = {item.extension_id: item for item, _ in scored_candidates}

    results: list[RankedRecommendationItem] = []
    for r in rationale_output.rationales:
        cat = item_map.get(r.item_id)
        if not cat:
            continue
        results.append(
            RankedRecommendationItem(
                item=RecommendationItem(
                    extension_id=cat.extension_id,
                    extension_type=cat.extension_type,
                    name=cat.name,
                    description=cat.description or "",
                    topics=cat.topics,
                    updated_at=cat.updated_at or "",
                    source_url=cat.source_url,
                    repo_name=cat.repo_full_name,
                    stars=cat.stars,
                    forks=cat.forks,
                    license=cat.license or "",
                    install_command=cat.install_command,
                    language=cat.language or "",
                ),
                rationale=r.rationale,
                scores={
                    "relevance": r.relevance,
                    "quality": quality_map.get(r.item_id, 0.0),
                    "composite": score_map.get(r.item_id, 0.0),
                },
            )
        )
    return results


def _build_empty_result(
    analysis_id: str,
    session_ids: list[str],
    skipped_session_ids: list[str],
    backend: InferenceBackend,
    reason: str,
) -> PersonalizationResult:
    """Build a result with zero recommendations.

    Args:
        analysis_id: Pre-generated analysis ID.
        session_ids: Successfully loaded session IDs.
        skipped_session_ids: Session IDs that could not be loaded.
        backend: Inference backend (for metadata).
        reason: Why no recommendations were generated.

    Returns:
        PersonalizationResult with empty recommendations.
    """
    return PersonalizationResult(
        id=analysis_id,
        mode=PersonalizationMode.RECOMMENDATION,
        session_ids=session_ids,
        skipped_session_ids=skipped_session_ids,
        title=reason,
        recommendations=[],
        backend=backend.backend_id,
        model=backend.model,
        created_at=datetime.now(timezone.utc).isoformat(),
        batch_count=0,
    )


def _recommendation_cache_key(session_ids: list[str] | None) -> str:
    """Generate a cache key from sorted session IDs."""
    if not session_ids:
        return "recommendation:all-local"
    sorted_ids = ",".join(sorted(session_ids))
    return f"recommendation:{hashlib.sha256(sorted_ids.encode()).hexdigest()[:16]}"

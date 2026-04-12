"""Recommendation engine — L1-L4 orchestrator.

Pipeline:
  L1: Context extraction (no LLM) — load sessions, compress to digest
  L2: LLM profile generation (1 call) — extract UserProfile from digest
  L3: TF-IDF retrieval + weighted scoring (no LLM)
  L4: LLM rationale generation (1 call) — personalize top candidates
"""

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from cachetools import TTLCache

from vibelens.deps import get_recommendation_store
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.recommendation.catalog import ITEM_TYPE_LABELS, CatalogItem
from vibelens.models.recommendation.profile import UserProfile
from vibelens.models.recommendation.results import (
    CatalogRecommendation,
    RationaleOutput,
    RecommendationResult,
)
from vibelens.models.trajectories.metrics import Metrics
from vibelens.prompts.recommendation import (
    RECOMMENDATION_PROFILE_PROMPT,
    RECOMMENDATION_RATIONALE_PROMPT,
)
from vibelens.services.analysis_shared import (
    CACHE_MAXSIZE,
    CACHE_TTL_SECONDS,
    build_system_kwargs,
    extract_all_contexts,
    format_batch_digest,
    require_backend,
    save_analysis_log,
    truncate_digest_to_fit,
)
from vibelens.services.analysis_store import generate_analysis_id
from vibelens.services.context_params import PRESET_RECOMMENDATION
from vibelens.services.recommendation.catalog import CatalogSnapshot, load_catalog
from vibelens.services.recommendation.retrieval import KeywordRetrieval
from vibelens.services.recommendation.scoring import score_candidates
from vibelens.services.skill.shared import parse_llm_output
from vibelens.utils.log import clear_analysis_id, get_logger, set_analysis_id

logger = get_logger(__name__)

# L3 retrieval: how many raw TF-IDF candidates to fetch
RETRIEVAL_TOP_K = 30
# L3 scoring: how many candidates survive weighted scoring
SCORING_TOP_K = 15
# Max output tokens for each LLM call (profile + rationale)
RECOMMENDATION_OUTPUT_TOKENS = 4096
# Timeout per LLM call (seconds)
RECOMMENDATION_TIMEOUT_SECONDS = 120
# Directory for detailed request/response analysis logs
RECOMMENDATION_LOG_DIR = Path("logs/recommendation")

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
        session_ids=session_ids,
        session_token=session_token,
        params=PRESET_RECOMMENDATION,
    )
    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    catalog = load_catalog()
    if not catalog or not catalog.items:
        raise ValueError("No catalog available for recommendations.")

    digest = format_batch_digest(context_set)
    profile_system = RECOMMENDATION_PROFILE_PROMPT.render_system()
    digest_tokens = count_tokens(digest)

    # L2 profile call: system + user (digest)
    # L4 rationale call: estimated as extra_call
    rationale_system = RECOMMENDATION_RATIONALE_PROMPT.render_system()
    rationale_input_estimate = count_tokens(rationale_system) + 2000  # profile + candidates

    return estimate_analysis_cost(
        batch_token_counts=[digest_tokens],
        system_prompt=profile_system,
        model=backend.model,
        max_output_tokens=RECOMMENDATION_OUTPUT_TOKENS,
        synthesis_output_tokens=0,
        synthesis_threshold=999,
        extra_calls=[(rationale_input_estimate, RECOMMENDATION_OUTPUT_TOKENS)],
    )


async def analyze_recommendation(
    session_ids: list[str], session_token: str | None = None
) -> RecommendationResult:
    """Run the full L1-L4 recommendation pipeline.

    L1: Extract session contexts (no LLM)
    L2: Generate user profile via LLM (1 call)
    L3: TF-IDF retrieval + weighted scoring (no LLM)
    L4: Generate personalized rationales via LLM (1 call)

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        RecommendationResult with ranked, rationalized recommendations.

    Raises:
        ValueError: If no sessions loaded or no catalog available.
        InferenceError: If LLM backend fails.
    """
    cache_key = _recommendation_cache_key(session_ids)
    if cache_key in _cache:
        return _cache[cache_key]

    start_time = time.monotonic()
    analysis_id = generate_analysis_id()
    set_analysis_id(analysis_id)

    try:
        result = await _run_pipeline(session_ids, session_token, analysis_id)
    finally:
        clear_analysis_id()

    result.duration_seconds = round(time.monotonic() - start_time, 2)
    get_recommendation_store().save(result, analysis_id)
    _cache[cache_key] = result
    return result


async def _run_pipeline(
    session_ids: list[str], session_token: str | None, analysis_id: str
) -> RecommendationResult:
    """Execute L1-L4 pipeline steps.

    Separated from analyze_recommendation for clean try/finally in caller.

    Args:
        session_ids: Sessions to analyze.
        session_token: Browser tab token.
        analysis_id: Pre-generated analysis ID for log correlation.

    Returns:
        RecommendationResult with all pipeline outputs.
    """
    backend = require_backend()

    # L1: Context extraction
    context_set = extract_all_contexts(
        session_ids=session_ids,
        session_token=session_token,
        params=PRESET_RECOMMENDATION,
    )
    if not context_set.contexts:
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    catalog = load_catalog()
    if not catalog or not catalog.items:
        return _build_empty_result(
            analysis_id=analysis_id,
            session_ids=context_set.session_ids,
            skipped_session_ids=context_set.skipped_session_ids,
            backend=backend,
            reason="No catalog available",
        )

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = RECOMMENDATION_LOG_DIR / run_timestamp
    digest = format_batch_digest(context_set)

    logger.info(
        "Recommendation pipeline: %d sessions, %d catalog items",
        len(context_set.session_ids),
        len(catalog.items),
    )

    # L2: Profile generation (1 LLM call)
    profile, profile_cost = await _generate_profile(
        backend, digest, context_set.session_ids, log_dir
    )

    # L3: Retrieval + scoring (no LLM)
    scored_candidates = _retrieve_and_score(catalog, profile)
    if not scored_candidates:
        return _build_empty_result(
            analysis_id=analysis_id,
            session_ids=context_set.session_ids,
            skipped_session_ids=context_set.skipped_session_ids,
            backend=backend,
            reason="No matching catalog items found",
            profile=profile,
            catalog_version=catalog.version,
        )

    # L4: Rationale generation (1 LLM call)
    rationale_output, rationale_cost = await _generate_rationales(
        backend, profile, scored_candidates, log_dir
    )

    total_cost = profile_cost + rationale_cost
    recommendations = _merge_scores_and_rationales(scored_candidates, rationale_output)

    title = f"Top {len(recommendations)} recommendations for your workflow"
    if len(recommendations) == 1:
        title = "1 recommendation for your workflow"

    return RecommendationResult(
        analysis_id=analysis_id,
        session_ids=context_set.session_ids,
        skipped_session_ids=context_set.skipped_session_ids,
        title=title,
        summary=_build_summary(profile, len(recommendations)),
        user_profile=profile,
        recommendations=recommendations,
        backend_id=backend.backend_id,
        model=backend.model,
        created_at=datetime.now(timezone.utc).isoformat(),
        metrics=Metrics(cost_usd=total_cost if total_cost > 0 else None),
        catalog_version=catalog.version,
    )


async def _generate_profile(
    backend: InferenceBackend, digest: str, session_ids: list[str], log_dir: Path
) -> tuple[UserProfile, float]:
    """L2: Generate user profile from session digest.

    Args:
        backend: Configured inference backend.
        digest: Concatenated session context text.
        session_ids: IDs of loaded sessions (for template).
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (parsed UserProfile, cost in USD).
    """
    system_kwargs = build_system_kwargs(RECOMMENDATION_PROFILE_PROMPT, backend)
    system_prompt = RECOMMENDATION_PROFILE_PROMPT.render_system(**system_kwargs)

    non_digest_overhead = RECOMMENDATION_PROFILE_PROMPT.render_user(
        session_count=len(session_ids), session_digest=""
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = RECOMMENDATION_PROFILE_PROMPT.render_user(
        session_count=len(session_ids), session_digest=digest
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=RECOMMENDATION_OUTPUT_TOKENS,
        timeout=RECOMMENDATION_TIMEOUT_SECONDS,
        json_schema=RECOMMENDATION_PROFILE_PROMPT.output_json_schema(),
    )

    save_analysis_log(log_dir, "profile_system.txt", system_prompt)
    save_analysis_log(log_dir, "profile_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, "profile_output.txt", result.text)

    profile = parse_llm_output(result.text, UserProfile, "recommendation profile")
    cost = result.cost_usd or 0.0
    logger.info(
        "L2 profile: %d domains, %d languages, %d keywords",
        len(profile.domains),
        len(profile.languages),
        len(profile.search_keywords),
    )
    return profile, cost


def _retrieve_and_score(
    catalog: CatalogSnapshot, profile: UserProfile
) -> list[tuple[CatalogItem, float]]:
    """L3: TF-IDF retrieval then weighted scoring.

    Args:
        catalog: Loaded catalog snapshot.
        profile: User profile from L2.

    Returns:
        Top-k scored (CatalogItem, composite_score) pairs.
    """
    retrieval = KeywordRetrieval()
    retrieval.build_index(catalog.items)

    query = " ".join(profile.search_keywords)
    raw_candidates = retrieval.search(query=query, top_k=RETRIEVAL_TOP_K)
    keyword_count = len(profile.search_keywords)
    logger.info("L3 retrieval: %d candidates from %d keywords", len(raw_candidates), keyword_count)

    if not raw_candidates:
        return []

    scored = score_candidates(
        candidates=raw_candidates,
        profile=profile,
        top_k=SCORING_TOP_K,
    )
    logger.info("L3 scoring: %d → %d candidates", len(raw_candidates), len(scored))
    return scored


async def _generate_rationales(
    backend: InferenceBackend,
    profile: UserProfile,
    scored_candidates: list[tuple[CatalogItem, float]],
    log_dir: Path,
) -> tuple[RationaleOutput, float]:
    """L4: Generate personalized rationales for top candidates.

    Args:
        backend: Configured inference backend.
        profile: User profile from L2.
        scored_candidates: Scored (CatalogItem, score) pairs from L3.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (RationaleOutput, cost in USD).
    """
    candidates_for_template = [
        {
            "item_id": item.item_id,
            "name": item.name,
            "description": item.description,
        }
        for item, _ in scored_candidates
    ]

    system_kwargs = build_system_kwargs(RECOMMENDATION_RATIONALE_PROMPT, backend)
    system_prompt = RECOMMENDATION_RATIONALE_PROMPT.render_system(**system_kwargs)
    user_prompt = RECOMMENDATION_RATIONALE_PROMPT.render_user(
        user_profile=profile.model_dump(),
        candidates=candidates_for_template,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=RECOMMENDATION_OUTPUT_TOKENS,
        timeout=RECOMMENDATION_TIMEOUT_SECONDS,
        json_schema=RECOMMENDATION_RATIONALE_PROMPT.output_json_schema(),
    )

    save_analysis_log(log_dir, "rationale_system.txt", system_prompt)
    save_analysis_log(log_dir, "rationale_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, "rationale_output.txt", result.text)

    rationale_output = parse_llm_output(result.text, RationaleOutput, "recommendation rationale")
    cost = result.cost_usd or 0.0
    logger.info("L4 rationale: %d rationales generated", len(rationale_output.rationales))
    return rationale_output, cost


def _merge_scores_and_rationales(
    scored_candidates: list[tuple[CatalogItem, float]],
    rationale_output: RationaleOutput,
) -> list[CatalogRecommendation]:
    """Combine L3 scores with L4 rationales into final recommendations.

    Items without a matching rationale get a generic fallback.
    Order follows the L3 scoring rank.

    Args:
        scored_candidates: Ranked (CatalogItem, score) pairs from L3.
        rationale_output: LLM rationales from L4.

    Returns:
        Ordered list of CatalogRecommendation.
    """
    rationale_map = {r.item_id: r for r in rationale_output.rationales}

    recommendations: list[CatalogRecommendation] = []
    for item, score in scored_candidates:
        rationale_item = rationale_map.get(item.item_id)
        rationale_text = rationale_item.rationale if rationale_item else "Matches your workflow."
        confidence = rationale_item.confidence if rationale_item else 0.5

        recommendations.append(CatalogRecommendation(
            item_id=item.item_id,
            item_type=item.item_type,
            user_label=ITEM_TYPE_LABELS.get(item.item_type, item.item_type.value),
            name=item.name,
            description=item.description,
            rationale=rationale_text,
            confidence=confidence,
            quality_score=item.quality_score,
            score=round(score, 4),
            install_method=item.install_method,
            install_command=item.install_command,
            has_content=item.install_content is not None,
            source_url=item.source_url,
        ))
    return recommendations


def _build_empty_result(
    analysis_id: str,
    session_ids: list[str],
    skipped_session_ids: list[str],
    backend: InferenceBackend,
    reason: str,
    profile: UserProfile | None = None,
    catalog_version: str = "unknown",
) -> RecommendationResult:
    """Build a result with zero recommendations.

    Args:
        analysis_id: Pre-generated analysis ID.
        session_ids: Successfully loaded session IDs.
        skipped_session_ids: Session IDs that could not be loaded.
        backend: Inference backend (for metadata).
        reason: Why no recommendations were generated.
        profile: Optional user profile (if L2 completed before failure).
        catalog_version: Catalog version string.

    Returns:
        RecommendationResult with empty recommendations list.
    """
    empty_profile = profile or UserProfile(
        domains=[],
        languages=[],
        frameworks=[],
        agent_platforms=[],
        bottlenecks=[],
        workflow_style="unknown",
        search_keywords=[],
    )
    return RecommendationResult(
        analysis_id=analysis_id,
        session_ids=session_ids,
        skipped_session_ids=skipped_session_ids,
        title="No recommendations available",
        summary=reason,
        user_profile=empty_profile,
        recommendations=[],
        backend_id=backend.backend_id,
        model=backend.model,
        created_at=datetime.now(timezone.utc).isoformat(),
        catalog_version=catalog_version,
    )


def _build_summary(profile: UserProfile, count: int) -> str:
    """Build a 1-2 sentence narrative summary from the profile.

    Args:
        profile: Extracted user profile.
        count: Number of recommendations generated.

    Returns:
        Plain-language summary string.
    """
    domains_text = ", ".join(profile.domains[:3]) if profile.domains else "general development"
    return (
        f"Based on {domains_text} sessions, found {count} "
        f"tool{'s' if count != 1 else ''} that match your workflow."
    )


def _recommendation_cache_key(session_ids: list[str]) -> str:
    """Generate a cache key from sorted session IDs."""
    sorted_ids = ",".join(sorted(session_ids))
    return f"recommendation:{hashlib.sha256(sorted_ids.encode()).hexdigest()[:16]}"

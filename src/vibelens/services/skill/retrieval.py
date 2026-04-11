"""Skill retrieval mode — recommend existing skills from the featured catalog."""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from vibelens.deps import get_skill_analysis_store
from vibelens.llm.backend import InferenceBackend
from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.prompts.skill_retrieval import (
    SKILL_RETRIEVAL_PROMPT,
    SKILL_RETRIEVAL_SYNTHESIS_PROMPT,
)
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContextBatch
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.skill import (
    SkillAnalysisResult,
    SkillMode,
    SkillRetrievalOutput,
    WorkflowPattern,
)
from vibelens.models.trajectories.metrics import Metrics
from vibelens.services.analysis_shared import (
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
from vibelens.services.context_params import PRESET_CONCISE, PRESET_MEDIUM
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

# JSON manifest of all skills available for recommendation
FEATURED_SKILLS_PATH = Path(__file__).resolve().parents[4] / "featured-skills.json"
# Skip keyword prefiltering when the catalog has fewer candidates than this
CANDIDATE_PREFILTER_THRESHOLD = 200
# Max candidates to pass to the LLM after keyword prefiltering
PREFILTER_TOP_K = 100
# Max output tokens for retrieval and synthesis LLM calls
SKILL_RETRIEVAL_OUTPUT_TOKENS = 8192
SKILL_RETRIEVAL_SYNTHESIS_OUTPUT_TOKENS = 8192
# Timeout per retrieval LLM call (seconds)
SKILL_RETRIEVAL_TIMEOUT_SECONDS = 300


def estimate_skill_retrieval(
    session_ids: list[str], session_token: str | None = None
) -> CostEstimate:
    """Pre-flight cost estimate for skill retrieval analysis.

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
    system_prompt = SKILL_RETRIEVAL_PROMPT.render_system(
        **build_system_kwargs(SKILL_RETRIEVAL_PROMPT, backend)
    )
    batch_token_counts = [count_tokens(format_batch_digest(batch)) for batch in batches]

    return estimate_analysis_cost(
        batch_token_counts=batch_token_counts,
        system_prompt=system_prompt,
        model=backend.model,
        max_output_tokens=SKILL_RETRIEVAL_OUTPUT_TOKENS,
        synthesis_output_tokens=SKILL_RETRIEVAL_SYNTHESIS_OUTPUT_TOKENS,
        synthesis_threshold=1,
    )


async def analyze_skill_retrieval(
    session_ids: list[str], session_token: str | None = None
) -> SkillAnalysisResult:
    """Run retrieval-mode skill analysis: recommend existing skills from catalog."""
    cache_key = skill_cache_key(session_ids, SkillMode.RETRIEVAL)
    if cache_key in _cache:
        return _cache[cache_key]

    start_time = time.monotonic()
    analysis_id = generate_analysis_id()
    set_analysis_id(analysis_id)

    backend = require_backend()
    context_set = extract_all_contexts(
        session_ids=session_ids, session_token=session_token, params=PRESET_CONCISE
    )

    if not context_set:
        clear_analysis_id()
        raise ValueError(f"No sessions could be loaded from: {session_ids}")

    installed_skills = gather_installed_skills()
    skill_candidates = _load_skill_retrieval_candidates()

    batches = build_batches(context_set.contexts)
    logger.info(
        "Skill retrieval: %d sessions → %d batch(es)",
        len(context_set.session_ids),
        len(batches),
    )
    log_analysis_summary(context_set, batches, backend)

    run_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = SKILL_LOG_DIR / run_timestamp

    tasks = [
        _infer_skill_retrieval_batch(
            backend, batch, installed_skills, skill_candidates, log_dir, idx
        )
        for idx, batch in enumerate(batches)
    ]
    batch_results, batch_warnings = await run_batches_concurrent(tasks, "retrieval")

    total_cost = sum(cost for _, cost in batch_results)

    # Single batch: use directly; multiple batches: synthesize
    if len(batch_results) == 1:
        llm_output = batch_results[0][0]
    else:
        llm_output, syn_cost = await _synthesize_skill_retrieval(
            backend, batch_results, len(context_set.session_ids), log_dir
        )
        total_cost += syn_cost
        # Synthesis LLM drops example_refs; recover from batch outputs
        merge_batch_refs(
            llm_output.workflow_patterns,
            [output.workflow_patterns for output, _ in batch_results],
        )

    rec_names = [r.skill_name for r in llm_output.recommendations]
    logger.info("Retrieval recommendations: %s", rec_names)

    validated_patterns = validate_patterns(llm_output.workflow_patterns, context_set)

    duration = round(time.monotonic() - start_time, 2)
    skill_result = _build_skill_retrieval_result(
        validated_patterns,
        llm_output,
        context_set.session_ids,
        context_set.skipped_session_ids,
        backend,
        total_cost if total_cost > 0 else None,
        batch_count=len(batches),
        warnings=batch_warnings,
        duration_seconds=duration,
    )
    get_skill_analysis_store().save(skill_result, analysis_id)
    clear_analysis_id()

    _cache[cache_key] = skill_result
    return skill_result


async def _infer_skill_retrieval_batch(
    backend: InferenceBackend,
    batch: SessionContextBatch,
    installed_skills: list[dict],
    skill_candidates: list[dict],
    log_dir: Path,
    batch_index: int,
) -> tuple[SkillRetrievalOutput, float]:
    """Run LLM inference for one retrieval batch.

    Args:
        backend: Configured inference backend.
        batch: Session batch with pre-extracted contexts.
        installed_skills: Already-installed skills to avoid duplicates.
        skill_candidates: Featured skill catalog entries.
        log_dir: Timestamped directory for saving prompts and outputs.
        batch_index: Zero-based batch index for file naming.

    Returns:
        Tuple of (parsed retrieval output, cost in USD).
    """
    digest = format_batch_digest(batch)
    session_count = len(batch.contexts)

    # Pre-filter candidates per batch using batch-specific keywords
    candidates = skill_candidates
    if len(candidates) > CANDIDATE_PREFILTER_THRESHOLD:
        candidates = _prefilter_skill_retrieval_candidates(candidates, digest)

    prompt = SKILL_RETRIEVAL_PROMPT
    system_kwargs = build_system_kwargs(prompt, backend)
    system_prompt = prompt.render_system(**system_kwargs)

    # Truncate digest to fit context budget
    non_digest_overhead = prompt.render_user(
        session_count=session_count,
        session_digest="",
        installed_skills=installed_skills if installed_skills else None,
        skill_candidates=candidates if candidates else None,
    )
    digest = truncate_digest_to_fit(digest, system_prompt, non_digest_overhead)

    user_prompt = prompt.render_user(
        session_count=session_count,
        session_digest=digest,
        installed_skills=installed_skills if installed_skills else None,
        skill_candidates=candidates if candidates else None,
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_RETRIEVAL_OUTPUT_TOKENS,
        timeout=SKILL_RETRIEVAL_TIMEOUT_SECONDS,
        json_schema=prompt.output_json_schema(),
    )

    if batch_index == 0:
        save_analysis_log(log_dir, "skill_retrieval_system.txt", system_prompt)
    save_analysis_log(log_dir, f"skill_retrieval_user_{batch_index}.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, f"skill_retrieval_output_{batch_index}.txt", result.text)

    retrieval_output = parse_llm_output(result.text, SkillRetrievalOutput, "retrieval")
    cost = result.cost_usd or 0.0
    return retrieval_output, cost


async def _synthesize_skill_retrieval(
    backend: InferenceBackend,
    batch_results: list[tuple[SkillRetrievalOutput, float]],
    session_count: int,
    log_dir: Path,
) -> tuple[SkillRetrievalOutput, float]:
    """Merge retrieval results from multiple batches via LLM synthesis.

    Args:
        backend: Configured inference backend.
        batch_results: Per-batch retrieval outputs and costs.
        session_count: Total number of sessions analyzed.
        log_dir: Timestamped directory for saving prompts and outputs.

    Returns:
        Tuple of (merged SkillRetrievalOutput, synthesis cost in USD).
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
            "recommendations": [
                {
                    "skill_name": r.skill_name,
                    "rationale": r.rationale,
                    "addressed_patterns": r.addressed_patterns,
                    "confidence": r.confidence,
                }
                for r in output.recommendations
            ],
        }
        for output, _ in batch_results
    ]

    prompt = SKILL_RETRIEVAL_SYNTHESIS_PROMPT
    system_kwargs = build_system_kwargs(prompt, backend)
    system_prompt = prompt.render_system(**system_kwargs)
    user_prompt = prompt.render_user(
        batch_count=len(batch_results), session_count=session_count, batch_results=batch_data
    )

    request = InferenceRequest(
        system=system_prompt,
        user=user_prompt,
        max_tokens=SKILL_RETRIEVAL_SYNTHESIS_OUTPUT_TOKENS,
        timeout=SKILL_RETRIEVAL_TIMEOUT_SECONDS,
        json_schema=prompt.output_json_schema(),
    )

    save_analysis_log(log_dir, "skill_retrieval_synthesis_system.txt", system_prompt)
    save_analysis_log(log_dir, "skill_retrieval_synthesis_user.txt", user_prompt)

    result = await backend.generate(request)
    save_analysis_log(log_dir, "skill_retrieval_synthesis_output.txt", result.text)

    synthesis_output = parse_llm_output(result.text, SkillRetrievalOutput, "retrieval synthesis")
    cost = result.cost_usd or 0.0
    return synthesis_output, cost


def _load_skill_retrieval_candidates() -> list[dict]:
    """Load skill candidates from the featured skills catalog.

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


def _prefilter_skill_retrieval_candidates(candidates: list[dict], digest: str) -> list[dict]:
    """Keyword-based pre-filtering for large skill catalogs.

    Extracts keywords from the digest (tool names, user topics, alpha tokens)
    and scores each candidate by keyword overlap in name + summary + tags.

    Args:
        candidates: Full list of skill candidate dicts.
        digest: Session digest text used for keyword extraction.

    Returns:
        Top PREFILTER_TOP_K candidates sorted by relevance score.
    """
    keywords = _extract_skill_retrieval_keywords(digest)
    if not keywords:
        return candidates[:PREFILTER_TOP_K]

    scored: list[tuple[int, dict]] = []
    for candidate in candidates:
        searchable = " ".join(
            [
                candidate.get("name", ""),
                candidate.get("summary", ""),
                " ".join(candidate.get("tags", [])),
            ]
        ).lower()
        score = sum(1 for kw in keywords if kw in searchable)
        scored.append((score, candidate))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in scored[:PREFILTER_TOP_K]]


def _extract_skill_retrieval_keywords(digest: str) -> set[str]:
    """Extract keywords from a session digest for candidate matching.

    Pulls tool names from "TOOL FREQUENCY:" blocks, user topics,
    and alpha tokens longer than 3 characters.

    Args:
        digest: Session digest text.

    Returns:
        Set of lowercase keywords.
    """
    keywords: set[str] = set()

    # Extract tool names from TOOL FREQUENCY lines (e.g. "  Edit: 15")
    for match in re.finditer(r"^\s+(\w+):\s+\d+", digest, re.MULTILINE):
        keywords.add(match.group(1).lower())

    # Extract user topics from USER TOPICS lines
    topic_match = re.search(r"USER TOPICS:\s*(.+)", digest)
    if topic_match:
        topic_text = topic_match.group(1)
        for token in re.findall(r"[a-zA-Z]{4,}", topic_text):
            keywords.add(token.lower())

    # Extract general alpha tokens from fn= tool calls
    for match in re.finditer(r"fn=(\w+)", digest):
        keywords.add(match.group(1).lower())

    return keywords


def _load_skill_descriptions() -> dict[str, str]:
    """Load skill name-to-summary mapping from the featured skills catalog.

    Returns:
        Dict mapping skill slug to its summary text.
    """
    if not FEATURED_SKILLS_PATH.is_file():
        return {}
    try:
        raw = FEATURED_SKILLS_PATH.read_text(encoding="utf-8")
        catalog = json.loads(raw)
        return {
            entry.get("slug", entry.get("name", "")): entry["summary"]
            for entry in catalog.get("skills", [])
            if entry.get("summary")
        }
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load featured skills catalog for descriptions")
        return {}


def _build_skill_retrieval_result(
    validated_patterns: list[WorkflowPattern],
    llm_output: SkillRetrievalOutput,
    loaded_ids: list[str],
    skipped_ids: list[str],
    backend: InferenceBackend,
    cost_usd: float | None,
    batch_count: int = 1,
    warnings: list[str] | None = None,
    duration_seconds: float | None = None,
) -> SkillAnalysisResult:
    """Build a SkillAnalysisResult for retrieval mode."""
    all_descriptions = _load_skill_descriptions()
    for rec in llm_output.recommendations:
        rec.description = all_descriptions.get(rec.skill_name, "")

    return SkillAnalysisResult(
        mode=SkillMode.RETRIEVAL,
        title=llm_output.title,
        workflow_patterns=validated_patterns,
        recommendations=llm_output.recommendations,
        session_ids=loaded_ids,
        skipped_session_ids=skipped_ids,
        warnings=warnings or [],
        backend_id=backend.backend_id,
        model=backend.model,
        metrics=Metrics(cost_usd=cost_usd),
        duration_seconds=duration_seconds,
        batch_count=batch_count,
        created_at=datetime.now(UTC).isoformat(),
    )

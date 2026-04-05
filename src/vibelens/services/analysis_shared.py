"""Shared infrastructure for LLM-powered analysis services.

Consolidates functions duplicated across friction, skill, and insight
analysis modules: backend retrieval, session context extraction, caching,
and log persistence.
"""

import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path

from cachetools import TTLCache
from pydantic import BaseModel

from vibelens.deps import get_inference_backend
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.inference import BackendType
from vibelens.services.context_extraction import SessionContext, extract_session_context
from vibelens.services.context_params import PRESET_DETAIL, ContextParams
from vibelens.services.session.store_resolver import (
    get_metadata_from_stores,
    load_from_stores,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 3600
CACHE_MAXSIZE = 64


def require_backend() -> InferenceBackend:
    """Get the inference backend or raise if unavailable.

    Returns:
        Configured inference backend.

    Raises:
        ValueError: If no backend is configured.
    """
    backend = get_inference_backend()
    if not backend:
        raise ValueError("No inference backend configured. Set llm.backend in config.")
    return backend


def extract_all_contexts(
    session_ids: list[str], session_token: str | None, params: ContextParams = PRESET_DETAIL
) -> tuple[list[SessionContext], list[str], list[str]]:
    """Load sessions and extract compressed contexts.

    Args:
        session_ids: Sessions to load.
        session_token: Browser tab token for upload scoping.
        params: Context extraction parameters controlling detail level.

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

        ctx = extract_session_context(trajectories, params)
        contexts.append(ctx)
        loaded_ids.append(sid)

    return contexts, loaded_ids, skipped_ids


def make_ttl_cache(
    maxsize: int = CACHE_MAXSIZE,
    ttl: int = CACHE_TTL_SECONDS,
) -> TTLCache:
    """Create a TTLCache with project defaults.

    Args:
        maxsize: Maximum number of entries before LRU eviction.
        ttl: Time-to-live in seconds.

    Returns:
        Configured TTLCache instance.
    """
    return TTLCache(maxsize=maxsize, ttl=ttl)


def build_digest_from_contexts(contexts: list[SessionContext]) -> str:
    """Concatenate session context texts into a single digest string.

    Args:
        contexts: Extracted session contexts.

    Returns:
        Combined context text, or placeholder if empty.
    """
    if not contexts:
        return "[no sessions]"
    return "\n\n".join(ctx.context_text for ctx in contexts)


def save_analysis_log(log_dir: Path, filename: str, content: str) -> None:
    """Save analysis log to a timestamped directory.

    Args:
        log_dir: Target directory (e.g. logs/friction/20260326153000).
        filename: File name within the directory.
        content: Text content to write.
    """
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / filename).write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to save analysis log %s/%s: %s", log_dir, filename, exc)


CLI_BACKEND_RULES = """
## Backend Rules

You are running as a headless analysis backend. Follow these rules strictly:

1. Output ONLY a single JSON object. No markdown fences, no prose, no explanation.
2. Do NOT use any tools (Read, Edit, Bash, etc.). You are a pure text generator.
3. Do NOT ask clarifying questions. Work with the data provided.
4. Do NOT write or modify any files. Your only output is the JSON response.
5. Start your response with `{` and end with `}`.
"""

CONTEXT_TOKEN_BUDGET = 100_000


def build_schema_json(output_model: type[BaseModel]) -> str:
    """Serialize a Pydantic model's JSON schema for prompt injection.

    Args:
        output_model: Pydantic model class.

    Returns:
        Pretty-printed JSON schema string.
    """
    return json.dumps(output_model.model_json_schema(), indent=2)


def build_system_kwargs(output_model: type[BaseModel], backend: InferenceBackend) -> dict[str, str]:
    """Build common kwargs for render_system(): output_schema + backend_rules.

    Args:
        output_model: Pydantic model class for the output schema.
        backend: Active inference backend.

    Returns:
        Dict with output_schema and backend_rules keys.
    """
    kwargs: dict[str, str] = {"output_schema": build_schema_json(output_model)}
    if backend.backend_id != BackendType.LITELLM:
        kwargs["backend_rules"] = CLI_BACKEND_RULES
    else:
        kwargs["backend_rules"] = ""
    return kwargs


def truncate_digest_to_fit(
    digest: str,
    system_prompt: str,
    other_user_content: str,
    budget_tokens: int = CONTEXT_TOKEN_BUDGET,
) -> str:
    """Truncate digest so the total prompt stays within budget.

    Preserves the first and last portions of the digest, cutting from the middle.

    Args:
        digest: Session digest text.
        system_prompt: Rendered system prompt.
        other_user_content: Non-digest portion of the user prompt.
        budget_tokens: Maximum token budget for the full prompt.

    Returns:
        Possibly truncated digest string.
    """
    overhead_tokens = count_tokens(system_prompt) + count_tokens(other_user_content)
    digest_tokens = count_tokens(digest)
    available = budget_tokens - overhead_tokens
    logger.info(
        "Token budget: overhead=%d, digest=%d, available=%d, budget=%d",
        overhead_tokens, digest_tokens, available, budget_tokens,
    )
    if available <= 0:
        return "[digest truncated -- no token budget remaining]"

    if digest_tokens <= available:
        return digest

    total_chars = len(digest)
    target_chars = int(total_chars * (available / digest_tokens))
    head_chars = int(target_chars * 0.7)
    tail_chars = target_chars - head_chars

    head = digest[:head_chars]
    tail = digest[-tail_chars:] if tail_chars > 0 else ""
    truncated_count = digest_tokens - available
    logger.info(
        "Digest truncated: %d → %d tokens (%d removed)",
        digest_tokens, available, truncated_count,
    )
    return f"{head}\n\n[... {truncated_count} tokens truncated ...]\n\n{tail}"


async def run_batches_concurrent(
    tasks: list[Coroutine], label: str
) -> tuple[list[tuple], list[str]]:
    """Run batch coroutines concurrently, tolerating individual failures.

    Generic replacement for per-module _run_all_batches / _run_proposal_batches
    functions. Each task should return a tuple (output, cost_usd).

    Args:
        tasks: List of coroutines that each return (output, cost_usd).
        label: Human-readable label for log messages (e.g. "proposal", "friction").

    Returns:
        Tuple of (successful result tuples, warning messages).

    Raises:
        InferenceError: If every task fails.
    """
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    successes: list[tuple] = []
    warnings: list[str] = []
    for idx, result in enumerate(raw_results):
        if isinstance(result, BaseException):
            warnings.append(f"Batch {idx + 1}/{len(raw_results)} failed: {result}")
            logger.warning("%s batch %d failed: %s", label.capitalize(), idx, result)
        else:
            successes.append(result)

    if not successes:
        raise InferenceError(
            f"All {len(raw_results)} {label} batch(es) failed. Last error: {raw_results[-1]}"
        )

    return successes, warnings

"""Insight service — LLM-powered session analysis orchestration.

Pipeline: load session → digest → format prompt → infer → parse → cache.
Generic over any AnalysisPrompt — the service doesn't know or care
what specific analysis type is being run.
"""

import json
import time
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from vibelens.deps import get_inference_backend, get_store
from vibelens.llm.backend import InferenceBackend, InferenceError
from vibelens.llm.digest import digest_trajectory, select_depth
from vibelens.llm.prompts import PROMPT_REGISTRY
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.analysis.insights import InsightReport
from vibelens.models.analysis.prompts import AnalysisPrompt
from vibelens.models.inference import BackendType, InferenceRequest
from vibelens.models.trajectories import Trajectory
from vibelens.services.upload_visibility import is_session_visible
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 3600

_cache: dict[str, tuple[float, BaseModel]] = {}


def is_inference_available() -> bool:
    """Check if any inference backend is configured and available."""
    return get_inference_backend() is not None


def get_backend_status() -> dict:
    """Return current inference backend status.

    Returns:
        Dict with available, backend_id, and model fields.
    """
    backend = get_inference_backend()
    if not backend:
        return {"available": False, "backend_id": BackendType.DISABLED, "model": None}
    return {
        "available": True,
        "backend_id": backend.backend_id,
        "model": _get_backend_model(backend),
    }


async def analyze_session(
    session_id: str, prompt: AnalysisPrompt, session_token: str | None = None
) -> BaseModel:
    """Run an analysis task on a session.

    Pipeline: load → digest → format prompt → infer → parse → cache.

    Args:
        session_id: Session to analyze.
        prompt: Analysis prompt template.
        session_token: Browser tab token for upload scoping.

    Returns:
        Parsed output model instance.

    Raises:
        ValueError: If session not found or backend unavailable.
        InferenceError: On inference failures.
    """
    cache_key = f"{session_id}:{prompt.task_id}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    backend = _require_backend()
    trajectories = _load_session(session_id, session_token)
    digest = _prepare_digest(trajectories)
    user_prompt = _format_user_prompt(prompt, digest)

    request = InferenceRequest(
        system=prompt.render_system(),
        user=user_prompt,
    )
    result = await backend.generate(request)
    parsed = _parse_result(result.text, prompt.output_model)

    _cache[cache_key] = (time.monotonic(), parsed)
    return parsed


async def get_session_report(session_id: str, session_token: str | None = None) -> InsightReport:
    """Run highlights + friction analysis and combine into InsightReport.

    Args:
        session_id: Session to analyze.
        session_token: Browser tab token for upload scoping.

    Returns:
        Combined InsightReport.
    """
    backend = _require_backend()

    highlights = None
    friction = None
    total_cost: float | None = None

    highlights_prompt = PROMPT_REGISTRY.get("highlights")
    friction_prompt = PROMPT_REGISTRY.get("friction")

    if highlights_prompt:
        highlights = await analyze_session(session_id, highlights_prompt, session_token)
    if friction_prompt:
        friction = await analyze_session(session_id, friction_prompt, session_token)

    return InsightReport(
        session_id=session_id,
        highlights=highlights,
        friction=friction,
        backend_id=backend.backend_id,
        model=_get_backend_model(backend),
        cost_usd=total_cost,
        created_at=datetime.now(UTC).isoformat(),
    )


async def estimate_cost(session_id: str, session_token: str | None = None) -> float | None:
    """Estimate analysis cost for a session.

    Args:
        session_id: Session to estimate.
        session_token: Browser tab token for upload scoping.

    Returns:
        Estimated cost in USD, or None for free backends.
    """
    backend = get_inference_backend()
    if not backend:
        return None

    # CLI backends are free
    if backend.backend_id in (BackendType.CLAUDE_CLI, BackendType.CODEX_CLI):
        return None

    trajectories = _load_session(session_id, session_token)
    digest = _prepare_digest(trajectories)

    estimated_input_tokens = count_tokens(digest)
    estimated_output_tokens = 1000

    from vibelens.llm.pricing import TOKENS_PER_MTOK, lookup_pricing

    model = _get_backend_model(backend)
    pricing = lookup_pricing(model)
    if not pricing:
        return None

    input_cost = (estimated_input_tokens / TOKENS_PER_MTOK) * pricing.input_per_mtok
    output_cost = (estimated_output_tokens / TOKENS_PER_MTOK) * pricing.output_per_mtok
    # Two analysis tasks (highlights + friction)
    return round((input_cost + output_cost) * 2, 6)


def _require_backend() -> InferenceBackend:
    """Get the inference backend or raise if unavailable."""
    backend = get_inference_backend()
    if not backend:
        raise ValueError("No inference backend configured. Set llm.backend in config.")
    return backend


def _load_session(session_id: str, session_token: str | None) -> list[Trajectory]:
    """Load trajectories for a session or raise if not found."""
    store = get_store()
    if not is_session_visible(store.get_metadata(session_id), session_token):
        raise ValueError(f"Session not found: {session_id}")
    trajectories = store.load(session_id)
    if not trajectories:
        raise ValueError(f"Session not found: {session_id}")
    return trajectories


def _prepare_digest(trajectories: list[Trajectory]) -> str:
    """Prepare trajectory digest with auto-selected depth."""
    total_steps = sum(len(t.steps) for t in trajectories)
    depth = select_depth(total_steps)
    return digest_trajectory(trajectories, depth)


def _format_user_prompt(prompt: AnalysisPrompt, digest: str) -> str:
    """Format the user prompt template with digest and output schema."""
    output_schema = json.dumps(prompt.output_model.model_json_schema(), indent=2)
    return prompt.render_user(trajectory_digest=digest, output_schema=output_schema)


def _parse_result(text: str, output_model: type[BaseModel]) -> BaseModel:
    """Parse LLM output text into the expected Pydantic model.

    Args:
        text: Raw LLM output text.
        output_model: Pydantic model class to parse into.

    Returns:
        Validated model instance.

    Raises:
        InferenceError: If parsing or validation fails.
    """
    json_str = _extract_json(text)
    try:
        data = json.loads(json_str)
        return output_model.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InferenceError(
            f"Failed to parse LLM output as {output_model.__name__}: {exc}"
        ) from exc


def _extract_json(text: str) -> str:
    """Extract JSON from LLM output, handling markdown code blocks."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        start = 1
        end = len(lines) - 1
        while end > start and not lines[end].strip().startswith("```"):
            end -= 1
        return "\n".join(lines[start:end])
    return stripped


def _get_cached(cache_key: str) -> BaseModel | None:
    """Return cached result if still valid, or None."""
    entry = _cache.get(cache_key)
    if not entry:
        return None
    cached_at, result = entry
    if time.monotonic() - cached_at > CACHE_TTL_SECONDS:
        del _cache[cache_key]
        return None
    return result


def _get_backend_model(backend: InferenceBackend) -> str:
    """Extract model name from a backend instance."""
    if hasattr(backend, "_model"):
        return backend._model or "unknown"
    return "unknown"

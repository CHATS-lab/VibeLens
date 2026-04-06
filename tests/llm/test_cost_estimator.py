"""Tests for the LLM cost estimation module.

Validates that pre-flight cost estimates are within acceptable range
of actual costs from real friction analysis runs.
"""

from pathlib import Path

import pytest

from vibelens.llm.cost_estimator import CostEstimate, estimate_analysis_cost
from vibelens.llm.pricing import lookup_pricing
from vibelens.llm.tokenizer import count_tokens

FRICTION_LOG_DIR = Path("logs/friction")


def _find_log_dirs_with_batches(min_batches: int) -> list[Path]:
    """Find friction log directories with at least min_batches user prompts."""
    if not FRICTION_LOG_DIR.exists():
        return []
    result = []
    for d in sorted(FRICTION_LOG_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        prompt_count = len(list(d.glob("user_prompt_*.txt")))
        if prompt_count >= min_batches:
            result.append(d)
    return result


def _load_log_dir_data(log_dir: Path) -> tuple[str, list[int]]:
    """Load system prompt and user prompt token counts from a log dir."""
    system_prompt = (log_dir / "system_prompt.txt").read_text()
    batch_tokens = []
    for f in sorted(log_dir.glob("user_prompt_*.txt")):
        batch_tokens.append(count_tokens(f.read_text()))
    return system_prompt, batch_tokens


def test_estimate_basic_structure() -> None:
    """CostEstimate has all required fields."""
    estimate = estimate_analysis_cost(
        batch_token_counts=[1000, 2000],
        system_prompt="You are a test assistant.",
        model="anthropic/claude-haiku-4-5",
        max_output_tokens=4096,
        synthesis_output_tokens=8192,
    )
    assert isinstance(estimate, CostEstimate)
    assert estimate.batch_count == 2
    assert estimate.total_input_tokens > 0
    assert estimate.total_output_tokens_budget > 0
    assert estimate.pricing_found is True
    assert estimate.cost_min_usd > 0
    assert estimate.cost_max_usd >= estimate.cost_min_usd
    assert estimate.estimated_cost_usd > 0
    print(f"Basic estimate: {estimate.formatted_cost}")
    print(f"  Range: ${estimate.cost_min_usd:.4f} – ${estimate.cost_max_usd:.4f}")
    print(f"  Input tokens: {estimate.total_input_tokens}")
    print(f"  Output budget: {estimate.total_output_tokens_budget}")


def test_estimate_unknown_model() -> None:
    """Unknown model returns pricing_found=False and zero cost."""
    estimate = estimate_analysis_cost(
        batch_token_counts=[1000],
        system_prompt="test",
        model="unknown/nonexistent-model",
        max_output_tokens=4096,
        synthesis_output_tokens=8192,
    )
    assert estimate.pricing_found is False
    assert estimate.estimated_cost_usd == 0.0
    assert "unknown" in estimate.formatted_cost
    print(f"Unknown model: {estimate.formatted_cost}")


def test_estimate_empty_batches() -> None:
    """Zero batches produces zero cost."""
    estimate = estimate_analysis_cost(
        batch_token_counts=[],
        system_prompt="test",
        model="anthropic/claude-haiku-4-5",
        max_output_tokens=4096,
        synthesis_output_tokens=8192,
    )
    assert estimate.batch_count == 0
    print(f"Empty batches: {estimate.formatted_cost}")


def test_estimate_scales_with_batches() -> None:
    """More batches produce higher estimates."""
    small = estimate_analysis_cost(
        batch_token_counts=[50000],
        system_prompt="You are a test assistant.",
        model="anthropic/claude-haiku-4-5",
        max_output_tokens=8192,
        synthesis_output_tokens=20000,
    )
    large = estimate_analysis_cost(
        batch_token_counts=[50000, 50000, 50000, 50000],
        system_prompt="You are a test assistant.",
        model="anthropic/claude-haiku-4-5",
        max_output_tokens=8192,
        synthesis_output_tokens=20000,
    )
    assert large.estimated_cost_usd > small.estimated_cost_usd
    print(f"1 batch: {small.formatted_cost}")
    print(f"4 batches: {large.formatted_cost}")
    print(f"Ratio: {large.estimated_cost_usd / small.estimated_cost_usd:.2f}")


def test_haiku_pricing_lookup() -> None:
    """Verify Claude Haiku 4.5 pricing is available."""
    pricing = lookup_pricing("anthropic/claude-haiku-4-5")
    assert pricing is not None
    assert pricing.input_per_mtok == 1.00
    assert pricing.output_per_mtok == 5.00
    print(f"Haiku pricing: ${pricing.input_per_mtok}/MTok in, ${pricing.output_per_mtok}/MTok out")


@pytest.mark.skipif(
    not _find_log_dirs_with_batches(4),
    reason="No friction logs with 4+ batches available for validation",
)
def test_estimate_vs_real_4_batch() -> None:
    """Validate estimate against a real 4-batch friction analysis."""
    log_dirs = _find_log_dirs_with_batches(4)
    log_dir = next(d for d in log_dirs if len(list(d.glob("user_prompt_*.txt"))) == 4)

    system_prompt, batch_tokens = _load_log_dir_data(log_dir)
    estimate = estimate_analysis_cost(
        batch_token_counts=batch_tokens,
        system_prompt=system_prompt,
        model="anthropic/claude-haiku-4-5",
        max_output_tokens=8192,
        synthesis_output_tokens=20000,
    )

    print(f"\n4-batch validation (log: {log_dir.name}):")
    print(f"  Estimated: {estimate.formatted_cost}")
    print(f"  Batch token counts: {batch_tokens}")
    print(f"  Total input: {estimate.total_input_tokens}")
    print(f"  Output budget: {estimate.total_output_tokens_budget}")

    # Estimate should be in a reasonable range (0.7x - 1.5x actual)
    assert estimate.estimated_cost_usd > 0.1, "Estimate too low"
    assert estimate.estimated_cost_usd < 2.0, "Estimate too high"


@pytest.mark.skipif(
    not _find_log_dirs_with_batches(8),
    reason="No friction logs with 8+ batches available for validation",
)
def test_estimate_vs_real_8_batch() -> None:
    """Validate estimate against a real 8+ batch friction analysis."""
    log_dirs = _find_log_dirs_with_batches(8)
    log_dir = log_dirs[0]
    batch_count = len(list(log_dir.glob("user_prompt_*.txt")))

    system_prompt, batch_tokens = _load_log_dir_data(log_dir)
    estimate = estimate_analysis_cost(
        batch_token_counts=batch_tokens,
        system_prompt=system_prompt,
        model="anthropic/claude-haiku-4-5",
        max_output_tokens=8192,
        synthesis_output_tokens=20000,
    )

    print(f"\n{batch_count}-batch validation (log: {log_dir.name}):")
    print(f"  Estimated: {estimate.formatted_cost}")
    print(f"  Batch token counts: {batch_tokens}")
    print(f"  Total input: {estimate.total_input_tokens}")

    assert estimate.estimated_cost_usd > 0.2, "Estimate too low"
    assert estimate.estimated_cost_usd < 3.0, "Estimate too high"

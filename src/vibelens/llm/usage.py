"""Provider-specific usage-dict parsers for InferenceResult.metrics.

Each function accepts a raw provider-usage dict (shape varies) and returns
a canonical ``Metrics`` with prompt/completion/cache tokens populated.
"""

from vibelens.models.trajectories.metrics import Metrics


def metrics_from_anthropic_usage(usage_data: dict) -> Metrics:
    """Build a Metrics from an Anthropic-style usage dict.

    Shared by Claude Code and Amp CLIs, both of which emit the four
    ``*_input_tokens`` / ``output_tokens`` keys.

    Args:
        usage_data: Dict with ``input_tokens``, ``output_tokens``,
            ``cache_creation_input_tokens``, ``cache_read_input_tokens``.

    Returns:
        Populated Metrics (missing keys default to 0).
    """
    return Metrics(
        prompt_tokens=usage_data.get("input_tokens", 0),
        completion_tokens=usage_data.get("output_tokens", 0),
        cache_read_tokens=usage_data.get("cache_read_input_tokens", 0),
        cache_write_tokens=usage_data.get("cache_creation_input_tokens", 0),
    )

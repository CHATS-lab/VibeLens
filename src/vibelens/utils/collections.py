"""Generic collection helpers."""


def truncate_to_cap(items: list, cap: int) -> None:
    """Truncate a list to at most ``cap`` entries, keeping the first ``cap`` in place.

    Used as the deterministic guard behind every LLM count cap in the
    analysis services (friction_types, mitigations, workflow_patterns,
    proposals, example_refs) — LLMs regularly exceed max-N prompt
    instructions, so a post-processing cap is required. First-N is the
    right slice because LLMs implicitly rank by importance when writing,
    and prompts instruct them to emit the most representative entries
    first.

    Args:
        items: Any list. Mutated in place.
        cap: Maximum length retained. Must be positive.

    Raises:
        ValueError: If ``cap`` is not positive.
    """
    if cap <= 0:
        raise ValueError(f"cap must be positive, got {cap}")
    if len(items) > cap:
        del items[cap:]

"""Session batcher — group sessions into LLM-sized batches.

Groups extracted session contexts into batches for concurrent LLM calls.
Strategy: project-aware grouping, linked-session chaining, greedy packing.

Budget is token-based: each session's char_count is converted to estimated
tokens, and batches are packed within max_batch_tokens from Settings.

Reusable by friction analysis, skill analysis, and other batch-inference modules.
"""

from dataclasses import dataclass, field
from datetime import datetime

from vibelens.deps import get_settings
from vibelens.llm.tokenizer import count_tokens
from vibelens.services.context_extraction import SessionContext
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


@dataclass
class SessionBatch:
    """A batch of session contexts sized for one LLM call."""

    batch_id: str
    session_contexts: list[SessionContext]
    total_tokens: int
    project_paths: set[str] = field(default_factory=set)


def build_batches(
    session_contexts: list[SessionContext], max_batch_tokens: int | None = None
) -> list[SessionBatch]:
    """Group session contexts into batches for LLM calls.

    Strategy:
    1. Group sessions by project_path
    2. Within each project, sort by timestamp
    3. Merge linked sessions into chains
    4. Pack chains into batches greedily, same-project preferred
    5. Oversized single sessions get their own batch

    Args:
        session_contexts: Extracted session contexts.
        max_batch_tokens: Max tokens per batch for session content.
            When None, reads from Settings.max_batch_tokens.

    Returns:
        List of SessionBatch ready for concurrent LLM calls.
    """
    if not session_contexts:
        return []

    settings = get_settings()
    budget = max_batch_tokens if max_batch_tokens is not None else settings.max_batch_tokens

    project_groups = _group_by_project(session_contexts)
    all_chains = _build_all_chains(project_groups)
    return _pack_batches(all_chains, budget)


def _group_by_project(contexts: list[SessionContext]) -> dict[str, list[SessionContext]]:
    """Group session contexts by project_path, sorted by timestamp."""
    groups: dict[str, list[SessionContext]] = {}
    for ctx in contexts:
        key = ctx.project_path or "__unknown__"
        groups.setdefault(key, []).append(ctx)

    for group in groups.values():
        group.sort(key=lambda c: c.timestamp or datetime.min)

    return groups


def _build_all_chains(
    project_groups: dict[str, list[SessionContext]],
) -> list[list[SessionContext]]:
    """Merge linked sessions into chains across all project groups.

    Sessions linked via last_trajectory_ref/continued_trajectory_ref
    are merged into ordered chains for co-location in the same batch.
    """
    all_chains: list[list[SessionContext]] = []
    for contexts in project_groups.values():
        chains = _merge_linked_sessions(contexts)
        all_chains.extend(chains)

    # Sort chains by total token estimate descending for better bin packing
    all_chains.sort(
        key=lambda chain: sum(count_tokens(c.context_text) for c in chain),
        reverse=True,
    )
    return all_chains


def _merge_linked_sessions(contexts: list[SessionContext]) -> list[list[SessionContext]]:
    """Merge linked sessions into chains.

    Two sessions are linked if one's last_trajectory_ref_id matches
    the other's session_id, or one's continued_trajectory_ref_id matches.

    The chain concept groups sessions that form a single logical conversation
    spanning multiple CLI invocations (e.g. the user resumed a session).
    Co-locating linked sessions in the same batch gives the LLM full context
    about the conversation flow, improving friction detection accuracy.
    """
    if not contexts:
        return []

    by_id = {c.session_id: c for c in contexts}
    visited: set[str] = set()
    chains: list[list[SessionContext]] = []

    for ctx in contexts:
        if ctx.session_id in visited:
            continue
        chain = _follow_chain(ctx, by_id, visited)
        chains.append(chain)
    return chains


def _follow_chain(
    start: SessionContext, by_id: dict[str, SessionContext], visited: set[str]
) -> list[SessionContext]:
    """Follow linked sessions forward and backward to build a chain."""
    chain: list[SessionContext] = []

    # Follow backward (find the earliest in the chain)
    current = start
    backward: list[SessionContext] = []
    while True:
        ref_id = current.last_trajectory_ref_id
        if not ref_id or ref_id not in by_id or ref_id in visited:
            break
        current = by_id[ref_id]
        backward.append(current)

    backward.reverse()
    chain.extend(backward)
    chain.append(start)

    # Follow forward (find continuations)
    current = start
    while True:
        ref_id = current.continued_trajectory_ref_id
        if not ref_id or ref_id not in by_id or ref_id in visited:
            break
        current = by_id[ref_id]
        chain.append(current)

    for c in chain:
        visited.add(c.session_id)

    return chain


def _chain_tokens(chain: list[SessionContext]) -> int:
    """Estimate total tokens for a chain of session contexts."""
    return sum(count_tokens(c.context_text) for c in chain)


def _pack_batches(chains: list[list[SessionContext]], budget: int) -> list[SessionBatch]:
    """Pack chains into batches greedily within the token budget.

    Uses a first-fit-decreasing strategy: chains are pre-sorted by size
    descending (in _build_all_chains). Each chain starts a new batch,
    then smaller chains are greedily packed into remaining space.
    This produces fewer batches than naive sequential packing while
    keeping the algorithm O(n^2) and deterministic.

    Args:
        chains: Session chains sorted by size descending.
        budget: Available tokens per batch for session content.

    Returns:
        List of SessionBatch objects.
    """
    batches: list[SessionBatch] = []
    used: set[int] = set()

    for i, chain in enumerate(chains):
        if i in used:
            continue

        chain_tok = _chain_tokens(chain)

        # Start new batch with this chain
        batch_contexts = list(chain)
        batch_tokens = chain_tok
        batch_projects = {c.project_path or "__unknown__" for c in chain}
        used.add(i)

        # Try to fit more chains into this batch
        for j, other_chain in enumerate(chains):
            if j in used:
                continue
            other_tok = _chain_tokens(other_chain)
            if batch_tokens + other_tok <= budget:
                batch_contexts.extend(other_chain)
                batch_tokens += other_tok
                batch_projects.update(c.project_path or "__unknown__" for c in other_chain)
                used.add(j)

        batch_id = f"batch-{len(batches) + 1:03d}"
        batches.append(
            SessionBatch(
                batch_id=batch_id,
                session_contexts=batch_contexts,
                total_tokens=batch_tokens,
                project_paths=batch_projects,
            )
        )

    if batches:
        logger.info(
            "Built %d batch(es) from %d chain(s), avg %d tokens/batch",
            len(batches),
            len(chains),
            sum(b.total_tokens for b in batches) // len(batches),
        )

    return batches

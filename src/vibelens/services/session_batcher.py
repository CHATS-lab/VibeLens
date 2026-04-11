"""Session batcher — group sessions into LLM-sized batches.

Groups extracted session contexts into batches for concurrent LLM calls.

Packing priority (highest → lowest):
1. Continued-trajectory chains — sessions linked via prev/next refs
2. Same-project, time-nearest sessions
3. Cross-project, time-nearest sessions

Budget is token-based: each batch is packed as close to max_batch_tokens
as possible without exceeding it.

Oversized handling: when a single session's context exceeds the budget,
its text is split at step boundaries into multiple parts, each fitting
within the budget. Parts use suffixed IDs (e.g., session_id__part1).

Reusable by friction analysis, skill analysis, and other batch-inference modules.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from vibelens.deps import get_settings
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContext, SessionContextBatch
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Placeholder for sessions that lack a project path
NO_PROJECT = "__unknown__"
# Regex anchor for splitting oversized contexts at step boundaries
STEP_BOUNDARY_PATTERN = re.compile(r"\n\n(?=\[step_id=)")
# Extra tokens reserved for separator text between context parts
SEPARATOR_TOKEN_ALLOWANCE = 5


@dataclass
class _Chain:
    """A chain of linked sessions treated as an atomic packing unit.

    Sessions linked via next_trajectory_ref form a chain that
    must stay together in the same batch to preserve conversation flow.
    Unlinked sessions become single-item chains.
    """

    contexts: list[SessionContext]
    tokens: int
    project: str
    timestamp: datetime | None


def build_batches(
    session_contexts: list[SessionContext], max_batch_tokens: int | None = None
) -> list[SessionContextBatch]:
    """Group session contexts into batches for LLM calls.

    Args:
        session_contexts: Extracted session contexts.
        max_batch_tokens: Max tokens per batch for session content.
            When None, reads from Settings.max_batch_tokens.

    Returns:
        List of SessionContextBatch ready for concurrent LLM calls.
    """
    if not session_contexts:
        return []

    settings = get_settings()
    budget = max_batch_tokens or settings.max_batch_tokens

    # Split large sessions first, then chain, then pack
    contexts = _split_oversized_sessions(session_contexts, budget)
    chains = _group_into_chains(contexts)
    chains = _enforce_chain_budget(chains, budget)
    batches = _assemble_batches(chains, budget)

    if batches:
        logger.info(
            "Built %d batch(es) from %d chain(s), avg %d tokens/batch",
            len(batches),
            len(chains),
            sum(b.total_tokens for b in batches) // len(batches),
        )

    return batches


def _split_oversized_sessions(contexts: list[SessionContext], budget: int) -> list[SessionContext]:
    """Split sessions exceeding the token budget at step boundaries.

    Each oversized session's text is divided into segments at step boundaries
    (double-newline before ``[step_id=...]``). Segments are grouped into parts
    that each fit within the token budget. Parts use suffixed IDs
    (e.g., session_id__part1).

    Args:
        contexts: All session contexts, some possibly oversized.
        budget: Max tokens per batch.

    Returns:
        Flat list of session contexts, all within budget (except
        unsplittable sessions that lack step boundaries).
    """
    result: list[SessionContext] = []

    for ctx in contexts:
        tokens = count_tokens(ctx.context_text)
        if tokens <= budget:
            result.append(ctx)
            continue
        result.extend(_split_session_at_steps(ctx, tokens, budget))

    return result


def _split_session_at_steps(
    ctx: SessionContext, total_tokens: int, budget: int
) -> list[SessionContext]:
    """Split a single oversized session at step boundaries into parts.

    The session header (=== SESSION: ... ===) is prepended to every
    part so the LLM always knows which session it's reading.

    Args:
        ctx: Session context whose text exceeds budget.
        total_tokens: Pre-computed token count for ctx.context_text.
        budget: Max tokens per batch.

    Returns:
        List of SessionContext parts, each within budget.
    """
    text = ctx.context_text
    segments = STEP_BOUNDARY_PATTERN.split(text)

    # Extract header (lines before first [step_id=] block)
    header = ""
    first_segment = segments[0]
    step_match = re.search(r"\[step_id=", first_segment)
    if step_match:
        header = first_segment[: step_match.start()].rstrip()
        segments[0] = first_segment[step_match.start() :]
    else:
        header = first_segment.rstrip()
        segments = segments[1:]

    if not segments:
        logger.warning(
            "Cannot split oversized session %s (%d tokens) — no step boundaries",
            ctx.session_id,
            total_tokens,
        )
        return [ctx]

    header_tokens = count_tokens(header) if header else 0
    part_budget = budget - header_tokens - SEPARATOR_TOKEN_ALLOWANCE

    if part_budget <= 0:
        logger.warning(
            "Session %s header alone exceeds budget (%d tokens)",
            ctx.session_id,
            header_tokens,
        )
        return [ctx]

    # Greedily pack segments into parts
    parts: list[str] = []
    current_segments: list[str] = []
    current_tokens = 0

    def flush_part() -> None:
        """Join accumulated segments with header and append to parts."""
        body = "\n\n".join(current_segments)
        parts.append(f"{header}\n\n{body}" if header else body)

    for segment in segments:
        seg_tokens = count_tokens(segment)

        if current_tokens + seg_tokens > part_budget and current_segments:
            flush_part()
            current_segments = []
            current_tokens = 0

        current_segments.append(segment)
        current_tokens += seg_tokens

    if current_segments:
        flush_part()

    result: list[SessionContext] = []
    for i, part_text in enumerate(parts, 1):
        part_ctx = SessionContext(
            session_id=f"{ctx.session_id}_part{i}",
            session_index=ctx.session_index,
            project_path=ctx.project_path,
            context_text=part_text,
            trajectory_group=ctx.trajectory_group,
            prev_trajectory_ref_id=ctx.prev_trajectory_ref_id,
            next_trajectory_ref_id=ctx.next_trajectory_ref_id,
            timestamp=ctx.timestamp,
            step_index2id=ctx.step_index2id,
        )
        result.append(part_ctx)

    logger.info(
        "Split oversized session %s (%d tokens) into %d parts",
        ctx.session_id,
        total_tokens,
        len(parts),
    )
    return result


def _group_into_chains(contexts: list[SessionContext]) -> list[_Chain]:
    """Merge linked sessions into chains.

    Sessions linked via prev_trajectory_ref/next_trajectory_ref
    are merged into ordered chains. Unlinked sessions become
    single-item chains. Visiting earlier sessions first ensures
    chains are built from the chronological start.

    Args:
        contexts: All session contexts to process.

    Returns:
        List of _Chain objects with cached token counts.
    """
    by_id = {c.session_id: c for c in contexts}
    visited: set[str] = set()
    chains: list[_Chain] = []

    sorted_contexts = sorted(contexts, key=lambda c: c.timestamp or datetime.min)
    for ctx in sorted_contexts:
        if ctx.session_id in visited:
            continue
        chain_ctxs = _collect_linked_sessions(ctx, by_id, visited)
        tokens = sum(count_tokens(c.context_text) for c in chain_ctxs)
        project = chain_ctxs[0].project_path or NO_PROJECT
        earliest = min((c.timestamp for c in chain_ctxs if c.timestamp), default=None)
        chains.append(
            _Chain(contexts=chain_ctxs, tokens=tokens, project=project, timestamp=earliest)
        )
    return chains


def _collect_linked_sessions(
    start: SessionContext, by_id: dict[str, SessionContext], visited: set[str]
) -> list[SessionContext]:
    """Follow linked sessions to build an ordered chain.

    Walks backward via prev_trajectory_ref_id to find the chain head,
    then forward via next_trajectory_ref_id collecting all members.
    All visited sessions are marked to prevent re-processing.

    Args:
        start: Starting session context.
        by_id: Lookup table of all session contexts by ID.
        visited: Set of already-processed session IDs (mutated).

    Returns:
        Ordered list of linked sessions from earliest to latest.
    """
    # Walk backward to find chain head (no list needed)
    head = start
    while (ref := head.prev_trajectory_ref_id) and ref in by_id and ref not in visited:
        head = by_id[ref]

    # Walk forward from head, marking visited as we go
    chain: list[SessionContext] = []
    current: SessionContext | None = head
    while current and current.session_id not in visited:
        visited.add(current.session_id)
        chain.append(current)
        next_id = current.next_trajectory_ref_id
        current = by_id.get(next_id) if next_id else None

    return chain


def _enforce_chain_budget(chains: list[_Chain], budget: int) -> list[_Chain]:
    """Break chains that exceed the token budget into individual chains.

    Individual sessions already fit within budget (split in an earlier
    step), so this only needs to unlink multi-session chains that
    collectively exceed the budget.

    Args:
        chains: Chains from _group_into_chains, possibly oversized.
        budget: Max tokens per batch.

    Returns:
        New list of chains where every chain fits within budget.
    """
    result: list[_Chain] = []

    for chain in chains:
        if chain.tokens <= budget:
            result.append(chain)
        else:
            for ctx in chain.contexts:
                result.append(
                    _Chain(
                        contexts=[ctx],
                        tokens=count_tokens(ctx.context_text),
                        project=ctx.project_path or NO_PROJECT,
                        timestamp=ctx.timestamp,
                    )
                )
    return result


def _assemble_batches(chains: list[_Chain], budget: int) -> list[SessionContextBatch]:
    """Pack chains into batches using affinity-based greedy packing.

    Algorithm:
    1. Sort all chains by (project, timestamp) for deterministic ordering
    2. Pop the first unplaced chain as the batch seed
    3. Rank remaining chains by affinity: same-project time-nearest
       first, then cross-project time-nearest
    4. Greedily add chains that fit within the token budget
    5. Repeat until all chains are placed

    Oversized chains (exceeding budget alone) get their own batch.

    Args:
        chains: All session chains, each within budget.
        budget: Max tokens per batch.

    Returns:
        List of SessionContextBatch objects.
    """
    unplaced = sorted(chains, key=lambda c: (c.project, c.timestamp or datetime.min))
    batches: list[SessionContextBatch] = []

    while unplaced:
        seed = unplaced.pop(0)

        batch_contexts = list(seed.contexts)
        batch_tokens = seed.tokens
        batch_projects = {seed.project}

        selected = _select_batch_candidates(unplaced, seed, budget)
        for chain in selected:
            batch_contexts.extend(chain.contexts)
            batch_tokens += chain.tokens
            batch_projects.add(chain.project)
            unplaced.remove(chain)

        for idx, ctx in enumerate(batch_contexts):
            ctx.reindex(idx)

        batch_id = f"batch-{len(batches) + 1:03d}"
        batches.append(
            SessionContextBatch(
                batch_id=batch_id,
                contexts=batch_contexts,
                total_tokens=batch_tokens,
                project_paths=batch_projects,
            )
        )
    return batches


def _select_batch_candidates(candidates: list[_Chain], seed: _Chain, budget: int) -> list[_Chain]:
    """Select chains to add to a batch, ranked by affinity.

    Affinity sort key: (is_cross_project, time_distance_seconds).
    Same-project chains rank higher; within each group, closer in
    time ranks higher. Chains that exceed remaining budget are skipped.

    Args:
        candidates: Unplaced chains available for selection.
        seed: The seed chain that started this batch.
        budget: Max tokens per batch.

    Returns:
        Chains selected to add (caller removes from unplaced).
    """
    seed_time = seed.timestamp or datetime.min

    def affinity_key(chain: _Chain) -> tuple[int, float]:
        is_cross_project = 0 if chain.project == seed.project else 1
        if chain.timestamp and seed_time != datetime.min:
            time_dist = abs((chain.timestamp - seed_time).total_seconds())
        else:
            time_dist = float("inf")
        return (is_cross_project, time_dist)

    ranked = sorted(candidates, key=affinity_key)

    selected: list[_Chain] = []
    current_tokens = seed.tokens
    for chain in ranked:
        if current_tokens + chain.tokens > budget:
            continue
        selected.append(chain)
        current_tokens += chain.tokens

    return selected

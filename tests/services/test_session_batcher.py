"""Tests for session batcher module.

Tests chain merging, affinity-based packing, budget constraints,
oversized sessions, and settings-based defaults.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from vibelens.config.settings import Settings
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.context import SessionContext
from vibelens.services.session_batcher import build_batches


def _make_context(
    session_id: str,
    project_path: str | None = None,
    text_length: int = 1000,
    prev_ref: str | None = None,
    next_ref: str | None = None,
    timestamp: datetime | None = None,
) -> SessionContext:
    """Build a minimal SessionContext for testing."""
    text = "x" * text_length
    return SessionContext(
        session_id=session_id,
        project_path=project_path,
        context_text=text,
        trajectory_group=[],
        prev_trajectory_ref_id=prev_ref,
        next_trajectory_ref_id=next_ref,
        timestamp=timestamp,
    )


def test_single_session_single_batch() -> None:
    """One session produces one batch."""
    ctx = _make_context("s1", text_length=5000)
    batches = build_batches([ctx])

    assert len(batches) == 1
    assert len(batches[0].contexts) == 1
    assert batches[0].batch_id == "batch-001"
    print(f"Single session: {batches[0].total_tokens} tokens")


def test_multiple_sessions_single_batch() -> None:
    """Small sessions fit into a single batch."""
    contexts = [_make_context(f"s{i}", text_length=2000) for i in range(5)]
    batches = build_batches(contexts)

    assert len(batches) == 1
    total = sum(len(b.contexts) for b in batches)
    assert total == 5
    print(f"5 sessions in 1 batch: {batches[0].total_tokens} tokens")


def test_budget_splits_into_multiple_batches() -> None:
    """Sessions exceeding budget are split across batches.

    Each session is 40K chars = 5,000 tokens.
    Budget 6,000 → one session per batch.
    """
    contexts = [_make_context(f"s{i}", text_length=40_000) for i in range(3)]
    batches = build_batches(contexts, max_batch_tokens=6_000)

    assert len(batches) == 3
    total = sum(len(b.contexts) for b in batches)
    assert total == 3
    for batch in batches:
        n = len(batch.contexts)
        print(f"  {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")


def test_linked_sessions_stay_in_same_chain() -> None:
    """Linked sessions are merged into chains via build_batches."""
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    contexts = [
        _make_context("s1", project_path="/p", timestamp=ts, next_ref="s2"),
        _make_context("s2", project_path="/p", timestamp=ts, prev_ref="s1"),
        _make_context("s3", project_path="/p", timestamp=ts),
    ]
    batches = build_batches(contexts)

    # All fit in one batch; s1 and s2 must be adjacent
    assert len(batches) == 1
    ids = [c.session_id for c in batches[0].contexts]
    s1_idx = ids.index("s1")
    s2_idx = ids.index("s2")
    assert s2_idx == s1_idx + 1, f"Linked pair not adjacent: {ids}"
    print(f"Linked chain preserved: {ids}")


def test_empty_input() -> None:
    """Empty input produces no batches."""
    assert build_batches([]) == []


def test_oversized_session_gets_own_batch() -> None:
    """A session exceeding the budget gets its own batch.

    s1: 100K chars = 12,500 tokens. s2: 5K chars = 625 tokens.
    Budget 8,000 → s1 gets split, s2 in its own batch.
    """
    contexts = [
        _make_context("s1", text_length=100_000),
        _make_context("s2", text_length=5_000),
    ]
    batches = build_batches(contexts, max_batch_tokens=8_000)

    total = sum(len(b.contexts) for b in batches)
    assert total >= 2
    for batch in batches:
        n = len(batch.contexts)
        print(f"  {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")


def test_default_batch_tokens_from_settings() -> None:
    """When max_batch_tokens is None, reads from Settings."""
    custom_settings = Settings(max_batch_tokens=2_000)

    with patch("vibelens.services.session_batcher.get_settings", return_value=custom_settings):
        contexts = [_make_context(f"s{i}", text_length=10_000) for i in range(3)]
        batches = build_batches(contexts)

    assert len(batches) == 3
    total = sum(len(b.contexts) for b in batches)
    assert total == 3
    print(f"Settings-based batching: {len(batches)} batches from 3 sessions")


def test_token_counting_accuracy() -> None:
    """Token counting uses tiktoken and produces exact results."""
    long_text = "x" * 10_000
    tokens = count_tokens(long_text)
    assert tokens == 1_250
    print(f"10K 'x' chars → {tokens} tokens (exact)")

    code_text = 'def hello():\n    print("Hello, world!")\n' * 100
    code_tokens = count_tokens(code_text)
    print(f"Code sample ({len(code_text)} chars) → {code_tokens} tokens")
    assert code_tokens > 0


def test_same_project_time_near_packed_together() -> None:
    """Same-project sessions close in time pack into one batch.

    Budget 5,000 tokens. Each session = 1,250 tokens.
    4 same-project sessions should pack into 1 batch, time-ordered.
    """
    t0 = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=30)
    t2 = t0 + timedelta(hours=1)
    t3 = t0 + timedelta(hours=2)
    p = "/project-a"
    contexts = [
        _make_context("s1", project_path=p, text_length=10_000, timestamp=t0),
        _make_context("s2", project_path=p, text_length=10_000, timestamp=t1),
        _make_context("s3", project_path=p, text_length=10_000, timestamp=t2),
        _make_context("s4", project_path=p, text_length=10_000, timestamp=t3),
    ]
    batches = build_batches(contexts, max_batch_tokens=5_000)

    assert len(batches) == 1
    assert len(batches[0].contexts) == 4
    ids = [c.session_id for c in batches[0].contexts]
    assert ids == ["s1", "s2", "s3", "s4"]
    print(f"Same-project packing: {len(batches)} batch, {batches[0].total_tokens} tokens")


def test_same_project_preferred_over_cross_project() -> None:
    """Same-project affinity outranks cross-project time proximity.

    Budget 2,600 (fits 2 sessions of 1,250 each).
    s1(proj-a) + s2(proj-a) should go together, not s1 + s3(proj-b).
    """
    t0 = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    t_near = t0 + timedelta(minutes=5)
    pa, pb = "/project-a", "/project-b"
    contexts = [
        _make_context("s1", project_path=pa, text_length=10_000, timestamp=t0),
        _make_context("s2", project_path=pa, text_length=10_000, timestamp=t1),
        _make_context("s3", project_path=pb, text_length=10_000, timestamp=t_near),
    ]
    batches = build_batches(contexts, max_batch_tokens=2_600)

    assert len(batches) == 2
    batch_a = next(b for b in batches if pa in b.project_paths)
    assert len(batch_a.contexts) == 2
    ids = {c.session_id for c in batch_a.contexts}
    assert ids == {"s1", "s2"}
    print(f"Project affinity: batch-a has {ids}")


def test_linked_chain_stays_together() -> None:
    """A continued-trajectory chain is never split across batches.

    s1 → s2 (linked). s3 is standalone. Budget fits all.
    s1 and s2 must be in the same batch and adjacent.
    """
    t0 = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    t2 = t0 + timedelta(hours=2)
    n = 10_000
    contexts = [
        _make_context("s1", project_path="/p", text_length=n, timestamp=t0, next_ref="s2"),
        _make_context("s2", project_path="/p", text_length=n, timestamp=t1, prev_ref="s1"),
        _make_context("s3", project_path="/p", text_length=n, timestamp=t2),
    ]
    batches = build_batches(contexts, max_batch_tokens=5_000)

    assert len(batches) == 1
    assert len(batches[0].contexts) == 3
    ids = [c.session_id for c in batches[0].contexts]
    s1_pos = ids.index("s1")
    s2_pos = ids.index("s2")
    assert s2_pos == s1_pos + 1, f"Linked sessions not adjacent: {ids}"
    print(f"Chain preserved: {ids}")


def test_small_sessions_packed_fully() -> None:
    """Small sessions fill batches, not one-per-batch.

    9 sessions of 1,250 tokens each. Budget 5,000.
    Should produce ≤3 batches, not 9.
    """
    contexts = [_make_context(f"s{i}", text_length=10_000) for i in range(9)]
    batches = build_batches(contexts, max_batch_tokens=5_000)

    assert len(batches) <= 3
    total = sum(len(b.contexts) for b in batches)
    assert total == 9
    for batch in batches:
        n = len(batch.contexts)
        print(f"  {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")


def test_cross_project_fills_remaining_budget() -> None:
    """Cross-project sessions fill remaining batch space.

    Budget 3,800. Three sessions of 1,250 tokens each.
    s1 + s3 (same project) pack first, then s2 (cross-project) fills.
    """
    t0 = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    t2 = t0 + timedelta(hours=2)
    pa, pb = "/project-a", "/project-b"
    contexts = [
        _make_context("s1", project_path=pa, text_length=10_000, timestamp=t0),
        _make_context("s2", project_path=pb, text_length=10_000, timestamp=t1),
        _make_context("s3", project_path=pa, text_length=10_000, timestamp=t2),
    ]
    batches = build_batches(contexts, max_batch_tokens=3_800)

    assert len(batches) == 1
    assert len(batches[0].contexts) == 3
    print(f"Cross-project fill: 1 batch, {batches[0].total_tokens} tokens")


def _make_stepped_context(
    session_id: str,
    step_count: int,
    chars_per_step: int,
    project_path: str | None = None,
) -> SessionContext:
    """Build a SessionContext with realistic step boundaries for split testing."""
    header = f"=== SESSION: {session_id} ==="
    if project_path:
        header += f"\nPROJECT: {project_path}"
    steps = []
    for i in range(step_count):
        step_body = "x" * chars_per_step
        steps.append(f"[step_id={i}] USER: {step_body}")
    text = header + "\n\n" + "\n\n".join(steps)
    return SessionContext(
        session_id=session_id,
        project_path=project_path,
        context_text=text,
        trajectory_group=[],
    )


def test_oversized_session_split_at_step_boundaries() -> None:
    """An oversized session is split at step boundaries into multiple parts.

    20 steps × 4,000 chars each ≈ 10,000 tokens total.
    Budget 3,000 → should produce ~4 parts, each within budget.
    Each part keeps the session header.
    """
    ctx = _make_stepped_context("s1", step_count=20, chars_per_step=4_000)
    total_tokens = count_tokens(ctx.context_text)
    print(f"Oversized session: {total_tokens} tokens, {len(ctx.context_text)} chars")

    batches = build_batches([ctx], max_batch_tokens=3_000)

    assert len(batches) >= 2, f"Expected split, got {len(batches)} batch(es)"
    for batch in batches:
        assert batch.total_tokens <= 3_000, f"{batch.batch_id} exceeds budget: {batch.total_tokens}"
        # Each part should contain the header
        for sc in batch.contexts:
            assert "=== SESSION:" in sc.context_text
            assert sc.session_id.startswith("s1")
        n = len(batch.contexts)
        print(f"  {batch.batch_id}: {n} session(s), {batch.total_tokens:,} tokens")


def test_oversized_session_no_step_boundaries_stays_intact() -> None:
    """An oversized session without step boundaries cannot be split.

    Falls back to a single batch even if it exceeds budget.
    """
    ctx = _make_context("s1", text_length=100_000)
    batches = build_batches([ctx], max_batch_tokens=5_000)

    assert len(batches) == 1
    print(f"Unsplittable: 1 batch, {batches[0].total_tokens:,} tokens")


def test_realistic_mixed_sizes() -> None:
    """Realistic scenario: 17 sessions with varied sizes pack efficiently.

    Simulates the user's real data: token sizes from ~4K to ~59K.
    Budget 80K. Total ~169K tokens → should produce 3 batches, not 8.

    Token sizes (chars = tokens * 8 for 'x' strings):
      59K, 23K, 21K, 21K, 18K, 10K, 10K, 8K, 5K, 4K + 7 small (1-3K)
    """
    t0 = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
    sizes = [
        59000,
        23000,
        21000,
        21000,
        18000,
        10000,
        10000,
        8000,
        5000,
        4000,
        3000,
        3000,
        2000,
        2000,
        1000,
        1000,
        1000,
    ]
    contexts = [
        _make_context(
            f"s{i}",
            project_path="/project-a",
            text_length=sz * 8,
            timestamp=t0 + timedelta(hours=i),
        )
        for i, sz in enumerate(sizes)
    ]
    batches = build_batches(contexts, max_batch_tokens=80_000)

    total_sessions = sum(len(b.contexts) for b in batches)
    assert total_sessions == 17
    # With 169K total and 80K budget, 3 batches is optimal
    assert len(batches) <= 3, f"Expected ≤3 batches, got {len(batches)}"
    for batch in batches:
        n = len(batch.contexts)
        print(f"  {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")
        assert batch.total_tokens <= 80_000, (
            f"{batch.batch_id} exceeds budget: {batch.total_tokens}"
        )

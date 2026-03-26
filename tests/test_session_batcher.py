"""Tests for session batcher module.

Tests project grouping, chain merging, budget packing, oversized sessions,
and settings-based defaults.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from vibelens.config.settings import Settings
from vibelens.llm.tokenizer import count_tokens
from vibelens.services.context_extraction import SessionContext
from vibelens.services.session_batcher import (
    _group_by_project,
    _merge_linked_sessions,
    build_batches,
)


def _make_context(
    session_id: str,
    project_path: str | None = None,
    char_count: int = 1000,
    last_ref: str | None = None,
    continued_ref: str | None = None,
    timestamp: datetime | None = None,
) -> SessionContext:
    """Build a minimal SessionContext for testing."""
    text = "x" * char_count
    return SessionContext(
        session_id=session_id,
        project_path=project_path,
        context_text=text,
        char_count=char_count,
        trajectory_group=[],
        last_trajectory_ref_id=last_ref,
        continued_trajectory_ref_id=continued_ref,
        timestamp=timestamp,
    )


def test_single_session_single_batch():
    """One session produces one batch."""
    ctx = _make_context("s1", char_count=5000)
    batches = build_batches([ctx])

    assert len(batches) == 1
    assert len(batches[0].session_contexts) == 1
    assert batches[0].batch_id == "batch-001"
    print(f"Single session: {batches[0].total_tokens} tokens")


def test_multiple_sessions_single_batch():
    """Small sessions fit into a single batch."""
    contexts = [_make_context(f"s{i}", char_count=2000) for i in range(5)]
    batches = build_batches(contexts)

    assert len(batches) == 1
    total = sum(len(b.session_contexts) for b in batches)
    assert total == 5
    print(f"5 sessions in 1 batch: {batches[0].total_tokens} tokens")


def test_budget_splits_into_multiple_batches():
    """Large sessions get split across multiple batches.

    Each session is 40K chars of 'x' = 5,000 tokens (tiktoken cl100k_base).
    Budget is 6,000 tokens → each batch fits 1 session.
    """
    contexts = [_make_context(f"s{i}", char_count=40_000) for i in range(3)]
    batches = build_batches(contexts, max_batch_tokens=6_000)

    assert len(batches) == 3
    total = sum(len(b.session_contexts) for b in batches)
    assert total == 3
    for batch in batches:
        n = len(batch.session_contexts)
        print(f"  {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")


def test_group_by_project():
    """Sessions are grouped by project_path."""
    contexts = [
        _make_context("s1", project_path="/project-a"),
        _make_context("s2", project_path="/project-b"),
        _make_context("s3", project_path="/project-a"),
        _make_context("s4", project_path=None),
    ]

    groups = _group_by_project(contexts)
    assert "/project-a" in groups
    assert "/project-b" in groups
    assert "__unknown__" in groups
    assert len(groups["/project-a"]) == 2
    assert len(groups["/project-b"]) == 1
    assert len(groups["__unknown__"]) == 1


def test_linked_sessions_merged():
    """Linked sessions are merged into chains."""
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    contexts = [
        _make_context("s1", project_path="/p", timestamp=ts, continued_ref="s2"),
        _make_context("s2", project_path="/p", timestamp=ts, last_ref="s1"),
        _make_context("s3", project_path="/p", timestamp=ts),
    ]

    chains = _merge_linked_sessions(contexts)

    # s1 and s2 should be in one chain, s3 in another
    assert len(chains) == 2
    chain_sizes = sorted(len(c) for c in chains)
    assert chain_sizes == [1, 2]


def test_empty_input():
    """Empty input produces no batches."""
    batches = build_batches([])
    assert len(batches) == 0


def test_oversized_session():
    """A session exceeding the budget gets its own batch.

    s1: 100K chars = 12,500 tokens. s2: 5K chars = 625 tokens.
    Budget of 8,000 tokens → s1 exceeds budget, gets its own batch.
    """
    contexts = [
        _make_context("s1", char_count=100_000),
        _make_context("s2", char_count=5_000),
    ]
    batches = build_batches(contexts, max_batch_tokens=8_000)

    assert len(batches) == 2
    total = sum(len(b.session_contexts) for b in batches)
    assert total == 2
    for batch in batches:
        n = len(batch.session_contexts)
        print(f"  {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")


def test_default_batch_tokens_from_settings():
    """When max_batch_tokens is None, values come from Settings.

    Each session is 10K chars of 'x' = 1,250 tokens (tiktoken cl100k_base).
    Budget = 2,000 tokens → fits 1 session per batch.
    """
    custom_settings = Settings(max_batch_tokens=2_000)

    with patch("vibelens.services.session_batcher.get_settings", return_value=custom_settings):
        contexts = [_make_context(f"s{i}", char_count=10_000) for i in range(3)]
        batches = build_batches(contexts)

    assert len(batches) == 3
    total = sum(len(b.session_contexts) for b in batches)
    assert total == 3
    print(f"Settings-based batching: {len(batches)} batches from 3 sessions")


def test_token_counting_accuracy():
    """Token counting uses tiktoken and produces exact results."""
    text = "Hello world, this is a test of token counting."
    tokens = count_tokens(text)
    assert tokens > 0

    # A 10K char string of 'x' should be exactly 1,250 tokens
    long_text = "x" * 10_000
    tokens = count_tokens(long_text)
    assert tokens == 1_250
    print(f"10K 'x' chars → {tokens} tokens (exact)")

    # Realistic mixed code/prose should tokenize predictably
    code_text = 'def hello():\n    print("Hello, world!")\n' * 100
    code_tokens = count_tokens(code_text)
    print(f"Code sample ({len(code_text)} chars) → {code_tokens} tokens")
    assert code_tokens > 0

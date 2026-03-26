"""Context extraction and batching analysis.

Tests the context extraction and session batching pipeline with real data.
Replaces the old tier-based digest tests.
"""

import json
from pathlib import Path

from vibelens.llm.tokenizer import count_tokens
from vibelens.models.trajectories import Trajectory
from vibelens.services.context_extraction import extract_session_context
from vibelens.services.friction.digest import format_batch_digest
from vibelens.services.session_batcher import build_batches

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "claude-codex-example" / "parsed"


def _load_trajectory_groups() -> dict[str, list[Trajectory]]:
    """Load all parsed trajectories grouped by session_id."""
    json_files = sorted(EXAMPLES_DIR.glob("*.json"))
    session_files = [f for f in json_files if not f.name.endswith(".meta.json")]

    groups: dict[str, list[Trajectory]] = {}
    for filepath in session_files:
        data = json.loads(filepath.read_text())
        trajectories = []
        if isinstance(data, list):
            for item in data:
                trajectories.append(Trajectory.model_validate(item))
        else:
            trajectories.append(Trajectory.model_validate(data))
        for t in trajectories:
            groups.setdefault(t.session_id, []).append(t)
    return groups


def test_context_extraction():
    """Test context extraction produces valid output for each session."""
    if not EXAMPLES_DIR.exists():
        print(f"[SKIP] {EXAMPLES_DIR}")
        return

    groups = _load_trajectory_groups()
    print(f"\n{'=' * 70}")
    print("CONTEXT EXTRACTION ANALYSIS")
    print(f"{'=' * 70}")

    contexts = []
    for session_id, traj_group in groups.items():
        ctx = extract_session_context(traj_group)
        contexts.append(ctx)

        total_steps = sum(len(t.steps) for t in traj_group)
        has_compaction = any("acompact-" in t.session_id for t in traj_group)
        sub_agents = [t for t in traj_group if t.parent_trajectory_ref is not None]

        print(f"\n  Session: {session_id[:16]}...")
        print(f"    Trajectories: {len(traj_group)} (main + {len(sub_agents)} sub-agents)")
        print(f"    Total steps: {total_steps}")
        print(f"    Has compaction: {has_compaction}")
        print(f"    Context chars: {ctx.char_count:,}")
        print(f"    Context tokens: {count_tokens(ctx.context_text):,}")
        print(f"    Project: {ctx.project_path or 'unknown'}")
        print(f"    Last ref: {ctx.last_trajectory_ref_id or 'none'}")
        print(f"    Continued ref: {ctx.continued_trajectory_ref_id or 'none'}")

        # Verify context text is non-empty and starts with session header
        assert ctx.context_text.startswith("=== SESSION:")
        assert ctx.char_count > 0
        assert ctx.session_id == session_id

    print(f"\n  Total sessions: {len(contexts)}")
    print(f"  Total chars: {sum(c.char_count for c in contexts):,}")


def test_batching_small():
    """Test that 2 sessions fit into a single batch."""
    if not EXAMPLES_DIR.exists():
        print(f"[SKIP] {EXAMPLES_DIR}")
        return

    groups = _load_trajectory_groups()
    session_ids = list(groups.keys())[:2]

    contexts = []
    for sid in session_ids:
        ctx = extract_session_context(groups[sid])
        contexts.append(ctx)

    batches = build_batches(contexts)
    print("\n--- 2-Session Batching ---")
    print(f"  Sessions: {len(contexts)}")
    print(f"  Batches: {len(batches)}")
    for batch in batches:
        n = len(batch.session_contexts)
        print(f"  {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")

    assert len(batches) >= 1
    total_sessions = sum(len(b.session_contexts) for b in batches)
    assert total_sessions == 2


def test_batching_all():
    """Test batching with all available sessions."""
    if not EXAMPLES_DIR.exists():
        print(f"[SKIP] {EXAMPLES_DIR}")
        return

    groups = _load_trajectory_groups()

    contexts = []
    for traj_group in groups.values():
        ctx = extract_session_context(traj_group)
        contexts.append(ctx)

    batches = build_batches(contexts)
    print("\n--- All-Session Batching ---")
    print(f"  Sessions: {len(contexts)}")
    print(f"  Batches: {len(batches)}")
    for batch in batches:
        digest = format_batch_digest(batch)
        print(
            f"  {batch.batch_id}: {len(batch.session_contexts)} sessions, "
            f"{batch.total_tokens:,} tokens, digest={len(digest):,} chars"
        )

    assert len(batches) >= 1
    total_sessions = sum(len(b.session_contexts) for b in batches)
    assert total_sessions == len(contexts)


def test_batch_digest_format():
    """Test that batch digest produces valid formatted text."""
    if not EXAMPLES_DIR.exists():
        print(f"[SKIP] {EXAMPLES_DIR}")
        return

    groups = _load_trajectory_groups()
    contexts = []
    for traj_group in groups.values():
        contexts.append(extract_session_context(traj_group))

    batches = build_batches(contexts)
    assert len(batches) > 0

    for batch in batches:
        digest = format_batch_digest(batch)
        assert len(digest) > 0
        assert "=== SESSION:" in digest

        print(f"\n--- {batch.batch_id} Digest Sample (first 300 chars) ---")
        print(digest[:300])
        print("...")

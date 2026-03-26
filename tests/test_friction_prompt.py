"""Prompt length analysis for friction analysis.

Loads real sessions from examples/, extracts contexts, builds batches,
formats the full prompt, and prints detailed size analysis for context
window fit assessment.
"""

import json
from pathlib import Path

from vibelens.llm.prompts.friction_analysis import FRICTION_ANALYSIS_PROMPT
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.analysis.friction import FrictionLLMBatchOutput
from vibelens.models.trajectories import Trajectory
from vibelens.services.context_extraction import extract_session_context
from vibelens.services.friction.digest import format_batch_digest
from vibelens.services.session_batcher import build_batches

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "claude-codex-example" / "parsed"

CONTEXT_WINDOWS = {
    "Claude (200K)": 200_000,
    "GPT-4.1 (1M)": 1_000_000,
    "Gemini 2.5 (1M)": 1_000_000,
}


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


def test_friction_prompt_length():
    """Analyze prompt length for friction analysis with real session data."""
    if not EXAMPLES_DIR.exists():
        print(f"[SKIP] Examples directory not found: {EXAMPLES_DIR}")
        return

    groups = _load_trajectory_groups()
    print(f"\n{'=' * 70}")
    print("FRICTION ANALYSIS PROMPT LENGTH ANALYSIS")
    print(f"{'=' * 70}")

    # Extract contexts
    contexts = []
    print(f"\n--- Per-Session Context ({len(groups)} sessions) ---")
    for session_id, traj_group in groups.items():
        ctx = extract_session_context(traj_group)
        contexts.append(ctx)
        total_steps = sum(len(t.steps) for t in traj_group)
        ctx_tokens = count_tokens(ctx.context_text)
        print(
            f"  {session_id[:12]}...  steps={total_steps:>4}"
            f"  context={ctx.char_count:>6,} chars ({ctx_tokens:,} tok)"
        )

    # Build batches
    batches = build_batches(contexts)
    print("\n--- Batching ---")
    print(f"  Sessions: {len(contexts)}")
    print(f"  Batches: {len(batches)}")
    for batch in batches:
        n = len(batch.session_contexts)
        print(f"  {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")

    # Format first batch as sample prompt
    batch = batches[0]
    digest = format_batch_digest(batch)

    output_schema = json.dumps(FrictionLLMBatchOutput.model_json_schema(), indent=2)
    system_prompt = FRICTION_ANALYSIS_PROMPT.render_system()
    user_prompt = FRICTION_ANALYSIS_PROMPT.render_user(
        session_count=len(batch.session_contexts),
        batch_digest=digest,
        output_schema=output_schema,
    )

    system_tokens = count_tokens(system_prompt)
    user_tokens = count_tokens(user_prompt)
    schema_tokens = count_tokens(output_schema)
    digest_tokens = count_tokens(digest)
    total_tokens = count_tokens(system_prompt + user_prompt)

    print("\n--- Prompt Size Breakdown (batch-001) ---")
    print(f"  System prompt:  {len(system_prompt):>8,} chars  ({system_tokens:,} tok)")
    print(f"  Output schema:  {len(output_schema):>8,} chars  ({schema_tokens:,} tok)")
    print(f"  Batch digest:   {len(digest):>8,} chars  ({digest_tokens:,} tok)")
    print(f"  User prompt:    {len(user_prompt):>8,} chars  ({user_tokens:,} tok)")
    total_chars = len(system_prompt) + len(user_prompt)
    print(f"  Total:          {total_chars:>8,} chars  ({total_tokens:,} tok)")

    print("\n--- Context Window Fit ---")
    for model_name, window_size in CONTEXT_WINDOWS.items():
        pct = (total_tokens / window_size) * 100
        remaining = window_size - total_tokens
        status = "OK" if pct < 80 else "TIGHT" if pct < 95 else "OVER"
        print(
            f"  {model_name:>20}: {pct:5.1f}% used  ({remaining:>+10,} tok remaining)  [{status}]"
        )

    print("\n--- Digest Sample (first 500 chars) ---")
    print(digest[:500])
    print("...")
    print(f"\n{'=' * 70}")

    assert len(contexts) > 0
    assert len(digest) > 0
    assert total_tokens > 0

"""Prompt length analysis for friction analysis.

Loads real sessions from examples/, builds StepSignals, creates digest,
formats the full prompt, and prints detailed size analysis for context
window fit assessment.
"""

import json
from pathlib import Path

from vibelens.analysis.step_signals import build_step_signals
from vibelens.llm.digest_friction import digest_step_signals
from vibelens.llm.prompts.friction_analysis import FRICTION_ANALYSIS_PROMPT
from vibelens.models.analysis.friction import FrictionLLMOutput
from vibelens.models.trajectories import Trajectory

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "claude-codex-example" / "parsed"
CHARS_PER_TOKEN = 4

# Context window sizes for popular models (in tokens)
CONTEXT_WINDOWS = {
    "Claude (200K)": 200_000,
    "GPT-4.1 (1M)": 1_000_000,
    "Gemini 2.5 (1M)": 1_000_000,
}


def _load_trajectories() -> list[Trajectory]:
    """Load all parsed trajectory JSON files from examples directory."""
    trajectories = []
    json_files = sorted(EXAMPLES_DIR.glob("*.json"))
    session_files = [f for f in json_files if not f.name.endswith(".meta.json")]

    for filepath in session_files:
        data = json.loads(filepath.read_text())
        # Handle both single trajectory and list of trajectories
        if isinstance(data, list):
            for item in data:
                trajectories.append(Trajectory.model_validate(item))
        else:
            trajectories.append(Trajectory.model_validate(data))
    return trajectories


def test_friction_prompt_length():
    """Analyze prompt length for friction analysis with real session data."""
    if not EXAMPLES_DIR.exists():
        print(f"[SKIP] Examples directory not found: {EXAMPLES_DIR}")
        return

    trajectories = _load_trajectories()
    print(f"\n{'=' * 70}")
    print("FRICTION ANALYSIS PROMPT LENGTH ANALYSIS")
    print(f"{'=' * 70}")

    # Per-session stats
    print(f"\n--- Per-Session Stats ({len(trajectories)} trajectories) ---")
    total_steps = 0
    for traj in trajectories:
        step_count = len(traj.steps)
        total_steps += step_count
        file_size = "?"
        session_file = EXAMPLES_DIR / f"{traj.session_id}.json"
        if session_file.exists():
            file_size = f"{session_file.stat().st_size / 1024:.1f} KB"
        print(f"  {traj.session_id[:12]}...  steps={step_count:>4}  file={file_size}")
    print(f"  Total steps: {total_steps}")

    # Build signals and digest
    signals = build_step_signals(trajectories)
    print("\n--- StepSignal Stats ---")
    print(f"  Total signals: {len(signals)}")

    digest = digest_step_signals(signals)
    digest_chars = len(digest)
    digest_tokens_est = digest_chars // CHARS_PER_TOKEN
    print("\n--- Digest Stats ---")
    print(f"  Digest chars: {digest_chars:,}")
    print(f"  Digest tokens (est): {digest_tokens_est:,}")

    # Format full prompt
    output_schema = json.dumps(FrictionLLMOutput.model_json_schema(), indent=2)
    user_prompt = FRICTION_ANALYSIS_PROMPT.render_user(
        session_count=len(trajectories),
        session_digest=digest,
        output_schema=output_schema,
    )

    system_chars = len(FRICTION_ANALYSIS_PROMPT.render_system())
    user_chars = len(user_prompt)
    schema_chars = len(output_schema)
    total_chars = system_chars + user_chars
    total_tokens_est = total_chars // CHARS_PER_TOKEN

    sys_tokens = system_chars // CHARS_PER_TOKEN
    schema_tokens = schema_chars // CHARS_PER_TOKEN
    user_tokens = user_chars // CHARS_PER_TOKEN

    print("\n--- Prompt Size Breakdown ---")
    print(f"  System prompt:  {system_chars:>8,} chars  ({sys_tokens:,} tok)")
    print(f"  Output schema:  {schema_chars:>8,} chars  ({schema_tokens:,} tok)")
    print(f"  Session digest: {digest_chars:>8,} chars  ({digest_tokens_est:,} tok)")
    print(f"  User prompt:    {user_chars:>8,} chars  ({user_tokens:,} tok)")
    print(f"  Total:          {total_chars:>8,} chars  ({total_tokens_est:,} tok)")

    # Context window fit assessment
    print("\n--- Context Window Fit (input prompt only) ---")
    for model_name, window_size in CONTEXT_WINDOWS.items():
        pct = (total_tokens_est / window_size) * 100
        remaining = window_size - total_tokens_est
        status = "OK" if pct < 80 else "TIGHT" if pct < 95 else "OVER"
        print(
            f"  {model_name:>20}: {pct:5.1f}% used  "
            f"({remaining:>+10,} tok remaining)  [{status}]"
        )

    # Show first 500 chars of digest as sample
    print("\n--- Digest Sample (first 500 chars) ---")
    print(digest[:500])
    print("...")

    print(f"\n{'=' * 70}")

    # Assertions for test framework
    assert len(signals) == total_steps
    assert digest_chars > 0
    assert total_tokens_est > 0

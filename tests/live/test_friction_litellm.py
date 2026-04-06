"""Live friction analysis tests -- calls the real LLM backend.

Tests user-centric friction analysis with batched pipeline using
the configured LLM backend. Saves detailed logs to logs/friction/.

Requires: config/llm.yaml with a working API key.
Skip: Set SKIP_LIVE_LLM=1 to skip these tests.
"""

import asyncio
import json
import os
import time
from datetime import UTC, datetime

import pytest

from vibelens.config.llm_config import load_llm_config
from vibelens.llm.backends.litellm_backend import LiteLLMBackend
from vibelens.llm.prompts.friction_analysis import FRICTION_ANALYSIS_PROMPT
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.analysis.friction import FrictionAnalysisOutput
from vibelens.models.llm.inference import InferenceRequest
from vibelens.models.trajectories import Trajectory
from vibelens.services.analysis_shared import format_batch_digest
from vibelens.services.context_extraction import extract_session_context
from vibelens.services.friction.analysis import FRICTION_OUTPUT_TOKENS
from vibelens.services.session_batcher import build_batches
from vibelens.utils.json_extract import extract_json as _extract_json
from vibelens.utils.json_extract import repair_truncated_json as _repair_truncated_json

from .conftest import EXAMPLES_DIR, LOGS_DIR, load_trajectory_groups

FRICTION_LOGS_DIR = LOGS_DIR / "friction"

_no_api_key = not os.environ.get("ANTHROPIC_API_KEY")
SKIP_LIVE = os.environ.get("SKIP_LIVE_LLM", "0") == "1" or _no_api_key
SKIP_REASON = "No ANTHROPIC_API_KEY or SKIP_LIVE_LLM=1 -- skipping live LLM tests"


def _select_sessions(
    groups: dict[str, list[Trajectory]], count: int | None = None
) -> dict[str, list[Trajectory]]:
    """Select first N sessions from groups."""
    if count is None:
        return groups
    selected = {}
    for session_id, traj_group in groups.items():
        if len(selected) >= count:
            break
        selected[session_id] = traj_group
    return selected


def _run_friction_analysis(label: str, groups: dict[str, list[Trajectory]]) -> None:
    """Run full batched friction analysis pipeline and log results.

    Args:
        label: Label for the test case (used in log filename).
        groups: Session ID → trajectory group mapping.
    """
    # Extract contexts
    contexts = []
    for traj_group in groups.values():
        ctx = extract_session_context(traj_group)
        contexts.append(ctx)

    # Build batches
    batches = build_batches(contexts)
    session_ids = list(groups.keys())

    print(f"\n{'=' * 70}")
    print(f"  LIVE FRICTION ANALYSIS: {label}")
    print(f"{'=' * 70}")
    print(f"  Sessions: {len(session_ids)}")
    print(f"  Batches: {len(batches)}")
    for batch in batches:
        n = len(batch.contexts)
        print(f"    {batch.batch_id}: {n} sessions, {batch.total_tokens:,} tokens")

    # Load LLM config and create backend
    llm_config = load_llm_config()
    backend = LiteLLMBackend(llm_config)

    # Process each batch
    all_outputs: list[FrictionAnalysisOutput] = []
    total_cost = 0.0

    for batch in batches:
        digest = format_batch_digest(batch)
        output_schema = json.dumps(FrictionAnalysisOutput.model_json_schema(), indent=2)
        system_prompt = FRICTION_ANALYSIS_PROMPT.render_system()
        user_prompt = FRICTION_ANALYSIS_PROMPT.render_user(
            session_count=len(batch.contexts),
            batch_digest=digest,
            output_schema=output_schema,
        )

        total_prompt_tokens = count_tokens(system_prompt + user_prompt)

        print(f"\n  --- {batch.batch_id} ---")
        print(f"  Digest: {len(digest):,} chars")
        print(f"  Total prompt: {total_prompt_tokens:,} tokens")

        request = InferenceRequest(
            system=system_prompt,
            user=user_prompt,
            max_tokens=FRICTION_OUTPUT_TOKENS,
            timeout=300,
            temperature=0.0,
        )

        start = time.monotonic()
        result = asyncio.get_event_loop().run_until_complete(backend.generate(request))
        elapsed_ms = int((time.monotonic() - start) * 1000)

        print(f"  Model: {result.model}")
        print(f"  Duration: {elapsed_ms:,}ms")
        if result.usage:
            print(f"  Input tokens: {result.usage.input_tokens:,}")
            print(f"  Output tokens: {result.usage.output_tokens:,}")
        if result.cost_usd:
            print(f"  Cost: ${result.cost_usd:.4f}")
            total_cost += result.cost_usd

        # Parse output
        raw_text = result.text.strip()
        json_str = _extract_json(raw_text)

        batch_output = None
        parse_error = None
        try:
            data = json.loads(json_str)
            batch_output = FrictionAnalysisOutput.model_validate(data)
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(json_str)
            try:
                data = json.loads(repaired)
                batch_output = FrictionAnalysisOutput.model_validate(data)
                print("  (JSON repaired from truncated output)")
            except (json.JSONDecodeError, Exception) as exc:
                parse_error = str(exc)
        except Exception as exc:
            parse_error = str(exc)

        if batch_output:
            all_outputs.append(batch_output)
            print(f"  Events: {len(batch_output.friction_events)}")
            print(f"  Summary: {len(batch_output.summary)} chars")
            if batch_output.friction_events:
                for event in batch_output.friction_events:
                    print(
                        f"    [{event.severity}] {event.friction_type}"
                        f" — {event.user_intention[:80]}..."
                    )
        else:
            print(f"  PARSE ERROR: {parse_error}")
            print(f"  Raw output (first 500):\n{raw_text[:500]}")

    # Summary
    total_events = sum(len(o.events) for o in all_outputs)
    print("\n  --- Summary ---")
    print(f"  Total events: {total_events}")
    print(f"  Total cost: ${total_cost:.4f}")

    # Save log
    FRICTION_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    safe_label = label.lower().replace(" ", "_").replace("/", "-")
    log_path = FRICTION_LOGS_DIR / f"{timestamp}_{safe_label}.txt"

    log_lines = [
        f"FRICTION ANALYSIS LOG — {label}",
        f"Timestamp: {datetime.now(UTC).isoformat()}",
        f"Sessions: {len(session_ids)} — {', '.join(session_ids)}",
        f"Batches: {len(batches)}",
        f"Total events: {total_events}",
        f"Total cost: ${total_cost:.4f}",
        "",
    ]
    for i, output in enumerate(all_outputs):
        log_lines.append(f"BATCH {i + 1} OUTPUT:")
        log_lines.append(json.dumps(output.model_dump(), indent=2, default=str))
        log_lines.append("")

    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\n  Log saved: {log_path}")

    # Assertions
    assert len(all_outputs) > 0, "No batch produced valid output"
    assert all(len(o.summary) > 0 for o in all_outputs), "All batches should have summaries"


@pytest.mark.slow
@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
def test_friction_2_sessions():
    """Friction analysis with 2 sessions — should fit in 1 batch."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples not found: {EXAMPLES_DIR}")

    groups = _select_sessions(load_trajectory_groups(), count=2)
    _run_friction_analysis("2_sessions", groups)


@pytest.mark.slow
@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
def test_friction_5_sessions():
    """Friction analysis with all sessions — may produce multiple batches."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples not found: {EXAMPLES_DIR}")

    groups = load_trajectory_groups()
    _run_friction_analysis("all_sessions", groups)

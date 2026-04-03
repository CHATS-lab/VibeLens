"""Live friction analysis test via Claude Code CLI backend.

Exercises the full pipeline: extract → batch → claude -p - --output-format json → parse.
Saves raw prompts, raw CLI output, and parsed results to logs/friction/.

Run: python -m pytest tests/friction/test_friction_cli.py -s -v
"""

import asyncio
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from vibelens.llm.backends.claude_cli import ClaudeCliBackend
from vibelens.llm.prompts.friction_analysis import (
    FRICTION_ANALYSIS_PROMPT,
    FRICTION_SYNTHESIS_PROMPT,
)
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.analysis.friction import (
    FrictionLLMBatchOutput,
    FrictionSynthesisOutput,
)
from vibelens.models.inference import InferenceRequest
from vibelens.models.trajectories import Trajectory
from vibelens.services.context_extraction import extract_session_context, remap_session_ids
from vibelens.services.friction.analysis import (
    FRICTION_OUTPUT_TOKENS,
    FRICTION_TIMEOUT_SECONDS,
    SYNTHESIS_OUTPUT_TOKENS,
    SYNTHESIS_TIMEOUT_SECONDS,
)
from vibelens.services.friction.digest import format_batch_digest
from vibelens.services.session_batcher import build_batches
from vibelens.utils.json_extract import extract_json as _extract_json
from vibelens.utils.json_extract import repair_truncated_json as _repair_truncated_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = PROJECT_ROOT / "examples" / "claude-codex-example" / "parsed"
LOGS_DIR = PROJECT_ROOT / "logs" / "friction"


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


def _save_log(log_dir: Path, filename: str, content: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / filename).write_text(content, encoding="utf-8")


def _run_cli_friction_test(label: str, session_count: int | None = None) -> None:
    """Run friction analysis through Claude CLI backend and log everything."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples not found: {EXAMPLES_DIR}")

    groups = _load_trajectory_groups()
    if session_count:
        groups = dict(list(groups.items())[:session_count])

    # Extract contexts
    contexts = []
    for traj_group in groups.values():
        ctx = extract_session_context(traj_group)
        contexts.append(ctx)

    remap_session_ids(contexts)
    batches = build_batches(contexts)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = LOGS_DIR / f"{timestamp}_cli_{label}"

    # Create Claude CLI backend
    backend = ClaudeCliBackend(timeout=FRICTION_TIMEOUT_SECONDS)

    print(f"\n{'=' * 70}")
    print(f"  CLAUDE CLI FRICTION TEST: {label}")
    print(f"  Sessions: {len(groups)}, Batches: {len(batches)}")
    print(f"{'=' * 70}")

    all_batch_outputs: list[FrictionLLMBatchOutput] = []

    for idx, batch in enumerate(batches):
        digest = format_batch_digest(batch)
        output_schema = json.dumps(
            FRICTION_ANALYSIS_PROMPT.output_model.model_json_schema(), indent=2
        )
        system_prompt = FRICTION_ANALYSIS_PROMPT.render_system()
        user_prompt = FRICTION_ANALYSIS_PROMPT.render_user(
            session_count=len(batch.session_contexts),
            batch_digest=digest,
            output_schema=output_schema,
        )

        total_prompt = system_prompt + "\n\n" + user_prompt
        prompt_tokens = count_tokens(total_prompt)

        print(f"\n  --- Batch {idx} ---")
        print(f"  Prompt tokens: {prompt_tokens:,}")

        # Save prompts
        if idx == 0:
            _save_log(log_dir, "system_prompt.txt", system_prompt)
        _save_log(log_dir, f"user_prompt_{idx}.txt", user_prompt)
        _save_log(log_dir, f"full_prompt_{idx}.txt", total_prompt)

        request = InferenceRequest(
            system=system_prompt,
            user=user_prompt,
            max_tokens=FRICTION_OUTPUT_TOKENS,
            timeout=FRICTION_TIMEOUT_SECONDS,
            json_schema=FRICTION_ANALYSIS_PROMPT.output_model.model_json_schema(),
        )

        start = time.monotonic()
        result = asyncio.run(backend.generate(request))
        elapsed_ms = int((time.monotonic() - start) * 1000)

        print(f"  Model: {result.model}")
        print(f"  Duration: {elapsed_ms:,}ms")
        if result.usage:
            print(f"  Input tokens: {result.usage.input_tokens:,}")
            print(f"  Output tokens: {result.usage.output_tokens:,}")

        # Save raw result
        _save_log(log_dir, f"raw_result_{idx}.txt", result.text)
        _save_log(
            log_dir,
            f"result_metadata_{idx}.json",
            json.dumps(
                {
                    "model": result.model,
                    "duration_ms": result.duration_ms,
                    "usage": result.usage.model_dump() if result.usage else None,
                    "cost_usd": result.cost_usd,
                },
                indent=2,
            ),
        )

        # Parse
        raw_text = result.text.strip()
        print(f"  Raw output length: {len(raw_text)} chars")
        print(f"  First 200 chars: {raw_text[:200]!r}")

        batch_output = None
        parse_error = None

        # Attempt 1: direct JSON parse
        json_str = _extract_json(raw_text)
        try:
            data = json.loads(json_str)
            batch_output = FrictionLLMBatchOutput.model_validate(data)
        except json.JSONDecodeError as exc:
            print(f"  JSON decode error: {exc}")
            # Attempt 2: repair truncated
            repaired = _repair_truncated_json(json_str)
            try:
                data = json.loads(repaired)
                batch_output = FrictionLLMBatchOutput.model_validate(data)
                print("  (JSON repaired from truncated output)")
            except (json.JSONDecodeError, Exception) as exc2:
                parse_error = f"Repair also failed: {exc2}"
        except Exception as exc:
            parse_error = f"Validation error: {exc}"

        if batch_output:
            all_batch_outputs.append(batch_output)
            _save_log(
                log_dir,
                f"parsed_output_{idx}.json",
                json.dumps(batch_output.model_dump(), indent=2, default=str),
            )
            print(f"  Events: {len(batch_output.events)}")
            print(f"  Summary: {batch_output.summary!r}")
            if batch_output.top_mitigation:
                print(f"  Top mitigation: {batch_output.top_mitigation.action}")
            for event in batch_output.events:
                print(
                    f"    [{event.severity}] {event.friction_type}"
                    f" | help={event.claude_helpfulness}"
                    f" | span=({event.span_ref.session_id}, {event.span_ref.start_step_id}"
                    f"→{event.span_ref.end_step_id})"
                    f" | {event.user_intention[:60]}"
                )
                for m in event.mitigations:
                    print(f"        ↳ {m.action}: {m.content[:80]}")
        else:
            print(f"  PARSE ERROR: {parse_error}")
            _save_log(log_dir, f"parse_error_{idx}.txt", parse_error or "unknown")

    # Synthesis test (if we have events)
    total_events = sum(len(o.events) for o in all_batch_outputs)
    if total_events > 0 and all_batch_outputs:
        print("\n  --- Synthesis ---")
        batch_summaries = [o.summary for o in all_batch_outputs if o.summary]

        # Quick type summary for synthesis
        type_counts: dict[str, list] = {}
        for o in all_batch_outputs:
            for e in o.events:
                type_counts.setdefault(e.friction_type, []).append(e)

        type_stats = [
            {
                "friction_type": ft,
                "count": len(evts),
                "affected_sessions": len({e.span_ref.session_id for e in evts}),
                "avg_severity": round(sum(e.severity for e in evts) / len(evts), 1),
            }
            for ft, evts in type_counts.items()
        ]

        top_events = [
            {
                "friction_type": e.friction_type,
                "severity": e.severity,
                "user_intention": e.user_intention,
                "friction_detail": e.friction_detail,
            }
            for o in all_batch_outputs
            for e in sorted(o.events, key=lambda x: x.severity, reverse=True)
        ][:7]

        output_schema = json.dumps(
            FRICTION_SYNTHESIS_PROMPT.output_model.model_json_schema(), indent=2
        )
        system_prompt = FRICTION_SYNTHESIS_PROMPT.render_system()
        user_prompt = FRICTION_SYNTHESIS_PROMPT.render_user(
            batch_count=len(batches),
            session_count=len(groups),
            batch_summaries=batch_summaries,
            type_stats=type_stats,
            top_events=top_events,
            output_schema=output_schema,
        )

        _save_log(log_dir, "synthesis_system.txt", system_prompt)
        _save_log(log_dir, "synthesis_user.txt", user_prompt)

        syn_request = InferenceRequest(
            system=system_prompt,
            user=user_prompt,
            max_tokens=SYNTHESIS_OUTPUT_TOKENS,
            timeout=SYNTHESIS_TIMEOUT_SECONDS,
            json_schema=FRICTION_SYNTHESIS_PROMPT.output_model.model_json_schema(),
        )

        start = time.monotonic()
        syn_result = asyncio.get_event_loop().run_until_complete(backend.generate(syn_request))
        elapsed_ms = int((time.monotonic() - start) * 1000)

        _save_log(log_dir, "synthesis_raw.txt", syn_result.text)
        print(f"  Duration: {elapsed_ms:,}ms")
        print(f"  Raw length: {len(syn_result.text)} chars")
        print(f"  First 200: {syn_result.text.strip()[:200]!r}")

        # Parse synthesis
        syn_json = _extract_json(syn_result.text.strip())
        try:
            syn_data = json.loads(syn_json)
            synthesis = FrictionSynthesisOutput.model_validate(syn_data)
            _save_log(
                log_dir,
                "synthesis_parsed.json",
                json.dumps(synthesis.model_dump(), indent=2, default=str),
            )
            print(f"  Title: {synthesis.title!r}")
            print(f"  Summary: {synthesis.summary!r}")
            print(f"  Type descriptions: {len(synthesis.type_descriptions)}")
            print(f"  Cross-session patterns: {len(synthesis.cross_session_patterns)}")
            print(f"  Mitigations: {len(synthesis.mitigations)}")
        except Exception as exc:
            print(f"  SYNTHESIS PARSE ERROR: {exc}")
            _save_log(log_dir, "synthesis_error.txt", str(exc))

    print(f"\n  Total events: {total_events}")
    print(f"  Logs: {log_dir}")
    print(f"{'=' * 70}\n")

    assert len(all_batch_outputs) > 0, "No batch produced valid output"


SKIP_NO_EXAMPLES = pytest.mark.skipif(
    not EXAMPLES_DIR.exists(), reason="Example data not found"
)
SKIP_NO_CLAUDE_CLI = pytest.mark.skipif(
    shutil.which("claude") is None, reason="claude CLI not in PATH"
)


@SKIP_NO_EXAMPLES
@SKIP_NO_CLAUDE_CLI
def test_friction_cli_2_sessions():
    """Friction analysis via Claude CLI with 2 sessions."""
    _run_cli_friction_test("2_sessions", session_count=2)


@SKIP_NO_EXAMPLES
@SKIP_NO_CLAUDE_CLI
def test_friction_cli_all_sessions():
    """Friction analysis via Claude CLI with all sessions."""
    _run_cli_friction_test("all_sessions")

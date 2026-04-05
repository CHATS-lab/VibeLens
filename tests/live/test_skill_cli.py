"""Live skill analysis tests via LiteLLM and Codex CLI backends.

Exercises the full proposal + deep-creation pipeline:
  1. Load example sessions -> extract contexts -> build batches
  2. Run proposal inference via backend
  3. Parse SkillCreationProposalOutput
  4. Run deep creation for the first proposal
  5. Parse SkillCreation
  6. Log everything to logs/skill/

Run: python -m pytest tests/live/test_skill_cli.py -s -v
"""

import asyncio
import json
import shutil
import time
from datetime import UTC, datetime

import pytest

from vibelens.config.llm_config import load_llm_config
from vibelens.llm.backends import create_backend_from_llm_config
from vibelens.llm.backends.codex_cli import CodexCliBackend
from vibelens.llm.prompts.skill_creation import (
    SKILL_CREATION_GENERATE_PROMPT,
    SKILL_CREATION_PROPOSAL_PROMPT,
    SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT,
)
from vibelens.llm.tokenizer import count_tokens
from vibelens.models.inference import InferenceRequest
from vibelens.models.skill import SkillCreation, SkillCreationProposalOutput
from vibelens.services.context_extraction import extract_session_context
from vibelens.services.friction.digest import format_batch_digest
from vibelens.services.session_batcher import build_batches
from vibelens.services.skill.creation import (
    SKILL_CREATION_GENERATE_OUTPUT_TOKENS,
    SKILL_CREATION_GENERATE_TIMEOUT_SECONDS,
    SKILL_CREATION_PROPOSAL_OUTPUT_TOKENS,
    SKILL_CREATION_PROPOSAL_TIMEOUT_SECONDS,
)
from vibelens.services.skill.shared import gather_installed_skills
from vibelens.utils.json_extract import extract_json as _extract_json

from .conftest import EXAMPLES_DIR, LOGS_DIR, load_trajectory_groups, save_log

SKILL_LOGS_DIR = LOGS_DIR / "skill"


def _parse_proposal_output(raw_text: str) -> SkillCreationProposalOutput:
    """Parse and validate raw LLM text as SkillCreationProposalOutput."""
    json_str = _extract_json(raw_text)
    data = json.loads(json_str)
    return SkillCreationProposalOutput.model_validate(data)


def _parse_deep_creation_output(raw_text: str) -> SkillCreation:
    """Parse and validate raw LLM text as SkillCreation."""
    json_str = _extract_json(raw_text)
    data = json.loads(json_str)
    return SkillCreation.model_validate(data)


def _run_proposal_test(backend, label: str, session_count: int = 2) -> None:
    """Run skill proposal pipeline through a backend and log everything."""
    if not EXAMPLES_DIR.exists():
        pytest.skip(f"Examples not found: {EXAMPLES_DIR}")

    groups = load_trajectory_groups()
    groups = dict(list(groups.items())[:session_count])

    # Extract contexts
    contexts = []
    for traj_group in groups.values():
        ctx = extract_session_context(traj_group)
        contexts.append(ctx)

    batches = build_batches(contexts)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_dir = SKILL_LOGS_DIR / f"{timestamp}_{label}"

    installed_skills = gather_installed_skills()

    print(f"\n{'=' * 70}")
    print(f"  SKILL PROPOSAL TEST: {label}")
    print(f"  Sessions: {len(groups)}, Batches: {len(batches)}")
    print(f"{'=' * 70}")

    all_proposal_outputs: list[SkillCreationProposalOutput] = []

    for idx, batch in enumerate(batches):
        digest = format_batch_digest(batch)
        output_schema = json.dumps(
            SKILL_CREATION_PROPOSAL_PROMPT.output_model.model_json_schema(), indent=2
        )
        system_prompt = SKILL_CREATION_PROPOSAL_PROMPT.render_system()
        user_prompt = SKILL_CREATION_PROPOSAL_PROMPT.render_user(
            session_count=len(batch.session_contexts),
            session_digest=digest,
            output_schema=output_schema,
            installed_skills=installed_skills if installed_skills else None,
        )

        prompt_tokens = count_tokens(system_prompt + "\n\n" + user_prompt)

        print(f"\n  --- Proposal Batch {idx} ---")
        print(f"  Prompt tokens: {prompt_tokens:,}")

        if idx == 0:
            save_log(log_dir, "proposal_system.txt", system_prompt)
        save_log(log_dir, f"proposal_user_{idx}.txt", user_prompt)

        request = InferenceRequest(
            system=system_prompt,
            user=user_prompt,
            max_tokens=SKILL_CREATION_PROPOSAL_OUTPUT_TOKENS,
            timeout=SKILL_CREATION_PROPOSAL_TIMEOUT_SECONDS,
            json_schema=SKILL_CREATION_PROPOSAL_PROMPT.output_model.model_json_schema(),
        )

        start = time.monotonic()
        result = asyncio.run(backend.generate(request))
        elapsed_ms = int((time.monotonic() - start) * 1000)

        print(f"  Model: {result.model}")
        print(f"  Duration: {elapsed_ms:,}ms")
        if result.usage:
            print(f"  Input tokens: {result.usage.input_tokens:,}")
            print(f"  Output tokens: {result.usage.output_tokens:,}")
        if result.cost_usd:
            print(f"  Cost: ${result.cost_usd:.4f}")

        save_log(log_dir, f"proposal_raw_{idx}.txt", result.text)
        save_log(
            log_dir,
            f"proposal_metadata_{idx}.json",
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

        raw_text = result.text.strip()
        print(f"  Raw output length: {len(raw_text)} chars")
        print(f"  First 300 chars: {raw_text[:300]!r}")

        proposal_output = None
        parse_error = None

        try:
            proposal_output = _parse_proposal_output(raw_text)
        except Exception as exc:
            parse_error = f"Parse failed: {exc}"

        if proposal_output:
            all_proposal_outputs.append(proposal_output)
            save_log(
                log_dir,
                f"proposal_parsed_{idx}.json",
                json.dumps(proposal_output.model_dump(), indent=2, default=str),
            )
            print(f"  Patterns: {len(proposal_output.workflow_patterns)}")
            print(f"  Proposals: {len(proposal_output.proposals)}")
            print(f"  Summary: {proposal_output.summary[:120]!r}")
            print(f"  User profile: {proposal_output.user_profile[:120]!r}")
            for pattern in proposal_output.workflow_patterns:
                print(
                    f"    PATTERN: {pattern.title}"
                    f" | refs={len(pattern.example_refs)}"
                    f" | {pattern.description[:60]}"
                )
            for proposal in proposal_output.proposals:
                print(
                    f"    PROPOSAL: {proposal.skill_name}"
                    f" | {proposal.description[:60]}"
                    f" | addresses={proposal.addressed_patterns}"
                )
        else:
            print(f"  PARSE ERROR: {parse_error}")
            save_log(log_dir, f"proposal_error_{idx}.txt", parse_error or "unknown")

    # Synthesis test (if multiple batches)
    if len(all_proposal_outputs) > 1:
        print("\n  --- Proposal Synthesis ---")
        batch_data = [
            {
                "summary": output.summary,
                "user_profile": output.user_profile,
                "workflow_patterns": [
                    {
                        "title": p.title,
                        "description": p.description,
                        "gap": p.gap,
                    }
                    for p in output.workflow_patterns
                ],
                "proposals": [
                    {
                        "skill_name": p.skill_name,
                        "description": p.description,
                        "rationale": p.rationale,
                        "addressed_patterns": p.addressed_patterns,
                    }
                    for p in output.proposals
                ],
            }
            for output in all_proposal_outputs
        ]

        output_schema = json.dumps(
            SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT.output_model.model_json_schema(), indent=2
        )
        system_prompt = SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT.render_system()
        user_prompt = SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT.render_user(
            batch_count=len(batches),
            session_count=len(groups),
            batch_results=batch_data,
            output_schema=output_schema,
        )

        save_log(log_dir, "synthesis_system.txt", system_prompt)
        save_log(log_dir, "synthesis_user.txt", user_prompt)

        syn_request = InferenceRequest(
            system=system_prompt,
            user=user_prompt,
            max_tokens=SKILL_CREATION_PROPOSAL_OUTPUT_TOKENS,
            timeout=SKILL_CREATION_PROPOSAL_TIMEOUT_SECONDS,
            json_schema=SKILL_CREATION_PROPOSAL_SYNTHESIS_PROMPT.output_model.model_json_schema(),
        )

        start = time.monotonic()
        syn_result = asyncio.run(backend.generate(syn_request))
        elapsed_ms = int((time.monotonic() - start) * 1000)

        save_log(log_dir, "synthesis_raw.txt", syn_result.text)
        print(f"  Duration: {elapsed_ms:,}ms")

        try:
            synthesis = _parse_proposal_output(syn_result.text.strip())
            save_log(
                log_dir,
                "synthesis_parsed.json",
                json.dumps(synthesis.model_dump(), indent=2, default=str),
            )
            print(f"  Merged patterns: {len(synthesis.workflow_patterns)}")
            print(f"  Merged proposals: {len(synthesis.proposals)}")
            print(f"  Summary: {synthesis.summary[:120]!r}")
        except Exception as exc:
            print(f"  SYNTHESIS PARSE ERROR: {exc}")
            save_log(log_dir, "synthesis_error.txt", str(exc))

    # Deep creation test for first proposal
    total_proposals = sum(len(o.proposals) for o in all_proposal_outputs)
    if total_proposals > 0:
        first_proposal = all_proposal_outputs[0].proposals[0]
        print(f"\n  --- Deep Creation: {first_proposal.skill_name} ---")

        # Use first batch digest as session evidence
        first_batch = batches[0]
        digest = format_batch_digest(first_batch)
        output_schema = json.dumps(
            SKILL_CREATION_GENERATE_PROMPT.output_model.model_json_schema(), indent=2
        )
        system_prompt = SKILL_CREATION_GENERATE_PROMPT.render_system()
        user_prompt = SKILL_CREATION_GENERATE_PROMPT.render_user(
            proposal_name=first_proposal.skill_name,
            proposal_description=first_proposal.description,
            proposal_rationale=first_proposal.rationale,
            addressed_patterns=first_proposal.addressed_patterns,
            session_digest=digest,
            installed_skills=installed_skills if installed_skills else None,
            output_schema=output_schema,
        )

        save_log(log_dir, "deep_creation_system.txt", system_prompt)
        save_log(log_dir, "deep_creation_user.txt", user_prompt)

        dc_request = InferenceRequest(
            system=system_prompt,
            user=user_prompt,
            max_tokens=SKILL_CREATION_GENERATE_OUTPUT_TOKENS,
            timeout=SKILL_CREATION_GENERATE_TIMEOUT_SECONDS,
            json_schema=SKILL_CREATION_GENERATE_PROMPT.output_model.model_json_schema(),
        )

        start = time.monotonic()
        dc_result = asyncio.run(backend.generate(dc_request))
        elapsed_ms = int((time.monotonic() - start) * 1000)

        save_log(log_dir, "deep_creation_raw.txt", dc_result.text)
        save_log(
            log_dir,
            "deep_creation_metadata.json",
            json.dumps(
                {
                    "model": dc_result.model,
                    "duration_ms": dc_result.duration_ms,
                    "usage": dc_result.usage.model_dump() if dc_result.usage else None,
                    "cost_usd": dc_result.cost_usd,
                },
                indent=2,
            ),
        )

        print(f"  Duration: {elapsed_ms:,}ms")
        if dc_result.cost_usd:
            print(f"  Cost: ${dc_result.cost_usd:.4f}")

        try:
            deep_output = _parse_deep_creation_output(dc_result.text.strip())
            save_log(
                log_dir,
                "deep_creation_parsed.json",
                json.dumps(deep_output.model_dump(), indent=2, default=str),
            )
            print(f"  Name: {deep_output.name}")
            print(f"  Description: {deep_output.description}")
            print(f"  Tools: {deep_output.tools_used}")
            print(f"  Rationale: {deep_output.rationale[:120]}")
            print(f"  SKILL.md length: {len(deep_output.skill_md_content)} chars")
            print(f"  SKILL.md preview:\n{deep_output.skill_md_content[:500]}")
        except Exception as exc:
            print(f"  DEEP CREATION PARSE ERROR: {exc}")
            save_log(log_dir, "deep_creation_error.txt", str(exc))

    print(f"\n  Total proposals: {total_proposals}")
    print(f"  Logs: {log_dir}")
    print(f"{'=' * 70}\n")

    assert len(all_proposal_outputs) > 0, "No batch produced valid proposal output"
    assert total_proposals > 0, "No proposals generated"


@pytest.mark.slow
@pytest.mark.skipif(not EXAMPLES_DIR.exists(), reason="Example data not found")
def test_skill_proposals_litellm():
    """Skill proposal + deep creation via LiteLLM backend."""
    config = load_llm_config()
    backend = create_backend_from_llm_config(config)
    if backend is None:
        pytest.skip("LLM backend not configured (backend=disabled)")
    _run_proposal_test(backend, "litellm_proposals", session_count=2)


@pytest.mark.slow
@pytest.mark.skipif(not EXAMPLES_DIR.exists(), reason="Example data not found")
@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not in PATH")
def test_skill_proposals_codex_cli():
    """Skill proposal + deep creation via Codex CLI backend."""
    backend = CodexCliBackend(timeout=SKILL_CREATION_PROPOSAL_TIMEOUT_SECONDS)
    _run_proposal_test(backend, "codex_proposals", session_count=2)

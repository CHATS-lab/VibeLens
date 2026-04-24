"""Run one inference mode against multiple backends in parallel.

Spawns one subprocess per backend (each invokes the corresponding
``run_<mode>.py`` with ``--backend <name>`` overrides), captures output,
and prints a comparison table.

Parameters — all have sensible defaults so a bare call "just works":

    mode                    Positional. creation | evolution | recommendation | friction.
    --backends CSV          Comma-separated backend list
                            (default: claude_code,codex,gemini,openclaw,opencode).
    --model STR             Force one model for every backend. When omitted, each
                            backend uses its own default from the model catalog
                            (e.g. claude-haiku-4-5 for Claude, gpt-5.4-mini for Codex).
                            Do NOT pass a single backend-specific model when
                            fanning out — it will break the others.
    --thinking              Enable reasoning. Default: off (project policy).
    --count N               Random-sample N eligible local sessions. Default: 15.
    --sessions ID[,ID,...]  Explicit session IDs (skips sampling). Comma-separated.

Every subprocess runs with ``--no-thinking`` (or ``--thinking``) matching
the top-level flag, so all backends operate under identical policy.

Usage examples:

    python run_all_backends.py evolution
    python run_all_backends.py friction --count 5
    python run_all_backends.py creation --backends claude_code,codex
    python run_all_backends.py evolution --sessions example-session-claude-01

Each backend runs with its own ``InferenceConfig`` (via
``scripts/inference/_shared.py``'s ``apply_config_overrides``), which
updates both the backend singleton AND ``get_settings().inference`` so
the ``InferenceLogWriter`` snapshot reflects the actual runtime config.
"""

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from vibelens.llm.model_catalog import default_model
from vibelens.models.llm.inference import BackendType

MODES = ["creation", "evolution", "recommendation", "friction"]
DEFAULT_BACKENDS = ["claude_code", "codex", "gemini", "openclaw", "opencode"]
DEFAULT_SAMPLE_COUNT = 15
RESULT_PATTERN = re.compile(r"Analysis ID:\s*(\S+)")
COST_PATTERN = re.compile(r"Cost:\s*\$([\d.]+)")
TITLE_PATTERN = re.compile(r"Title:\s*(.+)")


@dataclass
class BackendRun:
    """Captured output from one backend subprocess."""

    backend: str
    returncode: int
    stdout: str
    stderr: str


def _script_for_mode(mode: str) -> Path:
    """Resolve the per-mode runner path relative to this file."""
    return Path(__file__).parent / f"run_{mode}.py"


async def _run_one(
    mode: str,
    backend: str,
    model: str | None,
    thinking: bool,
    count: int,
    session_ids: list[str],
) -> BackendRun:
    """Launch one backend's runner as a subprocess.

    If ``model`` is None, resolve each backend's default from the model
    catalog so the parallel fan-out doesn't accidentally send
    claude-haiku-4-5 (from on-disk config) to every backend.
    """
    try:
        backend_enum = BackendType(backend)
    except ValueError as exc:
        return BackendRun(backend=backend, returncode=2, stdout="", stderr=f"{exc}\n")
    resolved_model = model or default_model(backend_enum)
    cmd = [
        sys.executable,
        str(_script_for_mode(mode)),
        "--backend",
        backend,
        "--count",
        str(count),
    ]
    if resolved_model:
        cmd.extend(["--model", resolved_model])
    cmd.append("--thinking" if thinking else "--no-thinking")
    cmd.extend(session_ids)

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return BackendRun(
        backend=backend,
        returncode=proc.returncode or 0,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


def _parse_summary(stdout: str) -> dict[str, str | None]:
    """Pull key metadata out of the runner's summary footer."""
    analysis_id = _search(RESULT_PATTERN, stdout)
    title = _search(TITLE_PATTERN, stdout)
    cost = _search(COST_PATTERN, stdout)
    return {"analysis_id": analysis_id, "title": title, "cost": cost}


def _search(pattern: re.Pattern, text: str) -> str | None:
    """Return the first capture group of ``pattern`` in ``text``, or None."""
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _print_table(mode: str, runs: list[BackendRun]) -> None:
    """Print the comparison table + per-backend error context."""
    print(f"\n{'=' * 90}")
    print(f"Parallel {mode} across {len(runs)} backend(s)")
    print(f"{'=' * 90}")
    print(f"{'backend':<15} {'status':<8} {'cost':<10} {'analysis_id':<30} title")
    print(f"{'-' * 90}")
    for run in runs:
        info = _parse_summary(run.stdout)
        status = "OK" if run.returncode == 0 else f"EXIT-{run.returncode}"
        cost = f"${info['cost']}" if info["cost"] else "-"
        aid = info["analysis_id"] or "-"
        title = (info["title"] or "-")[:40]
        print(f"{run.backend:<15} {status:<8} {cost:<10} {aid:<30} {title}")

    failures = [r for r in runs if r.returncode != 0]
    if failures:
        print(f"\n{'=' * 90}")
        print(f"{len(failures)} backend(s) failed — stderr tail below:")
        for run in failures:
            print(f"\n--- {run.backend} ---")
            print(run.stderr[-800:])

    if runs:
        print(f"\n{'=' * 90}")
        print(f"Verify logs: python scripts/inference/verify.py --mode {mode}")


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("mode", choices=MODES, help="Analysis mode to run.")
    parser.add_argument(
        "--backends",
        default=",".join(DEFAULT_BACKENDS),
        help=(
            "Comma-separated backend list to fan out to "
            f"(default: {','.join(DEFAULT_BACKENDS)})."
        ),
    )
    parser.add_argument(
        "--model",
        help=(
            "Force one model across every backend. "
            "Default: each backend uses its own catalog default."
        ),
    )
    parser.add_argument("--thinking", action="store_true", help="Enable thinking (default: off).")
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_SAMPLE_COUNT,
        help=f"Random-sample N eligible sessions per run (default: {DEFAULT_SAMPLE_COUNT}).",
    )
    parser.add_argument(
        "--sessions",
        default="",
        help="Comma-separated explicit session IDs (skips random sampling).",
    )
    ns = parser.parse_args()

    backends = [b.strip() for b in ns.backends.split(",") if b.strip()]
    session_ids = [s.strip() for s in ns.sessions.split(",") if s.strip()]
    print(
        f"Launching {len(backends)} parallel {ns.mode} runs; "
        f"thinking={ns.thinking} model={ns.model or 'backend-default'} "
        f"count={ns.count if not session_ids else len(session_ids)} "
        f"source={'explicit' if session_ids else 'random-sample'}"
    )
    tasks = [
        _run_one(
            mode=ns.mode,
            backend=b,
            model=ns.model,
            thinking=ns.thinking,
            count=ns.count,
            session_ids=session_ids,
        )
        for b in backends
    ]
    runs = await asyncio.gather(*tasks)
    _print_table(ns.mode, runs)


if __name__ == "__main__":
    asyncio.run(_main())

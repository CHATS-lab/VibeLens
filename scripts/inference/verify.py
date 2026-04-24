"""Verify an inference run by inspecting its ``inference.json`` log.

Usage:
    python verify.py                     # latest across all modes
    python verify.py --mode evolution    # latest evolution run
    python verify.py --id 20260424T192533-yKtuSqzm

Reports per-call reasoning tokens, thinking tokens, cost backfill status,
and flags any warnings. Use this after any inference run to confirm that
the thinking/cost/config configuration actually took effect at runtime.
"""

import argparse
import json
from pathlib import Path

ANALYSIS_MODES = ["creation", "evolution", "recommendation", "friction"]
VIBELENS_LOGS = Path.home() / ".vibelens" / "logs"


def _collect_candidates(mode: str | None) -> list[Path]:
    """Return all ``inference.json`` files for the given mode (or all)."""
    search_modes = [mode] if mode else ANALYSIS_MODES
    candidates: list[Path] = []
    for m in search_modes:
        if m == "friction":
            base = VIBELENS_LOGS / "friction"
        else:
            base = VIBELENS_LOGS / "personalization" / m
        if not base.exists():
            continue
        candidates.extend(base.rglob("inference.json"))
    return candidates


def _find_latest(mode: str | None) -> Path | None:
    """Return the most recently modified ``inference.json`` matching mode."""
    candidates = _collect_candidates(mode)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _find_by_id(analysis_id: str) -> Path | None:
    """Locate the ``inference.json`` matching an analysis id across all modes."""
    for m in ANALYSIS_MODES:
        if m == "friction":
            path = VIBELENS_LOGS / "friction" / analysis_id / "inference.json"
        else:
            path = VIBELENS_LOGS / "personalization" / m / analysis_id / "inference.json"
        if path.exists():
            return path
    return None


def _print_report(path: Path) -> None:
    """Pretty-print one inference.json's key diagnostics."""
    data = json.loads(path.read_text())
    config = data.get("config") or {}
    calls = data.get("calls") or []

    print(f"\n{'=' * 70}")
    print(f"Log:        {path}")
    print(f"Mode:       {data.get('mode')}")
    print(f"Analysis:   {data.get('analysis_id')}")
    print(
        f"Config:     backend={config.get('backend')} model={config.get('model')} "
        f"thinking={config.get('thinking')}"
    )
    print(f"Calls:      {len(calls)}")
    print(f"{'-' * 70}")

    total_reasoning = 0
    total_thinking = 0
    total_cost = 0.0
    for i, call in enumerate(calls, start=1):
        result = call.get("result") or {}
        metrics = result.get("metrics") or {}
        extra = metrics.get("extra") or {}
        reasoning = extra.get("reasoning_tokens") or 0
        thinking = extra.get("thinking_tokens") or 0
        cost = metrics.get("cost_usd")
        completion = metrics.get("completion_tokens") or 0
        prompt = metrics.get("prompt_tokens") or 0
        duration_ms = metrics.get("duration_ms") or 0
        total_reasoning += reasoning
        total_thinking += thinking
        total_cost += cost or 0
        cost_str = f"${cost:.5f}" if cost is not None else "null"
        print(
            f"  [{i:>2}] model={result.get('model')!r:<30} "
            f"compl={completion:>5} prompt={prompt:>7} "
            f"reason={reasoning:>5} think={thinking:>5} "
            f"dur={duration_ms / 1000:>5.1f}s cost={cost_str}"
        )

    print(f"{'-' * 70}")
    print(
        f"TOTAL       reasoning={total_reasoning} thinking={total_thinking} "
        f"cost=${total_cost:.5f}"
    )

    # Sanity checks: flag obvious config/behavior mismatches.
    flags: list[str] = []
    if config.get("thinking") is False and (total_reasoning or total_thinking):
        flags.append(
            f"thinking=False but reasoning/thinking tokens > 0 "
            f"(reasoning={total_reasoning} thinking={total_thinking})"
        )
    if any(c.get("result", {}).get("metrics", {}).get("cost_usd") is None for c in calls):
        missing = sum(
            1 for c in calls if (c.get("result", {}).get("metrics") or {}).get("cost_usd") is None
        )
        flags.append(f"{missing}/{len(calls)} call(s) missing cost_usd (pricing lookup failed)")
    if flags:
        print(f"{'-' * 70}")
        print("FLAGS:")
        for f in flags:
            print(f"  - {f}")
    print(f"{'=' * 70}")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--mode", choices=ANALYSIS_MODES, help="Filter by analysis mode.")
    parser.add_argument("--id", dest="analysis_id", help="Inspect a specific analysis id.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Print every matching log instead of only the latest.",
    )
    ns = parser.parse_args()

    if ns.analysis_id:
        path = _find_by_id(ns.analysis_id)
        if not path:
            raise SystemExit(f"No inference.json found for id {ns.analysis_id}")
        _print_report(path)
        return

    if ns.all:
        paths = sorted(_collect_candidates(ns.mode), key=lambda p: p.stat().st_mtime)
        if not paths:
            raise SystemExit("No inference.json files found.")
        for p in paths:
            _print_report(p)
        return

    path = _find_latest(ns.mode)
    if not path:
        raise SystemExit("No inference.json files found.")
    _print_report(path)


if __name__ == "__main__":
    main()

"""Mock friction analysis data for demo/test mode.

Builds realistic FrictionAnalysisResult with 9 events covering all 5 severity
levels, spread across all available sessions, including edge cases (null tokens,
null time, single-step events, empty mitigations).
"""

from collections import defaultdict
from datetime import UTC, datetime

from vibelens.deps import get_store
from vibelens.models.analysis.friction import (
    ClaudeMdSuggestion,
    FrictionAnalysisResult,
    FrictionCost,
    FrictionEvent,
    ModeSummary,
)
from vibelens.models.analysis.step_ref import StepRef


def build_mock_friction_result(session_ids: list[str]) -> FrictionAnalysisResult:
    """Build a realistic mock FrictionAnalysisResult for demo/test mode.

    Loads real trajectories from the store to extract actual step IDs,
    ensuring jump-to-step navigation works end-to-end.

    Args:
        session_ids: Session IDs from the request.

    Returns:
        Mock FrictionAnalysisResult with sample events and suggestions.
    """
    step_id_pool = _collect_step_ids(session_ids)
    events = _build_mock_events(step_id_pool)
    suggestions = _build_mock_suggestions()
    mode_summary = _build_mock_mode_summary(events)
    skipped = [sid for sid in session_ids if sid not in step_id_pool]
    session_count = len(step_id_pool)
    total_wasted = sum(e.estimated_cost.wasted_steps for e in events)
    total_tokens = sum(e.estimated_cost.wasted_tokens or 0 for e in events)
    total_time = sum(e.estimated_cost.wasted_time_seconds or 0 for e in events)

    return FrictionAnalysisResult(
        events=events,
        summary=(
            f"Analysis of {session_count} session{'s' if session_count != 1 else ''} "
            f"revealed {len(events)} friction events across "
            f"{len(mode_summary)} distinct modes. "
            f"A total of {total_wasted} steps were wasted, consuming approximately "
            f"{total_tokens:,} tokens and {total_time / 60:.1f} minutes of wall-clock time. "
            "The most critical event was a cascading-failure where a broken import "
            "propagated through 5 dependent files, requiring extensive rework."
        ),
        top_mitigation=(
            "Add a CLAUDE.md rule enforcing structured parsing over regex for data formats. "
            "This single rule would have prevented the highest-severity friction event."
        ),
        claude_md_suggestions=suggestions,
        mode_summary=mode_summary,
        session_ids=list(step_id_pool.keys()),
        sessions_skipped=skipped,
        backend_id="mock",
        model="mock/test-model",
        cost_usd=0.042,
        computed_at=datetime.now(UTC).isoformat(),
    )


def _collect_step_ids(session_ids: list[str]) -> dict[str, list[str]]:
    """Load trajectories and collect agent step IDs per session.

    Args:
        session_ids: Requested session IDs.

    Returns:
        Mapping of session_id to list of step_ids (agent steps only).
    """
    store = get_store()
    pool: dict[str, list[str]] = {}
    for sid in session_ids:
        trajectories = store.load(sid)
        if not trajectories:
            continue
        step_ids = [
            step.step_id
            for traj in trajectories
            for step in traj.steps
            if step.source == "agent"
        ]
        if step_ids:
            pool[sid] = step_ids
    return pool


def _pick_steps(
    pool: dict[str, list[str]], session_idx: int, start: int, count: int
) -> tuple[str, list[str]]:
    """Pick consecutive step IDs from the pool for a mock event.

    Args:
        pool: session_id -> step_ids mapping.
        session_idx: Which session to pick from (wraps around).
        start: Starting index within the session's step list.
        count: Number of step IDs to pick.

    Returns:
        Tuple of (session_id, step_ids slice).
    """
    sids = list(pool.keys())
    sid = sids[session_idx % len(sids)]
    steps = pool[sid]
    actual_start = min(start, max(len(steps) - count, 0))
    return sid, steps[actual_start : actual_start + count]


def _mock_event(
    event_id: str,
    mode: str,
    sid: str,
    steps: list[str],
    severity: int,
    description: str,
    evidence: str,
    root_cause: str,
    mitigations: list[str],
    estimated_cost: FrictionCost,
    related_event_ids: list[str],
) -> FrictionEvent:
    """Build a single mock FrictionEvent with StepRef from picked steps."""
    return FrictionEvent(
        event_id=event_id,
        mode=mode,
        ref=StepRef(
            session_id=sid,
            start_step_id=steps[0],
            end_step_id=steps[-1] if len(steps) > 1 else None,
        ),
        step_ids=steps,
        severity=severity,
        description=description,
        evidence=evidence,
        root_cause=root_cause,
        mitigations=mitigations,
        estimated_cost=estimated_cost,
        related_event_ids=related_event_ids,
    )


def _build_mock_events(pool: dict[str, list[str]]) -> list[FrictionEvent]:
    """Build 9 mock friction events covering all severity levels.

    Spreads across all available sessions and includes edge cases
    (null tokens, null time, single-step, many steps, empty mitigations).

    Args:
        pool: session_id -> step_ids mapping from _collect_step_ids.

    Returns:
        List of mock FrictionEvents referencing real step IDs.
    """
    if not pool:
        return []

    n = len(pool)

    sid_1, steps_1 = _pick_steps(pool, 0, 1, 3)
    sid_2, steps_2 = _pick_steps(pool, 1 % n, 1, 2)
    sid_3, steps_3 = _pick_steps(pool, 2 % n, 8, 4)
    sid_4, steps_4 = _pick_steps(pool, 3 % n, 4, 3)
    sid_5, steps_5 = _pick_steps(pool, 4 % n, 0, 1)
    sid_6, steps_6 = _pick_steps(pool, 5 % n, 2, 5)
    sid_7, steps_7 = _pick_steps(pool, 6 % n, 6, 2)
    sid_8, steps_8 = _pick_steps(pool, 0, 12, 6)
    sid_9, steps_9 = _pick_steps(pool, 1 % n, 8, 1)

    return [
        # Severity 5: Critical
        _mock_event(
            event_id="f-1",
            mode="cascading-failure",
            sid=sid_6,
            steps=steps_6,
            severity=5,
            description=(
                "Agent refactored a shared utility module but broke the import "
                "contract. 5 downstream files failed to import, triggering a "
                "chain of fixes that each introduced new errors."
            ),
            evidence=(
                "Edit to utils/core.py renamed 'parse_config' to '_parse_config'. "
                "Subsequent runs of app.py, cli.py, api.py, worker.py, and tests/ "
                "all raised ImportError. Each fix attempt addressed one file but "
                "missed the re-export in __init__.py."
            ),
            root_cause=(
                "Renamed a public function without grep-checking all call sites. "
                "No CLAUDE.md rule about verifying cross-file impact before renaming."
            ),
            mitigations=[
                "Add CLAUDE.md rule: 'Before renaming any public function, grep "
                "the entire codebase for all call sites.'",
                "Run the full test suite after any rename, not just the modified file's tests.",
                "Use IDE refactoring tools that update all references atomically.",
            ],
            estimated_cost=FrictionCost(
                wasted_steps=5, wasted_time_seconds=180, wasted_tokens=42000
            ),
            related_event_ids=["f-2", "f-4"],
        ),
        # Severity 4: High
        _mock_event(
            event_id="f-2",
            mode="wrong-approach",
            sid=sid_1,
            steps=steps_1,
            severity=4,
            description=(
                "Agent attempted regex-based parsing for a complex nested "
                "JSON structure, failed twice before switching to json.loads()."
            ),
            evidence=(
                "Steps show repeated regex attempts on nested JSON "
                "with increasing complexity, each producing parse errors."
            ),
            root_cause=(
                "Default preference for regex over structured parsing, "
                "no CLAUDE.md guidance for data format handling."
            ),
            mitigations=[
                "Add CLAUDE.md rule: 'Always use json.loads() for JSON parsing, never regex.'",
                "Use structured parsing libraries for nested data formats.",
            ],
            estimated_cost=FrictionCost(
                wasted_steps=3, wasted_time_seconds=45, wasted_tokens=8500
            ),
            related_event_ids=["f-5"],
        ),
        # Severity 3: Moderate
        _mock_event(
            event_id="f-3",
            mode="permission-denied-loop",
            sid=sid_2,
            steps=steps_2,
            severity=3,
            description=(
                "Agent tried writing to a read-only directory, then retried "
                "the same path before checking permissions."
            ),
            evidence=(
                "Bash tool call to write /etc/config failed with EACCES, "
                "immediate retry with same path, then a third attempt with sudo."
            ),
            root_cause=(
                "No error inspection before retry; agent retried without "
                "analyzing the failure message."
            ),
            mitigations=[
                "Add CLAUDE.md rule: 'On permission errors, check file "
                "ownership and directory permissions before retrying.'",
            ],
            estimated_cost=FrictionCost(
                wasted_steps=2, wasted_time_seconds=12, wasted_tokens=3200
            ),
            related_event_ids=[],
        ),
        _mock_event(
            event_id="f-4",
            mode="test-fix-loop",
            sid=sid_4,
            steps=steps_4,
            severity=3,
            description=(
                "Agent ran tests, saw a failure, applied a fix, "
                "but the fix introduced a new failure, "
                "requiring another cycle."
            ),
            evidence=(
                "pytest run failed on test_auth.py:42, fix applied "
                "to auth.py:18, re-run showed new failure on "
                "test_auth.py:55."
            ),
            root_cause=(
                "Fix was too narrow — addressed the symptom "
                "(assertion value) without understanding the "
                "full test contract."
            ),
            mitigations=[
                "Read the full test file before applying fixes to understand all assertions.",
                "Run the specific test in isolation before running the full suite.",
            ],
            estimated_cost=FrictionCost(
                wasted_steps=3, wasted_time_seconds=60, wasted_tokens=9500
            ),
            related_event_ids=["f-1"],
        ),
        # Severity 2: Low
        _mock_event(
            event_id="f-5",
            mode="excessive-exploration",
            sid=sid_3,
            steps=steps_3,
            severity=2,
            description=(
                "Agent read 4 files to understand a utility function "
                "that was already documented in the README."
            ),
            evidence=(
                "Sequential Read calls on utils.py, helpers.py, "
                "types.py, and constants.py when README.md section "
                "'Utilities' covers all APIs."
            ),
            root_cause=(
                "Agent did not check documentation before diving "
                "into source code exploration."
            ),
            mitigations=[
                "Add CLAUDE.md rule: 'Check README and docs/ "
                "before exploring source for utility APIs.'",
                "Keep utility function docstrings up to date.",
            ],
            estimated_cost=FrictionCost(
                wasted_steps=4, wasted_time_seconds=30, wasted_tokens=12000
            ),
            related_event_ids=["f-2"],
        ),
        _mock_event(
            event_id="f-6",
            mode="redundant-read",
            sid=sid_7,
            steps=steps_7,
            severity=2,
            description=(
                "Agent read the same configuration file twice within "
                "3 steps, wasting tokens on duplicate content."
            ),
            evidence=(
                "Read tool called on config/settings.yaml at step N, "
                "then identical Read at step N+2 with no edits in between."
            ),
            root_cause=(
                "No short-term memory of recently read files; agent "
                "did not check its own context for prior reads."
            ),
            mitigations=[
                "Remind agent to check conversation context before re-reading files.",
            ],
            estimated_cost=FrictionCost(
                wasted_steps=2, wasted_time_seconds=8, wasted_tokens=4200
            ),
            related_event_ids=[],
        ),
        # Severity 1: Minor
        _mock_event(
            event_id="f-7",
            mode="style-churn",
            sid=sid_5,
            steps=steps_5,
            severity=1,
            description=(
                "Agent reformatted an import block to alphabetical order, "
                "then the linter reverted it to grouped order."
            ),
            evidence=(
                "Edit tool sorted imports alphabetically in models.py. "
                "Next step ran ruff which re-ordered them back to "
                "stdlib/third-party/local grouping."
            ),
            root_cause=(
                "Agent did not know the project's import ordering convention."
            ),
            mitigations=[],
            estimated_cost=FrictionCost(
                wasted_steps=1, wasted_time_seconds=5, wasted_tokens=1200
            ),
            related_event_ids=[],
        ),
        # Edge case: many steps, high token cost, no time estimate
        _mock_event(
            event_id="f-8",
            mode="context-overflow",
            sid=sid_8,
            steps=steps_8,
            severity=4,
            description=(
                "Agent loaded 6 large files into context to trace a bug, "
                "exceeding useful context and losing track of the original "
                "goal. Restarted the investigation from scratch."
            ),
            evidence=(
                "Read tool called on 6 files totaling ~4,000 lines. "
                "Agent then said 'Let me start over' and re-read "
                "the first file, discarding prior context."
            ),
            root_cause=(
                "No strategy for incremental investigation; agent "
                "tried to load everything at once."
            ),
            mitigations=[
                "Add CLAUDE.md rule: 'For debugging, start with the error "
                "traceback and only read files referenced in the stack.'",
                "Use grep to narrow down relevant code before reading full files.",
                "Read files with offset/limit to avoid loading entire large files.",
            ],
            estimated_cost=FrictionCost(
                wasted_steps=6, wasted_time_seconds=None, wasted_tokens=58000
            ),
            related_event_ids=["f-5", "f-6"],
        ),
        # Edge case: single step, no tokens estimate
        _mock_event(
            event_id="f-9",
            mode="wrong-tool",
            sid=sid_9,
            steps=steps_9,
            severity=1,
            description=(
                "Agent used Bash to run 'cat' on a file instead of "
                "the dedicated Read tool."
            ),
            evidence=(
                "Bash tool call: 'cat src/main.py' when Read tool "
                "was available and would have provided line numbers."
            ),
            root_cause=(
                "Minor tool selection inefficiency, no functional impact."
            ),
            mitigations=[],
            estimated_cost=FrictionCost(
                wasted_steps=1, wasted_time_seconds=2, wasted_tokens=None
            ),
            related_event_ids=[],
        ),
    ]


def _build_mock_suggestions() -> list[ClaudeMdSuggestion]:
    """Build mock CLAUDE.md suggestions for test mode."""
    return [
        ClaudeMdSuggestion(
            rule=(
                "Before renaming any public function, grep the entire "
                "codebase for all call sites and update them atomically."
            ),
            section="Refactoring",
            rationale=(
                "A public function rename broke 5 downstream files, "
                "causing a cascading-failure chain (severity 5)."
            ),
            source_event_ids=["f-1"],
        ),
        ClaudeMdSuggestion(
            rule="Always use json.loads() for JSON parsing, never regex.",
            section="Coding Conventions",
            rationale=(
                "Agent wasted 3 steps attempting regex-based JSON parsing "
                "before switching to the standard library."
            ),
            source_event_ids=["f-2"],
        ),
        ClaudeMdSuggestion(
            rule=(
                "On permission errors, inspect the error message and "
                "check ownership before retrying."
            ),
            section="Error Handling",
            rationale=(
                "Agent retried a write to a read-only path without "
                "checking the EACCES error."
            ),
            source_event_ids=["f-3"],
        ),
        ClaudeMdSuggestion(
            rule=(
                "Check README and docs/ before exploring source "
                "code for utility APIs."
            ),
            section="Exploration Strategy",
            rationale=(
                "Agent read 4 source files for information already "
                "available in README."
            ),
            source_event_ids=["f-5"],
        ),
        ClaudeMdSuggestion(
            rule=(
                "For debugging, start with the error traceback and only "
                "read files referenced in the stack."
            ),
            section="Debugging",
            rationale=(
                "Agent loaded 6 large files at once, overflowed context, "
                "and had to restart the investigation from scratch."
            ),
            source_event_ids=["f-8"],
        ),
    ]


def _build_mock_mode_summary(
    events: list[FrictionEvent],
) -> list[ModeSummary]:
    """Build mode summary dynamically from mock events.

    Args:
        events: List of friction events to summarize.

    Returns:
        List of ModeSummary sorted by avg_severity descending.
    """
    mode_groups: dict[str, list[FrictionEvent]] = defaultdict(list)
    for event in events:
        mode_groups[event.mode].append(event)

    summaries = []
    for mode, group in mode_groups.items():
        total_steps = sum(e.estimated_cost.wasted_steps for e in group)
        total_time = sum(
            e.estimated_cost.wasted_time_seconds or 0 for e in group
        )
        total_tokens = sum(
            e.estimated_cost.wasted_tokens or 0 for e in group
        )
        affected = len({e.ref.session_id for e in group})
        avg_sev = sum(e.severity for e in group) / len(group)

        summaries.append(
            ModeSummary(
                mode=mode,
                count=len(group),
                affected_sessions=affected,
                total_estimated_cost=FrictionCost(
                    wasted_steps=total_steps,
                    wasted_time_seconds=total_time if total_time > 0 else None,
                    wasted_tokens=total_tokens if total_tokens > 0 else None,
                ),
                avg_severity=round(avg_sev, 1),
            )
        )

    summaries.sort(key=lambda s: s.avg_severity, reverse=True)
    return summaries

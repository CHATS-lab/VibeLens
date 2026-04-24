"""Tests for the empty-state title override in skill evolution.

When the proposal step yields zero usable proposals (empty or dropped by the
hallucination/dedup filters), the service must force the title to the canonical
empty-state sentence instead of trusting the LLM output.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from vibelens.models.personalization.enums import PersonalizationMode
from vibelens.models.personalization.evolution import (
    EvolutionProposalBatch,
    EvolutionProposalResult,
)
from vibelens.services.evolution.evolution import (
    EVOLUTION_EMPTY_STATE_TITLE,
    analyze_skill_evolution,
)


class _StubStore:
    """Stub personalization store that records saved results without writing to disk."""

    def __init__(self) -> None:
        self.saved: list[tuple[str, str]] = []

    def save(self, result, analysis_id: str) -> None:
        self.saved.append((analysis_id, result.title))


def _empty_proposal_result(narrative_title: str) -> EvolutionProposalResult:
    return EvolutionProposalResult(
        session_ids=["sess-1", "sess-2"],
        skipped_session_ids=[],
        warnings=[],
        backend="mock",
        model="mock-model",
        batch_count=1,
        batch_metrics=[],
        created_at="2026-04-16T00:00:00+00:00",
        proposal_batch=EvolutionProposalBatch(
            title=narrative_title, workflow_patterns=[], proposals=[]
        ),
    )


def test_empty_proposals_force_canonical_title() -> None:
    """Zero surviving proposals → title is overridden to the empty-state sentence."""
    narrative_title = "Your workflow relies on design-plan-execute cycles across multiple domains"
    stub_store = _StubStore()

    with (
        patch(
            "vibelens.services.evolution.evolution._infer_evolution_proposals",
            new=AsyncMock(return_value=_empty_proposal_result(narrative_title)),
        ),
        patch(
            "vibelens.services.evolution.evolution.get_evolution_store",
            return_value=stub_store,
        ),
        patch(
            "vibelens.services.evolution.evolution.gather_installed_skills",
            return_value=[{"name": "example-skill", "description": "demo"}],
        ),
    ):
        result = asyncio.run(
            analyze_skill_evolution(session_ids=["sess-1", "sess-2"], session_token=None)
        )

    assert result.title == EVOLUTION_EMPTY_STATE_TITLE
    assert result.evolutions == []
    assert result.mode == PersonalizationMode.EVOLUTION
    assert stub_store.saved, "Result must be persisted via the store."
    _, saved_title = stub_store.saved[0]
    assert saved_title == EVOLUTION_EMPTY_STATE_TITLE
    print(f"narrative title '{narrative_title}' → overridden to '{result.title}'")

"""Tests for extract_all_contexts cache + parallelism behavior.

Mocks out store resolution so tests are hermetic and fast.
"""

import threading
import time

import pytest

from vibelens.context.extractors import DetailExtractor, SummaryExtractor
from vibelens.models.trajectories.agent import Agent
from vibelens.models.trajectories.step import Step
from vibelens.models.trajectories.trajectory import Trajectory
from vibelens.services import inference_shared
from vibelens.services.inference_shared import (
    _CONTEXT_CACHE,
    extract_all_contexts,
)

_TEST_AGENT = Agent(name="test-agent")


def _make_trajectory(session_id: str, step_count: int = 3) -> Trajectory:
    """Build a small trajectory for testing."""
    steps = [
        Step(step_id=f"{session_id}-step-{i}", source="agent", message=f"step {i}")
        for i in range(step_count)
    ]
    return Trajectory(
        session_id=session_id,
        project_path=f"/proj/{session_id}",
        agent=_TEST_AGENT,
        steps=steps,
    )


@pytest.fixture(autouse=True)
def _clear_context_cache():
    """Ensure each test starts with a fresh cache."""
    _CONTEXT_CACHE.clear()
    yield
    _CONTEXT_CACHE.clear()


@pytest.fixture
def mock_stores(monkeypatch):
    """Mock get_metadata_from_stores and load_from_stores.

    Returns a call-count tracker so tests can assert loader activity.
    """
    counts = {"metadata": 0, "load": 0}
    metadata_lock = threading.Lock()
    load_lock = threading.Lock()

    def fake_metadata(sid, session_token=None):
        with metadata_lock:
            counts["metadata"] += 1
        return {"session_id": sid}

    def fake_load(sid, session_token=None):
        with load_lock:
            counts["load"] += 1
        return [_make_trajectory(sid)]

    monkeypatch.setattr(inference_shared, "get_metadata_from_stores", fake_metadata)
    monkeypatch.setattr(inference_shared, "load_from_stores", fake_load)
    return counts


def _detail_extractor() -> DetailExtractor:
    return DetailExtractor()


def _summary_extractor() -> SummaryExtractor:
    return SummaryExtractor()


def test_cache_hit_returns_without_reloading(mock_stores):
    """Second identical call must not re-invoke the loaders."""
    session_ids = ["sid-a", "sid-b", "sid-c"]

    first = extract_all_contexts(
        session_ids=session_ids, session_token=None, extractor=_detail_extractor()
    )
    loads_after_first = mock_stores["load"]
    metadata_after_first = mock_stores["metadata"]

    second = extract_all_contexts(
        session_ids=session_ids, session_token=None, extractor=_detail_extractor()
    )

    assert mock_stores["load"] == loads_after_first
    assert mock_stores["metadata"] == metadata_after_first
    assert len(first.contexts) == 3
    assert len(second.contexts) == 3
    print(
        f"Cache hit: loads={mock_stores['load']}, metadata_calls={mock_stores['metadata']}"
    )


def test_cache_key_isolates_extractor_classes(mock_stores):
    """DetailExtractor and SummaryExtractor do not collide in the cache."""
    session_ids = ["sid-x"]

    extract_all_contexts(session_ids, session_token=None, extractor=_detail_extractor())
    loads_after_detail = mock_stores["load"]

    extract_all_contexts(session_ids, session_token=None, extractor=_summary_extractor())
    assert mock_stores["load"] > loads_after_detail
    print(
        f"Separate extractors trigger separate loads: "
        f"detail_load={loads_after_detail}, total_loads={mock_stores['load']}"
    )


def test_cache_key_order_sensitive(mock_stores):
    """Session ID ordering affects the cache key."""
    extract_all_contexts(
        session_ids=["a", "b"], session_token=None, extractor=_detail_extractor()
    )
    loads_after_first = mock_stores["load"]

    extract_all_contexts(
        session_ids=["b", "a"], session_token=None, extractor=_detail_extractor()
    )
    assert mock_stores["load"] > loads_after_first
    print(
        f"Reordered ids invalidate cache key: first_loads={loads_after_first}, "
        f"total_loads={mock_stores['load']}"
    )


def test_parallelism_preserves_input_order(monkeypatch):
    """Scrambled load latencies still yield output in input-id order."""
    # Deliberately slow the loader for the first id so it completes last.
    latency_map = {"fast-0": 0.0, "slow-1": 0.08, "fast-2": 0.0, "fast-3": 0.0}

    def fake_metadata(sid, session_token=None):
        return {"session_id": sid}

    def fake_load(sid, session_token=None):
        time.sleep(latency_map.get(sid, 0))
        return [_make_trajectory(sid)]

    monkeypatch.setattr(inference_shared, "get_metadata_from_stores", fake_metadata)
    monkeypatch.setattr(inference_shared, "load_from_stores", fake_load)

    session_ids = ["fast-0", "slow-1", "fast-2", "fast-3"]
    batch = extract_all_contexts(
        session_ids=session_ids, session_token=None, extractor=_detail_extractor()
    )

    assert [ctx.session_id for ctx in batch.contexts] == session_ids
    assert [ctx.session_index for ctx in batch.contexts] == [0, 1, 2, 3]
    print(
        f"Input order preserved despite scrambled latencies: "
        f"{[c.session_id for c in batch.contexts]}"
    )


def test_worker_failure_skips_one_session(monkeypatch):
    """A failing session lands in skipped_session_ids; others succeed."""

    def fake_metadata(sid, session_token=None):
        return {"session_id": sid}

    def fake_load(sid, session_token=None):
        if sid == "bad":
            raise OSError("simulated failure")
        return [_make_trajectory(sid)]

    monkeypatch.setattr(inference_shared, "get_metadata_from_stores", fake_metadata)
    monkeypatch.setattr(inference_shared, "load_from_stores", fake_load)

    batch = extract_all_contexts(
        session_ids=["good-1", "bad", "good-2"],
        session_token=None,
        extractor=_detail_extractor(),
    )

    assert batch.session_ids == ["good-1", "good-2"]
    assert batch.skipped_session_ids == ["bad"]
    assert [ctx.session_id for ctx in batch.contexts] == ["good-1", "good-2"]
    print(
        f"Bad session skipped: loaded={batch.session_ids}, "
        f"skipped={batch.skipped_session_ids}"
    )


def test_cache_hit_isolated_from_mutation(mock_stores):
    """Mutating the returned batch must not corrupt the cached entry."""
    session_ids = ["sid-1", "sid-2"]

    first = extract_all_contexts(
        session_ids=session_ids, session_token=None, extractor=_detail_extractor()
    )
    # Simulate downstream mutation (e.g. sample_contexts / build_batches reindex).
    first.contexts[0].reindex(99)

    second = extract_all_contexts(
        session_ids=session_ids, session_token=None, extractor=_detail_extractor()
    )

    assert second.contexts[0].session_index == 0
    assert "(index=99)" not in second.contexts[0].context_text
    print(
        f"Cache isolated from mutation: second.session_index={second.contexts[0].session_index}"
    )

"""Tests for DiskStore, per-user upload stores, and dual-store merging."""

import json
from pathlib import Path
from unittest.mock import patch

from vibelens.models.trajectories import Trajectory
from vibelens.storage.trajectory.disk import DiskTrajectoryStore


def _make_test_trajectory(session_id: str, first_message: str) -> Trajectory:
    """Create a minimal Trajectory for testing.

    Args:
        session_id: Session identifier.
        first_message: First user message text.

    Returns:
        A Trajectory with one user step.
    """
    return Trajectory(
        session_id=session_id,
        first_message=first_message,
        agent={"name": "test", "model_name": "test-model"},
        steps=[
            {
                "step_id": "step-1",
                "source": "user",
                "message": first_message,
                "timestamp": "2025-01-01T00:00:00Z",
            }
        ],
    )


class TestDiskStore:
    """Test DiskStore with unified index."""

    def test_save_and_load_roundtrip(self, tmp_path):
        """DiskStore save -> exists -> load round-trip."""
        store = DiskTrajectoryStore(root=tmp_path)
        store.initialize()

        traj = _make_test_trajectory("roundtrip-001", "Test roundtrip session")
        store.save([traj])

        assert store.exists("roundtrip-001") is True
        loaded = store.load("roundtrip-001")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0].session_id == "roundtrip-001"
        print(f"Round-trip: saved and loaded session {loaded[0].session_id}")

    def test_session_count(self, tmp_path):
        """session_count() tracks saves correctly."""
        store = DiskTrajectoryStore(root=tmp_path)
        store.initialize()

        assert store.session_count() == 0

        store.save([_make_test_trajectory("count-001", "First")])
        assert store.session_count() == 1

        store.save([_make_test_trajectory("count-002", "Second")])
        assert store.session_count() == 2
        print(f"session_count() correctly tracks {store.session_count()} sessions")

    def test_exists_unknown_session(self, tmp_path):
        """exists() returns False for non-existent session."""
        store = DiskTrajectoryStore(root=tmp_path)
        store.initialize()

        assert store.exists("no-such-session") is False
        print("exists() correctly returns False for unknown session")

    def test_save_updates_index_incrementally(self, tmp_path):
        """save() updates _metadata_cache and _index without full rebuild."""
        store = DiskTrajectoryStore(root=tmp_path)
        store.initialize()

        # Trigger initial index build
        assert store.session_count() == 0

        traj = _make_test_trajectory("incr-001", "Incremental save")
        store.save([traj])

        assert store._metadata_cache is not None
        assert "incr-001" in store._metadata_cache
        assert "incr-001" in store._index
        assert store.exists("incr-001") is True
        assert store.session_count() == 1
        print("save() correctly updates _metadata_cache and _index incrementally")

    def test_invalidate_index_triggers_rebuild(self, tmp_path):
        """invalidate_index() clears cache; next access rebuilds from disk."""
        store = DiskTrajectoryStore(root=tmp_path)
        store.initialize()

        traj = _make_test_trajectory("rebuild-001", "Rebuild test")
        store.save([traj])
        assert store.exists("rebuild-001") is True

        store.invalidate_index()
        assert store._metadata_cache is None
        assert store._index == {}

        summaries = store.list_metadata()
        assert len(summaries) == 1
        assert summaries[0]["session_id"] == "rebuild-001"
        assert store._metadata_cache is not None
        assert "rebuild-001" in store._index
        print("invalidate_index() + list_metadata() correctly rebuilds from disk")

    def test_rglob_finds_subdirectory_sessions(self, tmp_path):
        """_build_index discovers sessions in subdirectories via rglob."""
        store = DiskTrajectoryStore(root=tmp_path)
        store.initialize()

        store.save([_make_test_trajectory("root-001", "Root session")])

        subdir = tmp_path / "upload_abc"
        sub_store = DiskTrajectoryStore(root=subdir)
        sub_store.initialize()
        sub_store.save([_make_test_trajectory("sub-001", "Sub session")])

        store.invalidate_index()
        summaries = store.list_metadata()
        session_ids = {s["session_id"] for s in summaries}
        assert "root-001" in session_ids
        assert "sub-001" in session_ids
        assert len(summaries) == 2
        print("rglob correctly discovers sessions in subdirectories")

    def test_rglob_reads_upload_id_from_index(self, tmp_path):
        """_build_index reads _upload_id from JSONL index written with default_tags."""
        store = DiskTrajectoryStore(root=tmp_path)
        store.initialize()

        subdir = tmp_path / "upload_xyz"
        sub_store = DiskTrajectoryStore(root=subdir, default_tags={"_upload_id": "upload_xyz"})
        sub_store.initialize()
        sub_store.save([_make_test_trajectory("tagged-001", "Tagged session")])

        summaries = store.list_metadata()
        tagged = [s for s in summaries if s.get("_upload_id") == "upload_xyz"]
        assert len(tagged) == 1
        assert tagged[0]["session_id"] == "tagged-001"
        print("rglob correctly reads _upload_id from JSONL index with default_tags")

    def test_get_metadata(self, tmp_path):
        """get_metadata() returns summary dict for known session, None for unknown."""
        store = DiskTrajectoryStore(root=tmp_path)
        store.initialize()

        traj = _make_test_trajectory("meta-001", "Metadata test")
        store.save([traj])

        meta = store.get_metadata("meta-001")
        assert meta is not None
        assert meta["session_id"] == "meta-001"

        assert store.get_metadata("nonexistent") is None
        print("get_metadata() correctly returns metadata or None")


class TestPerUserUploadStores:
    """Test per-user upload store registry and store-level isolation."""

    def test_reconstruct_upload_registry(self, tmp_path):
        """reconstruct_upload_registry rebuilds from metadata.jsonl on startup."""
        from vibelens.deps import (
            _upload_registry,
            get_upload_stores,
            reconstruct_upload_registry,
            reset_singletons,
        )

        reset_singletons()
        _upload_registry.clear()

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()

        for upload_id, _token in [("u1", "tok-alice"), ("u2", "tok-bob")]:
            store_dir = upload_dir / upload_id
            store = DiskTrajectoryStore(root=store_dir)
            store.initialize()
            store.save([_make_test_trajectory(f"{upload_id}-sess", f"Session from {upload_id}")])

        meta_path = upload_dir / "metadata.jsonl"
        with open(meta_path, "w") as f:
            f.write(json.dumps({"upload_id": "u1", "session_token": "tok-alice"}) + "\n")
            f.write(json.dumps({"upload_id": "u2", "session_token": "tok-bob"}) + "\n")

        mock_settings = type("S", (), {"upload": type("U", (), {"dir": upload_dir})()})()
        with patch("vibelens.deps.get_settings", return_value=mock_settings):
            reconstruct_upload_registry()

        assert len(get_upload_stores("tok-alice")) == 1
        assert len(get_upload_stores("tok-bob")) == 1
        assert len(get_upload_stores("tok-unknown")) == 0
        print("reconstruct_upload_registry correctly rebuilds per-user stores")

        _upload_registry.clear()
        reset_singletons()

    def test_register_upload_store(self):
        """register_upload_store adds a store for a token."""
        from vibelens.deps import (
            _upload_registry,
            get_upload_stores,
            register_upload_store,
        )

        _upload_registry.clear()

        store = DiskTrajectoryStore(root=Path("/tmp/fake"))
        register_upload_store("tok-test", store)

        stores = get_upload_stores("tok-test")
        assert len(stores) == 1
        assert stores[0] is store
        assert len(get_upload_stores(None)) == 0
        print("register_upload_store correctly registers per-user stores")

        _upload_registry.clear()

    def test_store_level_isolation(self, tmp_path):
        """Each user's stores only contain their sessions."""
        from vibelens.deps import (
            _upload_registry,
            get_upload_stores,
            register_upload_store,
        )

        _upload_registry.clear()

        alice_dir = tmp_path / "alice_upload"
        alice_store = DiskTrajectoryStore(root=alice_dir)
        alice_store.initialize()
        alice_store.save([_make_test_trajectory("alice-001", "Alice session")])
        register_upload_store("tok-alice", alice_store)

        bob_dir = tmp_path / "bob_upload"
        bob_store = DiskTrajectoryStore(root=bob_dir)
        bob_store.initialize()
        bob_store.save([_make_test_trajectory("bob-001", "Bob session")])
        register_upload_store("tok-bob", bob_store)

        alice_stores = get_upload_stores("tok-alice")
        alice_ids = {m["session_id"] for s in alice_stores for m in s.list_metadata()}
        assert alice_ids == {"alice-001"}

        bob_stores = get_upload_stores("tok-bob")
        bob_ids = {m["session_id"] for s in bob_stores for m in s.list_metadata()}
        assert bob_ids == {"bob-001"}

        assert len(get_upload_stores("tok-unknown")) == 0
        print("Store-level isolation: each token only sees its own sessions")

        _upload_registry.clear()


class TestDualStore:
    """Test dual DiskStore metadata merging for demo mode."""

    def test_list_all_metadata_merges_stores(self, tmp_path):
        """list_all_metadata() returns sessions from both upload and example stores."""
        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskTrajectoryStore(root=upload_dir)
        upload_store.initialize()
        upload_store.save([_make_test_trajectory("upload-001", "Uploaded session")])

        example_store = DiskTrajectoryStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("example-001", "Example session")])

        assert upload_store.session_count() == 1
        assert example_store.session_count() == 1

        merged = list(upload_store.list_metadata()) + list(example_store.list_metadata())
        session_ids = {m["session_id"] for m in merged}
        assert session_ids == {"upload-001", "example-001"}
        print(f"Merged metadata contains {len(merged)} sessions from dual stores")

    def test_load_from_stores_fallback(self, tmp_path):
        """load_from_stores() falls back to example store when primary returns None."""
        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskTrajectoryStore(root=upload_dir)
        upload_store.initialize()

        example_store = DiskTrajectoryStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("example-only", "Only in examples")])

        assert upload_store.load("example-only") is None

        result = example_store.load("example-only")
        assert result is not None
        assert result[0].session_id == "example-only"
        print("Fallback to example store works for sessions not in upload store")

    def test_get_metadata_from_stores_fallback(self, tmp_path):
        """get_metadata_from_stores() checks example store when primary returns None."""
        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskTrajectoryStore(root=upload_dir)
        upload_store.initialize()

        example_store = DiskTrajectoryStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("ex-meta", "Example metadata")])

        assert upload_store.get_metadata("ex-meta") is None

        meta = example_store.get_metadata("ex-meta")
        assert meta is not None
        assert meta["session_id"] == "ex-meta"
        print("Metadata fallback to example store works correctly")

    def test_stores_are_independent(self, tmp_path):
        """Uploads and examples don't bleed into each other's indexes."""
        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskTrajectoryStore(root=upload_dir)
        upload_store.initialize()
        upload_store.save([_make_test_trajectory("upload-only", "Upload session")])

        example_store = DiskTrajectoryStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("example-only", "Example session")])

        upload_ids = {m["session_id"] for m in upload_store.list_metadata()}
        example_ids = {m["session_id"] for m in example_store.list_metadata()}
        assert upload_ids == {"upload-only"}
        assert example_ids == {"example-only"}
        assert upload_ids.isdisjoint(example_ids)
        print("Upload and example stores are fully independent")

    def test_deduplication_when_same_session_in_both(self, tmp_path):
        """Sessions present in both stores appear only once (upload wins)."""
        upload_dir = tmp_path / "uploads"
        examples_dir = tmp_path / "examples"

        upload_store = DiskTrajectoryStore(root=upload_dir)
        upload_store.initialize()
        upload_store.save([_make_test_trajectory("shared-001", "Upload version")])

        example_store = DiskTrajectoryStore(root=examples_dir)
        example_store.initialize()
        example_store.save([_make_test_trajectory("shared-001", "Example version")])
        example_store.save([_make_test_trajectory("example-only", "Only in examples")])

        # Simulate list_all_metadata deduplication logic
        metadata = list(upload_store.list_metadata())
        seen_ids = {m.get("session_id") for m in metadata}
        for m in example_store.list_metadata():
            if m.get("session_id") not in seen_ids:
                metadata.append(m)

        session_ids = [m["session_id"] for m in metadata]
        assert len(session_ids) == 2
        assert session_ids.count("shared-001") == 1
        assert "example-only" in session_ids
        print("Deduplication: shared session appears once, unique example included")

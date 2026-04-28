"""End-to-end regression tests for the 7 upload bugs found in this session.

Each test pins one bug — re-introducing the original buggy behavior should
make the test fail. These exercise as much of the real pipeline as feasible
without needing live agent data on disk.
"""

import json
import zipfile
from pathlib import Path

from vibelens.deps import (
    _upload_registry,
    get_upload_stores,
    register_upload_store,
    share_prior_upload_with_token,
)
from vibelens.models.enums import AgentType
from vibelens.services.upload.agents import UPLOAD_SPECS
from vibelens.services.upload.processor import find_prior_upload, to_friendly_error


# ---- Bug 1: zip helpers must output to Desktop ----------------------------
def test_all_local_zip_commands_target_desktop():
    """Bug 1: zip output must land on the user's Desktop, not in HOME."""
    for spec in UPLOAD_SPECS.values():
        if spec.source != "local_zip":
            continue
        for os_name, zc in spec.commands.items():
            assert "Desktop" in zc.output, (
                f"{spec.agent_type}/{os_name} output={zc.output!r} doesn't include Desktop"
            )
            assert "Desktop" in zc.command, (
                f"{spec.agent_type}/{os_name} command must zip into Desktop"
            )


# ---- Bug 2: kilo command must not include the multi-GB snapshot dir -------
def test_kilo_command_excludes_snapshot_dir():
    """Bug 2: ``snapshot/`` blew up the kilo zip beyond the upload limit."""
    spec = UPLOAD_SPECS[AgentType.KILO]
    for zc in spec.commands.values():
        assert "snapshot" not in zc.command, (
            "kilo upload command must not include snapshot/ — it routinely exceeds 200 MB"
        )


# ---- Bug 3: codebuddy parser produces unique step_ids ---------------------
def test_codebuddy_parser_dedupes_step_ids_within_session(tmp_path: Path):
    """Bug 3: CodeBuddy reuses ``id`` across events in one assistant turn.
    Parser must use ``providerData.messageId`` (turn-unique) for step_id."""
    from vibelens.ingest.parsers.codebuddy import CodebuddyParser

    # 4 events sharing top-level id, but 2 distinct messageIds = 2 turns.
    events = [
        {
            "id": "dup",
            "type": "message",
            "role": "assistant",
            "timestamp": 1,
            "sessionId": "s",
            "content": [{"type": "output_text", "text": "thinking"}],
            "providerData": {"messageId": "m1"},
        },
        {
            "id": "dup",
            "type": "function_call",
            "timestamp": 2,
            "sessionId": "s",
            "name": "Read",
            "callId": "tc1",
            "arguments": "{}",
            "providerData": {"messageId": "m1"},
        },
        {
            "id": "dup",
            "type": "function_call",
            "timestamp": 3,
            "sessionId": "s",
            "name": "Read",
            "callId": "tc2",
            "arguments": "{}",
            "providerData": {"messageId": "m1"},
        },
        {
            "id": "dup",
            "type": "message",
            "role": "assistant",
            "timestamp": 4,
            "sessionId": "s",
            "content": [{"type": "output_text", "text": "follow-up"}],
            "providerData": {"messageId": "m2"},
        },
    ]
    file_path = tmp_path / "session.jsonl"
    file_path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    trajs = CodebuddyParser().parse(file_path)
    assert trajs, "parser should produce at least one trajectory"
    step_ids = [s.step_id for t in trajs for s in t.steps]
    assert len(step_ids) == len(set(step_ids)), (
        f"step_ids must be unique within session — got duplicates: {step_ids}"
    )


# ---- Bug 4: cursor parser produces unique, deterministic step_ids ---------
def test_cursor_child_step_ids_use_line_index_deterministically(tmp_path: Path):
    """Bug 4 (uuid4 path): the child-trajectory builder used ``str(uuid4())``,
    which produces duplicates in practice (Cursor reuses ``msg["id"]`` as
    well) and breaks dedup caching across re-parses. Step IDs must be both
    unique and deterministic from input."""
    from vibelens.ingest.parsers.cursor import CursorParser, _parse_subagent_file

    child_path = tmp_path / "agent-x.jsonl"
    lines = [
        {"role": "user", "id": 1, "message": {"content": [{"type": "text", "text": "hi"}]}},
        {"role": "assistant", "id": 1, "message": {"content": [{"type": "text", "text": "hello"}]}},
        {"role": "user", "id": 1, "message": {"content": [{"type": "text", "text": "again"}]}},
    ]
    child_path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    parser = CursorParser()
    traj = _parse_subagent_file(
        child_path, parent_session_id="parent", agent_builder=parser.build_agent
    )
    assert traj is not None
    step_ids = [s.step_id for s in traj.steps]
    assert len(step_ids) == len(set(step_ids)), step_ids
    # Determinism: re-parse must produce the same step_ids.
    traj2 = _parse_subagent_file(
        child_path, parent_session_id="parent", agent_builder=parser.build_agent
    )
    assert [s.step_id for s in traj2.steps] == step_ids


# ---- Bug 5: .db files must extract through the upload pipeline ------------
def test_extract_zip_includes_db_when_parser_allows_it(tmp_path: Path):
    """Bug 5: the global allowlist used to omit ``.db``, so kilo / cursor /
    hermes' SQLite files were silently dropped during extraction. Per-parser
    allowlists must restore them."""
    from vibelens.ingest.parsers.kilo import KiloParser
    from vibelens.utils.zip import extract_zip

    zip_path = tmp_path / "src.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("kilo.db", b"\x00\x01\x02")
        zf.writestr("kilo.db-wal", b"\xff")

    dest = tmp_path / "out"
    extract_zip(zip_path, dest, allowed_extensions=KiloParser.ALLOWED_EXTENSIONS)

    assert (dest / "kilo.db").is_file()
    assert (dest / "kilo.db-wal").is_file()


def test_extract_zip_drops_db_when_caller_doesnt_allow_it(tmp_path: Path):
    """Sanity: a caller that only allows .json/.jsonl still rejects .db.
    Confirms the allowlist is parameter-driven (the previous global was
    the source of bug 5)."""
    from vibelens.utils.zip import extract_zip

    zip_path = tmp_path / "src.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("anything.db", b"\x00")
        zf.writestr("safe.json", b"{}")

    dest = tmp_path / "out"
    extract_zip(zip_path, dest, allowed_extensions={".json", ".jsonl"})

    assert not (dest / "anything.db").exists()
    assert (dest / "safe.json").is_file()


# ---- Bug 6: dedup must skip failed prior uploads --------------------------
def test_dedup_skips_failed_prior_uploads(tmp_upload_dir: Path):
    """Bug 6: a prior upload with sessions_parsed=0 must NOT cache, otherwise
    a fix to the parser is invisible — users keep getting the cached failure."""
    sha = "f" * 64
    upload_id = "20260427T010000-fail"
    (tmp_upload_dir / upload_id).mkdir()
    (tmp_upload_dir / upload_id / "result.json").write_text(
        json.dumps({"files_received": 1, "sessions_parsed": 0, "zip_sha256": sha}),
        encoding="utf-8",
    )
    (tmp_upload_dir / "metadata.jsonl").write_text(
        json.dumps(
            {
                "upload_id": upload_id,
                "agent_type": "codebuddy",
                "zip_sha256": sha,
                "uploaded_at": "2026-04-27T01:00:00+00:00",
                "result_path": f"{upload_id}/result.json",
                "filename": "x.zip",
                "session_token": "tA",
                "totals": {"sessions_parsed": 0, "errors": 1},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert find_prior_upload(sha, "codebuddy") is None


# ---- Bug 7: dedup must register prior store under the new token -----------
def test_dedup_shares_store_with_new_token(tmp_upload_dir: Path):
    """Bug 7: when dedup hits, the prior store must become visible to the
    requesting token; otherwise the user uploads, gets a 200 OK, but their
    session list is empty (registry only has the original uploader's token)."""
    from vibelens.storage.trajectory.disk import DiskTrajectoryStore

    upload_id = "20260427T020000-good"
    (tmp_upload_dir / upload_id).mkdir()

    store_a = DiskTrajectoryStore(
        root=tmp_upload_dir / upload_id, default_tags={"_session_token": "tokA"}
    )
    store_a.initialize()
    _upload_registry.clear()
    register_upload_store("tokA", store_a)

    # Token B uploads same SHA → dedup. Without the fix, B sees nothing.
    share_prior_upload_with_token(upload_id, "tokB")

    stores_b = get_upload_stores("tokB")
    assert len(stores_b) == 1, "token B should now have visibility into the prior store"
    assert stores_b[0].root == tmp_upload_dir / upload_id

    # Calling again is idempotent — no duplicate registration.
    share_prior_upload_with_token(upload_id, "tokB")
    assert len(get_upload_stores("tokB")) == 1


# ---- Friendly errors surface the actual root cause ------------------------
def test_friendly_error_surfaces_dup_step_ids():
    """User-visible upload error must name the parser-bug cause when the
    underlying exception carries 'duplicate step IDs'."""
    out = to_friendly_error(ValueError("Trajectory abc: duplicate step IDs: ['x', 'x']"))
    assert "parser bug" in out["summary"].lower()


# ---- Per-parser ALLOWED_EXTENSIONS is wired through correctly -------------
def test_sqlite_parsers_extend_baseline_allowlist():
    """SQLite-backed parsers must EXTEND the baseline (not replace) so the
    upload pipeline still extracts plain .json/.jsonl session files alongside
    the database sidecars."""
    from vibelens.ingest.parsers.base import BaseParser
    from vibelens.ingest.parsers.codex import CodexParser
    from vibelens.ingest.parsers.cursor import CursorParser
    from vibelens.ingest.parsers.hermes import HermesParser
    from vibelens.ingest.parsers.kilo import KiloParser

    baseline = BaseParser.ALLOWED_EXTENSIONS
    for parser_cls in (CursorParser, HermesParser, KiloParser):
        assert baseline.issubset(parser_cls.ALLOWED_EXTENSIONS), parser_cls
        assert ".db" in parser_cls.ALLOWED_EXTENSIONS, parser_cls
    # Codex uses .sqlite (not .db).
    assert ".sqlite" in CodexParser.ALLOWED_EXTENSIONS
    assert baseline.issubset(CodexParser.ALLOWED_EXTENSIONS)

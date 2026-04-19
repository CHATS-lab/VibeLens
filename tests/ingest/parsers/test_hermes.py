"""Unit tests for the HermesParser."""

import json
import sqlite3
from pathlib import Path

from vibelens.ingest.parsers.hermes import (
    HermesParser,
    _canonical_model_name,
    _derive_project_path,
    _parse_tool_arguments,
    _session_id_from_path,
)
from vibelens.models.enums import AgentType, StepSource

_parser = HermesParser()

_JSONL_SESSION_ID = "20260418_120000_abc123"
_SNAPSHOT_SESSION_ID = "20260418_130000_def456"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write JSONL records to a session file."""
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def _write_snapshot(path: Path, payload: dict) -> None:
    """Write a snapshot JSON file."""
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_state_db(
    db_path: Path,
    session_id: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    estimated_cost_usd: float | None = None,
    started_at: float = 100.0,
    ended_at: float = 160.0,
    parent_session_id: str | None = None,
    source: str = "slack",
) -> None:
    """Create a minimal state.db with one sessions row."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            started_at REAL NOT NULL,
            ended_at REAL,
            end_reason TEXT,
            title TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_write_tokens INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL,
            actual_cost_usd REAL,
            cost_status TEXT,
            cost_source TEXT,
            billing_provider TEXT,
            billing_base_url TEXT,
            parent_session_id TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sessions
            (id, source, started_at, ended_at, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens, estimated_cost_usd,
             parent_session_id, cost_status, billing_provider)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'estimated', 'openrouter')
        """,
        (
            session_id,
            source,
            started_at,
            ended_at,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_write_tokens,
            estimated_cost_usd,
            parent_session_id,
        ),
    )
    conn.commit()
    conn.close()


def _seed_index(sessions_dir: Path, session_id: str, user_name: str = "Xu Li") -> None:
    """Write a sessions.json index entry for the session."""
    index = {
        "agent:main:slack:dm:C123:1.0": {
            "session_key": "agent:main:slack:dm:C123:1.0",
            "session_id": session_id,
            "platform": "slack",
            "chat_type": "dm",
            "origin": {
                "platform": "slack",
                "chat_id": "C123",
                "chat_type": "dm",
                "user_name": user_name,
                "thread_id": "1.0",
            },
        }
    }
    (sessions_dir / "sessions.json").write_text(json.dumps(index), encoding="utf-8")


def test_session_id_from_path_accepts_jsonl_and_snapshot() -> None:
    """Session IDs are extracted from both filename shapes."""
    assert _session_id_from_path(Path(f"/x/{_JSONL_SESSION_ID}.jsonl")) == _JSONL_SESSION_ID
    assert (
        _session_id_from_path(Path(f"/x/session_{_JSONL_SESSION_ID}.json")) == _JSONL_SESSION_ID
    )
    assert _session_id_from_path(Path("/x/sessions.json")) is None
    assert _session_id_from_path(Path("/x/random.jsonl")) is None


def test_derive_project_path_by_platform_and_chat() -> None:
    """Project path URIs reflect the chat surface so the UI can group by origin."""
    # Slack with chat_id: chat-specific URI
    assert (
        _derive_project_path(
            "slack",
            {"origin": {"platform": "slack", "chat_id": "D0ATU26RX1Q"}},
            None,
        )
        == "slack://D0ATU26RX1Q"
    )
    # CLI with no chat_id: generic cli bucket
    assert _derive_project_path("cli", None, None) == "hermes://cli"
    # Other known platform with no chat_id: platform bucket
    assert _derive_project_path("telegram", None, None) == "hermes://telegram"
    # Fully unknown: fall back to local
    assert _derive_project_path(None, None, None) == "hermes://local"
    # Platform only available via db_row.source
    assert (
        _derive_project_path(None, None, {"source": "cli"}) == "hermes://cli"
    )


def test_canonical_model_name_uses_llm_normalizer() -> None:
    """Hermes hands model names to the shared llm.normalize_model_name.

    Known models canonicalise to the pricing-catalog key (dashed Anthropic
    versions, provider prefix stripped). Unknown models fall back to the
    raw string so they still surface in the UI.
    """
    # Dotted Anthropic names resolve via the shared normaliser
    assert _canonical_model_name("anthropic/claude-opus-4.7") == "claude-opus-4-7"
    assert _canonical_model_name("claude-opus-4.6") == "claude-opus-4-6"
    assert _canonical_model_name("claude-opus-4-7") == "claude-opus-4-7"
    # "glm-5.1" starts with the known prefix "glm-5" so it normalises
    assert _canonical_model_name("z-ai/glm-5.1") == "glm-5"
    # Totally unknown model -> fall back to raw (no silent data loss)
    assert _canonical_model_name("brand-new-model-v1") == "brand-new-model-v1"
    assert _canonical_model_name(None) is None
    assert _canonical_model_name("") == ""


def test_parse_tool_arguments_decodes_json_strings() -> None:
    """JSON-string arguments are parsed to dict; non-JSON stays as string."""
    assert _parse_tool_arguments('{"url": "x"}') == {"url": "x"}
    assert _parse_tool_arguments("not json") == "not json"
    assert _parse_tool_arguments({"k": 1}) == {"k": 1}
    assert _parse_tool_arguments(None) is None
    assert _parse_tool_arguments("") is None


def test_discover_dedupes_paired_files(tmp_path: Path) -> None:
    """When a jsonl and its snapshot both exist, only the jsonl is returned."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / f"{_JSONL_SESSION_ID}.jsonl").write_text("{}\n", encoding="utf-8")
    (sessions_dir / f"session_{_JSONL_SESSION_ID}.json").write_text("{}", encoding="utf-8")
    (sessions_dir / f"session_{_SNAPSHOT_SESSION_ID}.json").write_text("{}", encoding="utf-8")
    (sessions_dir / "sessions.json").write_text("{}", encoding="utf-8")

    discovered = _parser.discover_session_files(tmp_path)
    names = sorted(p.name for p in discovered)
    print("discovered files:", names)

    assert names == sorted(
        [
            f"session_{_SNAPSHOT_SESSION_ID}.json",
            f"{_JSONL_SESSION_ID}.jsonl",
        ]
    )


def test_discover_drops_stale_snapshots_without_db_row(tmp_path: Path) -> None:
    """Snapshot-only files with no state.db row are treated as stale and dropped.

    Hermes rewrites ``session_<id>.json`` with a new session_id during
    interrupt recovery; the stale copy stays on disk but is never
    registered in state.db. We filter those out so the dashboard doesn't
    double-count tokens.
    """
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    # Three snapshot-only candidates
    (sessions_dir / "session_20260418_111111_aaaaaa.json").write_text("{}", encoding="utf-8")
    (sessions_dir / "session_20260418_222222_bbbbbb.json").write_text("{}", encoding="utf-8")
    (sessions_dir / "session_20260418_333333_cccccc.json").write_text("{}", encoding="utf-8")

    # state.db contains only the first two — the third is stale
    _seed_state_db(tmp_path / "state.db", "20260418_111111_aaaaaa")
    # Append a second row manually
    import sqlite3

    conn = sqlite3.connect(tmp_path / "state.db")
    conn.execute(
        "INSERT INTO sessions (id, source, started_at) VALUES (?, 'cli', 0.0)",
        ("20260418_222222_bbbbbb",),
    )
    conn.commit()
    conn.close()

    discovered = _parser.discover_session_files(tmp_path)
    names = sorted(p.name for p in discovered)
    print("kept:", names)

    assert names == sorted(
        [
            "session_20260418_111111_aaaaaa.json",
            "session_20260418_222222_bbbbbb.json",
        ]
    )


def test_discover_keeps_snapshots_when_state_db_missing(tmp_path: Path) -> None:
    """Without state.db (e.g. extracted archive), all snapshots are kept.

    We only filter stale snapshots when we have authoritative knowledge
    of which sessions are real. Missing db => be conservative.
    """
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "session_20260418_111111_aaaaaa.json").write_text("{}", encoding="utf-8")
    (sessions_dir / "session_20260418_222222_bbbbbb.json").write_text("{}", encoding="utf-8")

    discovered = _parser.discover_session_files(tmp_path)
    assert len(discovered) == 2


def test_parse_jsonl_with_tools_and_enrichment(tmp_path: Path) -> None:
    """A full jsonl session is parsed with per-turn metadata and state.db enrichment."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    records = [
        {
            "role": "session_meta",
            "timestamp": "2026-04-18T12:00:00.000000",
            "model": "anthropic/claude-opus-4.7",
            "platform": "slack",
            "tools": [{"type": "function", "function": {"name": "browser_navigate"}}],
        },
        {
            "role": "user",
            "content": "hi",
            "timestamp": "2026-04-18T12:00:01.000000",
        },
        {
            "role": "assistant",
            "content": "",
            "reasoning": "planning",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "browser_navigate",
                        "arguments": '{"url": "https://x"}',
                    },
                    "response_item_id": "fc-call-1",
                }
            ],
            "timestamp": "2026-04-18T12:00:02.000000",
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": '{"ok": true}',
            "timestamp": "2026-04-18T12:00:03.000000",
        },
        {
            "role": "assistant",
            "content": "done",
            "finish_reason": "stop",
            "timestamp": "2026-04-18T12:00:04.000000",
        },
    ]
    _write_jsonl(sessions_dir / f"{_JSONL_SESSION_ID}.jsonl", records)
    _write_snapshot(
        sessions_dir / f"session_{_JSONL_SESSION_ID}.json",
        {
            "session_id": _JSONL_SESSION_ID,
            "model": "anthropic/claude-opus-4.7",
            "base_url": "https://openrouter.ai/api/v1",
            "platform": "slack",
            "session_start": "2026-04-18T12:00:00.000000",
            "last_updated": "2026-04-18T12:00:04.000000",
            "system_prompt": "be helpful",
            "tools": [{"type": "function", "function": {"name": "browser_navigate"}}],
            "message_count": 4,
            "messages": [],
        },
    )
    _seed_state_db(
        tmp_path / "state.db",
        _JSONL_SESSION_ID,
        input_tokens=1000,
        output_tokens=200,
        cache_read_tokens=500,
        cache_write_tokens=100,
        estimated_cost_usd=0.15,
    )
    _seed_index(sessions_dir, _JSONL_SESSION_ID)

    jsonl_path = sessions_dir / f"{_JSONL_SESSION_ID}.jsonl"
    trajectories = _parser.parse_file(jsonl_path)
    print("parsed:", len(trajectories))
    assert len(trajectories) == 1
    traj = trajectories[0]

    print("session_id:", traj.session_id)
    print("agent:", traj.agent.model_dump())
    print("extra:", traj.extra)
    print("final_metrics:", traj.final_metrics.model_dump())

    assert traj.session_id == _JSONL_SESSION_ID
    assert traj.agent.name == AgentType.HERMES.value
    assert traj.agent.model_name == "claude-opus-4-7"
    assert traj.agent.tool_definitions is not None
    assert len(traj.steps) == 3
    assert traj.steps[0].source == StepSource.USER
    assert traj.steps[0].message == "hi"
    assert traj.steps[1].source == StepSource.AGENT
    assert traj.steps[1].reasoning_content == "planning"
    assert traj.steps[1].extra == {"finish_reason": "tool_calls"}
    assert len(traj.steps[1].tool_calls) == 1
    assert traj.steps[1].tool_calls[0].arguments == {"url": "https://x"}
    assert traj.steps[1].tool_calls[0].extra == {"response_item_id": "fc-call-1"}
    assert traj.steps[1].observation is not None
    assert traj.steps[1].observation.results[0].content == '{"ok": true}'
    assert traj.first_message == "hi"
    assert traj.extra["platform"] == "slack"
    assert traj.extra["base_url"] == "https://openrouter.ai/api/v1"
    assert traj.extra["chat_type"] == "dm"
    assert traj.extra["user_name"] == "Xu Li"
    assert traj.extra["billing_provider"] == "openrouter"
    assert traj.project_path == "slack://C123"
    fm = traj.final_metrics
    assert fm.total_prompt_tokens == 1000
    assert fm.total_completion_tokens == 200
    assert fm.total_cache_read == 500
    assert fm.total_cache_write == 100
    assert fm.total_cost_usd == 0.15
    assert fm.duration == 60
    assert fm.tool_call_count == 1


def test_db_totals_attached_to_last_assistant_step(tmp_path: Path) -> None:
    """Session-level db totals surface on the last assistant Step.metrics.

    The dashboard aggregator sums per-step metrics rather than reading
    trajectory.final_metrics, so we attach the session totals once to
    the last assistant step. Earlier steps keep metrics=None.
    """
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    records = [
        {
            "role": "session_meta",
            "timestamp": "2026-04-18T12:00:00",
            "model": "anthropic/claude-opus-4.7",
            "platform": "slack",
            "tools": [],
        },
        {"role": "user", "content": "hi", "timestamp": "2026-04-18T12:00:01"},
        {"role": "assistant", "content": "first", "timestamp": "2026-04-18T12:00:02"},
        {"role": "user", "content": "more", "timestamp": "2026-04-18T12:00:03"},
        {"role": "assistant", "content": "second", "timestamp": "2026-04-18T12:00:04"},
    ]
    _write_jsonl(sessions_dir / f"{_JSONL_SESSION_ID}.jsonl", records)
    _seed_state_db(
        tmp_path / "state.db",
        _JSONL_SESSION_ID,
        input_tokens=1000,
        output_tokens=200,
        cache_read_tokens=400,
        cache_write_tokens=50,
        estimated_cost_usd=0.25,
    )

    trajectories = _parser.parse_file(sessions_dir / f"{_JSONL_SESSION_ID}.jsonl")
    traj = trajectories[0]
    assistant_steps = [s for s in traj.steps if s.source == StepSource.AGENT]
    print("assistant steps:", len(assistant_steps))
    for s in assistant_steps:
        print("  metrics:", s.metrics.model_dump() if s.metrics else None)

    assert len(assistant_steps) == 2
    assert assistant_steps[0].metrics is None
    last_metrics = assistant_steps[1].metrics
    assert last_metrics is not None
    # prompt_tokens follows the VibeLens convention of input + cached
    assert last_metrics.prompt_tokens == 1400
    assert last_metrics.completion_tokens == 200
    assert last_metrics.cached_tokens == 400
    assert last_metrics.cache_creation_tokens == 50
    # Model name propagates for pricing lookup
    assert assistant_steps[1].model_name == "claude-opus-4-7"


def test_parse_snapshot_only_without_db(tmp_path: Path) -> None:
    """A snapshot-only session parses with coarse timestamps and no token totals."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    _write_snapshot(
        sessions_dir / f"session_{_SNAPSHOT_SESSION_ID}.json",
        {
            "session_id": _SNAPSHOT_SESSION_ID,
            "model": "anthropic/claude-opus-4.7",
            "base_url": "https://openrouter.ai/api/v1",
            "platform": "cli",
            "session_start": "2026-04-18T13:00:00.000000",
            "last_updated": "2026-04-18T13:00:10.000000",
            "system_prompt": "...",
            "tools": [],
            "message_count": 2,
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello", "finish_reason": "stop"},
            ],
        },
    )

    snapshot_path = sessions_dir / f"session_{_SNAPSHOT_SESSION_ID}.json"
    trajectories = _parser.parse_file(snapshot_path)
    assert len(trajectories) == 1
    traj = trajectories[0]
    print("extra:", traj.extra)
    print("final_metrics:", traj.final_metrics.model_dump())

    assert traj.extra["platform"] == "cli"
    assert traj.extra["base_url"] == "https://openrouter.ai/api/v1"
    assert traj.project_path == "hermes://cli"
    # No db row → token totals stay None
    assert traj.final_metrics.total_prompt_tokens is None
    assert traj.final_metrics.total_completion_tokens is None
    assert traj.final_metrics.total_cost_usd is None
    assert len(traj.steps) == 2
    # Both steps share session_start as fallback timestamp
    assert traj.steps[0].timestamp == traj.steps[1].timestamp


def test_parent_trajectory_ref_from_db(tmp_path: Path) -> None:
    """parent_session_id in state.db surfaces as parent_trajectory_ref."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    records = [
        {
            "role": "session_meta",
            "timestamp": "2026-04-18T12:00:00",
            "model": "m",
            "platform": "slack",
            "tools": [],
        },
        {"role": "user", "content": "hi", "timestamp": "2026-04-18T12:00:01"},
        {"role": "assistant", "content": "ok", "timestamp": "2026-04-18T12:00:02"},
    ]
    _write_jsonl(sessions_dir / f"{_JSONL_SESSION_ID}.jsonl", records)
    _seed_state_db(
        tmp_path / "state.db",
        _JSONL_SESSION_ID,
        parent_session_id="parent-xyz",
    )

    trajectories = _parser.parse_file(sessions_dir / f"{_JSONL_SESSION_ID}.jsonl")
    assert len(trajectories) == 1
    traj = trajectories[0]
    print("parent_ref:", traj.parent_trajectory_ref)
    assert traj.parent_trajectory_ref is not None
    assert traj.parent_trajectory_ref.session_id == "parent-xyz"


def test_error_tool_result_passthrough(tmp_path: Path) -> None:
    """Hermes lacks structured error signals; tool errors pass through as plain content."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    records = [
        {
            "role": "session_meta",
            "timestamp": "2026-04-18T12:00:00",
            "model": "m",
            "platform": "slack",
            "tools": [],
        },
        {"role": "user", "content": "go", "timestamp": "2026-04-18T12:00:01"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-err",
                    "type": "function",
                    "function": {"name": "browser_navigate", "arguments": "{}"},
                }
            ],
            "timestamp": "2026-04-18T12:00:02",
        },
        {
            "role": "tool",
            "tool_call_id": "call-err",
            "content": '{"success": false, "error": "Chrome not found"}',
            "timestamp": "2026-04-18T12:00:03",
        },
    ]
    _write_jsonl(sessions_dir / f"{_JSONL_SESSION_ID}.jsonl", records)

    trajectories = _parser.parse_file(sessions_dir / f"{_JSONL_SESSION_ID}.jsonl")
    traj = trajectories[0]
    obs_content = traj.steps[1].observation.results[0].content
    print("obs content:", obs_content)
    assert not obs_content.startswith("[ERROR] ")
    assert "Chrome not found" in obs_content

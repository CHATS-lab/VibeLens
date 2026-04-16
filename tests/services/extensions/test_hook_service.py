"""Tests for HookService — orchestrator for hook management via settings.json."""

import json

import pytest

from vibelens.models.enums import AgentType
from vibelens.services.extensions.hook_service import (
    VIBELENS_MARKER_KEY,
    HookService,
    HookSyncTarget,
)
from vibelens.storage.extension.hook_store import HookStore

SAMPLE_CONFIG = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "/bin/echo sample"}],
        }
    ]
}
UPDATED_CONFIG = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "/bin/echo updated"}],
        }
    ]
}


@pytest.fixture
def central(tmp_path):
    return HookStore(root=tmp_path / "central", create=True)


@pytest.fixture
def claude_settings(tmp_path):
    return tmp_path / "claude" / "settings.json"


@pytest.fixture
def codex_settings(tmp_path):
    return tmp_path / "codex" / "settings.json"


@pytest.fixture
def service(central, claude_settings, codex_settings):
    return HookService(
        central=central,
        agent_settings={AgentType.CLAUDE: claude_settings, AgentType.CODEX: codex_settings},
    )


def _read_settings(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestInstall:
    def test_install_creates_hook(self, service):
        hook = service.install(
            name="my-hook", description="desc", tags=["a"], hook_config=SAMPLE_CONFIG
        )
        assert hook.name == "my-hook"
        assert hook.description == "desc"
        assert hook.hook_config == SAMPLE_CONFIG
        assert hook.installed_in == []

    def test_install_with_sync(self, service, claude_settings):
        hook = service.install(
            name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG, sync_to=["claude"]
        )
        assert "claude" in hook.installed_in
        assert claude_settings.exists()

    def test_install_duplicate_raises(self, service):
        service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        with pytest.raises(FileExistsError):
            service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)

    def test_install_invalid_name_raises(self, service):
        with pytest.raises(ValueError, match="kebab-case"):
            service.install(name="Not Valid", description="", tags=[], hook_config=SAMPLE_CONFIG)


class TestSync:
    def test_sync_adds_marker(self, service, claude_settings):
        """CRITICAL: After sync, agent's settings.json has the _vibelens_managed marker."""
        service.install(name="safety-guard", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.sync_to_agents("safety-guard", ["claude"])

        data = _read_settings(claude_settings)
        print(f"settings after sync: {json.dumps(data, indent=2)}")
        groups = data["hooks"]["PreToolUse"]
        assert len(groups) == 1
        assert groups[0][VIBELENS_MARKER_KEY] == "safety-guard"
        assert groups[0]["matcher"] == "Bash"

    def test_sync_idempotent(self, service, claude_settings):
        """CRITICAL: Calling sync twice does not duplicate entries."""
        service.install(name="safety-guard", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.sync_to_agents("safety-guard", ["claude"])
        service.sync_to_agents("safety-guard", ["claude"])

        data = _read_settings(claude_settings)
        groups = data["hooks"]["PreToolUse"]
        managed = [g for g in groups if g.get(VIBELENS_MARKER_KEY) == "safety-guard"]
        print(f"managed groups after double-sync: {len(managed)}")
        assert len(managed) == 1

    def test_sync_unknown_agent_returns_false(self, service):
        service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        results = service.sync_to_agents("my-hook", ["unknown"])
        assert results["unknown"] is False

    def test_sync_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.sync_to_agents("nonexistent", ["claude"])

    def test_sync_preserves_unmanaged_entries(self, service, claude_settings):
        """Manually-added hooks in settings.json (without marker) are preserved on sync."""
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "ReadFile", "hooks": [{"type": "command", "command": "x"}]}
                ]
            }
        }
        claude_settings.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        service.install(name="safety-guard", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.sync_to_agents("safety-guard", ["claude"])

        data = _read_settings(claude_settings)
        groups = data["hooks"]["PreToolUse"]
        assert any(g["matcher"] == "ReadFile" for g in groups)
        assert any(g.get(VIBELENS_MARKER_KEY) == "safety-guard" for g in groups)


class TestUnsync:
    def test_unsync_removes_only_matching(self, service, claude_settings):
        """CRITICAL: Two hooks synced; unsyncing one leaves the other."""
        service.install(name="hook-a", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.install(name="hook-b", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.sync_to_agents("hook-a", ["claude"])
        service.sync_to_agents("hook-b", ["claude"])

        service.uninstall_from_agent("hook-a", "claude")

        data = _read_settings(claude_settings)
        groups = data["hooks"]["PreToolUse"]
        markers = [g.get(VIBELENS_MARKER_KEY) for g in groups]
        print(f"remaining markers: {markers}")
        assert "hook-b" in markers
        assert "hook-a" not in markers

    def test_unsync_preserves_unmanaged_entries(self, service, claude_settings):
        """CRITICAL: Manually-added hooks (no marker) are NOT removed by unsync."""
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "ReadFile", "hooks": [{"type": "command", "command": "x"}]}
                ]
            }
        }
        claude_settings.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        service.install(name="managed-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.sync_to_agents("managed-hook", ["claude"])
        service.uninstall_from_agent("managed-hook", "claude")

        data = _read_settings(claude_settings)
        groups = data["hooks"]["PreToolUse"]
        print(f"after unsync remaining groups: {groups}")
        assert any(g["matcher"] == "ReadFile" for g in groups)
        assert not any(g.get(VIBELENS_MARKER_KEY) == "managed-hook" for g in groups)

    def test_unsync_not_found_raises(self, service):
        service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        with pytest.raises(FileNotFoundError):
            service.uninstall_from_agent("my-hook", "claude")

    def test_unsync_unknown_agent_raises(self, service):
        service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        with pytest.raises(KeyError):
            service.uninstall_from_agent("my-hook", "unknown")


class TestUninstall:
    def test_uninstall_removes_from_central_and_agents(self, service, claude_settings):
        service.install(
            name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG, sync_to=["claude"]
        )
        removed = service.uninstall("my-hook")
        assert "claude" in removed
        assert not service._central.exists("my-hook")
        data = _read_settings(claude_settings)
        assert "hooks" not in data or "my-hook" not in json.dumps(data)

    def test_uninstall_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.uninstall("nonexistent")


class TestModify:
    def test_modify_updates_fields(self, service):
        service.install(name="my-hook", description="old", tags=[], hook_config=SAMPLE_CONFIG)
        updated = service.modify("my-hook", description="new")
        assert updated.description == "new"
        assert updated.hook_config == SAMPLE_CONFIG

    def test_modify_auto_syncs(self, service, claude_settings):
        """CRITICAL: If installed in an agent, modify updates agent's settings.json."""
        service.install(
            name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG, sync_to=["claude"]
        )
        service.modify("my-hook", hook_config=UPDATED_CONFIG)

        data = _read_settings(claude_settings)
        groups = data["hooks"]["PreToolUse"]
        managed = [g for g in groups if g.get(VIBELENS_MARKER_KEY) == "my-hook"]
        print(f"after modify: {managed}")
        assert len(managed) == 1
        assert managed[0]["hooks"][0]["command"] == "/bin/echo updated"

    def test_modify_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.modify("nonexistent", description="x")


class TestQuery:
    def test_find_installed_agents_scans_settings(self, service):
        """CRITICAL: returns agents with any matching marker in settings.json."""
        service.install(
            name="my-hook",
            description="",
            tags=[],
            hook_config=SAMPLE_CONFIG,
            sync_to=["claude", "codex"],
        )
        installed = service.find_installed_agents("my-hook")
        print(f"installed in: {installed}")
        assert sorted(str(a) for a in installed) == ["claude", "codex"]

    def test_list_hooks(self, service):
        service.install(name="alpha", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.install(name="beta", description="", tags=[], hook_config=SAMPLE_CONFIG)
        hooks, total = service.list_hooks()
        assert total == 2
        assert {h.name for h in hooks} == {"alpha", "beta"}

    def test_list_hooks_search(self, service):
        service.install(name="alpha", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.install(name="beta", description="", tags=[], hook_config=SAMPLE_CONFIG)
        hooks, total = service.list_hooks(search="alpha")
        assert total == 1
        assert hooks[0].name == "alpha"

    def test_get_hook(self, service):
        service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        hook = service.get_hook("my-hook")
        assert hook.name == "my-hook"

    def test_get_hook_not_found(self, service):
        with pytest.raises(FileNotFoundError):
            service.get_hook("nonexistent")

    def test_get_hook_content(self, service):
        service.install(name="my-hook", description="sample", tags=[], hook_config=SAMPLE_CONFIG)
        content = service.get_hook_content("my-hook")
        assert "sample" in content

    def test_list_sync_targets(self, service):
        targets = service.list_sync_targets()
        assert len(targets) == 2
        assert all(isinstance(t, HookSyncTarget) for t in targets)


class TestImportFromAgent:
    def test_import_from_agent(self, service, claude_settings):
        """CRITICAL: Extracts a hook group from settings.json into central."""
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "/bin/echo"}],
                    }
                ]
            }
        }
        claude_settings.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        hook = service.import_from_agent(
            agent="claude", name="imported-hook", event_name="PreToolUse", matcher="Bash"
        )
        print(f"imported hook: {hook.model_dump()}")
        assert hook.name == "imported-hook"
        assert "PreToolUse" in hook.hook_config
        imported_group = hook.hook_config["PreToolUse"][0]
        assert imported_group["matcher"] == "Bash"
        assert VIBELENS_MARKER_KEY not in imported_group
        assert service._central.exists("imported-hook")

    def test_import_missing_group_raises(self, service, claude_settings):
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        claude_settings.write_text("{}", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            service.import_from_agent(
                agent="claude", name="missing", event_name="PreToolUse", matcher="Bash"
            )

    def test_import_unknown_agent_raises(self, service):
        with pytest.raises(KeyError):
            service.import_from_agent(
                agent="unknown", name="x", event_name="PreToolUse", matcher="Bash"
            )

    def test_import_duplicate_name_raises(self, service, claude_settings):
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "/bin/echo"}],
                    }
                ]
            }
        }
        claude_settings.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        service.install(name="existing", description="", tags=[], hook_config=SAMPLE_CONFIG)
        with pytest.raises(FileExistsError):
            service.import_from_agent(
                agent="claude",
                name="existing",
                event_name="PreToolUse",
                matcher="Bash",
            )


class TestCache:
    def test_invalidate_clears_cache(self, service):
        service.install(name="my-hook", description="", tags=[], hook_config=SAMPLE_CONFIG)
        service.list_hooks()
        service.invalidate()
        assert service._cache is None

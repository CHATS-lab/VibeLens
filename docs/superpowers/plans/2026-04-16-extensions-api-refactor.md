# Extensions API Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant extensions forwarding layer; reorganize into a read-only catalog API + type-specific CRUD APIs under `/api/extensions/`; extract `BaseExtensionService[T]`; unify schemas, frontend API client, and components.

**Architecture:** Backend splits into `api/extensions/{catalog,skill,command,hook,subagent}.py` routers and a `BaseExtensionService[T]` in `services/extensions/base_service.py`. Schemas are unified (one set for skill/command/subagent, hook keeps its own). Frontend gets a single `api/extensions.ts` client factory consumed via React context. Existing storage layer is unchanged.

**Tech Stack:** Python/FastAPI, Pydantic, React/TypeScript

---

## Refinements Applied

| Area | Before | After |
|------|--------|-------|
| Route factory | 12-param factory function | No factory; 3 standalone routers (~60 lines each) |
| Service subclasses | Alias methods (`list_skills` → `list_items`) | No aliases; callers use `list_items()` / `get_item()` directly |
| Sync targets | 4 dataclasses + 4 schema responses | 1 `SyncTarget` dataclass + 1 `SyncTargetResponse` schema |
| Schemas | 4 near-identical schema files | 1 unified `schemas/extensions.py` + hook-specific in `schemas/hooks.py` |
| Subclasses | Empty shells with alias methods | Empty shells, no aliases (preserved for future specialization) |
| Frontend TypeApi | `Promise<any>` returns | Generic `TypeApi<T>` with typed returns |

---

## File Map

### Backend: New Files
- `src/vibelens/api/extensions/__init__.py` — router aggregator
- `src/vibelens/api/extensions/catalog.py` — read-only catalog + install
- `src/vibelens/api/extensions/skill.py` — skill CRUD (~60 lines)
- `src/vibelens/api/extensions/command.py` — command CRUD (~60 lines)
- `src/vibelens/api/extensions/hook.py` — hook CRUD (hand-written, structural differences)
- `src/vibelens/api/extensions/subagent.py` — subagent CRUD (~60 lines)
- `src/vibelens/services/extensions/base_service.py` — `BaseExtensionService[T]`
- `src/vibelens/services/extensions/catalog_resolver.py` — refactored from `catalog_install.py`

### Backend: Modified Files
- `src/vibelens/api/__init__.py` — remove 5 old routers, add 1 extensions router
- `src/vibelens/schemas/extensions.py` — expand with unified CRUD schemas
- `src/vibelens/schemas/hooks.py` — keep hook-specific schemas, remove redundant ones
- `src/vibelens/services/extensions/catalog.py` — remove install re-export
- `src/vibelens/services/extensions/skill_service.py` — inherit BaseExtensionService, no aliases
- `src/vibelens/services/extensions/command_service.py` — inherit BaseExtensionService, no aliases
- `src/vibelens/services/extensions/hook_service.py` — inherit BaseExtensionService, override sync
- `src/vibelens/services/extensions/subagent_service.py` — inherit BaseExtensionService, no aliases
- `src/vibelens/deps.py` — update imports, string agent keys

### Backend: Deleted Files
- `src/vibelens/api/extensions.py`
- `src/vibelens/api/skill.py`
- `src/vibelens/api/command.py`
- `src/vibelens/api/hook.py`
- `src/vibelens/api/subagent.py`
- `src/vibelens/services/extensions/catalog_install.py`
- `src/vibelens/schemas/skills.py`
- `src/vibelens/schemas/commands.py`
- `src/vibelens/schemas/subagents.py`

### Frontend: New Files
- `frontend/src/api/extensions.ts` — unified API client factory

### Frontend: Modified Files
- `frontend/src/app.tsx` — create and provide extensions client via context
- `frontend/src/types.ts` — add `ExtensionsClient` type, `SyncTarget`
- `frontend/src/components/personalization/extensions/extension-explore-tab.tsx`
- `frontend/src/components/personalization/extensions/extension-card.tsx`
- `frontend/src/components/personalization/extensions/extension-detail-view.tsx`
- `frontend/src/components/personalization/local-extensions-tab.tsx`
- `frontend/src/components/personalization/recommendations-view.tsx`
- `frontend/src/components/personalization/personalization-panel.tsx`
- `frontend/src/components/personalization/install-target-dialog.tsx`

### Frontend: Deleted Files
- `frontend/src/components/personalization/cards.tsx`
- `frontend/src/components/personalization/extensions/extension-endpoints.ts`
- `frontend/src/components/personalization/extensions/use-sync-targets.ts`

### Test Files: Modified
- `tests/api/test_skill_api.py` — update imports, URL paths, schema types
- `tests/api/test_command_api.py` — same
- `tests/api/test_hook_api.py` — update imports, URL paths
- `tests/api/test_subagent_api.py` — same as skill
- `tests/api/test_extension_api.py` — update imports, URL paths
- `tests/api/test_catalog_api.py` — update imports, URL paths
- `tests/services/extensions/test_skill_service.py` — string agent keys
- `tests/services/extensions/test_command_service.py` — string agent keys
- `tests/services/extensions/test_hook_service.py` — string agent keys
- `tests/services/extensions/test_subagent_service.py` — string agent keys
- `tests/services/extensions/test_catalog_install.py` → rename to `test_catalog_resolver.py`
- `tests/services/extensions/test_catalog_install_service_dispatch.py` — update imports

### Test Files: New
- `tests/services/extensions/test_base_service.py`

---

## Task 1: Unify schemas

**Files:**
- Modify: `src/vibelens/schemas/extensions.py`
- Modify: `src/vibelens/schemas/hooks.py`
- Delete: `src/vibelens/schemas/skills.py`
- Delete: `src/vibelens/schemas/commands.py`
- Delete: `src/vibelens/schemas/subagents.py`

- [ ] **Step 1: Read current schema files to confirm what can be unified**

Read `src/vibelens/schemas/skills.py`, `src/vibelens/schemas/commands.py`, `src/vibelens/schemas/subagents.py`, `src/vibelens/schemas/hooks.py`, `src/vibelens/schemas/extensions.py`.

Confirm:
- `SkillInstallRequest`, `CommandInstallRequest`, `SubagentInstallRequest` have identical fields: `name: str`, `content: str`, `sync_to: list[str]`
- `SkillModifyRequest`, `CommandModifyRequest`, `SubagentModifyRequest` all have: `content: str`
- `SkillSyncRequest`, `CommandSyncRequest`, `SubagentSyncRequest` all have: `agents: list[str]`
- `*SyncTargetResponse` differ only in field names (`skill_count`/`skills_dir` vs `command_count`/`commands_dir`)

- [ ] **Step 2: Expand `schemas/extensions.py` with unified CRUD schemas**

Add these to the existing `src/vibelens/schemas/extensions.py` (which already has catalog schemas):

```python
from vibelens.models.extension.command import Command
from vibelens.models.extension.skill import Skill
from vibelens.models.extension.subagent import Subagent


class SyncTargetResponse(BaseModel):
    """Unified sync target for all extension types."""

    agent: str = Field(description="Agent identifier (e.g. 'claude').")
    count: int = Field(description="Number of extensions of this type in agent.")
    dir: str = Field(description="Agent directory or settings path.")


class ExtensionInstallRequest(BaseModel):
    """Install a new file-based extension (skill, command, subagent)."""

    name: str = Field(description="Kebab-case extension name.")
    content: str = Field(description="Full file content.")
    sync_to: list[str] = Field(
        default_factory=list, description="Agent keys to sync to after install."
    )


class ExtensionModifyRequest(BaseModel):
    """Update extension content."""

    content: str = Field(description="New file content.")


class ExtensionSyncRequest(BaseModel):
    """Sync extension to specific agents."""

    agents: list[str] = Field(description="Agent keys to sync to.")


class ExtensionDetailResponse(BaseModel):
    """Full extension detail including content. Generic for skill/command/subagent."""

    item: dict = Field(description="Extension metadata with install status.")
    content: str = Field(description="Raw file text.")
    path: str = Field(description="Central store path.")


class SkillListResponse(BaseModel):
    """Paginated skill listing with sync targets."""

    items: list[Skill] = Field(description="Page of skills.")
    total: int = Field(description="Total matching.")
    page: int = Field(description="Current page.")
    page_size: int = Field(description="Items per page.")
    sync_targets: list[SyncTargetResponse] = Field(description="Agent platforms available.")


class CommandListResponse(BaseModel):
    """Paginated command listing with sync targets."""

    items: list[Command] = Field(description="Page of commands.")
    total: int = Field(description="Total matching.")
    page: int = Field(description="Current page.")
    page_size: int = Field(description="Items per page.")
    sync_targets: list[SyncTargetResponse] = Field(description="Agent platforms available.")


class SubagentListResponse(BaseModel):
    """Paginated subagent listing with sync targets."""

    items: list[Subagent] = Field(description="Page of subagents.")
    total: int = Field(description="Total matching.")
    page: int = Field(description="Current page.")
    page_size: int = Field(description="Items per page.")
    sync_targets: list[SyncTargetResponse] = Field(description="Agent platforms available.")
```

Note: `*ListResponse` must remain separate because `items` field types differ (`list[Skill]` vs `list[Command]` vs `list[Subagent]`). The other schemas (`InstallRequest`, `ModifyRequest`, `SyncRequest`, `SyncTargetResponse`, `DetailResponse`) are truly unified.

Also rename the existing `ExtensionListResponse` (catalog) to `CatalogListResponse` to avoid name collision, and `ExtensionInstallRequest` (catalog) to `CatalogInstallRequest`:

```python
# Rename existing catalog schemas
class CatalogListResponse(BaseModel):
    """Paginated catalog listing response."""
    items: list[dict] = Field(description="Extension items.")
    total: int
    page: int
    per_page: int


class CatalogInstallRequest(BaseModel):
    """Request body for installing from catalog."""
    target_platforms: list[str] = Field(min_length=1)
    overwrite: bool = Field(default=False)
```

- [ ] **Step 3: Update `schemas/hooks.py` — remove redundant, keep hook-specific**

Keep `HookInstallRequest`, `HookModifyRequest` (structurally different). Remove `HookSyncRequest`, `HookSyncTargetResponse` — use the unified versions from `extensions.py`. Update `HookListResponse` to use `SyncTargetResponse`.

```python
# src/vibelens/schemas/hooks.py — after cleanup
"""Hook API schemas — hook-specific request/response models."""

from pydantic import BaseModel, Field

from vibelens.models.extension.hook import Hook
from vibelens.schemas.extensions import SyncTargetResponse


class HookInstallRequest(BaseModel):
    """Create a new hook (structured fields, not raw content)."""

    name: str = Field(description="Kebab-case hook name.")
    description: str = Field(default="", description="Hook description.")
    tags: list[str] = Field(default_factory=list, description="Tags for discovery.")
    hook_config: dict[str, list[dict]] = Field(
        description="Event-name to list-of-hook-groups mapping.",
    )
    sync_to: list[str] = Field(
        default_factory=list, description="Agent keys to sync to after install."
    )


class HookModifyRequest(BaseModel):
    """Partially update a hook. None fields are left unchanged."""

    description: str | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    hook_config: dict[str, list[dict]] | None = Field(default=None)


class HookDetailResponse(BaseModel):
    """Full hook detail including raw JSON content."""

    hook: Hook = Field(description="Hook metadata.")
    content: str = Field(description="Raw JSON text.")
    path: str = Field(description="Central store file path.")


class HookListResponse(BaseModel):
    """Paginated hook listing with sync targets."""

    items: list[Hook] = Field(description="Page of hooks.")
    total: int
    page: int
    page_size: int
    sync_targets: list[SyncTargetResponse] = Field(description="Agent platforms available.")
```

- [ ] **Step 4: Delete old schema files**

```bash
git rm src/vibelens/schemas/skills.py src/vibelens/schemas/commands.py src/vibelens/schemas/subagents.py
```

- [ ] **Step 5: Update all imports across the codebase**

Search for imports from `vibelens.schemas.skills`, `vibelens.schemas.commands`, `vibelens.schemas.subagents` and replace with `vibelens.schemas.extensions`. Key files:
- `src/vibelens/api/skill.py` (will be deleted later, but update for now)
- `src/vibelens/api/command.py` (same)
- `src/vibelens/api/subagent.py` (same)
- `tests/api/test_skill_api.py`
- `tests/api/test_command_api.py`
- `tests/api/test_subagent_api.py`

Also update `src/vibelens/api/extensions.py` to use the renamed catalog schemas (`CatalogListResponse`, `CatalogInstallRequest`).

- [ ] **Step 6: Run all tests**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Run ruff**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 8: Commit**

```bash
git add src/vibelens/schemas/ tests/
git commit -m "refactor(schemas): unify extension schemas, keep hook-specific"
```

---

## Task 2: Create `BaseExtensionService[T]` with unified `SyncTarget`

**Files:**
- Create: `src/vibelens/services/extensions/base_service.py`
- Test: `tests/services/extensions/test_base_service.py`

- [ ] **Step 1: Write the base service test**

```python
# tests/services/extensions/test_base_service.py
"""Tests for BaseExtensionService — shared extension management logic."""

import pytest

from vibelens.models.extension.skill import Skill
from vibelens.services.extensions.base_service import BaseExtensionService, SyncTarget
from vibelens.storage.extension.skill_store import SkillStore

SAMPLE_MD = """\
---
description: A sample skill
tags:
  - testing
---
# Sample

Body.
"""

UPDATED_MD = """\
---
description: Updated
tags:
  - updated
---
# Updated

New body.
"""


@pytest.fixture
def central(tmp_path):
    return SkillStore(root=tmp_path / "central", create=True)


@pytest.fixture
def agents(tmp_path):
    claude = SkillStore(root=tmp_path / "claude", create=True)
    codex = SkillStore(root=tmp_path / "codex", create=True)
    return {"claude": claude, "codex": codex}


@pytest.fixture
def service(central, agents):
    return BaseExtensionService[Skill](
        central_store=central,
        agent_stores=agents,
    )


class TestInstall:
    def test_creates_item(self, service):
        item = service.install(name="my-skill", content=SAMPLE_MD)
        assert item.name == "my-skill"
        assert item.description == "A sample skill"

    def test_syncs_to_agents(self, service):
        item = service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        assert "claude" in item.installed_in

    def test_duplicate_raises(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        with pytest.raises(FileExistsError):
            service.install(name="my-skill", content=SAMPLE_MD)

    def test_bad_name_raises(self, service):
        with pytest.raises(ValueError, match="kebab-case"):
            service.install(name="Bad Name", content=SAMPLE_MD)

    def test_empty_content_raises(self, service):
        with pytest.raises(ValueError, match="empty"):
            service.install(name="my-skill", content="   ")


class TestModify:
    def test_updates_content(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        updated = service.modify(name="my-skill", content=UPDATED_MD)
        assert updated.description == "Updated"

    def test_auto_syncs(self, service):
        service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        updated = service.modify(name="my-skill", content=UPDATED_MD)
        assert "claude" in updated.installed_in

    def test_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.modify(name="nope", content=UPDATED_MD)


class TestUninstall:
    def test_removes_from_central_and_agents(self, service):
        service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        removed = service.uninstall(name="my-skill")
        assert "claude" in removed
        with pytest.raises(FileNotFoundError):
            service.get_item(name="my-skill")

    def test_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            service.uninstall(name="nope")


class TestList:
    def test_empty(self, service):
        items, total = service.list_items(page=1, page_size=50)
        assert items == []
        assert total == 0

    def test_pagination(self, service):
        for i in range(5):
            service.install(name=f"skill-{i:02d}", content=SAMPLE_MD)
        items, total = service.list_items(page=1, page_size=2)
        assert len(items) == 2
        assert total == 5

    def test_search(self, service):
        service.install(name="alpha", content=SAMPLE_MD)
        service.install(name="beta", content=SAMPLE_MD)
        items, total = service.list_items(page=1, page_size=50, search="alpha")
        assert total == 1
        assert items[0].name == "alpha"


class TestSyncTargets:
    def test_returns_unified_sync_targets(self, service):
        service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        targets = service.list_sync_targets()
        assert len(targets) == 2
        assert all(isinstance(t, SyncTarget) for t in targets)
        claude_target = next(t for t in targets if t.agent == "claude")
        assert claude_target.count >= 1


class TestSync:
    def test_sync_to_agents(self, service):
        service.install(name="my-skill", content=SAMPLE_MD)
        results = service.sync_to_agents(name="my-skill", agents=["claude", "codex"])
        assert results["claude"] is True
        assert results["codex"] is True

    def test_uninstall_from_agent(self, service):
        service.install(name="my-skill", content=SAMPLE_MD, sync_to=["claude"])
        service.uninstall_from_agent(name="my-skill", agent="claude")
        item = service.get_item(name="my-skill")
        assert "claude" not in item.installed_in


class TestImport:
    def test_import_from_agent(self, service, agents):
        agents["claude"].write("imported-skill", SAMPLE_MD)
        item = service.import_from_agent(agent="claude", name="imported-skill")
        assert item.name == "imported-skill"

    def test_import_all_from_agent(self, service, agents):
        agents["claude"].write("skill-a", SAMPLE_MD)
        agents["claude"].write("skill-b", SAMPLE_MD)
        imported = service.import_all_from_agent(agent="claude")
        assert len(imported) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/services/extensions/test_base_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vibelens.services.extensions.base_service'`

- [ ] **Step 3: Implement `BaseExtensionService[T]`**

```python
# src/vibelens/services/extensions/base_service.py
"""Generic base service for extension management (skills, commands, hooks, subagents)."""

import time
from dataclasses import dataclass
from typing import Generic, TypeVar

from vibelens.storage.extension.base_store import VALID_EXTENSION_NAME, BaseExtensionStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

CACHE_TTL_SECONDS = 300


@dataclass
class SyncTarget:
    """Unified sync target for all extension types."""

    agent: str
    count: int
    dir: str


class BaseExtensionService(Generic[T]):
    """Orchestrates extension CRUD across a central store and agent stores.

    Subclasses override ``_sync_to_agent`` / ``_unsync_from_agent`` for
    type-specific agent-side behavior (e.g. HookService does JSON merge
    instead of file copy).
    """

    def __init__(
        self,
        central_store: BaseExtensionStore[T],
        agent_stores: dict[str, BaseExtensionStore[T]],
        cache_ttl: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._central = central_store
        self._agents = agent_stores
        self._cache: list[T] | None = None
        self._cache_at: float = 0.0
        self._cache_ttl = cache_ttl

    def install(self, name: str, content: str, sync_to: list[str] | None = None) -> T:
        """Write to central store and optionally sync to agents."""
        if not VALID_EXTENSION_NAME.match(name):
            raise ValueError(f"Extension name must be kebab-case: {name!r}")
        if not content.strip():
            raise ValueError("Extension content must not be empty")
        if self._central.exists(name):
            raise FileExistsError(f"Extension {name!r} already exists. Use modify() to update.")
        self._central.write(name, content)
        self._invalidate_cache()
        if sync_to:
            self.sync_to_agents(name, sync_to)
        return self.get_item(name)

    def modify(self, name: str, content: str) -> T:
        """Update content in central store and auto-sync to agents that have it."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found in central store")
        self._central.write(name, content)
        self._invalidate_cache()
        for agent_key in self._find_installed_agents(name):
            store = self._agents.get(agent_key)
            if store:
                self._sync_to_agent(name, store)
        return self.get_item(name)

    def uninstall(self, name: str) -> list[str]:
        """Delete from central and all agent stores. Returns agents removed from."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found")
        removed_from: list[str] = []
        for agent_key, store in self._agents.items():
            if store.exists(name):
                self._unsync_from_agent(name, store)
                removed_from.append(agent_key)
        self._central.delete(name)
        self._invalidate_cache()
        return removed_from

    def uninstall_from_agent(self, name: str, agent: str) -> None:
        """Remove from a single agent store."""
        store = self._agents.get(agent)
        if store is None:
            raise KeyError(f"Unknown agent: {agent!r}")
        if not store.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not in agent {agent!r}")
        self._unsync_from_agent(name, store)

    def import_from_agent(self, agent: str, name: str) -> T:
        """Copy an extension from an agent store into central."""
        store = self._agents.get(agent)
        if store is None:
            raise KeyError(f"Unknown agent: {agent!r}")
        if not store.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not in agent {agent!r}")
        content = store.read_raw(name)
        self._central.write(name, content)
        self._invalidate_cache()
        return self.get_item(name)

    def import_all_from_agent(self, agent: str) -> list[str]:
        """Import all extensions from an agent store. Returns names imported."""
        store = self._agents.get(agent)
        if store is None:
            raise KeyError(f"Unknown agent: {agent!r}")
        imported: list[str] = []
        for name in store.list_names():
            content = store.read_raw(name)
            self._central.write(name, content)
            imported.append(name)
        self._invalidate_cache()
        return imported

    def import_all_agents(self) -> None:
        """Import from all known agent stores."""
        for agent_key in self._agents:
            try:
                self.import_all_from_agent(agent_key)
            except Exception:
                logger.warning("Failed to import from agent %s", agent_key, exc_info=True)

    def list_items(
        self, page: int = 1, page_size: int = 50, search: str | None = None
    ) -> tuple[list[T], int]:
        """List extensions with pagination and optional search."""
        all_items = self._get_cached_items()
        if search:
            term = search.lower()
            all_items = [i for i in all_items if self._matches_search(i, term)]
        total = len(all_items)
        start = (page - 1) * page_size
        return all_items[start : start + page_size], total

    def get_item(self, name: str) -> T:
        """Get a single extension by name with installed_in populated."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found")
        item = self._central.read(name)
        self._populate_installed_in(item, name)
        return item

    def get_item_content(self, name: str) -> str:
        """Get raw content of an extension."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found")
        return self._central.read_raw(name)

    def get_item_path(self, name: str) -> str:
        """Get the central store path for an extension."""
        return str(self._central._item_path(name))

    def sync_to_agents(self, name: str, agents: list[str]) -> dict[str, bool]:
        """Sync to specified agents. Returns per-agent success map."""
        if not self._central.exists(name):
            raise FileNotFoundError(f"Extension {name!r} not found")
        results: dict[str, bool] = {}
        for agent_key in agents:
            store = self._agents.get(agent_key)
            if store is None:
                results[agent_key] = False
                continue
            try:
                self._sync_to_agent(name, store)
                results[agent_key] = True
            except Exception:
                logger.warning("Failed to sync %s to %s", name, agent_key, exc_info=True)
                results[agent_key] = False
        return results

    def invalidate(self) -> None:
        """Clear the item cache."""
        self._invalidate_cache()

    def list_sync_targets(self) -> list[SyncTarget]:
        """Return available agent sync targets with item counts."""
        return [
            SyncTarget(
                agent=agent_key,
                count=len(store.list_names()),
                dir=str(store._root),
            )
            for agent_key, store in self._agents.items()
        ]

    # --- Hooks for subclass override ---

    def _sync_to_agent(self, name: str, agent_store: BaseExtensionStore[T]) -> None:
        """Copy extension from central to agent store. Override for hooks."""
        content = self._central.read_raw(name)
        agent_store.write(name, content)

    def _unsync_from_agent(self, name: str, agent_store: BaseExtensionStore[T]) -> None:
        """Remove extension from agent store. Override for hooks."""
        agent_store.delete(name)

    # --- Internal helpers ---

    def _find_installed_agents(self, name: str) -> list[str]:
        return [k for k, s in self._agents.items() if s.exists(name)]

    def _populate_installed_in(self, item: T, name: str) -> None:
        installed = self._find_installed_agents(name)
        if hasattr(item, "installed_in"):
            item.installed_in = installed  # type: ignore[attr-defined]

    def _matches_search(self, item: T, term: str) -> bool:
        name = getattr(item, "name", "")
        desc = getattr(item, "description", "")
        tags = getattr(item, "tags", [])
        return term in name.lower() or term in desc.lower() or any(term in t.lower() for t in tags)

    def _get_cached_items(self) -> list[T]:
        now = time.time()
        if self._cache is not None and (now - self._cache_at) < self._cache_ttl:
            return list(self._cache)
        names = sorted(self._central.list_names())
        items = []
        for name in names:
            try:
                item = self._central.read(name)
                self._populate_installed_in(item, name)
                items.append(item)
            except Exception:
                logger.warning("Failed to read extension %s", name, exc_info=True)
        self._cache = items
        self._cache_at = now
        return list(items)

    def _invalidate_cache(self) -> None:
        self._cache = None
        self._cache_at = 0.0
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/services/extensions/test_base_service.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/vibelens/services/extensions/base_service.py tests/services/extensions/test_base_service.py
git commit -m "feat(extensions): add BaseExtensionService[T] with unified SyncTarget"
```

---

## Task 3: Migrate all four services to inherit `BaseExtensionService`

**Files:**
- Modify: `src/vibelens/services/extensions/skill_service.py`
- Modify: `src/vibelens/services/extensions/command_service.py`
- Modify: `src/vibelens/services/extensions/subagent_service.py`
- Modify: `src/vibelens/services/extensions/hook_service.py`
- Modify: `tests/services/extensions/test_skill_service.py`
- Modify: `tests/services/extensions/test_command_service.py`
- Modify: `tests/services/extensions/test_subagent_service.py`
- Modify: `tests/services/extensions/test_hook_service.py`

- [ ] **Step 1: Run all existing service tests to verify baseline**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/services/extensions/ -v`
Expected: All PASS

- [ ] **Step 2: Rewrite `SkillService` — empty shell inheriting base**

```python
# src/vibelens/services/extensions/skill_service.py
"""Skill management service — extends BaseExtensionService for future specialization."""

from vibelens.models.extension.skill import Skill
from vibelens.services.extensions.base_service import BaseExtensionService
from vibelens.storage.extension.skill_store import SkillStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class SkillService(BaseExtensionService[Skill]):
    """Skill-specific service. Currently inherits everything from base."""

    def __init__(self, central: SkillStore, agents: dict[str, SkillStore]) -> None:
        super().__init__(central_store=central, agent_stores=agents)
```

- [ ] **Step 3: Rewrite `CommandService` — same pattern**

```python
# src/vibelens/services/extensions/command_service.py
"""Command management service — extends BaseExtensionService for future specialization."""

from vibelens.models.extension.command import Command
from vibelens.services.extensions.base_service import BaseExtensionService
from vibelens.storage.extension.command_store import CommandStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class CommandService(BaseExtensionService[Command]):
    """Command-specific service. Currently inherits everything from base."""

    def __init__(self, central: CommandStore, agents: dict[str, CommandStore]) -> None:
        super().__init__(central_store=central, agent_stores=agents)
```

- [ ] **Step 4: Rewrite `SubagentService` — same pattern**

```python
# src/vibelens/services/extensions/subagent_service.py
"""Subagent management service — extends BaseExtensionService for future specialization."""

from vibelens.models.extension.subagent import Subagent
from vibelens.services.extensions.base_service import BaseExtensionService
from vibelens.storage.extension.subagent_store import SubagentStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class SubagentService(BaseExtensionService[Subagent]):
    """Subagent-specific service. Currently inherits everything from base."""

    def __init__(self, central: SubagentStore, agents: dict[str, SubagentStore]) -> None:
        super().__init__(central_store=central, agent_stores=agents)
```

- [ ] **Step 5: Rewrite `HookService` — overrides sync methods**

```python
# src/vibelens/services/extensions/hook_service.py
"""Hook management service — extends BaseExtensionService with JSON merge sync."""

from vibelens.models.extension.hook import Hook
from vibelens.services.extensions.base_service import BaseExtensionService, SyncTarget
from vibelens.storage.extension.hook_store import HookStore, serialize_hook
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class HookService(BaseExtensionService[Hook]):
    """Hook-specific service. Overrides sync for JSON merge into settings.json."""

    def __init__(
        self,
        central: HookStore,
        agents: dict[str, HookStore],
        agent_settings_paths: dict[str, str],
    ) -> None:
        super().__init__(central_store=central, agent_stores=agents)
        self._settings_paths = agent_settings_paths

    def install(  # type: ignore[override]
        self,
        name: str,
        description: str = "",
        tags: list[str] | None = None,
        hook_config: dict[str, list[dict]] | None = None,
        sync_to: list[str] | None = None,
        content: str | None = None,
    ) -> Hook:
        """Install a hook. Accepts structured fields or raw JSON content."""
        if content is None:
            hook = Hook(
                name=name,
                description=description,
                tags=tags or [],
                hook_config=hook_config or {},
            )
            content = serialize_hook(hook)
        return super().install(name=name, content=content, sync_to=sync_to)

    def modify(  # type: ignore[override]
        self,
        name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        hook_config: dict[str, list[dict]] | None = None,
        content: str | None = None,
    ) -> Hook:
        """Partial update. None fields are left unchanged."""
        if content is None:
            existing = self.get_item(name)
            hook = Hook(
                name=name,
                description=description if description is not None else existing.description,
                tags=tags if tags is not None else existing.tags,
                hook_config=hook_config if hook_config is not None else existing.hook_config,
            )
            content = serialize_hook(hook)
        return super().modify(name=name, content=content)

    def import_from_agent(  # type: ignore[override]
        self,
        agent: str,
        name: str,
        event_name: str | None = None,
        matcher: str | None = None,
    ) -> Hook:
        """Import a hook from agent settings.json.

        Extracts managed hook groups from the agent's settings.json.
        Copy the full implementation from the current hook_service.py —
        reads settings.json, finds matching hook groups by event_name/matcher,
        writes to central store.
        """
        # IMPORTANT: Copy the exact import logic from current hook_service.py.
        # This reads the agent's settings.json and extracts hook groups.
        raise NotImplementedError("Copy from current hook_service.py")

    def _sync_to_agent(self, name: str, agent_store: HookStore) -> None:
        """Merge hook config into agent's settings.json with _vibelens_managed tag.

        Copy the full implementation from the current hook_service.py —
        reads settings.json, merges hook groups with _vibelens_managed markers,
        writes back.
        """
        # IMPORTANT: Copy the exact sync logic from current hook_service.py.
        raise NotImplementedError("Copy from current hook_service.py")

    def _unsync_from_agent(self, name: str, agent_store: HookStore) -> None:
        """Remove managed hook groups from agent's settings.json.

        Copy the full implementation from the current hook_service.py —
        scans for _vibelens_managed markers matching this hook name, removes them.
        """
        # IMPORTANT: Copy the exact unsync logic from current hook_service.py.
        raise NotImplementedError("Copy from current hook_service.py")

    def list_sync_targets(self) -> list[SyncTarget]:
        """Return sync targets with settings_path as dir."""
        return [
            SyncTarget(
                agent=agent_key,
                count=len(store.list_names()),
                dir=self._settings_paths.get(agent_key, ""),
            )
            for agent_key, store in self._agents.items()
        ]
```

**CRITICAL:** The three `NotImplementedError` methods must be filled with the actual logic from the current `hook_service.py`. Read that file and copy the JSON merge logic verbatim into these methods. The logic involves reading/writing `settings.json`, tagging hook groups with `_vibelens_managed`, and surgical removal.

- [ ] **Step 6: Update all four test files — string agent keys**

For each test file (`test_skill_service.py`, `test_command_service.py`, `test_subagent_service.py`, `test_hook_service.py`):
- Change agent dict keys from `AgentType.CLAUDE` to `"claude"`, `AgentType.CODEX` to `"codex"`
- Remove unused `AgentType` import
- Update any assertions that check agent keys

Also update test method calls from type-specific names to base names:
- `service.list_skills(...)` → `service.list_items(...)`
- `service.get_skill(name)` → `service.get_item(name)`
- `service.get_skill_content(name)` → `service.get_item_content(name)`
- Same for command/subagent/hook equivalents

- [ ] **Step 7: Run all service tests**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/services/extensions/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/vibelens/services/extensions/ tests/services/extensions/
git commit -m "refactor(extensions): migrate all services to BaseExtensionService"
```

---

## Task 4: Update `deps.py` for string agent keys

**Files:**
- Modify: `src/vibelens/deps.py`

- [ ] **Step 1: Read `deps.py` and update agent store construction**

Change all `_build_agent_*_stores()` functions to return `dict[str, Store]` using string keys instead of `AgentType` enum. Use the platform's `install_key` string or agent key string.

- [ ] **Step 2: Update `app.py` background startup**

In `_run_background_startup()`, `get_skill_service().import_all_agents()` should still work since `import_all_agents()` is on the base class. Verify no other callers use type-specific methods that were removed.

- [ ] **Step 3: Run all tests**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/vibelens/deps.py src/vibelens/app.py
git commit -m "refactor(deps): use string agent keys, remove AgentType enum dependency"
```

---

## Task 5: Create `catalog_resolver.py` and clean up `catalog.py`

**Files:**
- Create: `src/vibelens/services/extensions/catalog_resolver.py`
- Modify: `src/vibelens/services/extensions/catalog.py`
- Delete: `src/vibelens/services/extensions/catalog_install.py`
- Rename: `tests/services/extensions/test_catalog_install.py` → `test_catalog_resolver.py`
- Modify: `tests/services/extensions/test_catalog_install_service_dispatch.py`

- [ ] **Step 1: Run existing catalog tests to verify baseline**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/services/extensions/test_catalog_install.py tests/services/extensions/test_catalog_install_service_dispatch.py tests/api/test_catalog_api.py -v`
Expected: All PASS

- [ ] **Step 2: Create `catalog_resolver.py`**

Move all install-related functions from `catalog_install.py` into `catalog_resolver.py`. Same function signatures, same implementations. Key functions: `install_extension()`, `_install_file()`, `_install_subagent()`, `_install_command()`, `_install_hook_via_service()`, `_install_mcp()`, `install_from_source_url()`.

- [ ] **Step 3: Update `catalog.py` — remove install re-export**

Remove any `install_extension` function or re-export that delegates to `catalog_install.py`.

- [ ] **Step 4: Delete `catalog_install.py` and rename test**

```bash
git rm src/vibelens/services/extensions/catalog_install.py
git mv tests/services/extensions/test_catalog_install.py tests/services/extensions/test_catalog_resolver.py
```

- [ ] **Step 5: Update all imports**

Search for `vibelens.services.extensions.catalog_install` and replace with `vibelens.services.extensions.catalog_resolver` in all files.

- [ ] **Step 6: Run tests**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/services/extensions/ tests/api/test_catalog_api.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(extensions): rename catalog_install to catalog_resolver"
```

---

## Task 6: Create `api/extensions/` package

**Files:**
- Create: `src/vibelens/api/extensions/__init__.py`
- Create: `src/vibelens/api/extensions/catalog.py`
- Create: `src/vibelens/api/extensions/skill.py`
- Create: `src/vibelens/api/extensions/command.py`
- Create: `src/vibelens/api/extensions/subagent.py`
- Create: `src/vibelens/api/extensions/hook.py`

- [ ] **Step 1: Create `api/extensions/skill.py` (~60 lines)**

```python
# src/vibelens/api/extensions/skill.py
"""Skill CRUD routes."""

from fastapi import APIRouter, HTTPException

from vibelens.deps import get_skill_service
from vibelens.schemas.extensions import (
    ExtensionDetailResponse,
    ExtensionInstallRequest,
    ExtensionModifyRequest,
    ExtensionSyncRequest,
    SkillListResponse,
    SyncTargetResponse,
)

router = APIRouter(prefix="/skills", tags=["skills"])

DEFAULT_PAGE_SIZE = 50


@router.post("/import/{agent}")
def import_from_agent(agent: str) -> dict:
    """Import all skills from an agent directory into central store."""
    service = get_skill_service()
    try:
        imported = service.import_all_from_agent(agent)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
    return {"agent": agent, "imported": imported, "count": len(imported)}


@router.get("")
def list_skills(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    search: str | None = None,
    refresh: bool = False,
) -> SkillListResponse:
    """List skills with pagination, optional search, and sync targets."""
    service = get_skill_service()
    if refresh:
        service.invalidate()
    items, total = service.list_items(page=page, page_size=page_size, search=search)
    targets = service.list_sync_targets()
    return SkillListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        sync_targets=[SyncTargetResponse(agent=t.agent, count=t.count, dir=t.dir) for t in targets],
    )


@router.get("/{name}")
def get_skill(name: str) -> ExtensionDetailResponse:
    """Get full skill detail with content."""
    service = get_skill_service()
    try:
        item = service.get_item(name)
        content = service.get_item_content(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found") from None
    return ExtensionDetailResponse(
        item=item.model_dump(), content=content, path=service.get_item_path(name)
    )


@router.post("")
def install_skill(req: ExtensionInstallRequest) -> dict:
    """Install a new skill."""
    service = get_skill_service()
    try:
        item = service.install(name=req.name, content=req.content, sync_to=req.sync_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return item.model_dump()


@router.put("/{name}")
def modify_skill(name: str, req: ExtensionModifyRequest) -> dict:
    """Update an existing skill's content."""
    service = get_skill_service()
    try:
        item = service.modify(name=name, content=req.content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found") from None
    return item.model_dump()


@router.delete("/{name}")
def uninstall_skill(name: str) -> dict:
    """Delete a skill from central and all agent stores."""
    service = get_skill_service()
    try:
        removed_from = service.uninstall(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found") from None
    return {"deleted": name, "removed_from": removed_from}


@router.post("/{name}/agents")
def sync_skill(name: str, req: ExtensionSyncRequest) -> dict:
    """Sync a skill to specified agent platforms."""
    service = get_skill_service()
    try:
        results = service.sync_to_agents(name, req.agents)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Skill {name!r} not found") from None
    item = service.get_item(name)
    return {"name": name, "results": results, "skill": item.model_dump()}


@router.delete("/{name}/agents/{agent}")
def unsync_skill(name: str, agent: str) -> dict:
    """Remove a skill from a single agent platform."""
    service = get_skill_service()
    try:
        service.uninstall_from_agent(name, agent)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent!r}") from None
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Skill {name!r} not in agent {agent!r}"
        ) from None
    item = service.get_item(name)
    return {"name": name, "agent": agent, "skill": item.model_dump()}
```

- [ ] **Step 2: Create `api/extensions/command.py` and `api/extensions/subagent.py`**

Same structure as `skill.py` — copy and change:
- `command.py`: `get_command_service`, `CommandListResponse`, error messages say "Command"
- `subagent.py`: `get_subagent_service`, `SubagentListResponse`, error messages say "Subagent"

- [ ] **Step 3: Create `api/extensions/hook.py` (hand-written)**

Copy current `api/hook.py` contents verbatim. Only change:
- Import schemas from `vibelens.schemas.hooks` and `vibelens.schemas.extensions` (for `SyncTargetResponse`, `ExtensionSyncRequest`)
- Use `service.list_items()` / `service.get_item()` / `service.get_item_content()` instead of `service.list_hooks()` etc.
- `list_sync_targets()` returns `SyncTarget` — wrap with `SyncTargetResponse`

- [ ] **Step 4: Create `api/extensions/catalog.py`**

Copy current `api/extensions.py` contents. Changes:
- Prefix from `/extensions` to `/catalog`
- Rename schema references: `ExtensionListResponse` → `CatalogListResponse`, `ExtensionInstallRequest` → `CatalogInstallRequest`
- Import `install_extension` from `catalog_resolver` instead of `catalog`

- [ ] **Step 5: Create `api/extensions/__init__.py`**

```python
# src/vibelens/api/extensions/__init__.py
"""Extension API router aggregation."""

from fastapi import APIRouter

from vibelens.api.extensions.catalog import router as catalog_router
from vibelens.api.extensions.command import router as commands_router
from vibelens.api.extensions.hook import router as hooks_router
from vibelens.api.extensions.skill import router as skills_router
from vibelens.api.extensions.subagent import router as subagents_router


def build_extensions_router() -> APIRouter:
    """Aggregate all extension sub-routers under /extensions prefix."""
    router = APIRouter(prefix="/extensions", tags=["extensions"])
    router.include_router(catalog_router)
    router.include_router(skills_router)
    router.include_router(commands_router)
    router.include_router(hooks_router)
    router.include_router(subagents_router)
    return router
```

- [ ] **Step 6: Commit**

```bash
git add src/vibelens/api/extensions/
git commit -m "feat(api): create api/extensions/ package with all type routers"
```

---

## Task 7: Wire up new routers and delete old ones

**Files:**
- Modify: `src/vibelens/api/__init__.py`
- Delete: `src/vibelens/api/extensions.py`, `skill.py`, `command.py`, `hook.py`, `subagent.py`
- Modify: all `tests/api/test_*_api.py`

- [ ] **Step 1: Update `api/__init__.py`**

```python
# src/vibelens/api/__init__.py
"""FastAPI route aggregation."""

from fastapi import APIRouter

from vibelens.api.creation import router as creation_router
from vibelens.api.dashboard import router as dashboard_router
from vibelens.api.donation import router as donation_router
from vibelens.api.evolution import router as evolution_router
from vibelens.api.extensions import build_extensions_router
from vibelens.api.friction import router as friction_router
from vibelens.api.recommendation import router as recommendation_router
from vibelens.api.sessions import router as sessions_router
from vibelens.api.shares import router as shares_router
from vibelens.api.system import router as system_router
from vibelens.api.upload import router as upload_router


def build_router() -> APIRouter:
    """Aggregate all sub-routers into a single API router."""
    router = APIRouter()
    router.include_router(sessions_router)
    router.include_router(donation_router)
    router.include_router(upload_router)
    router.include_router(dashboard_router)
    router.include_router(shares_router)
    router.include_router(system_router)
    router.include_router(friction_router)
    router.include_router(creation_router)
    router.include_router(evolution_router)
    router.include_router(recommendation_router)
    router.include_router(build_extensions_router())
    return router
```

- [ ] **Step 2: Delete old router files**

```bash
git rm src/vibelens/api/extensions.py src/vibelens/api/skill.py src/vibelens/api/command.py src/vibelens/api/hook.py src/vibelens/api/subagent.py
```

- [ ] **Step 3: Update API test files**

For each test file, update:

**`test_skill_api.py`:**
- `from vibelens.api.skill import router` → `from vibelens.api.extensions.skill import router`
- Monkeypatch target: `vibelens.api.extensions.skill` instead of `vibelens.api.skill`
- URL paths: `/api/skills` → `/api/extensions/skills`
- `app.include_router(router, prefix="/api")` → `app.include_router(router, prefix="/api/extensions")`
- Schema imports: from `vibelens.schemas.extensions` instead of `vibelens.schemas.skills`

Apply same pattern for `test_command_api.py`, `test_hook_api.py`, `test_subagent_api.py`.

**`test_extension_api.py` and `test_catalog_api.py`:**
- Import from `vibelens.api.extensions.catalog`
- URL paths: `/api/extensions` → `/api/extensions/catalog`

- [ ] **Step 4: Run all tests**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Run ruff**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(api): replace 5 standalone routers with unified extensions package"
```

---

## Task 8: Create frontend API client

**Files:**
- Create: `frontend/src/api/extensions.ts`
- Modify: `frontend/src/app.tsx`
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Create `api/extensions.ts` with typed client**

```typescript
// frontend/src/api/extensions.ts
import type {
  ExtensionItemSummary,
  ExtensionListResponse,
  ExtensionMetaResponse,
  SyncTarget,
} from "../types";

type FetchFn = (url: string, init?: RequestInit) => Promise<Response>;

const BASE = "/api/extensions";

interface CatalogApi {
  list(params: {
    page?: number;
    perPage?: number;
    sort?: string;
    search?: string;
    extensionType?: string;
    category?: string;
    platform?: string;
  }): Promise<ExtensionListResponse>;
  getMeta(): Promise<ExtensionMetaResponse>;
  getItem(id: string): Promise<ExtensionItemSummary>;
  getContent(id: string): Promise<{ content: string; source: string }>;
  install(
    id: string,
    targets: string[],
    overwrite?: boolean
  ): Promise<{
    success: boolean;
    installed_path: string;
    message: string;
    results: Record<string, { success: boolean; message: string }>;
  }>;
}

interface TypeApi<T> {
  list(params?: {
    page?: number;
    pageSize?: number;
    search?: string;
    refresh?: boolean;
  }): Promise<{ items: T[]; total: number; page: number; page_size: number; sync_targets: SyncTarget[] }>;
  get(name: string): Promise<{ item: Record<string, unknown>; content: string; path: string }>;
  install(name: string, content: string, syncTo?: string[]): Promise<T>;
  modify(name: string, content: string): Promise<T>;
  uninstall(name: string): Promise<{ deleted: string; removed_from: string[] }>;
  syncToAgents(name: string, agents: string[]): Promise<{ name: string; results: Record<string, boolean> }>;
  unsyncFromAgent(name: string, agent: string): Promise<{ name: string; agent: string }>;
  importFromAgent(agent: string): Promise<{ agent: string; imported: string[]; count: number }>;
}

interface SyncTargetsCache {
  get(): Promise<Record<string, SyncTarget[]>>;
  invalidate(): void;
}

export interface ExtensionsClient {
  catalog: CatalogApi;
  skills: TypeApi<any>;
  commands: TypeApi<any>;
  hooks: TypeApi<any>;
  subagents: TypeApi<any>;
  syncTargets: SyncTargetsCache;
}

function createTypeApi<T>(fetchFn: FetchFn, typePlural: string): TypeApi<T> {
  const base = `${BASE}/${typePlural}`;

  return {
    async list(params = {}) {
      const qs = new URLSearchParams();
      if (params.page) qs.set("page", String(params.page));
      if (params.pageSize) qs.set("page_size", String(params.pageSize));
      if (params.search) qs.set("search", params.search);
      if (params.refresh) qs.set("refresh", "true");
      const res = await fetchFn(`${base}?${qs}`);
      if (!res.ok) throw new Error(`Failed to list ${typePlural}`);
      return res.json();
    },

    async get(name) {
      const res = await fetchFn(`${base}/${encodeURIComponent(name)}`);
      if (!res.ok) throw new Error(`${typePlural} ${name} not found`);
      return res.json();
    },

    async install(name, content, syncTo) {
      const res = await fetchFn(base, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, content, sync_to: syncTo || [] }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to install ${name}`);
      }
      return res.json();
    },

    async modify(name, content) {
      const res = await fetchFn(`${base}/${encodeURIComponent(name)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error(`Failed to modify ${name}`);
      return res.json();
    },

    async uninstall(name) {
      const res = await fetchFn(`${base}/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`Failed to uninstall ${name}`);
      return res.json();
    },

    async syncToAgents(name, agents) {
      const res = await fetchFn(`${base}/${encodeURIComponent(name)}/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agents }),
      });
      if (!res.ok) throw new Error(`Failed to sync ${name}`);
      return res.json();
    },

    async unsyncFromAgent(name, agent) {
      const res = await fetchFn(
        `${base}/${encodeURIComponent(name)}/agents/${encodeURIComponent(agent)}`,
        { method: "DELETE" }
      );
      if (!res.ok) throw new Error(`Failed to unsync ${name} from ${agent}`);
      return res.json();
    },

    async importFromAgent(agent) {
      const res = await fetchFn(`${base}/import/${encodeURIComponent(agent)}`, { method: "POST" });
      if (!res.ok) throw new Error(`Failed to import from ${agent}`);
      return res.json();
    },
  };
}

export function createExtensionsClient(fetchFn: FetchFn): ExtensionsClient {
  let cachedTargets: Record<string, SyncTarget[]> | null = null;
  let cachePromise: Promise<Record<string, SyncTarget[]>> | null = null;

  const syncTargets: SyncTargetsCache = {
    async get() {
      if (cachedTargets) return cachedTargets;
      if (cachePromise) return cachePromise;
      cachePromise = (async () => {
        const types = ["skills", "commands", "hooks", "subagents"] as const;
        const results: Record<string, SyncTarget[]> = {};
        await Promise.all(
          types.map(async (type) => {
            try {
              const res = await fetchFn(`${BASE}/${type}?page_size=1`);
              if (res.ok) {
                const data = await res.json();
                results[type.replace(/s$/, "")] = (data.sync_targets || []).map(
                  (t: { agent: string; count: number; dir: string }) => ({
                    agent: t.agent,
                    count: t.count,
                    dir: t.dir,
                  })
                );
              }
            } catch {
              results[type.replace(/s$/, "")] = [];
            }
          })
        );
        cachedTargets = results;
        cachePromise = null;
        return results;
      })();
      return cachePromise;
    },
    invalidate() {
      cachedTargets = null;
      cachePromise = null;
    },
  };

  const catalog: CatalogApi = {
    async list(params) {
      const qs = new URLSearchParams();
      if (params.page) qs.set("page", String(params.page));
      if (params.perPage) qs.set("per_page", String(params.perPage));
      if (params.sort) qs.set("sort", params.sort);
      if (params.search) qs.set("search", params.search);
      if (params.extensionType) qs.set("extension_type", params.extensionType);
      if (params.category) qs.set("category", params.category);
      if (params.platform) qs.set("platform", params.platform);
      const res = await fetchFn(`${BASE}/catalog?${qs}`);
      if (!res.ok) throw new Error("Failed to list catalog");
      return res.json();
    },

    async getMeta() {
      const res = await fetchFn(`${BASE}/catalog/meta`);
      if (!res.ok) throw new Error("Failed to get catalog meta");
      return res.json();
    },

    async getItem(id) {
      const res = await fetchFn(`${BASE}/catalog/${id}`);
      if (!res.ok) throw new Error(`Catalog item ${id} not found`);
      return res.json();
    },

    async getContent(id) {
      const res = await fetchFn(`${BASE}/catalog/${id}/content`);
      if (!res.ok) throw new Error(`Content for ${id} not found`);
      return res.json();
    },

    async install(id, targets, overwrite = false) {
      const res = await fetchFn(`${BASE}/catalog/${id}/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_platforms: targets, overwrite }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Install failed");
      }
      return res.json();
    },
  };

  return {
    catalog,
    skills: createTypeApi("skills"),
    commands: createTypeApi("commands"),
    hooks: createTypeApi("hooks"),
    subagents: createTypeApi("subagents"),
    syncTargets,
  };
}
```

- [ ] **Step 2: Add `SyncTarget` to `types.ts` and `ExtensionsClient` to app context**

In `types.ts`, add:
```typescript
export interface SyncTarget {
  agent: string;
  count: number;
  dir: string;
}
```

In `app.tsx`:
1. Import `createExtensionsClient`, `ExtensionsClient`
2. Create client in App: `const extensionsClient = useMemo(() => createExtensionsClient(fetchWithToken), [fetchWithToken])`
3. Add to AppContext value
4. Export `useExtensionsClient()` hook

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/extensions.ts frontend/src/app.tsx frontend/src/types.ts
git commit -m "feat(frontend): add typed extensions API client with context provider"
```

---

## Task 9: Migrate frontend components to new client

**Files:**
- Modify: `frontend/src/components/personalization/extensions/extension-explore-tab.tsx`
- Modify: `frontend/src/components/personalization/extensions/extension-card.tsx`
- Modify: `frontend/src/components/personalization/extensions/extension-detail-view.tsx`
- Modify: `frontend/src/components/personalization/install-target-dialog.tsx`
- Modify: `frontend/src/components/personalization/recommendations-view.tsx`
- Delete: `frontend/src/components/personalization/extensions/extension-endpoints.ts`
- Delete: `frontend/src/components/personalization/extensions/use-sync-targets.ts`

- [ ] **Step 1: Update `extension-explore-tab.tsx`**

- Replace `fetchWithToken("/api/extensions?...")` → `client.catalog.list({...})`
- Replace `fetchWithToken("/api/extensions/meta")` → `client.catalog.getMeta()`
- Remove `useSyncTargetsByType` import/usage → `client.syncTargets.get()`
- Remove `extensionEndpoint` import

- [ ] **Step 2: Update `extension-card.tsx`**

- Install: `fetchWithToken("/api/extensions/${id}/install", ...)` → `client.catalog.install(id, targets)`
- Uninstall: `fetchWithToken("/api/${type}s/${name}/agents/${agent}", DELETE)` → use client type API
- Remove `extensionEndpoint` import

- [ ] **Step 3: Update `extension-detail-view.tsx`**

- `fetchWithToken("/api/extensions/${id}")` → `client.catalog.getItem(id)`
- `fetchWithToken("/api/extensions/${id}/content")` → `client.catalog.getContent(id)`

- [ ] **Step 4: Update `install-target-dialog.tsx`**

Replace `detailEndpoint` prop pattern with client calls.

- [ ] **Step 5: Update `recommendations-view.tsx`**

- `fetchWithToken("/api/extensions/${id}")` → `client.catalog.getItem(id)`

- [ ] **Step 6: Update `creations-view.tsx` and `evolutions-view.tsx`**

In `creations-view.tsx`:
- `fetchWithToken("/api/skills", {method: "POST", ...})` → `client.skills.install(name, content, syncTo)`

In `evolutions-view.tsx`:
- `fetchWithToken("/api/skills/${name}")` → `client.skills.get(name)`
- `fetchWithToken("/api/skills/${name}", {method: "PUT", ...})` → `client.skills.modify(name, content)`
- `fetchWithToken("/api/skills/${name}/agents", {method: "POST", ...})` → `client.skills.syncToAgents(name, agents)`

- [ ] **Step 7: Delete old files**

```bash
rm frontend/src/components/personalization/extensions/extension-endpoints.ts
rm frontend/src/components/personalization/extensions/use-sync-targets.ts
```

- [ ] **Step 8: Build frontend**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 9: Commit**

```bash
git add frontend/src/
git commit -m "refactor(frontend): migrate extension components to unified API client"
```

---

## Task 10: Rewrite `local-extensions-tab.tsx` and delete `cards.tsx`

**Files:**
- Modify: `frontend/src/components/personalization/local-extensions-tab.tsx`
- Delete: `frontend/src/components/personalization/cards.tsx`

- [ ] **Step 1: Rewrite `local-extensions-tab.tsx`**

1. Use `useExtensionsClient()` for all API calls
2. Support all four types via `client.skills`, `client.commands`, etc.
3. Type filter dropdown at top
4. **v1: only show "skill" filter** — `const VISIBLE_TYPES = ["skill"] as const;`
5. Use `ExtensionCard` from `extension-card.tsx` (not old `cards.tsx`)
6. Use `ExtensionDetailView` for detail (not `ExtensionDetailPopup`)

- [ ] **Step 2: Delete `cards.tsx`**

```bash
rm frontend/src/components/personalization/cards.tsx
```

- [ ] **Step 3: Update remaining imports of `cards.tsx`**

Search for `from.*cards` imports in personalization components. Update to use unified components.

- [ ] **Step 4: Build frontend**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/
git commit -m "refactor(frontend): rewrite local-extensions-tab, delete cards.tsx"
```

---

## Task 11: Update `personalization-panel.tsx` and clean up

**Files:**
- Modify: `frontend/src/components/personalization/personalization-panel.tsx`

- [ ] **Step 1: Update `personalization-panel.tsx`**

- Remove `useSyncTargetsByType` usage
- Update `onInstalled` callback to call `client.syncTargets.invalidate()`
- Remove unused imports

- [ ] **Step 2: Search for remaining old references**

Grep across frontend for:
- `"/api/skills"`, `"/api/commands"`, `"/api/hooks"`, `"/api/subagents"`
- `"/api/extensions"` (without `/catalog`)
- `extension-endpoints`, `use-sync-targets`, `from.*cards`

Fix any remaining references.

- [ ] **Step 3: Build frontend**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "refactor(frontend): final cleanup of old references"
```

---

## Task 12: Final verification

- [ ] **Step 1: Run all backend tests**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Run ruff**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Build frontend**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Copy built assets**

Run: `cp -r frontend/dist/* src/vibelens/static/`

- [ ] **Step 5: Smoke test**

Run: `cd /Users/JinghengYe/Documents/Projects/Agent-Guideline/VibeLens && uv run vibelens serve`

Verify:
- Server starts without errors
- `GET /api/extensions/catalog` returns catalog items
- `GET /api/extensions/skills` returns skills list
- Frontend loads, Extensions tab works

- [ ] **Step 6: Final commit**

```bash
git add src/vibelens/static/
git commit -m "build: update static assets after extensions API refactor"
```

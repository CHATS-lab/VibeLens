# Extensions API Refactor Design

## Summary

Remove the redundant `api/extensions.py` forwarding layer. Reorganize into:
- **Catalog API** — unified read-only browsing + install entry point
- **Type-specific APIs** — local CRUD + sync for skills, commands, hooks, subagents
- **Unified frontend** — shared API client, consolidated components

## Key Decisions

| Decision | Choice |
|----------|--------|
| Catalog split? | No, keep unified catalog |
| Catalog role | Read-only browsing + install entry point |
| Install flow | `POST /api/extensions/catalog/{id}/install`, routes to type service internally |
| Service directory | Stay in `services/extensions/`, extract `BaseExtensionService[T]` |
| API directory | `api/extensions/` subdirectory with catalog + 4 type routers |
| URL structure | Nested under `/api/extensions/` |
| Code reuse | Generic base class `BaseExtensionService[T]` + route factory (skill/command/subagent only; hook hand-written) |
| Frontend | Unified API client, consolidated components, support all 4 types |
| Local management UI | Unified list + type filter, v1 only shows skill |
| `repo` type | Catalog display only, no managed install |
| Hook editor | v1: view + uninstall only, no editing |

## Backend API Layer

### Directory Structure

```
api/extensions/
    __init__.py          # build_extensions_router() aggregates sub-routers
    catalog.py           # browsing + install entry point
    skill.py             # local skill CRUD + sync
    command.py           # local command CRUD + sync
    hook.py              # local hook CRUD + sync
    subagent.py          # local subagent CRUD + sync
```

### URL Map

```
# Catalog: discover + install
GET  /api/extensions/catalog                          # paginated browse + filter
GET  /api/extensions/catalog/meta                     # categories + has_profile
GET  /api/extensions/catalog/{item_id:path}           # item detail
GET  /api/extensions/catalog/{item_id:path}/content   # preview content (markdown/json)
POST /api/extensions/catalog/{item_id:path}/install   # install (routes to type service)

# Skills local management
POST   /api/extensions/skills/import/{agent}
GET    /api/extensions/skills
GET    /api/extensions/skills/{name}
POST   /api/extensions/skills
PUT    /api/extensions/skills/{name}
DELETE /api/extensions/skills/{name}
POST   /api/extensions/skills/{name}/agents
DELETE /api/extensions/skills/{name}/agents/{agent}

# Commands — same pattern as skills
POST   /api/extensions/commands/import/{agent}
GET    /api/extensions/commands
GET    /api/extensions/commands/{name}
POST   /api/extensions/commands
PUT    /api/extensions/commands/{name}
DELETE /api/extensions/commands/{name}
POST   /api/extensions/commands/{name}/agents
DELETE /api/extensions/commands/{name}/agents/{agent}

# Hooks — same pattern, structured body for POST/PUT
POST   /api/extensions/hooks/import/{agent}
GET    /api/extensions/hooks
GET    /api/extensions/hooks/{name}
POST   /api/extensions/hooks
PUT    /api/extensions/hooks/{name}
DELETE /api/extensions/hooks/{name}
POST   /api/extensions/hooks/{name}/agents
DELETE /api/extensions/hooks/{name}/agents/{agent}

# Subagents — same pattern as skills
POST   /api/extensions/subagents/import/{agent}
GET    /api/extensions/subagents
GET    /api/extensions/subagents/{name}
POST   /api/extensions/subagents
PUT    /api/extensions/subagents/{name}
DELETE /api/extensions/subagents/{name}
POST   /api/extensions/subagents/{name}/agents
DELETE /api/extensions/subagents/{name}/agents/{agent}
```

### Files to Delete

- `api/extensions.py` (old single-file router)
- `api/skill.py` (standalone router)
- `api/command.py` (standalone router)
- `api/hook.py` (standalone router)
- `api/subagent.py` (standalone router)

### Route Factory

`build_typed_router(service_getter, type_name, tag)` generates standard CRUD routes for skill, command, and subagent (identical interfaces). Hook router is hand-written in `api/extensions/hook.py` because its interfaces differ:
- `POST /hooks` and `PUT /hooks/{name}` accept structured body (`description`, `tags`, `hook_config`) instead of raw `content`
- `POST /hooks/import/{agent}` accepts extra query params (`name`, `event_name`, `matcher`)

## Backend Service Layer

### Directory Structure

```
services/extensions/
    __init__.py
    base_service.py      # BaseExtensionService[T] — new
    catalog.py           # read-only browsing logic
    catalog_resolver.py  # resolve installable content from catalog items (refactored from catalog_install.py)
    platforms.py         # unchanged
    skill_service.py     # extends BaseExtensionService
    command_service.py   # extends BaseExtensionService
    hook_service.py      # extends BaseExtensionService, overrides _sync_to_agent
    subagent_service.py  # extends BaseExtensionService
```

### BaseExtensionService[T]

```python
class BaseExtensionService(Generic[T]):
    # Common implementation
    install(name, content, sync_to?) -> T
    modify(name, content) -> T
    uninstall(name) -> None
    uninstall_from_agent(name, agent) -> None
    import_from_agent(agent, name?) -> T
    import_all_from_agent(agent) -> list[T]
    list_items(page, page_size, search?) -> PaginatedResult[T]
    get_item(name) -> T
    sync_to_agents(name, agents) -> dict[str, bool]
    invalidate() -> None

    # Subclass overrides
    _create_item(name, content) -> T          # parse content into domain model
    _sync_to_agent(name, agent_store) -> None # default: file copy
    _unsync_from_agent(name, agent_store) -> None
```

HookService overrides `_sync_to_agent` for JSON merge with `_vibelens_managed` tag. The other three use default file copy.

### catalog_resolver.py (refactored from catalog_install.py)

- `resolve_installable_content(item) -> ResolvedContent` — extract content from catalog item (inline content, GitHub download)
- `install_from_catalog(item_id, targets, overwrite)` — full install flow: resolve then route to type service's `install()`
- MCP config merge logic stays here (not part of the four type services)

### repo Type

Display-only in catalog. Shows `install_command` for user to execute manually. No VibeLens-managed install/uninstall.

### deps.py

Update singleton getters to point to refactored service classes. Adapt `import_all_agents()` call in app lifespan.

### api/__init__.py

Remove 5 old router includes (`skill_router`, `command_router`, `hook_router`, `subagent_router`, `extensions_router`). Replace with single `extensions_router` from `api/extensions/__init__.py`.

### BaseExtensionService Constructor

```python
class BaseExtensionService(Generic[T]):
    def __init__(
        self,
        central_store: BaseExtensionStore[T],
        agent_stores: dict[str, BaseExtensionStore[T]],
        cache_ttl: int = 300,
    ): ...
```

Accepts existing `BaseExtensionStore[T]` instances. No changes to storage layer needed.

## Frontend Refactor

### API Client Layer (new)

```
frontend/src/api/
    extensions.ts    # catalog + all 4 type CRUD request functions
```

```ts
// Factory: create once in AppContext, consume everywhere via useExtensionsClient()
export function createExtensionsClient(fetchFn: FetchFn) {
    // Catalog
    const catalog = {
        list(params) { ... },
        getMeta() { ... },
        getItem(id) { ... },
        getContent(id) { ... },
        install(id, targets, overwrite?) { ... },
    }

    // Sync targets with simple cache + invalidate
    const syncTargets = {
        get(): Promise<Record<string, ExtensionSyncTarget[]>> { ... },
        invalidate() { ... },
    }

    // Generic CRUD per type
    function createTypeApi(type: string) {
        return { list, get, install, modify, uninstall, syncToAgents, unsyncFromAgent, importFromAgent }
    }

    return {
        catalog,
        syncTargets,
        skills: createTypeApi("skills"),
        commands: createTypeApi("commands"),
        hooks: createTypeApi("hooks"),
        subagents: createTypeApi("subagents"),
    }
}
```

- `createExtensionsClient(fetchWithToken)` called once in `AppContext`
- Components access via `useExtensionsClient()` hook, no need to pass `fetchFn` per call
- `syncTargets` provides cached data with `invalidate()` after install/uninstall
- Type definitions stay in `types.ts`

### Component Consolidation

| Current | After |
|---------|-------|
| `cards.tsx` `ExtensionCard` (local) | Delete, unify into `extension-card.tsx` |
| `cards.tsx` `ExtensionDetailPopup` (local) | Delete, unify into `extension-detail-view.tsx` |
| `local-extensions-tab.tsx` (skill only) | Rewrite: logic supports all types, UI v1 shows skill filter only |
| `extension-endpoints.ts` | Delete, URL building moves to `api/extensions.ts` |
| `useSyncTargetsByType` (2 instances) | Delete, replaced by `client.syncTargets` with cache + invalidate |

### Local Management Tab

- Unified list with type filter at top
- Logic fully supports all four types
- v1 only renders skill filter; other type filters exist in code but are hidden
- Hook: v1 supports view + uninstall only, no edit/create

### Personalization Result Install Paths

| Source | Install method | Endpoint |
|--------|---------------|----------|
| Recommendation | Same as catalog install | `POST /api/extensions/catalog/{item_id}/install` |
| Creation | Install new skill locally | `POST /api/extensions/skills` |
| Evolution | Modify existing skill | `PUT /api/extensions/skills/{name}` |

"""Service layer for ExtensionCollection.

Sits in ``services/extensions/`` because collections compose per-type
extension services (skill, command, etc.) for batch install. The service is
not a ``BaseExtensionService`` subclass — collections are not an
``AgentExtensionType`` — but it lives here for discoverability.
"""

import json
from datetime import datetime, timezone
from typing import Any

from vibelens.models.collection import ExtensionCollection, ExtensionCollectionItem
from vibelens.models.enums import AgentExtensionType
from vibelens.services.extensions.base_service import DEFAULT_LINK_TYPE, LinkType
from vibelens.storage.extension.collection_store import CollectionStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Bump when the export JSON shape changes incompatibly. Old payloads then
# fail import with "unsupported export version" instead of silent corruption.
EXPORT_VERSION = 1


class CollectionService:
    """CRUD + batch install for ExtensionCollections.

    ``services_by_type`` maps extension type to its corresponding service so the
    collection installer can fan out to per-type install/sync logic.
    """

    def __init__(
        self, store: CollectionStore, services_by_type: dict[AgentExtensionType, Any]
    ) -> None:
        self._store = store
        self._services = services_by_type

    def create(
        self,
        name: str,
        description: str,
        items: list[tuple[AgentExtensionType, str]],
        tags: list[str],
    ) -> ExtensionCollection:
        """Create a new collection. Raises ``ValueError`` if the name already exists."""
        if self._store.read(name) is not None:
            raise ValueError(f"collection already exists: {name!r}")
        now = datetime.now(timezone.utc)
        collection = ExtensionCollection(
            name=name,
            description=description,
            items=[ExtensionCollectionItem(extension_type=t, name=n) for t, n in items],
            tags=tags,
            created_at=now,
            updated_at=now,
        )
        self._store.write(collection)
        return collection

    def get(self, name: str) -> ExtensionCollection:
        """Return the collection. Raises ``KeyError`` if missing."""
        coll = self._store.read(name)
        if coll is None:
            raise KeyError(name)
        return coll

    def list_all(self) -> list[ExtensionCollection]:
        """Return all collections (sorted by name)."""
        names = self._store.list_names()
        return [c for c in (self._store.read(n) for n in names) if c is not None]

    def update(
        self,
        name: str,
        description: str | None = None,
        items: list[tuple[AgentExtensionType, str]] | None = None,
        tags: list[str] | None = None,
    ) -> ExtensionCollection:
        """Partial update. Fields left as None retain their old values."""
        existing = self.get(name)
        new_items = (
            [ExtensionCollectionItem(extension_type=t, name=n) for t, n in items]
            if items is not None
            else existing.items
        )
        updated = ExtensionCollection(
            name=name,
            description=description if description is not None else existing.description,
            items=new_items,
            tags=tags if tags is not None else existing.tags,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self._store.write(updated)
        return updated

    def delete(self, name: str) -> bool:
        """Delete a collection. Returns False if it didn't exist."""
        return self._store.delete(name)

    def install_to_agents(
        self, collection_name: str, agents: list[str], link_type: LinkType = DEFAULT_LINK_TYPE
    ) -> dict[str, dict[str, str]]:
        """Install every item in a collection to every named agent.

        Per-item, per-agent status:
          - ``"ok"``: synced successfully
          - ``"missing"``: extension not found in central store
          - ``"failed"``: sync raised but was caught
          - any other string: the exception message
        """
        collection = self.get(collection_name)
        results: dict[str, dict[str, str]] = {}
        for item in collection.items:
            service = self._services.get(item.extension_type)
            per_agent: dict[str, str] = {}
            if service is None:
                per_agent["error"] = f"no service for type {item.extension_type.value}"
                results[item.name] = per_agent
                continue
            for agent in agents:
                try:
                    outcome = service.sync_to_agents(item.name, [agent], link_type=link_type)
                    per_agent[agent] = "ok" if outcome.get(agent) else "failed"
                except FileNotFoundError:
                    per_agent[agent] = "missing"
                except (OSError, KeyError, ValueError) as exc:
                    per_agent[agent] = str(exc)
            results[item.name] = per_agent
        return results

    def export_json(self, name: str) -> str:
        """Serialize a collection as a versioned JSON payload."""
        collection = self.get(name)
        payload = {
            "version": EXPORT_VERSION,
            "name": collection.name,
            "description": collection.description,
            "items": [
                {"extension_type": it.extension_type.value, "name": it.name}
                for it in collection.items
            ],
            "tags": collection.tags,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    def import_json(self, payload: str) -> ExtensionCollection:
        """Create a collection from an export_json payload."""
        data = json.loads(payload)
        if data.get("version") != EXPORT_VERSION:
            raise ValueError(f"unsupported export version: {data.get('version')!r}")
        return self.create(
            name=data["name"],
            description=data.get("description", ""),
            items=[
                (AgentExtensionType(it["extension_type"]), it["name"])
                for it in data.get("items", [])
            ],
            tags=data.get("tags", []),
        )

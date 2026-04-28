import { useEffect, useState } from "react";
import { Layers, Loader2, Plus } from "lucide-react";
import { useExtensionsClient } from "../../../../app";
import type { Collection } from "../../../../api/extensions";
import { CollectionDetailView } from "./collection-detail-view";
import { errorMessage } from "../../../../utils";

interface CollectionsTabProps {
  refreshTrigger?: number;
  onDetailOpenChange?: (open: boolean) => void;
}

export function CollectionsTab({
  refreshTrigger = 0,
  onDetailOpenChange,
}: CollectionsTabProps = {}) {
  const client = useExtensionsClient();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  function selectCollection(next: string | null) {
    if (next === selected) return;
    setSelected(next);
    onDetailOpenChange?.(next !== null);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    client.collections
      .list()
      .then((res) => {
        if (!cancelled) setCollections(res.items);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, refreshTrigger]);

  async function handleCreate() {
    if (!newName.trim()) return;
    try {
      const created = await client.collections.create({
        name: newName.trim(),
        description: newDescription.trim(),
        items: [],
        tags: [],
      });
      setCollections((prev) => [...prev, created]);
      setNewName("");
      setNewDescription("");
      setCreating(false);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (selected) {
    const cached = collections.find((c) => c.name === selected);
    return (
      <CollectionDetailView
        name={selected}
        initialCollection={cached}
        onBack={() => selectCollection(null)}
        onChanged={() => {
          setCollections((prev) => prev.filter((c) => c.name !== selected));
          selectCollection(null);
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-secondary">
          Group skills, commands, subagents, and hooks into reusable bundles.
        </p>
        <button
          onClick={() => setCreating(true)}
          className="px-3 py-1.5 text-xs rounded-md bg-accent-teal-subtle border border-accent-teal text-accent-teal flex items-center gap-1.5"
        >
          <Plus className="w-3.5 h-3.5" /> New collection
        </button>
      </div>

      {creating && (
        <div className="p-3 border border-card rounded-md space-y-2">
          <input
            placeholder="kebab-case-name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="w-full px-2 py-1 text-sm border border-card rounded"
          />
          <input
            placeholder="Description"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            className="w-full px-2 py-1 text-sm border border-card rounded"
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setCreating(false)}
              className="px-2 py-1 text-xs text-muted"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              className="px-3 py-1 text-xs rounded bg-accent-teal text-white"
            >
              Create
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-secondary text-sm">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading collections...
        </div>
      ) : error ? (
        <p className="text-sm text-rose-600">{error}</p>
      ) : collections.length === 0 ? (
        <p className="text-sm text-muted">
          No collections yet. Create one to group extensions for batch installs.
        </p>
      ) : (
        <ul className="space-y-2">
          {collections.map((c) => (
            <li key={c.name}>
              <button
                onClick={() => selectCollection(c.name)}
                className="w-full text-left p-3 border border-card rounded-md hover:bg-elevated transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-accent-teal" />
                  <span className="font-medium">{c.name}</span>
                  <span className="text-xs text-muted">
                    {c.items.length} {c.items.length === 1 ? "item" : "items"}
                  </span>
                </div>
                {c.description && (
                  <p className="text-xs text-secondary mt-1">{c.description}</p>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

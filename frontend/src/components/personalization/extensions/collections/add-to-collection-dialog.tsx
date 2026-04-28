import { useEffect, useState } from "react";
import { useExtensionsClient } from "../../../../app";
import type { Collection, CollectionItemRef } from "../../../../api/extensions";
import { errorMessage } from "../../../../utils";

interface AddToCollectionDialogProps {
  itemRefs: CollectionItemRef[];
  onClose: () => void;
  onAdded: () => void;
}

export function AddToCollectionDialog({
  itemRefs,
  onClose,
  onAdded,
}: AddToCollectionDialogProps) {
  const client = useExtensionsClient();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.collections
      .list()
      .then((res) => setCollections(res.items))
      .catch((err) => setError(errorMessage(err)));
  }, [client]);

  async function handleAdd() {
    if (!selected) return;
    setSubmitting(true);
    try {
      const existing = await client.collections.get(selected);
      const merged = [
        ...existing.items,
        ...itemRefs.filter(
          (it) =>
            !existing.items.some(
              (e) =>
                e.extension_type === it.extension_type && e.name === it.name,
            ),
        ),
      ];
      await client.collections.update(selected, { items: merged });
      onAdded();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-base p-6 rounded-lg max-w-md w-full mx-4 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold">
          Add {itemRefs.length} {itemRefs.length === 1 ? "item" : "items"} to a collection
        </h3>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        {collections.length === 0 ? (
          <p className="text-sm text-muted">
            No collections yet. Create one in the Collections tab first.
          </p>
        ) : (
          <ul className="space-y-1 max-h-64 overflow-auto">
            {collections.map((c) => (
              <li key={c.name}>
                <label className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-elevated cursor-pointer">
                  <input
                    type="radio"
                    name="collection"
                    checked={selected === c.name}
                    onChange={() => setSelected(c.name)}
                  />
                  <span>{c.name}</span>
                  <span className="text-xs text-muted">({c.items.length})</span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs text-secondary">
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={!selected || submitting}
            className="px-3 py-1.5 text-xs rounded-md bg-accent-teal text-white disabled:opacity-50"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  );
}

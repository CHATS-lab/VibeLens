import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Download, Loader2, Trash2 } from "lucide-react";
import { useExtensionsClient } from "../../../../app";
import type { Collection, LinkType } from "../../../../api/extensions";
import type { ExtensionSyncTarget } from "../../../../types";
import { SOURCE_LABELS } from "../../constants";
import { LinkTypeToggle } from "../link-type-toggle";
import { CollectionExportDialog } from "./collection-export-dialog";

interface CollectionDetailViewProps {
  name: string;
  /** Optional pre-fetched collection — skips an API round-trip on open. */
  initialCollection?: Collection;
  onBack: () => void;
  onChanged: () => void;
}

export function CollectionDetailView({
  name,
  initialCollection,
  onBack,
  onChanged,
}: CollectionDetailViewProps) {
  const client = useExtensionsClient();
  const [collection, setCollection] = useState<Collection | null>(
    initialCollection ?? null,
  );
  const [error, setError] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installResults, setInstallResults] = useState<
    Record<string, Record<string, string>> | null
  >(null);
  const [showExport, setShowExport] = useState(false);
  const [availableAgents, setAvailableAgents] = useState<ExtensionSyncTarget[]>([]);
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set());
  const [linkType, setLinkType] = useState<LinkType>("symlink");

  useEffect(() => {
    if (initialCollection && initialCollection.name === name) return;
    client.collections
      .get(name)
      .then(setCollection)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [client, name, initialCollection]);

  useEffect(() => {
    client.syncTargets
      .get()
      .then((map) => {
        const merged = new Map<string, ExtensionSyncTarget>();
        for (const targets of Object.values(map)) {
          for (const target of targets) {
            if (!merged.has(target.agent)) merged.set(target.agent, target);
          }
        }
        setAvailableAgents(Array.from(merged.values()));
      })
      .catch(() => setAvailableAgents([]));
  }, [client]);

  const toggleAgent = useCallback((agent: string) => {
    setSelectedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agent)) next.delete(agent);
      else next.add(agent);
      return next;
    });
  }, []);

  const canInstall = useMemo(
    () =>
      collection !== null &&
      collection.items.length > 0 &&
      selectedAgents.size > 0,
    [collection, selectedAgents],
  );

  async function handleInstall() {
    if (!collection || selectedAgents.size === 0) return;
    setInstalling(true);
    try {
      const res = await client.collections.install(
        collection.name,
        Array.from(selectedAgents),
        linkType,
      );
      setInstallResults(res.results);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstalling(false);
    }
  }

  async function handleDelete() {
    if (!collection) return;
    if (
      !window.confirm(
        `Delete collection "${collection.name}"? Items will not be uninstalled.`,
      )
    ) {
      return;
    }
    try {
      await client.collections.delete(collection.name);
      onChanged();
      onBack();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!collection) return <p className="text-sm text-secondary">Loading...</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button
          onClick={onBack}
          className="text-sm text-secondary flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="flex gap-2">
          <button
            onClick={() => setShowExport(true)}
            className="px-3 py-1.5 text-xs border border-card rounded-md flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" /> Export
          </button>
          <button
            onClick={handleDelete}
            className="px-3 py-1.5 text-xs border border-rose-200 text-rose-600 rounded-md flex items-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" /> Delete
          </button>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-semibold">{collection.name}</h2>
        {collection.description && (
          <p className="text-sm text-secondary mt-1">{collection.description}</p>
        )}
      </div>

      <div>
        <p className="text-xs font-medium text-secondary mb-2">
          {collection.items.length}{" "}
          {collection.items.length === 1 ? "item" : "items"}
        </p>
        {collection.items.length === 0 ? (
          <p className="text-xs text-muted">
            No items yet. Add some from the Local tab using multi-select.
          </p>
        ) : (
          <ul className="space-y-1">
            {collection.items.map((item) => (
              <li
                key={`${item.extension_type}-${item.name}`}
                className="flex items-center gap-2 px-3 py-2 border border-card rounded-md text-sm"
              >
                <span className="px-2 py-0.5 text-xs rounded bg-elevated border border-card text-secondary">
                  {item.extension_type}
                </span>
                <span>{item.name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-card pt-4 space-y-3">
        <div>
          <p className="text-xs font-medium text-secondary mb-2">Install to agents</p>
          {availableAgents.length === 0 ? (
            <p className="text-xs text-muted">No agents detected on this machine.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {availableAgents.map((target) => (
                <label
                  key={target.agent}
                  className={`flex items-center gap-1.5 px-2 py-1 text-xs border rounded-md cursor-pointer ${
                    selectedAgents.has(target.agent)
                      ? "bg-accent-teal-subtle border-accent-teal text-accent-teal"
                      : "border-card text-muted hover:text-secondary"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedAgents.has(target.agent)}
                    onChange={() => toggleAgent(target.agent)}
                    className="sr-only"
                  />
                  {SOURCE_LABELS[target.agent] || target.agent}
                </label>
              ))}
            </div>
          )}
        </div>

        <LinkTypeToggle value={linkType} onChange={setLinkType} withHelp={false} />

        <button
          onClick={handleInstall}
          disabled={installing || !canInstall}
          className="px-3 py-1.5 text-xs rounded-md bg-accent-teal text-white disabled:opacity-50 flex items-center gap-1.5"
        >
          {installing ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            `Install (${selectedAgents.size})`
          )}
        </button>
        {installResults && (
          <pre className="mt-2 p-2 text-xs bg-elevated rounded">
            {JSON.stringify(installResults, null, 2)}
          </pre>
        )}
      </div>

      {showExport && (
        <CollectionExportDialog
          collectionName={collection.name}
          onClose={() => setShowExport(false)}
        />
      )}
    </div>
  );
}

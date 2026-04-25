import { Check, Download, Loader2, Monitor, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useExtensionsClient } from "../../app";
import type { AgentCapability, LinkType } from "../../api/extensions";
import type { ExtensionSyncTarget } from "../../types";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../ui/modal";
import { normalizeSourceType, SOURCE_LABELS } from "./constants";
import { TYPE_PLURAL } from "./extensions/extension-constants";
import { LinkTypeToggle } from "./extensions/link-type-toggle";

function centralStoreLabel(type: string): string {
  if (type === "hook") return "~/.vibelens/hooks/";
  return `~/.vibelens/${type}s/`;
}

interface InstallTargetDialogProps {
  extensionName: string;
  /**
   * Human-readable type key (e.g. "skill", "subagent", "command", "hook").
   * Used for central-store label, body copy, count suffix, and for
   * fetching installed_in via the extensions client.
   */
  typeKey: string;
  syncTargets: ExtensionSyncTarget[];
  /**
   * Called with the agents to sync TO (add), agents to sync OFF (remove),
   * and the user-chosen link type. The caller is responsible for issuing
   * the POST/DELETE requests.
   */
  onInstall: (toAdd: string[], toRemove: string[], linkType: LinkType) => void;
  onCancel: () => void;
  /**
   * Agent keys that already contain this extension. When omitted, the dialog
   * fetches the item detail on mount to populate this.
   * Used to compute the diff between current and desired state.
   */
  installedIn?: string[];
}

/**
 * Dialog asking users which agent interfaces should contain this extension.
 * Uses diff semantics: each row shows its current state (installed or not),
 * and clicking toggles the desired future state. The submit handler receives
 * both the add list and the remove list so the caller can apply the diff.
 */
export function InstallTargetDialog({
  extensionName,
  typeKey,
  syncTargets,
  onInstall,
  onCancel,
  installedIn,
}: InstallTargetDialogProps) {
  const client = useExtensionsClient();
  const [fetchedInstalled, setFetchedInstalled] = useState<string[] | null>(null);
  const [capabilities, setCapabilities] = useState<AgentCapability[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await client.agents.list();
        if (!cancelled) setCapabilities(data.agents);
      } catch {
        /* best-effort */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client]);

  const supportedAgentKeys = useMemo(() => {
    if (capabilities === null) return null;
    return new Set(
      capabilities
        .filter((a) => a.installed && a.supported_types.includes(typeKey))
        .map((a) => a.key),
    );
  }, [capabilities, typeKey]);

  // Auto-fetch installed_in if caller didn't provide it.
  useEffect(() => {
    if (installedIn !== undefined) return;
    const typePlural = TYPE_PLURAL[typeKey];
    if (!typePlural) return;
    let cancelled = false;
    (async () => {
      try {
        const typeApi = client[typePlural as keyof typeof client] as {
          get: (name: string) => Promise<{ item: Record<string, unknown> }>;
        };
        const data = await typeApi.get(extensionName);
        if (cancelled) return;
        const item = data.item as { installed_in?: string[] };
        setFetchedInstalled(item.installed_in ?? []);
      } catch {
        /* best-effort — extension may not exist yet (fresh install) */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, installedIn, extensionName, typeKey]);

  const installedSet = useMemo(
    () => new Set(installedIn ?? fetchedInstalled ?? []),
    [installedIn, fetchedInstalled],
  );
  // Agents the user has toggled away from their current installed state.
  const [toggled, setToggled] = useState<Set<string>>(() => new Set());
  const [installing, setInstalling] = useState(false);
  const [linkType, setLinkType] = useState<LinkType>("symlink");

  const toggleTarget = useCallback((key: string) => {
    setToggled((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  // Desired state = installed XOR toggled. Diff against current.
  // Keys are normalized to plain lowercase (e.g. "claude") so the backend
  // receives valid platform install keys, not raw enum strings.
  const { toAdd, toRemove } = useMemo(() => {
    const add: string[] = [];
    const remove: string[] = [];
    for (const key of toggled) {
      const normalized = normalizeSourceType(key);
      if (installedSet.has(key)) remove.push(normalized);
      else add.push(normalized);
    }
    return { toAdd: add, toRemove: remove };
  }, [toggled, installedSet]);

  const centralOnly = syncTargets.length === 0;

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    // Central-only: no sync targets exist, install to default platform
    const effectiveAdd = centralOnly && toAdd.length === 0 ? ["claude"] : toAdd;
    await onInstall(effectiveAdd, toRemove, linkType);
  }, [onInstall, toAdd, toRemove, centralOnly, linkType]);

  const totalChanges = toAdd.length + toRemove.length;
  const buttonLabel = (() => {
    if (centralOnly) return "Install to Central Store";
    if (totalChanges === 0) return "No changes";
    if (toAdd.length > 0 && toRemove.length === 0) {
      return `Install & Sync to ${toAdd.length} interface${toAdd.length !== 1 ? "s" : ""}`;
    }
    if (toRemove.length > 0 && toAdd.length === 0) {
      return `Uninstall from ${toRemove.length} interface${toRemove.length !== 1 ? "s" : ""}`;
    }
    return `Update ${totalChanges} interface${totalChanges !== 1 ? "s" : ""}`;
  })();

  return (
    <Modal onClose={onCancel} maxWidth="max-w-md">
      <ModalHeader title={`Install "${extensionName}"`} onClose={onCancel} />
      <ModalBody>
        <p className="text-sm text-muted leading-relaxed">
          The {typeKey} will be saved to the VibeLens central store. Click an agent to sync or unsync:
        </p>

        {/* Central store — always selected */}
        <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-teal-50 dark:bg-teal-900/15 border border-teal-200 dark:border-teal-800/40">
          <Check className="w-4 h-4 text-accent-teal shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-secondary">Central Store</p>
            <p className="text-xs text-dimmed">{centralStoreLabel(typeKey)}</p>
          </div>
          <span className="text-[10px] text-accent-teal font-medium px-1.5 py-0.5 rounded bg-accent-teal-subtle">Always</span>
        </div>

        {syncTargets.length > 0 && (
          <div className="space-y-2">
            {syncTargets.map((target) => {
              const normalizedAgent = normalizeSourceType(target.agent);
              const supportsType =
                supportedAgentKeys === null ||
                supportedAgentKeys.has(normalizedAgent);
              const isInstalled = installedSet.has(target.agent);
              const isToggled = toggled.has(target.agent);
              // Four visual states based on (isInstalled, isToggled):
              // installed + not toggled = emerald "Installed" (keep)
              // installed + toggled     = rose "Will uninstall"
              // !installed + toggled    = teal "Will install"
              // !installed + not toggled = neutral (no change)
              const willUninstall = isInstalled && isToggled;
              const willInstall = !isInstalled && isToggled;
              const isCurrent = isInstalled && !isToggled;

              const rowClass = willUninstall
                ? "bg-rose-50 dark:bg-rose-900/15 border-rose-200 dark:border-rose-800/40 hover:border-rose-400 dark:hover:border-rose-700"
                : isCurrent
                  ? "bg-emerald-50 dark:bg-emerald-900/15 border-emerald-200 dark:border-emerald-800/40 hover:border-emerald-400 dark:hover:border-emerald-700"
                  : willInstall
                    ? "bg-control border-teal-600/40"
                    : "bg-subtle border-card hover:border-hover";

              const boxClass = willUninstall
                ? "bg-rose-600 border-rose-500"
                : isCurrent
                  ? "bg-emerald-600 border-emerald-500"
                  : willInstall
                    ? "bg-teal-600 border-teal-500"
                    : "border-hover";

              const boxIcon = willUninstall
                ? <X className="w-3 h-3 text-white" />
                : isCurrent || willInstall
                  ? <Check className="w-3 h-3 text-white" />
                  : null;

              const iconColor = willUninstall
                ? "text-accent-rose"
                : isCurrent
                  ? "text-accent-emerald"
                  : "text-muted";

              const badge = willUninstall
                ? { label: "Will uninstall", cls: "bg-accent-rose-subtle text-accent-rose border-accent-rose-border" }
                : isCurrent
                  ? { label: "Installed", cls: "bg-accent-emerald-subtle text-accent-emerald border-accent-emerald-border" }
                  : willInstall
                    ? { label: "Will install", cls: "bg-accent-teal-subtle text-accent-teal border-accent-teal-border" }
                    : null;

              const unsupportedTooltip = supportsType
                ? undefined
                : `${SOURCE_LABELS[normalizedAgent] || target.agent} does not support ${typeKey}`;

              return (
                <button
                  key={target.agent}
                  onClick={() => supportsType && toggleTarget(target.agent)}
                  disabled={!supportsType}
                  title={unsupportedTooltip}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border transition text-left ${rowClass} ${!supportsType ? "opacity-40 cursor-not-allowed" : ""}`}
                >
                  <div
                    className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition ${boxClass}`}
                  >
                    {boxIcon}
                  </div>
                  <Monitor className={`w-4 h-4 shrink-0 ${iconColor}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-secondary flex items-center gap-2 flex-wrap">
                      {SOURCE_LABELS[normalizedAgent] || target.agent}
                      {badge && supportsType && (
                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${badge.cls}`}>
                          {badge.label}
                        </span>
                      )}
                      {!supportsType && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border bg-subtle text-dimmed border-card">
                          Not supported
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-dimmed truncate">{target.dir}</p>
                  </div>
                  <span className="text-[10px] text-dimmed">
                    {target.count} {typeKey}{target.count !== 1 ? "s" : ""}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {syncTargets.length === 0 && (
          <p className="text-xs text-dimmed italic">
            No agent interfaces detected. The {typeKey} will only be saved to the central store.
          </p>
        )}

        {syncTargets.length > 0 && (
          <div className="pt-3 border-t border-card">
            <LinkTypeToggle value={linkType} onChange={setLinkType} />
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onCancel}
          disabled={installing}
          className="px-3 py-1.5 text-xs text-muted hover:text-secondary border border-card hover:border-hover rounded transition disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={handleInstall}
          disabled={installing || (!centralOnly && totalChanges === 0)}
          className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {installing
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : <Download className="w-3.5 h-3.5" />}
          {buttonLabel}
        </button>
      </ModalFooter>
    </Modal>
  );
}

import {
  Check,
  Clock,
  Download,
  ExternalLink,
  GitFork,
  Loader2,
  Package,
  Scale,
  Share2,
  Star,
  Trash2,
} from "lucide-react";
import { formatCount, formatRelativeDate } from "./extension-format";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useExtensionsClient } from "../../../app";
import { typeApi, type TypeApiKey } from "../../../api/extensions";
import type {
  ExtensionItemSummary,
  ExtensionSyncTarget,
  ExtensionTreeEntry,
} from "../../../types";
import { InstallTargetDialog } from "../install-target-dialog";
import { useDemoGuard } from "../../../hooks/use-demo-guard";
import { InstallLocallyDialog } from "../../install-locally-dialog";
import { Tooltip } from "../../ui/tooltip";
import { CopyButton } from "../../ui/copy-button";
import { DetailShell, pickPrimaryPath } from "./detail-shell";
import { TypeBadge } from "./extension-card";
import {
  ITEM_TYPE_ICON_COLORS,
  ITEM_TYPE_ICONS,
  PLATFORM_LABELS,
  TYPE_PLURAL,
} from "./extension-constants";
import { TopicsRow } from "./topics-row";
import { UninstallExtensionDialog } from "./uninstall-extension-dialog";
import { SOURCE_LABELS } from "../constants";

interface CatalogDetailViewProps {
  item: ExtensionItemSummary;
  isInstalled: boolean;
  onBack: () => void;
  onInstalled: (itemId: string) => void;
  syncTargets?: ExtensionSyncTarget[];
}

export function ExtensionDetailView({
  item,
  isInstalled,
  onBack,
  onInstalled,
  syncTargets = [],
}: CatalogDetailViewProps) {
  const client = useExtensionsClient();

  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(isInstalled);
  const [installError, setInstallError] = useState<string | null>(null);
  const [showTargetDialog, setShowTargetDialog] = useState(false);
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [descExpanded, setDescExpanded] = useState(false);
  const [descClamped, setDescClamped] = useState(false);
  const descRef = useRef<HTMLParagraphElement>(null);

  const [entries, setEntries] = useState<ExtensionTreeEntry[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  useLayoutEffect(() => {
    const el = descRef.current;
    if (el) setDescClamped(el.scrollHeight > el.clientHeight);
  }, [item.description]);

  useEffect(() => {
    let cancelled = false;
    // Clear per-item state before the new fetch so a slow request for the
    // previous item can't briefly paint stale content during an item switch.
    setEntries([]);
    setSelectedPath(null);
    setFileContent(null);
    setFileError(null);
    setFileLoading(true);
    (async () => {
      try {
        const tree = await client.catalog.getTree(item.extension_id);
        if (cancelled) return;
        setEntries(tree.entries);
        const primary = pickPrimaryPath(tree.entries, item.extension_type);
        setSelectedPath(primary);
        if (primary) {
          const file = await client.catalog.getFile(item.extension_id, primary);
          if (!cancelled) setFileContent(file.content);
        } else {
          const data = await client.catalog.getContent(item.extension_id);
          if (!cancelled) setFileContent(data.content);
        }
      } catch (err) {
        if (cancelled) return;
        // Tree fetch failed - fall back to the legacy single-file /content
        // endpoint so the user still sees something.
        try {
          const data = await client.catalog.getContent(item.extension_id);
          if (!cancelled) setFileContent(data.content);
        } catch (innerErr) {
          if (!cancelled)
            setFileError(innerErr instanceof Error ? innerErr.message : String(innerErr));
        }
      } finally {
        if (!cancelled) setFileLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, item.extension_id, item.extension_type]);

  const handleSelectPath = useCallback(
    async (path: string) => {
      setSelectedPath(path);
      setFileLoading(true);
      setFileError(null);
      try {
        const file = await client.catalog.getFile(item.extension_id, path);
        setFileContent(file.content);
      } catch (err) {
        setFileError(err instanceof Error ? err.message : String(err));
      } finally {
        setFileLoading(false);
      }
    },
    [client, item.extension_id],
  );

  const handleDialogSubmit = useCallback(
    async (toAdd: string[], toRemove: string[]) => {
      setInstalling(true);
      setInstallError(null);
      try {
        if (toAdd.length > 0) {
          await client.catalog.install(item.extension_id, toAdd, true);
        }
        const typePlural = TYPE_PLURAL[item.extension_type];
        if (toRemove.length > 0 && typePlural) {
          const api = typeApi(client, typePlural as TypeApiKey);
          for (const agent of toRemove) {
            await api.unsyncFromAgent(item.name, agent);
          }
        }
        setInstalled(toAdd.length > 0 || (installed && toRemove.length === 0));
        onInstalled(item.extension_id);
        setShowTargetDialog(false);
      } catch (err) {
        setInstallError(err instanceof Error ? err.message : String(err));
      } finally {
        setInstalling(false);
      }
    },
    [client, item.extension_id, item.extension_type, item.name, onInstalled, installed],
  );

  const handleInstall = useCallback(() => {
    guardAction(() => setShowTargetDialog(true));
  }, [guardAction]);

  const Icon = ITEM_TYPE_ICONS[item.extension_type] || Package;
  const iconColors = ITEM_TYPE_ICON_COLORS[item.extension_type] || ITEM_TYPE_ICON_COLORS.skill;
  const platformLabel = (item.platforms ?? []).map((p) => PLATFORM_LABELS[p] || p).join(", ");

  const headerContent = (
    <div className="px-6 pt-5 pb-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-4 min-w-0">
          <div className={`shrink-0 p-3 rounded-xl ${iconColors.bg}`}>
            <Icon className={`w-6 h-6 ${iconColors.text}`} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-3 flex-wrap mb-1.5">
              <TypeBadge itemType={item.extension_type} />
              <h1 className="text-xl font-bold font-mono text-primary">{item.name}</h1>
              {installed && (
                <span className="text-[10px] px-2 py-0.5 rounded bg-accent-emerald-subtle text-accent-emerald border border-accent-emerald-border font-medium">
                  Installed
                </span>
              )}
            </div>
            <p
              ref={descRef}
              className={`text-sm text-secondary leading-relaxed ${!descExpanded ? "line-clamp-3" : ""}`}
            >
              {item.description}
            </p>
            {descClamped && (
              <button
                onClick={() => setDescExpanded((v) => !v)}
                className="text-xs text-accent-teal hover:underline mt-0.5"
              >
                {descExpanded ? "Show less" : "Show more"}
              </button>
            )}
          </div>
        </div>

        <div className="shrink-0">
          {item.is_file_based &&
            (() => {
              const isHook = item.extension_type === "hook";
              return (
                <button
                  onClick={isHook ? undefined : handleInstall}
                  disabled={installing || isHook}
                  title={isHook ? "Hook install from catalog is not yet supported" : undefined}
                  className={
                    installed
                      ? "flex items-center gap-2 px-4 py-2 text-sm font-medium text-accent-emerald bg-accent-emerald-subtle hover:bg-emerald-100 dark:hover:bg-emerald-900/30 border border-accent-emerald-border rounded-lg transition disabled:opacity-50"
                      : "flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
                  }
                >
                  {installing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : installed ? (
                    <Check className="w-4 h-4" />
                  ) : (
                    <Download className="w-4 h-4" />
                  )}
                  {installed ? "Manage" : "Install"}
                </button>
              );
            })()}
        </div>
      </div>

      {installError && <p className="text-xs text-red-500 mt-2">{installError}</p>}
    </div>
  );

  const metadataContent = (
    <>
      <div className="px-6 py-3 border-t border-card/50 bg-control/30">
        <div className="flex items-center gap-4 text-xs text-muted flex-wrap">
          <span>{item.extension_type}</span>
          {platformLabel && <span className="text-secondary">{platformLabel}</span>}
          <Tooltip text={`Quality: ${Math.round(item.quality_score)}/100`}>
            <span className="flex items-center gap-1.5 cursor-help">
              <span className="inline-block w-16 h-1.5 rounded-full bg-control-hover overflow-hidden">
                <span
                  className="block h-full bg-teal-500 rounded-full"
                  style={{ width: `${item.quality_score}%` }}
                />
              </span>
              <span className="text-secondary tabular-nums">{Math.round(item.quality_score)}</span>
            </span>
          </Tooltip>
          {item.stars > 0 && (
            <span className="flex items-center gap-1">
              <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
              <span className="text-secondary tabular-nums">{formatCount(item.stars)}</span>
            </span>
          )}
          {item.forks > 0 && (
            <span className="flex items-center gap-1">
              <GitFork className="w-3 h-3" />
              <span className="text-secondary tabular-nums">{formatCount(item.forks)}</span>
            </span>
          )}
          {item.language && <span className="text-secondary">{item.language}</span>}
          {item.license && (
            <span className="flex items-center gap-1">
              <Scale className="w-3 h-3" />
              <span className="text-secondary">{item.license}</span>
            </span>
          )}
          {item.updated_at && (
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span className="text-secondary">{formatRelativeDate(item.updated_at)}</span>
            </span>
          )}
          {item.source_url && (
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-accent-cyan hover:underline underline-offset-2 transition"
            >
              Source <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
        <TopicsRow topics={item.topics} />
      </div>

      {item.install_command && (
        <div className="px-6 py-3 border-t border-card/50">
          <div className="flex items-center gap-2 bg-control/50 rounded-lg px-4 py-2.5 border border-card">
            <code className="flex-1 text-sm font-mono text-secondary overflow-x-auto">
              {item.install_command}
            </code>
            <CopyButton text={item.install_command} />
          </div>
        </div>
      )}
    </>
  );

  return (
    <>
      <DetailShell
        headerContent={headerContent}
        metadataContent={metadataContent}
        onBack={onBack}
        entries={entries}
        selectedPath={selectedPath}
        onSelectPath={handleSelectPath}
        rootLabel={item.name}
        fileContent={fileContent}
        fileError={fileError}
        loading={fileLoading}
      />

      {showTargetDialog && (
        <InstallTargetDialog
          extensionName={item.name}
          typeKey={item.extension_type}
          syncTargets={syncTargets}
          onInstall={handleDialogSubmit}
          onCancel={() => setShowTargetDialog(false)}
        />
      )}
      {showInstallDialog && <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />}
    </>
  );
}

/* ---------- Local detail view (Personalization "Local" tab) ---------- */

export type LocalExtensionKind = "skill" | "subagent" | "command" | "plugin";

const EDITABLE_KINDS: ReadonlySet<LocalExtensionKind> = new Set([
  "skill",
  "subagent",
  "command",
]);

/** Compose the on-disk install path for a synced agent.
 * Dir-based types (skill, plugin) land at ``{dir}/{name}``; single-file types
 * (subagent, command) land at ``{dir}/{name}.md``.
 */
function formatInstallPath(kind: LocalExtensionKind, dir: string, name: string): string {
  if (!dir) return "";
  const tail = kind === "subagent" || kind === "command" ? `${name}.md` : name;
  return dir.endsWith("/") ? `${dir}${tail}` : `${dir}/${tail}`;
}

interface LocalDetailViewProps {
  extensionType: LocalExtensionKind;
  name: string;
  syncTargets?: ExtensionSyncTarget[];
  onBack: () => void;
  onUninstalled: () => void;
}

export function LocalExtensionDetailView({
  extensionType,
  name,
  syncTargets = [],
  onBack,
  onUninstalled,
}: LocalDetailViewProps) {
  const client = useExtensionsClient();
  const api = typeApi(client, TYPE_PLURAL[extensionType] as TypeApiKey);

  const [entries, setEntries] = useState<ExtensionTreeEntry[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fileError, setFileError] = useState<string | null>(null);
  const [item, setItem] = useState<{
    description?: string;
    topics?: string[];
    installed_in?: string[];
  } | null>(null);
  const [uninstallOpen, setUninstallOpen] = useState(false);
  const [uninstalling, setUninstalling] = useState(false);
  const [uninstallError, setUninstallError] = useState<string | null>(null);
  const [syncInFlight, setSyncInFlight] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();

  const installedIn = item?.installed_in ?? [];
  const description = item?.description ?? "";
  const topics = item?.topics ?? [];

  const refreshItem = useCallback(async () => {
    try {
      const res = await api.get(name);
      const obj = res.item as {
        description?: string;
        topics?: string[];
        installed_in?: string[];
      };
      setItem({
        description: obj.description,
        topics: obj.topics,
        installed_in: obj.installed_in ?? [],
      });
    } catch {
      setItem({});
    }
  }, [api, name]);

  useEffect(() => {
    refreshItem();
  }, [refreshItem]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFileError(null);
    (async () => {
      try {
        const tree = await api.getTree(name);
        if (cancelled) return;
        setEntries(tree.entries);
        const primary = pickPrimaryPath(tree.entries, extensionType);
        setSelectedPath(primary);
        if (primary) {
          const file = await api.getFile(name, primary);
          if (!cancelled) setFileContent(file.content);
        }
      } catch (err) {
        if (!cancelled) setFileError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, extensionType, name]);

  const handleSelectPath = useCallback(
    async (path: string) => {
      setSelectedPath(path);
      setLoading(true);
      setFileError(null);
      try {
        const file = await api.getFile(name, path);
        setFileContent(file.content);
      } catch (err) {
        setFileError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [api, name],
  );

  // Only the central file (single-file types, or SKILL.md for skills) is safe
  // to save back via modify(). Sub-files of a dir-based type aren't writable
  // through the current API.
  const canSaveSelected =
    EDITABLE_KINDS.has(extensionType) &&
    selectedPath !== null &&
    (selectedPath === "SKILL.md" ||
      (extensionType !== "skill" && !selectedPath.includes("/")));

  const handleSaveContent = useCallback(
    async (_path: string, next: string) => {
      await api.modify(name, next);
      setFileContent(next);
      // Re-sync to every agent currently holding a copy so disk stays current.
      if (installedIn.length > 0) {
        api.syncToAgents(name, installedIn).catch(() => {});
      }
      refreshItem();
    },
    [api, installedIn, name, refreshItem],
  );

  const handleUninstallConfirm = useCallback(async () => {
    setUninstalling(true);
    setUninstallError(null);
    try {
      await api.uninstall(name);
      setUninstallOpen(false);
      onUninstalled();
    } catch (err) {
      setUninstallError(err instanceof Error ? err.message : String(err));
    } finally {
      setUninstalling(false);
    }
  }, [api, name, onUninstalled]);

  const handleSyncToggle = useCallback(
    async (agent: string) => {
      setSyncInFlight(agent);
      setSyncMessage(null);
      const target = syncTargets.find((t) => t.agent === agent);
      const label = SOURCE_LABELS[agent] || agent;
      const path = formatInstallPath(extensionType, target?.dir ?? "", name);
      try {
        if (installedIn.includes(agent)) {
          await api.unsyncFromAgent(name, agent);
          setSyncMessage(path ? `Removed from ${label} (${path})` : `Removed from ${label}`);
        } else {
          const data = await api.syncToAgents(name, [agent]);
          const ok = (data.results as Record<string, boolean>)?.[agent] === true;
          if (ok) {
            setSyncMessage(path ? `Installed to ${label} at ${path}` : `Installed to ${label}`);
          } else {
            setSyncMessage(`Failed to sync to ${label}`);
          }
        }
        await refreshItem();
      } catch (err) {
        setSyncMessage(err instanceof Error ? err.message : String(err));
      } finally {
        setSyncInFlight(null);
      }
    },
    [api, extensionType, installedIn, name, refreshItem, syncTargets],
  );

  const LocalIcon = ITEM_TYPE_ICONS[extensionType] || Package;
  const localIconColors = ITEM_TYPE_ICON_COLORS[extensionType] || ITEM_TYPE_ICON_COLORS.skill;

  const localHeader = (
    <div className="px-6 pt-5 pb-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-4 min-w-0 flex-1">
          <div className={`shrink-0 p-3 rounded-xl ${localIconColors.bg}`}>
            <LocalIcon className={`w-6 h-6 ${localIconColors.text}`} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3 flex-wrap mb-1.5">
              <TypeBadge itemType={extensionType} />
              <h1 className="text-xl font-bold font-mono text-primary">{name}</h1>
            </div>
            {description ? (
              <p className="text-sm text-secondary leading-relaxed">{description}</p>
            ) : (
              <p className="text-sm text-muted italic">No description</p>
            )}
          </div>
        </div>
        <div className="shrink-0">
          <button
            onClick={() => guardAction(() => setUninstallOpen(true))}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-rose-600 dark:text-rose-300 bg-rose-50 dark:bg-rose-900/20 hover:bg-rose-100 dark:hover:bg-rose-900/30 border border-rose-200 dark:border-rose-800/40 rounded-lg transition"
          >
            <Trash2 className="w-4 h-4" />
            Uninstall
          </button>
        </div>
      </div>
      {uninstallError && <p className="text-xs text-red-500 mt-2">{uninstallError}</p>}
    </div>
  );

  const localMetadata = (
    <>
      {topics.length > 0 && (
        <div className="px-6 py-3 border-t border-card/50 bg-control/30">
          <TopicsRow topics={topics} />
        </div>
      )}
      {syncTargets.length > 0 && (
        <div className="px-6 py-3 border-t border-card/50">
          <div className="flex items-center gap-1.5 mb-2.5">
            <Share2 className={`w-3.5 h-3.5 ${localIconColors.text}`} />
            <span className="text-xs font-semibold text-secondary">Sync to Agents</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {syncTargets.map((target) => {
              const isSynced = installedIn.includes(target.agent);
              const hasDir = !!target.dir;
              const label = SOURCE_LABELS[target.agent] || target.agent;
              const busy = syncInFlight === target.agent;
              const tooltipText = isSynced
                ? `Click to remove from ${label}`
                : hasDir
                  ? `Sync to ${target.dir}`
                  : `${label} not installed on this system`;
              return (
                <Tooltip key={target.agent} text={tooltipText}>
                  <button
                    onClick={() => guardAction(() => handleSyncToggle(target.agent))}
                    disabled={busy || (!isSynced && !hasDir)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full transition ${
                      isSynced
                        ? "bg-emerald-600 text-white dark:bg-emerald-500 hover:bg-emerald-500"
                        : hasDir
                          ? "bg-control text-secondary border border-card hover:border-accent-teal/40 hover:text-accent-teal"
                          : "bg-subtle text-faint border border-card cursor-not-allowed opacity-50"
                    }`}
                  >
                    {busy ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : isSynced ? (
                      <Check className="w-3 h-3" />
                    ) : (
                      <Share2 className="w-3 h-3 opacity-50" />
                    )}
                    {label}
                  </button>
                </Tooltip>
              );
            })}
          </div>
          {syncMessage && (
            <p className="text-xs text-emerald-600/80 dark:text-emerald-400/70 mt-2">
              {syncMessage}
            </p>
          )}
        </div>
      )}
    </>
  );

  return (
    <>
      <DetailShell
        headerContent={localHeader}
        metadataContent={localMetadata}
        onBack={onBack}
        entries={entries}
        selectedPath={selectedPath}
        onSelectPath={handleSelectPath}
        rootLabel={name}
        fileContent={fileContent}
        fileError={fileError}
        loading={loading}
        initialCollapsed
        onSaveContent={canSaveSelected ? handleSaveContent : undefined}
      />
      {uninstallOpen && (
        <UninstallExtensionDialog
          entityLabel={extensionType}
          name={name}
          installedIn={installedIn}
          loading={uninstalling}
          onConfirm={handleUninstallConfirm}
          onCancel={() => setUninstallOpen(false)}
        />
      )}
      {showInstallDialog && <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />}
    </>
  );
}

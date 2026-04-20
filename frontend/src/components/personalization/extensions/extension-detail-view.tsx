import {
  Check,
  Clock,
  Download,
  ExternalLink,
  GitFork,
  Loader2,
  Package,
  Scale,
  Star,
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

export { LocalExtensionDetailView, type LocalExtensionKind } from "./local-extension-detail-view";

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

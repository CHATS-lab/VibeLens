import {
  Anchor,
  ArrowLeft,
  Bot,
  Check,
  Clock,
  Download,
  ExternalLink,
  GitFork,
  Loader2,
  Package,
  Scale,
  Server,
  Star,
  Terminal,
} from "lucide-react";
import { formatCount, formatRelativeDate } from "./extension-format";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useExtensionsClient } from "../../../app";
import type { ExtensionItemSummary, ExtensionSyncTarget } from "../../../types";
import { InstallTargetDialog } from "../install-target-dialog";
import { useDemoGuard } from "../../../hooks/use-demo-guard";
import { InstallLocallyDialog } from "../../install-locally-dialog";
import { Tooltip } from "../../ui/tooltip";
import { CopyButton } from "../../ui/copy-button";
import { ExtensionDetailContent, stripFrontmatter, type TocEntry } from "./extension-detail-content";
import { TypeBadge } from "./extension-card";
import { ITEM_TYPE_ICON_COLORS, PLATFORM_LABELS } from "./extension-constants";

const ITEM_TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  skill: Package,
  subagent: Bot,
  command: Terminal,
  hook: Anchor,
  repo: Server,
};

const TYPE_PLURAL: Record<string, string> = {
  skill: "skills",
  subagent: "subagents",
  command: "commands",
  hook: "hooks",
};

function extractTocEntries(markdown: string): TocEntry[] {
  const regex = /^(#{1,3})\s+(.+)$/gm;
  const entries: TocEntry[] = [];
  let match: RegExpExecArray | null;
  while ((match = regex.exec(markdown)) !== null) {
    const level = match[1].length;
    const text = match[2].trim();
    const slug = text
      .toLowerCase()
      .replace(/[^\w\s-]/g, "")
      .replace(/\s+/g, "-");
    entries.push({ level, text, slug });
  }
  return entries;
}

interface ExtensionDetailViewProps {
  item: ExtensionItemSummary;
  isInstalled: boolean;
  onBack: () => void;
  onInstalled: (itemId: string) => void;
  syncTargets?: ExtensionSyncTarget[];
}

export function ExtensionDetailView({ item, isInstalled, onBack, onInstalled, syncTargets = [] }: ExtensionDetailViewProps) {
  const client = useExtensionsClient();

  const [loadError, setLoadError] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(isInstalled);
  const [installError, setInstallError] = useState<string | null>(null);
  const [displayContent, setDisplayContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);
  const [showTargetDialog, setShowTargetDialog] = useState(false);
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [descExpanded, setDescExpanded] = useState(false);
  const [descClamped, setDescClamped] = useState(false);
  const descRef = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    const el = descRef.current;
    if (el) setDescClamped(el.scrollHeight > el.clientHeight);
  }, [item.description]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await client.catalog.getItem(item.extension_id);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => { cancelled = true; };
  }, [client, item.extension_id]);

  useEffect(() => {
    let cancelled = false;
    setContentLoading(true);
    (async () => {
      try {
        const data = await client.catalog.getContent(item.extension_id);
        if (!cancelled) setDisplayContent(data.content);
      } catch (err) {
        if (!cancelled) setContentError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setContentLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [client, item.extension_id]);

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
          const typeApi = client[typePlural as keyof typeof client] as {
            unsyncFromAgent: (name: string, agent: string) => Promise<unknown>;
          };
          for (const agent of toRemove) {
            await typeApi.unsyncFromAgent(item.name, agent);
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
    [client, item.extension_id, item.extension_type, item.name, onInstalled],
  );

  const handleInstall = useCallback(() => {
    guardAction(() => setShowTargetDialog(true));
  }, [guardAction]);

  const tocEntries = useMemo(
    () => (displayContent ? extractTocEntries(stripFrontmatter(displayContent)) : []),
    [displayContent],
  );

  const Icon = ITEM_TYPE_ICONS[item.extension_type] || Package;
  const iconColors = ITEM_TYPE_ICON_COLORS[item.extension_type] || ITEM_TYPE_ICON_COLORS.skill;
  const platformLabel = (item.platforms ?? []).map((p) => PLATFORM_LABELS[p] || p).join(", ");

  return (
    <div className="max-w-6xl mx-auto px-6 py-6">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-muted hover:text-secondary mb-4 transition"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to extensions
      </button>

      {/* Header card */}
      <div className="border border-card rounded-xl bg-panel overflow-hidden mb-6">
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

            {/* Install / Manage button */}
            <div className="shrink-0">
              {item.is_file_based && (() => {
                const isHook = item.extension_type === "hook";
                return (
                  <button
                    onClick={isHook ? undefined : handleInstall}
                    disabled={installing || isHook}
                    title={isHook ? "Hook install from catalog is not yet supported" : undefined}
                    className={installed
                      ? "flex items-center gap-2 px-4 py-2 text-sm font-medium text-accent-emerald bg-accent-emerald-subtle hover:bg-emerald-100 dark:hover:bg-emerald-900/30 border border-accent-emerald-border rounded-lg transition disabled:opacity-50"
                      : "flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
                    }
                  >
                    {installing
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : installed
                        ? <Check className="w-4 h-4" />
                        : <Download className="w-4 h-4" />}
                    {installed ? "Manage" : "Install"}
                  </button>
                );
              })()}
            </div>
          </div>

          {installError && <p className="text-xs text-red-500 mt-2">{installError}</p>}
        </div>

        {/* Metadata bar */}
        <div className="px-6 py-3 border-t border-card/50 bg-control/30">
          <div className="flex items-center gap-4 text-xs text-muted flex-wrap">
            <span>{item.extension_type}</span>
            {platformLabel && (
              <span className="text-secondary">{platformLabel}</span>
            )}
            <Tooltip text={`Quality: ${Math.round(item.quality_score)}/100`}>
              <span className="flex items-center gap-1.5 cursor-help">
                <span className="inline-block w-16 h-1.5 rounded-full bg-control-hover overflow-hidden">
                  <span className="block h-full bg-teal-500 rounded-full" style={{ width: `${item.quality_score}%` }} />
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
            {item.language && (
              <span className="text-secondary">{item.language}</span>
            )}
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
          {item.topics.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {item.topics.map((topic) => (
                <span
                  key={topic}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-control-hover/60 text-secondary border border-hover/30"
                >
                  {topic}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Install command */}
        {item.install_command && (
          <div className="px-6 py-3 border-t border-card/50">
            <div className="flex items-center gap-2 bg-control/50 rounded-lg px-4 py-2.5 border border-card">
              <code className="flex-1 text-sm font-mono text-secondary overflow-x-auto">{item.install_command}</code>
              <CopyButton text={item.install_command} />
            </div>
          </div>
        )}
      </div>

      {/* Content area */}
      {loadError && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30">
          <p className="text-sm text-red-700 dark:text-red-300">Failed to load details: {loadError}</p>
        </div>
      )}

      {contentLoading && (
        <div className="flex items-center gap-2 text-sm text-muted py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading content...
        </div>
      )}

      {contentError && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30">
          <p className="text-sm text-red-700 dark:text-red-300">Failed to load content: {contentError}</p>
        </div>
      )}

      {!contentLoading && !contentError && displayContent && (
        <ExtensionDetailContent
          content={displayContent}
          tocEntries={tocEntries}
          itemName={item.name}
          itemDescription={item.description ?? undefined}
        />
      )}

      {!contentLoading && !contentError && !displayContent && (
        <div className="border border-card rounded-lg bg-panel p-6 text-center text-sm text-muted">
          No content available for this item.
          {item.install_command && (
            <span> Use the install command above to add it manually.</span>
          )}
        </div>
      )}

      {showTargetDialog && (
        <InstallTargetDialog
          extensionName={item.name}
          typeKey={item.extension_type}
          syncTargets={syncTargets}
          onInstall={handleDialogSubmit}
          onCancel={() => setShowTargetDialog(false)}
        />
      )}
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

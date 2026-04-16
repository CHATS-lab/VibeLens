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
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../app";
import type { ExtensionItemSummary } from "../../types";
import { Tooltip } from "../tooltip";
import { CopyButton } from "../copy-button";
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
}

export function ExtensionDetailView({ item, isInstalled, onBack, onInstalled }: ExtensionDetailViewProps) {
  const { fetchWithToken } = useAppContext();

  const [loadError, setLoadError] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(isInstalled);
  const [installError, setInstallError] = useState<string | null>(null);
  const [displayContent, setDisplayContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchWithToken(`/api/extensions/${encodeURIComponent(item.item_id)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => { cancelled = true; };
  }, [fetchWithToken, item.item_id]);

  useEffect(() => {
    let cancelled = false;
    setContentLoading(true);
    (async () => {
      try {
        const res = await fetchWithToken(`/api/extensions/${encodeURIComponent(item.item_id)}/content`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setDisplayContent(data.content);
      } catch (err) {
        if (!cancelled) setContentError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setContentLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [fetchWithToken, item.item_id]);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setInstallError(null);
    try {
      const res = await fetchWithToken(`/api/extensions/${encodeURIComponent(item.item_id)}/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_platform: "claude_code" }),
      });
      if (res.status === 409) {
        const retry = await fetchWithToken(`/api/extensions/${encodeURIComponent(item.item_id)}/install`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_platform: "claude_code", overwrite: true }),
        });
        if (!retry.ok) throw new Error((await retry.json().catch(() => ({}))).detail || `HTTP ${retry.status}`);
      } else if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      setInstalled(true);
      onInstalled(item.item_id);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstalling(false);
    }
  }, [fetchWithToken, item.item_id, onInstalled]);

  const tocEntries = useMemo(
    () => (displayContent ? extractTocEntries(stripFrontmatter(displayContent)) : []),
    [displayContent],
  );

  const Icon = ITEM_TYPE_ICONS[item.item_type] || Package;
  const iconColors = ITEM_TYPE_ICON_COLORS[item.item_type] || ITEM_TYPE_ICON_COLORS.skill;
  const platformLabel = item.platforms.map((p) => PLATFORM_LABELS[p] || p).join(", ");

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
                  <TypeBadge itemType={item.item_type} />
                  <h1 className="text-xl font-bold font-mono text-primary">{item.name}</h1>
                  {installed && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-accent-emerald-subtle text-accent-emerald border border-accent-emerald-border font-medium">
                      Installed
                    </span>
                  )}
                </div>
                <p className="text-sm text-secondary leading-relaxed">{item.description}</p>
              </div>
            </div>

            {/* Install button */}
            <div className="shrink-0">
              {item.is_file_based && !installed && (
                <button
                  onClick={handleInstall}
                  disabled={installing}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-lg transition disabled:opacity-50"
                >
                  {installing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                  Install
                </button>
              )}
              {installed && (
                <span className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-accent-emerald bg-accent-emerald-subtle border border-accent-emerald-border rounded-lg">
                  <Check className="w-4 h-4" />
                  Installed
                </span>
              )}
            </div>
          </div>

          {installError && <p className="text-xs text-red-500 mt-2">{installError}</p>}
        </div>

        {/* Metadata bar */}
        <div className="px-6 py-3 border-t border-card/50 bg-control/30">
          <div className="flex items-center gap-4 text-xs text-muted flex-wrap">
            <span>{item.category}</span>
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
            {item.license_name && (
              <span className="flex items-center gap-1">
                <Scale className="w-3 h-3" />
                <span className="text-secondary">{item.license_name}</span>
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
          {item.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {item.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-control-hover/60 text-secondary border border-hover/30"
                >
                  {tag}
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
          itemDescription={item.description}
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
    </div>
  );
}

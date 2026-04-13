import { ArrowLeft, Check, Clock, Download, ExternalLink, GitFork, Loader2, Scale, Star } from "lucide-react";
import { formatCount, formatRelativeDate } from "./catalog-format";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../app";
import type { CatalogItemSummary } from "../../types";
import { CopyButton } from "../copy-button";
import { CatalogDetailContent, type TocEntry } from "./catalog-detail-content";
import { TypeBadge } from "./catalog-card";
import { ITEM_TYPE_LABELS, PLATFORM_LABELS } from "./catalog-constants";

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

interface CatalogDetailViewProps {
  item: CatalogItemSummary;
  isInstalled: boolean;
  onBack: () => void;
  onInstalled: (itemId: string) => void;
}

export function CatalogDetailView({ item, isInstalled, onBack, onInstalled }: CatalogDetailViewProps) {
  const { fetchWithToken } = useAppContext();

  const [loadError, setLoadError] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(isInstalled);
  const [installError, setInstallError] = useState<string | null>(null);
  const [displayContent, setDisplayContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);

  // Fetch full item to surface load errors (e.g., item not found)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchWithToken(`/api/catalog/${encodeURIComponent(item.item_id)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => { cancelled = true; };
  }, [fetchWithToken, item.item_id]);

  // Fetch displayable content (may differ from install_content for repos/featured)
  useEffect(() => {
    let cancelled = false;
    setContentLoading(true);
    (async () => {
      try {
        const res = await fetchWithToken(`/api/catalog/${encodeURIComponent(item.item_id)}/content`);
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
      const res = await fetchWithToken(`/api/catalog/${encodeURIComponent(item.item_id)}/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_platform: "claude_code" }),
      });
      if (res.status === 409) {
        const retry = await fetchWithToken(`/api/catalog/${encodeURIComponent(item.item_id)}/install`, {
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
    () => (displayContent ? extractTocEntries(displayContent) : []),
    [displayContent],
  );

  const typeLabel = ITEM_TYPE_LABELS[item.item_type] || item.item_type;
  const platformLabel = item.platforms.map((p) => PLATFORM_LABELS[p] || p).join(", ");

  return (
    <div className="max-w-6xl mx-auto px-6 py-6">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-muted hover:text-secondary mb-4 transition"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to catalog
      </button>

      {/* Header section */}
      <div className="border border-card rounded-lg bg-panel p-6 mb-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3 flex-wrap mb-2">
              <h1 className="text-xl font-bold text-primary">{item.name}</h1>
              <TypeBadge itemType={item.item_type} />
            </div>
            <p className="text-sm text-secondary mb-3">{item.description}</p>
            <div className="flex items-center gap-4 text-xs text-muted flex-wrap">
              <span>Category: <span className="text-secondary">{item.category}</span></span>
              <span>Type: <span className="text-secondary">{typeLabel}</span></span>
              <span>Platform: <span className="text-secondary">{platformLabel}</span></span>
              <span>Quality: <span className="text-secondary">{Math.round(item.quality_score)}/100</span></span>
              {item.source_url && (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent-cyan hover:underline flex items-center gap-1"
                >
                  Source <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
            {(item.stars > 0 || item.forks > 0 || item.language || item.license_name || item.updated_at) && (
              <div className="flex items-center gap-4 text-xs text-muted flex-wrap mt-1">
                {item.stars > 0 && (
                  <span className="flex items-center gap-1">
                    <Star className="w-3 h-3 text-amber-400 fill-amber-400" />
                    <span className="text-secondary">{formatCount(item.stars)}</span>
                  </span>
                )}
                {item.forks > 0 && (
                  <span className="flex items-center gap-1">
                    <GitFork className="w-3 h-3" />
                    <span className="text-secondary">{formatCount(item.forks)}</span>
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
              </div>
            )}
            {item.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {item.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-[10px] px-1.5 py-0.5 rounded-full bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
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
              <span className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-emerald-600 dark:text-emerald-400 border border-emerald-300/40 rounded-lg">
                <Check className="w-4 h-4" />
                Installed
              </span>
            )}
          </div>
        </div>

        {installError && <p className="text-xs text-red-500 mt-2">{installError}</p>}

        {/* Install command */}
        {item.install_command && (
          <div className="mt-4 flex items-center gap-2 bg-zinc-900 rounded-lg px-4 py-2.5 border border-zinc-700/50">
            <code className="flex-1 text-sm font-mono text-zinc-300 overflow-x-auto">{item.install_command}</code>
            <CopyButton text={item.install_command} />
          </div>
        )}
      </div>

      {/* Content area: markdown + TOC sidebar */}
      {loadError && (
        <div className="border border-red-500/30 bg-red-950/20 rounded-lg p-4 text-sm text-red-400">
          Failed to load details: {loadError}
        </div>
      )}

      {contentLoading && (
        <div className="flex items-center gap-2 text-sm text-muted py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading content...
        </div>
      )}

      {contentError && (
        <div className="border border-red-500/30 bg-red-950/20 rounded-lg p-4 text-sm text-red-400">
          Failed to load content: {contentError}
        </div>
      )}

      {!contentLoading && !contentError && displayContent && (
        <CatalogDetailContent content={displayContent} tocEntries={tocEntries} />
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

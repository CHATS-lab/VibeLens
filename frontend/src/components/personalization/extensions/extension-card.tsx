import {
  Anchor,
  Bot,
  Check,
  Clock,
  Download,
  ExternalLink,
  GitFork,
  Loader2,
  Package,
  Server,
  Star,
  Terminal,
} from "lucide-react";
import { formatCount, formatRelativeDate } from "./extension-format";
import { useCallback, useState } from "react";
import { useAppContext } from "../../app";
import type { ExtensionItemSummary } from "../../types";
import { Tooltip } from "../tooltip";
import {
  CARD_VIEW_MAX_TAGS,
  ITEM_TYPE_COLORS,
  ITEM_TYPE_ICON_COLORS,
  ITEM_TYPE_LABELS,
  LIST_VIEW_MAX_TAGS,
  type ExtensionViewMode,
} from "./extension-constants";

const ITEM_TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  skill: Package,
  subagent: Bot,
  command: Terminal,
  hook: Anchor,
  repo: Server,
};

export function TypeBadge({ itemType }: { itemType: string }) {
  const color = ITEM_TYPE_COLORS[itemType] || ITEM_TYPE_COLORS.skill;
  const label = ITEM_TYPE_LABELS[itemType] || itemType;
  return (
    <span className={`inline-flex justify-center min-w-[54px] text-[10px] px-1.5 py-0.5 rounded border font-medium ${color}`}>
      {label}
    </span>
  );
}

function ItemTypeIcon({ itemType, size = "sm" }: { itemType: string; size?: "sm" | "lg" }) {
  const Icon = ITEM_TYPE_ICONS[itemType] || Package;
  const colors = ITEM_TYPE_ICON_COLORS[itemType] || ITEM_TYPE_ICON_COLORS.skill;
  const sizeClass = size === "lg" ? "p-2 rounded-lg" : "p-1.5 rounded-md";
  const iconSize = size === "lg" ? "w-5 h-5" : "w-4 h-4";
  return (
    <div className={`shrink-0 ${sizeClass} ${colors.bg}`}>
      <Icon className={`${iconSize} ${colors.text}`} />
    </div>
  );
}

function TagList({ tags, max }: { tags: string[]; max: number }) {
  if (tags.length === 0) return null;
  const visible = tags.slice(0, max);
  const overflow = tags.length - max;
  return (
    <div className="flex flex-wrap gap-1 mt-1.5">
      {visible.map((tag) => (
        <span
          key={tag}
          className="text-[10px] px-1.5 py-0.5 rounded-full bg-control text-dimmed"
        >
          {tag}
        </span>
      ))}
      {overflow > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-control text-dimmed">
          +{overflow}
        </span>
      )}
    </div>
  );
}

function QualityBar({ score }: { score: number }) {
  return (
    <Tooltip text={`Quality: ${score}/100`}>
      <span className="flex items-center gap-1 cursor-help">
        <span className="inline-block w-12 h-1.5 rounded-full bg-control-hover overflow-hidden">
          <span className="block h-full bg-teal-500 rounded-full" style={{ width: `${score}%` }} />
        </span>
        <span className="tabular-nums">{Math.round(score)}</span>
      </span>
    </Tooltip>
  );
}

interface ExtensionCardProps {
  item: ExtensionItemSummary;
  isInstalled: boolean;
  onInstalled: (itemId: string) => void;
  onViewDetail: (item: ExtensionItemSummary) => void;
  viewMode?: ExtensionViewMode;
}

export function ExtensionCard({
  item,
  isInstalled,
  onInstalled,
  onViewDetail,
  viewMode = "list",
}: ExtensionCardProps) {
  const { fetchWithToken } = useAppContext();
  const [installing, setInstalling] = useState(false);
  const [installed, setInstalled] = useState(isInstalled);
  const [error, setError] = useState<string | null>(null);

  const handleInstall = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      setInstalling(true);
      setError(null);
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
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setInstalling(false);
      }
    },
    [fetchWithToken, item.item_id, onInstalled],
  );

  const borderClass = installed
    ? "border-emerald-300/40 bg-emerald-50 hover:bg-emerald-100/80 dark:border-emerald-800/40 dark:bg-emerald-950/20 dark:hover:bg-emerald-950/30"
    : "border-card bg-panel hover:bg-control/80";

  if (viewMode === "card") {
    return (
      <div
        className={`border rounded-lg transition cursor-pointer flex flex-col h-full ${borderClass}`}
        onClick={() => onViewDetail(item)}
      >
        <div className="px-4 pt-3 pb-2 flex flex-col flex-1 min-w-0">
          <div className="flex items-start gap-2.5">
            <ItemTypeIcon itemType={item.item_type} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <TypeBadge itemType={item.item_type} />
                <span className="font-mono text-sm font-bold text-primary truncate">{item.name}</span>
                {installed && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-emerald-subtle text-accent-emerald border border-accent-emerald-border font-medium">
                    Installed
                  </span>
                )}
              </div>
            </div>
          </div>
          <p className="text-sm text-secondary mt-1.5 line-clamp-3">{item.description}</p>
          <TagList tags={item.tags} max={CARD_VIEW_MAX_TAGS} />
          {error && <p className="text-[10px] text-red-500 mt-1">{error}</p>}
          <div className="flex items-center justify-between mt-auto pt-3 text-[10px] text-muted">
            <div className="flex items-center gap-2.5">
              <span>{item.category}</span>
              {item.stars > 0 && (
                <span className="flex items-center gap-0.5">
                  <Star className="w-2.5 h-2.5 text-amber-400 fill-amber-400" />
                  {formatCount(item.stars)}
                </span>
              )}
              <QualityBar score={item.quality_score} />
            </div>
            <div className="flex items-center gap-1.5">
              {item.source_url && (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="p-1 text-faint hover:text-secondary rounded transition"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
              {item.is_file_based && !installed && (
                <button
                  onClick={handleInstall}
                  disabled={installing}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-md transition disabled:opacity-50"
                >
                  {installing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                  Install
                </button>
              )}
              {installed && (
                <span className="flex items-center gap-1 text-[10px] font-medium text-accent-emerald">
                  <Check className="w-3 h-3" />
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // List view — matches local SkillCard layout
  return (
    <div
      className={`border rounded-lg transition cursor-pointer ${borderClass}`}
      onClick={() => onViewDetail(item)}
    >
      <div className="flex items-start">
        <div className="flex-1 text-left px-4 py-3 flex items-start gap-3 min-w-0">
          <div className="mt-0.5">
            <ItemTypeIcon itemType={item.item_type} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <TypeBadge itemType={item.item_type} />
              <span className="font-mono text-base font-bold text-primary">{item.name}</span>
              {installed && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-emerald-subtle text-accent-emerald border border-accent-emerald-border font-medium">
                  Installed
                </span>
              )}
              {item.stars > 0 && (
                <Tooltip text={`${item.stars.toLocaleString()} GitHub stars`}>
                  <span className="flex items-center gap-0.5 text-[10px] text-amber-600/80 dark:text-amber-400/70 cursor-help">
                    <Star className="w-2.5 h-2.5 fill-current" />
                    {formatCount(item.stars)}
                  </span>
                </Tooltip>
              )}
            </div>
            <p className="text-sm text-secondary mt-1 line-clamp-2">{item.description}</p>
            <TagList tags={item.tags} max={LIST_VIEW_MAX_TAGS} />
            <div className="flex items-center gap-3 mt-2 text-[10px] text-muted">
              <span>{item.category}</span>
              <QualityBar score={item.quality_score} />
              {item.forks > 0 && (
                <span className="flex items-center gap-0.5">
                  <GitFork className="w-2.5 h-2.5" />
                  {formatCount(item.forks)}
                </span>
              )}
              {item.language && <span>{item.language}</span>}
              {item.updated_at && (
                <span className="flex items-center gap-0.5">
                  <Clock className="w-2.5 h-2.5" />
                  {formatRelativeDate(item.updated_at)}
                </span>
              )}
            </div>
            {error && <p className="text-[10px] text-red-500 mt-1">{error}</p>}
          </div>
        </div>
        <div className="shrink-0 flex items-center gap-1.5 px-3 py-3">
          {item.source_url && (
            <Tooltip text="View source">
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="p-2 text-dimmed hover:text-secondary hover:bg-control-hover rounded-md transition"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            </Tooltip>
          )}
          {item.is_file_based && !installed && (
            <Tooltip text={`Install ${ITEM_TYPE_LABELS[item.item_type] || item.item_type}`}>
              <button
                onClick={handleInstall}
                disabled={installing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-teal-600 hover:bg-teal-500 rounded-md transition disabled:opacity-50"
              >
                {installing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                Install
              </button>
            </Tooltip>
          )}
          {installed && (
            <span className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-accent-emerald bg-accent-emerald-subtle rounded-md border border-accent-emerald-border">
              <Check className="w-3.5 h-3.5" /> Installed
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

import {
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Lightbulb,
  Search,
  Star,
} from "lucide-react";
import { useCallback, useState } from "react";
import type {
  ExtensionItemSummary,
  RankedRecommendationItem,
} from "../../types";
import { useExtensionsClient } from "../../app";
import { BulletText } from "../bullet-text";
import { CollapsibleText } from "../collapsible-text";
import { Tooltip } from "../tooltip";
import { TagList } from "./badges";
import { TypeBadge } from "./extensions/extension-card";
import { ConfidenceBar, SectionHeader } from "./shared";

export function RecommendationSection({
  recommendations,
  installedIds,
  onOpenDetail,
}: {
  recommendations: RankedRecommendationItem[];
  installedIds: Set<string>;
  /** @deprecated No longer used — kept for backward compatibility */
  fetchWithToken?: (url: string, init?: RequestInit) => Promise<Response>;
  onOpenDetail: (item: ExtensionItemSummary) => void;
}) {
  return (
    <section>
      <SectionHeader
        icon={<Search className="w-5 h-5" />}
        title="Recommendations"
        tooltip="Catalog extensions matching your workflow"
      />
      <div className="space-y-3">
        {recommendations.map((rec) => (
          <RecommendationCard
            key={rec.item.extension_id}
            rec={rec}
            isInstalled={installedIds.has(rec.item.extension_id)}
            onOpenDetail={onOpenDetail}
          />
        ))}
      </div>
    </section>
  );
}

function RecommendationCard({
  rec,
  isInstalled,
  onOpenDetail,
}: {
  rec: RankedRecommendationItem;
  isInstalled: boolean;
  onOpenDetail: (item: ExtensionItemSummary) => void;
}) {
  const client = useExtensionsClient();
  const [rationaleExpanded, setRationaleExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const relevance = rec.scores.relevance ?? 0;
  const tags = rec.item.tags ?? [];

  const handleClick = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const item = await client.catalog.getItem(rec.item.extension_id);
      onOpenDetail(item);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [client, rec.item.extension_id, onOpenDetail]);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleClick();
        }
      }}
      className={`border border-default rounded-xl bg-subtle overflow-hidden cursor-pointer hover:border-hover transition ${
        loading ? "opacity-60" : ""
      }`}
    >
      {/* Header: Name + Type + Relevance + Installed pill */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0 flex-wrap">
            <TypeBadge itemType={rec.item.extension_type} />
            <span className="font-mono text-base font-bold text-primary">{rec.item.name}</span>
            {relevance > 0 && <ConfidenceBar confidence={relevance} accentColor="teal" />}
            {rec.item.stars > 0 && (
              <Tooltip text={`${rec.item.stars.toLocaleString()} stars`}>
                <span className="inline-flex items-center gap-0.5 text-[11px] text-amber-500 dark:text-amber-400 cursor-help">
                  <Star className="w-3 h-3 fill-amber-400 text-amber-400" /> {rec.item.stars.toLocaleString()}
                </span>
              </Tooltip>
            )}
            {rec.item.source_url && (
              <a
                href={rec.item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-dimmed hover:text-secondary transition"
              >
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
          {isInstalled && (
            <span className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold text-accent-emerald bg-accent-emerald-subtle rounded-lg border border-accent-emerald-border">
              <Check className="w-3.5 h-3.5" /> Installed
            </span>
          )}
        </div>
        {rec.item.description && (
          <CollapsibleText
            text={rec.item.description}
            label="Description:"
            className="text-sm text-secondary leading-relaxed mt-2"
          />
        )}
        <p className="text-xs text-dimmed mt-1.5">{rec.item.repo_name}</p>
        {tags.length > 0 && <TagList tags={tags} />}
        {error && (
          <p className="text-xs text-accent-rose mt-2">Failed to load: {error}</p>
        )}
      </div>

      {/* Why this helps */}
      <div className="px-5 py-3 border-t border-default">
        <button
          onClick={(e) => {
            e.stopPropagation();
            setRationaleExpanded(!rationaleExpanded);
          }}
          className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
        >
          {rationaleExpanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
          <Lightbulb className="w-3.5 h-3.5 text-accent-teal" />
          <span className="text-sm font-semibold text-accent-teal">Why this helps</span>
        </button>
        {rationaleExpanded && (
          <BulletText text={rec.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
        )}
      </div>
    </div>
  );
}

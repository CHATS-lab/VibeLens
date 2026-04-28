import {
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
  ExtensionSyncTarget,
  RankedRecommendationItem,
} from "../../types";
import { useExtensionsClient } from "../../app";
import { errorMessage } from "../../utils";
import { BulletText } from "../ui/bullet-text";
import { CollapsibleText } from "../ui/collapsible-text";
import { Tooltip } from "../ui/tooltip";
import { TagList } from "./source-badges";
import { CatalogInstallButton, TypeBadge } from "./extensions/extension-card";
import { ConfidenceBar, SectionHeader } from "./result-shared";

export function RecommendationSection({
  recommendations,
  installedIds,
  onOpenDetail,
  syncTargetsByType = {},
  onInstalled,
}: {
  recommendations: RankedRecommendationItem[];
  installedIds: Set<string>;
  onOpenDetail: (item: ExtensionItemSummary) => void;
  syncTargetsByType?: Record<string, ExtensionSyncTarget[]>;
  onInstalled?: (itemId: string) => void;
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
            syncTargets={syncTargetsByType[rec.item.extension_type] ?? []}
            onInstalled={onInstalled}
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
  syncTargets = [],
  onInstalled,
}: {
  rec: RankedRecommendationItem;
  isInstalled: boolean;
  onOpenDetail: (item: ExtensionItemSummary) => void;
  syncTargets?: ExtensionSyncTarget[];
  onInstalled?: (itemId: string) => void;
}) {
  const client = useExtensionsClient();
  const [rationaleExpanded, setRationaleExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installed, setInstalled] = useState(isInstalled);

  const relevance = rec.scores.relevance ?? 0;
  const tags = rec.item.topics ?? [];

  const handleInstallStateChange = useCallback(
    (itemId: string, success: boolean, installError: string | null) => {
      if (success) {
        setInstalled(true);
        onInstalled?.(itemId);
      }
      if (installError) setError(installError);
    },
    [onInstalled],
  );

  const handleClick = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const item = await client.catalog.getItem(rec.item.extension_id);
      onOpenDetail(item);
    } catch (err) {
      setError(errorMessage(err));
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
      className={`border border-card bg-panel hover:bg-control/80 rounded-xl overflow-hidden cursor-pointer transition ${
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
          <div className="shrink-0">
            <CatalogInstallButton
              item={rec.item}
              installed={installed}
              onStateChange={handleInstallStateChange}
              syncTargets={syncTargets}
              size="md"
            />
          </div>
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

      {/* Why this helps — clicking anywhere in this block toggles expand/collapse */}
      <div
        role="button"
        tabIndex={0}
        onClick={(e) => {
          e.stopPropagation();
          setRationaleExpanded(!rationaleExpanded);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            setRationaleExpanded(!rationaleExpanded);
          }
        }}
        className="px-5 py-3 border-t border-default cursor-pointer hover:bg-control/40 transition"
      >
        <div className="flex items-center gap-1.5 text-xs">
          {rationaleExpanded
            ? <ChevronDown className="w-3.5 h-3.5 text-accent-teal" />
            : <ChevronRight className="w-3.5 h-3.5 text-accent-teal" />}
          <Lightbulb className="w-3.5 h-3.5 text-accent-teal" />
          <span className="text-sm font-semibold text-accent-teal">Why this helps</span>
        </div>
        {rationaleExpanded && (
          <BulletText text={rec.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
        )}
      </div>
    </div>
  );
}

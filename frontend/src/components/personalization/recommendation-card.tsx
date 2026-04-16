import { Copy, ExternalLink } from "lucide-react";
import type { RankedRecommendationItem } from "../../types";
import { ITEM_TYPE_COLORS, ITEM_TYPE_LABELS, scoreColor } from "./recommendation-constants";

const MAX_VISIBLE_TAGS = 4;

interface RecommendationCardProps {
  recommendation: RankedRecommendationItem;
  rank: number;
  onInstall: (rec: RankedRecommendationItem) => void;
}

function QualityBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const label = pct >= 80 ? "High" : pct >= 50 ? "Good" : "Low";
  const color =
    pct >= 80
      ? "text-accent-emerald"
      : pct >= 50
        ? "text-accent-amber"
        : "text-dimmed";
  return (
    <span className={`text-xs font-medium tabular-nums ${color}`}>
      {label} ({pct})
    </span>
  );
}

export function RecommendationCard({ recommendation: rec, rank, onInstall }: RecommendationCardProps) {
  const { item } = rec;
  const typeColor = ITEM_TYPE_COLORS[item.extension_type] ?? ITEM_TYPE_COLORS.skill;
  const typeLabel = ITEM_TYPE_LABELS[item.extension_type] ?? item.extension_type;
  const composite = rec.scores.composite ?? 0;
  const relevance = rec.scores.relevance ?? 0;
  const quality = rec.scores.quality ?? 0;
  const barColor = scoreColor(composite);
  const relevancePct = Math.round(relevance * 100);
  const tags = item.tags?.slice(0, MAX_VISIBLE_TAGS) ?? [];

  return (
    <div className="rounded-lg border border-default bg-panel p-4 space-y-3">
      {/* Header: rank + type badge + name */}
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-sm font-medium text-dimmed w-6 shrink-0">
          #{rank}
        </span>
        <span className={`px-2 py-0.5 text-xs font-medium rounded-full border shrink-0 ${typeColor}`}>
          {typeLabel}
        </span>
        <h3 className="text-base font-semibold text-primary truncate">
          {item.name}
        </h3>
      </div>

      {/* Description */}
      <p className="text-sm text-secondary">{item.description}</p>

      {/* Tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs rounded-full bg-accent-cyan-subtle text-accent-cyan"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Rationale callout */}
      <div className="rounded-md bg-control border border-default px-3 py-2">
        <p className="text-sm text-secondary italic">{rec.rationale}</p>
      </div>

      {/* Quality score + relevance bar */}
      <div className="flex items-center gap-3">
        <QualityBadge score={quality} />
        <div className="flex-1 h-1.5 rounded-full bg-control overflow-hidden">
          <div className={`h-full rounded-full ${barColor}`} style={{ width: `${relevancePct}%` }} />
        </div>
        <span className="text-xs text-dimmed tabular-nums shrink-0">
          {relevancePct}% match
        </span>
      </div>

      {/* Install button */}
      {item.install_command && (
        <button
          onClick={() => onInstall(rec)}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-md bg-teal-600 hover:bg-teal-500 text-white transition-colors"
        >
          <Copy className="w-4 h-4" />
          Install
        </button>
      )}

      {/* Source URL */}
      {item.source_url && (
        <a
          href={item.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-dimmed hover:text-accent-cyan transition-colors"
        >
          <ExternalLink className="w-3 h-3" />
          Source
        </a>
      )}
    </div>
  );
}

import { ExternalLink, Download } from "lucide-react";
import type { CatalogRecommendation } from "../../types";
import { ITEM_TYPE_COLORS, ITEM_TYPE_LABELS, scoreColor } from "./recommendation-constants";

interface RecommendationCardProps {
  recommendation: CatalogRecommendation;
  rank: number;
  onInstall: (rec: CatalogRecommendation) => void;
}

export function RecommendationCard({ recommendation: rec, rank, onInstall }: RecommendationCardProps) {
  const typeColor = ITEM_TYPE_COLORS[rec.item_type] ?? ITEM_TYPE_COLORS.skill;
  const typeLabel = ITEM_TYPE_LABELS[rec.item_type] ?? rec.user_label;
  const barColor = scoreColor(rec.score);
  const barWidth = `${Math.round(rec.score * 100)}%`;

  return (
    <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800/50 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-zinc-400 dark:text-zinc-500 w-6 shrink-0">
            #{rank}
          </span>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${typeColor}`}>
            {typeLabel}
          </span>
          <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-100 truncate">
            {rec.name}
          </h3>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {rec.source_url && (
            <a
              href={rec.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
              title="View on GitHub"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
          {(rec.has_content || rec.install_command) && (
            <button
              onClick={() => onInstall(rec)}
              className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
              title="Install"
            >
              <Download className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-zinc-600 dark:text-zinc-300">{rec.description}</p>

      {/* Rationale callout */}
      <div className="rounded-md bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 px-3 py-2">
        <p className="text-sm text-zinc-700 dark:text-zinc-300 italic">{rec.rationale}</p>
      </div>

      {/* Score bar + confidence */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-1.5 rounded-full bg-zinc-200 dark:bg-zinc-700 overflow-hidden">
          <div className={`h-full rounded-full ${barColor}`} style={{ width: barWidth }} />
        </div>
        <span className="text-xs text-zinc-500 dark:text-zinc-400 tabular-nums shrink-0">
          {Math.round(rec.confidence * 100)}% match
        </span>
      </div>
    </div>
  );
}

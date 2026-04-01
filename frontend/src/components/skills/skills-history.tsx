import { Calendar, Clock, Coins, Layers, Loader2, Trash2, Workflow } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../app";
import type { SkillAnalysisMeta, SkillAnalysisResult, SkillMode } from "../../types";

const MODE_LABELS: Record<SkillMode, string> = {
  retrieval: "Recommend",
  creation: "Create",
  evolution: "Evolve",
};

const MODE_COLORS: Record<SkillMode, string> = {
  retrieval: "bg-teal-900/30 border-teal-700/30 text-teal-400",
  creation: "bg-emerald-900/30 border-emerald-700/30 text-emerald-400",
  evolution: "bg-amber-900/30 border-amber-700/30 text-amber-400",
};

function HistoryCard({
  meta,
  onSelect,
  onDelete,
}: {
  meta: SkillAnalysisMeta;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setDeleting(true);
      onDelete();
    },
    [onDelete],
  );

  const date = new Date(meta.created_at);
  const dateStr = date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });

  return (
    <div
      onClick={onSelect}
      className="group relative px-3 py-2.5 rounded-lg bg-zinc-800/40 hover:bg-zinc-800/80 border border-zinc-700/40 hover:border-zinc-600/50 cursor-pointer transition"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0 space-y-1.5">
          <p className="text-xs text-zinc-200 font-semibold truncate">
            {meta.summary_preview || "No summary"}
          </p>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium ${MODE_COLORS[meta.mode]}`}>
              {MODE_LABELS[meta.mode]}
            </span>
            <span className="text-[10px] text-zinc-400">
              {meta.pattern_count} pattern{meta.pattern_count !== 1 ? "s" : ""}
            </span>
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-violet-900/30 border border-violet-700/30 text-[10px] font-medium text-violet-300">
              <Layers className="w-2.5 h-2.5" />
              {meta.session_ids.length} session{meta.session_ids.length !== 1 ? "s" : ""}
            </span>
            {meta.cost_usd != null && (
              <span className="inline-flex items-center gap-1 text-[10px] text-zinc-300">
                <Coins className="w-2.5 h-2.5 text-amber-400" />
                ${meta.cost_usd.toFixed(3)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-[10px] text-zinc-400">
            <span className="inline-flex items-center gap-1">
              <Calendar className="w-2.5 h-2.5" />
              {dateStr}
            </span>
            <span className="inline-flex items-center gap-1">
              <Clock className="w-2.5 h-2.5" />
              {timeStr}
            </span>
          </div>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1 text-zinc-500 hover:text-rose-400 rounded transition"
          title="Delete analysis"
        >
          {deleting ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Trash2 className="w-3 h-3" />
          )}
        </button>
      </div>
    </div>
  );
}

export function SkillsHistory({
  onSelect,
  refreshTrigger,
  filterMode,
}: {
  onSelect: (result: SkillAnalysisResult) => void;
  refreshTrigger: number;
  filterMode: SkillMode | null;
}) {
  const { fetchWithToken } = useAppContext();
  const [analyses, setAnalyses] = useState<SkillAnalysisMeta[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithToken("/api/skills/analysis/history");
      if (res.ok) {
        const data: SkillAnalysisMeta[] = await res.json();
        setAnalyses(data);
      }
    } catch {
      // Silently ignore — sidebar is best-effort
    } finally {
      setLoading(false);
    }
  }, [fetchWithToken]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, refreshTrigger]);

  const filteredAnalyses = useMemo(() => {
    if (!filterMode) return analyses;
    return analyses.filter((a) => a.mode === filterMode);
  }, [analyses, filterMode]);

  const handleSelect = useCallback(
    async (meta: SkillAnalysisMeta) => {
      try {
        const res = await fetchWithToken(`/api/skills/analysis/${meta.analysis_id}`);
        if (res.ok) {
          const result: SkillAnalysisResult = await res.json();
          onSelect(result);
        }
      } catch {
        // Ignore load errors
      }
    },
    [fetchWithToken, onSelect],
  );

  const handleDelete = useCallback(
    async (analysisId: string) => {
      try {
        await fetchWithToken(`/api/skills/analysis/${analysisId}`, {
          method: "DELETE",
        });
        setAnalyses((prev) => prev.filter((a) => a.analysis_id !== analysisId));
      } catch {
        // Ignore delete errors
      }
    },
    [fetchWithToken],
  );

  const modeLabel = filterMode ? MODE_LABELS[filterMode] : null;

  if (loading && analyses.length === 0) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-4 h-4 text-zinc-500 animate-spin" />
      </div>
    );
  }

  if (!loading && filteredAnalyses.length === 0) {
    return (
      <div className="px-3 py-4 text-center">
        <Workflow className="w-5 h-5 mx-auto mb-2 text-zinc-600" />
        <p className="text-xs text-zinc-500">
          {modeLabel ? `No ${modeLabel.toLowerCase()} analyses yet` : "No analyses yet"}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {filteredAnalyses.map((meta) => (
        <HistoryCard
          key={meta.analysis_id}
          meta={meta}
          onSelect={() => handleSelect(meta)}
          onDelete={() => handleDelete(meta.analysis_id)}
        />
      ))}
    </div>
  );
}

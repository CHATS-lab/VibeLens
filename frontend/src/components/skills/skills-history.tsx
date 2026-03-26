import { Clock, Loader2, Trash2, Workflow } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAppContext } from "../../app";
import type { SkillAnalysisMeta, SkillAnalysisResult, SkillMode } from "../../types";

const MODE_LABELS: Record<SkillMode, string> = {
  retrieval: "Retrieve",
  creation: "Create",
  evolution: "Evolve",
};

const MODE_COLORS: Record<SkillMode, string> = {
  retrieval: "bg-cyan-900/30 text-cyan-400",
  creation: "bg-emerald-900/30 text-emerald-400",
  evolution: "bg-amber-900/30 text-amber-400",
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
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      setDeleting(true);
      onDelete();
    },
    [onDelete],
  );

  const date = new Date(meta.computed_at);
  const dateStr = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });

  return (
    <button
      onClick={onSelect}
      className="group w-full text-left px-3 py-2.5 rounded-md border border-zinc-800 hover:border-zinc-700 hover:bg-zinc-800/50 transition"
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${MODE_COLORS[meta.mode]}`}>
          {MODE_LABELS[meta.mode]}
        </span>
        <span className="text-[10px] text-zinc-600">
          {dateStr} {timeStr}
        </span>
      </div>
      <p className="text-xs text-zinc-400 line-clamp-2 mb-1.5">
        {meta.summary_preview || "No summary"}
      </p>
      <div className="flex items-center justify-between text-[10px] text-zinc-600">
        <div className="flex items-center gap-2">
          <span>{meta.pattern_count} pattern{meta.pattern_count !== 1 ? "s" : ""}</span>
          <span>{meta.session_ids.length} session{meta.session_ids.length !== 1 ? "s" : ""}</span>
          {meta.cost_usd != null && <span>${meta.cost_usd.toFixed(3)}</span>}
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1 text-zinc-600 hover:text-red-400 transition"
        >
          {deleting ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Trash2 className="w-3 h-3" />
          )}
        </button>
      </div>
    </button>
  );
}

export function SkillsHistory({
  onSelect,
  refreshTrigger,
}: {
  onSelect: (result: SkillAnalysisResult) => void;
  refreshTrigger: number;
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

  return (
    <div className="flex flex-col h-full border-l border-zinc-800">
      <div className="flex items-center gap-2 px-3 py-3 border-b border-zinc-800 shrink-0">
        <Clock className="w-3.5 h-3.5 text-zinc-500" />
        <span className="text-xs font-semibold text-zinc-400">History</span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1.5">
        {loading && analyses.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-4 h-4 text-zinc-600 animate-spin" />
          </div>
        )}

        {!loading && analyses.length === 0 && (
          <div className="text-center py-8 px-2">
            <Workflow className="w-6 h-6 text-zinc-700 mx-auto mb-2" />
            <p className="text-[10px] text-zinc-600">No analyses yet</p>
          </div>
        )}

        {analyses.map((meta) => (
          <HistoryCard
            key={meta.analysis_id}
            meta={meta}
            onSelect={() => handleSelect(meta)}
            onDelete={() => handleDelete(meta.analysis_id)}
          />
        ))}
      </div>
    </div>
  );
}

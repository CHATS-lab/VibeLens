import { AlertTriangle, Calendar, Clock, Coins, History, Layers, Loader2, Trash2, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAppContext } from "../../app";
import type { FrictionAnalysisResult, FrictionMeta } from "../../types";
import { formatCost } from "../../utils";

interface FrictionHistoryProps {
  onSelect: (result: FrictionAnalysisResult) => void;
  refreshTrigger: number;
}

export function FrictionHistory({ onSelect, refreshTrigger }: FrictionHistoryProps) {
  const { fetchWithToken } = useAppContext();
  const [items, setItems] = useState<FrictionMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithToken("/api/analysis/friction/history");
      if (res.ok) setItems(await res.json());
    } catch {
      /* best-effort */
    } finally {
      setLoading(false);
    }
  }, [fetchWithToken]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, refreshTrigger]);

  const handleSelect = useCallback(async (analysisId: string) => {
    try {
      const res = await fetchWithToken(`/api/analysis/friction/${analysisId}`);
      if (res.ok) onSelect(await res.json());
    } catch {
      /* best-effort */
    }
  }, [fetchWithToken, onSelect]);

  const handleDelete = useCallback(async (analysisId: string) => {
    setDeletingId(analysisId);
    try {
      const res = await fetchWithToken(`/api/analysis/friction/${analysisId}`, {
        method: "DELETE",
      });
      if (res.ok) setItems((prev) => prev.filter((i) => i.analysis_id !== analysisId));
    } catch {
      /* best-effort */
    } finally {
      setDeletingId(null);
    }
  }, [fetchWithToken]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-4 h-4 text-zinc-500 animate-spin" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="px-3 py-4 text-center">
        <History className="w-5 h-5 mx-auto mb-2 text-zinc-600" />
        <p className="text-xs text-zinc-500">No past analyses</p>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {items.map((item) => (
        <HistoryCard
          key={item.analysis_id}
          item={item}
          deleting={deletingId === item.analysis_id}
          onSelect={() => handleSelect(item.analysis_id)}
          onDelete={() => handleDelete(item.analysis_id)}
        />
      ))}
    </div>
  );
}

function HistoryCard({
  item,
  deleting,
  onSelect,
  onDelete,
}: {
  item: FrictionMeta;
  deleting: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const date = new Date(item.created_at);
  const dateStr = isNaN(date.getTime())
    ? item.created_at
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const timeStr = isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

  const hasFriction = item.event_count > 0;

  return (
    <div
      onClick={onSelect}
      className="group relative px-3 py-2.5 rounded-lg bg-zinc-800/40 hover:bg-zinc-800/80 border border-zinc-700/40 hover:border-zinc-600/50 cursor-pointer transition"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0 space-y-1.5">
          {item.title && (
            <p className="text-xs text-zinc-200 font-semibold truncate">{item.title}</p>
          )}
          <p className="text-xs text-zinc-100 line-clamp-2 leading-relaxed font-medium">
            {item.summary_preview}
          </p>

          <div className="flex items-center gap-1.5 flex-wrap">
            {hasFriction ? (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-900/30 border border-amber-700/30 text-[10px] font-medium text-amber-300">
                <AlertTriangle className="w-2.5 h-2.5" />
                {item.event_count}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-900/30 border border-emerald-700/30 text-[10px] font-medium text-emerald-300">
                <Zap className="w-2.5 h-2.5" />
                Clean
              </span>
            )}
            <span className="inline-flex items-center gap-1 text-[10px] text-zinc-300">
              <Layers className="w-2.5 h-2.5 text-violet-400" />
              {item.session_ids.length}
            </span>
            {item.cost_usd != null && (
              <span className="inline-flex items-center gap-1 text-[10px] text-zinc-300">
                <Coins className="w-2.5 h-2.5 text-amber-400" />
                {formatCost(item.cost_usd)}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-[10px] text-zinc-400">
            <span className="inline-flex items-center gap-1">
              <Calendar className="w-2.5 h-2.5" />
              {dateStr}
            </span>
            {timeStr && (
              <span className="inline-flex items-center gap-1">
                <Clock className="w-2.5 h-2.5" />
                {timeStr}
              </span>
            )}
          </div>

          <p className="text-[10px] text-zinc-500 truncate">{item.model}</p>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
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

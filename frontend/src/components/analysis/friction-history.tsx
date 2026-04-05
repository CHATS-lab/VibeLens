import { Calendar, Clock, Coins, History, Layers, Loader2, Timer, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAppContext } from "../../app";
import type { FrictionAnalysisResult, FrictionMeta } from "../../types";
import { formatCost } from "../../utils";
import { ConfirmDialog } from "../confirm-dialog";

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

interface FrictionHistoryProps {
  onSelect: (result: FrictionAnalysisResult) => void;
  refreshTrigger: number;
  activeJobId?: string | null;
}

export function FrictionHistory({ onSelect, refreshTrigger, activeJobId }: FrictionHistoryProps) {
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
      {activeJobId && (
        <div className="px-3 py-2.5 rounded-lg bg-amber-900/20 border border-amber-700/30 animate-pulse">
          <div className="flex items-center gap-2">
            <Loader2 className="w-3 h-3 text-amber-400 animate-spin" />
            <span className="text-xs text-amber-300 font-medium">Analysis running...</span>
          </div>
        </div>
      )}
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
  const [showConfirm, setShowConfirm] = useState(false);
  const date = new Date(item.created_at);
  const dateStr = isNaN(date.getTime())
    ? item.created_at
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const timeStr = isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

  return (
    <div
      onClick={onSelect}
      className="group relative px-3 py-2.5 rounded-lg bg-zinc-800/40 hover:bg-zinc-800/80 border border-zinc-700/40 hover:border-zinc-600/50 cursor-pointer transition"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0 space-y-1.5">
          <p className="text-xs text-zinc-200 font-semibold truncate">
            {item.title || `Analysis · ${item.session_ids.length} sessions`}
          </p>

          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium bg-amber-900/30 border-amber-700/30 text-amber-400">
              <Layers className="w-2.5 h-2.5" />
              {item.session_ids.length} session{item.session_ids.length !== 1 ? "s" : ""}
            </span>
            {item.cost_usd != null && (
              <span className="inline-flex items-center gap-1 text-[10px] text-zinc-300">
                <Coins className="w-2.5 h-2.5 text-amber-400" />
                {formatCost(item.cost_usd)}
              </span>
            )}
            {item.duration_seconds != null && (
              <span className="inline-flex items-center gap-1 text-[10px] text-zinc-400">
                <Timer className="w-2.5 h-2.5" />
                {formatDuration(item.duration_seconds)}
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
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setShowConfirm(true);
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
      {showConfirm && (
        <ConfirmDialog
          title="Delete Analysis"
          message="This analysis result will be permanently deleted."
          confirmLabel="Delete"
          onConfirm={() => {
            setShowConfirm(false);
            onDelete();
          }}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </div>
  );
}

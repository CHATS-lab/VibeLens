import { Calendar, Clock, Coins, History, Layers, Loader2, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../app";
import { analysisClient } from "../../api/analysis";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import type { FrictionAnalysisResult, FrictionMeta } from "../../types";
import { formatCost } from "../../utils";
import { ConfirmDialog } from "../ui/confirm-dialog";
import { InstallLocallyDialog } from "../install-locally-dialog";

const FRICTION_API_BASE = "/api/analysis/friction";

interface FrictionHistoryProps {
  onSelect: (result: FrictionAnalysisResult) => void;
  refreshTrigger: number;
  activeJobId?: string | null;
}

export function FrictionHistory({ onSelect, refreshTrigger, activeJobId }: FrictionHistoryProps) {
  const { fetchWithToken } = useAppContext();
  const api = useMemo(
    () => analysisClient(fetchWithToken, FRICTION_API_BASE),
    [fetchWithToken],
  );
  const [items, setItems] = useState<FrictionMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.history<FrictionMeta>());
    } catch {
      /* best-effort */
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, refreshTrigger]);

  const handleSelect = useCallback(async (analysisId: string) => {
    try {
      onSelect(await api.load<FrictionAnalysisResult>(analysisId));
    } catch {
      /* best-effort */
    }
  }, [api, onSelect]);

  const handleDelete = useCallback(async (analysisId: string) => {
    setDeletingId(analysisId);
    try {
      await api.remove(analysisId);
      setItems((prev) => prev.filter((i) => i.id !== analysisId));
    } catch {
      /* best-effort */
    } finally {
      setDeletingId(null);
    }
  }, [api]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 className="w-4 h-4 text-muted animate-spin" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="px-3 py-4 text-center">
        <History className="w-5 h-5 mx-auto mb-2 text-faint" />
        <p className="text-xs text-dimmed">No past analyses</p>
      </div>
    );
  }

  return (
    <div>
      {activeJobId && (
        <div className="px-3 py-2.5 border-b border-card animate-pulse">
          <div className="flex items-center gap-2">
            <Loader2 className="w-3 h-3 text-muted animate-spin" />
            <span className="text-xs text-muted font-medium">Analysis running...</span>
          </div>
        </div>
      )}
      {items.map((item) => (
        <HistoryCard
          key={item.id}
          item={item}
          deleting={deletingId === item.id}
          onSelect={() => handleSelect(item.id)}
          onDelete={() => handleDelete(item.id)}
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
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
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
      className="group relative px-3 py-2.5 border-b border-card hover:bg-control cursor-pointer transition"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0 space-y-1">
          <p className="text-xs text-secondary font-semibold truncate">
            {item.title || `Analysis · ${item.session_count} sessions`}
          </p>
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center gap-1 text-[10px] text-accent-cyan/70">
              <Layers className="w-2.5 h-2.5" />
              {item.session_count} session{item.session_count !== 1 ? "s" : ""}
            </span>
            {(item.is_example || item.model.startsWith("mock/")) && (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-accent-amber-subtle border border-accent-amber-border text-accent-amber">Example</span>
            )}
          </div>
          {item.final_metrics.total_cost_usd != null && (
            <div className="flex items-center gap-2.5 text-[10px] text-muted">
              <span className="inline-flex items-center gap-1">
                <Coins className="w-2.5 h-2.5" />
                {formatCost(item.final_metrics.total_cost_usd)}
              </span>
            </div>
          )}
          <div className="flex items-center gap-2 text-[10px] text-muted">
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
            guardAction(() => setShowConfirm(true));
          }}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-100 p-1 text-dimmed hover:text-accent-rose hover:bg-accent-rose-subtle rounded transition"
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
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

import { Calendar, Clock, Coins, Layers, Loader2, Square, Timer, Trash2, Workflow } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../app";
import { analysisClient } from "../../api/analysis";
import { useDemoGuard } from "../../hooks/use-demo-guard";
import type { PersonalizationMeta, PersonalizationResult, PersonalizationMode } from "../../types";
import { ConfirmDialog } from "../ui/confirm-dialog";
import { InstallLocallyDialog } from "../install-locally-dialog";

const MODE_LABELS: Record<PersonalizationMode, string> = {
  recommendation: "Discover",
  creation: "Customize",
  evolution: "Evolve",
};

const MODE_API_BASE: Record<PersonalizationMode, string> = {
  recommendation: "/api/recommendation",
  creation: "/api/creation",
  evolution: "/api/evolution",
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}


function HistoryCard({
  meta,
  isLoading,
  onSelect,
  onDelete,
}: {
  meta: PersonalizationMeta;
  isLoading: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const { guardAction, showInstallDialog, setShowInstallDialog } = useDemoGuard();
  const [deleting, setDeleting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleDeleteClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      guardAction(() => setShowConfirm(true));
    },
    [guardAction],
  );

  const handleConfirmDelete = useCallback(() => {
    setShowConfirm(false);
    setDeleting(true);
    onDelete();
  }, [onDelete]);

  const date = new Date(meta.created_at);
  const dateStr = date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });

  return (
    <>
      <button
        type="button"
        onClick={onSelect}
        disabled={isLoading}
        className={`group relative w-full text-left px-3 py-2.5 border-b border-card cursor-pointer transition ${
          isLoading
            ? "bg-accent-teal-subtle/50"
            : "hover:bg-control"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0 space-y-1">
            <p className="text-xs text-secondary font-semibold truncate">
              {meta.title || "Untitled"}
            </p>
            <div className="flex items-center gap-1.5">
              <span className="inline-flex items-center gap-1 text-[10px] text-accent-cyan/70">
                <Layers className="w-2.5 h-2.5" />
                {meta.session_count} session{meta.session_count !== 1 ? "s" : ""}
              </span>
              {(meta.is_example || meta.model.startsWith("mock/")) && (
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-accent-amber-subtle border border-accent-amber-border text-accent-amber">Example</span>
              )}
            </div>
            <div className="flex items-center gap-2.5 text-[10px] text-muted">
              {meta.final_metrics?.total_cost_usd != null && (
                <span className="inline-flex items-center gap-1">
                  <Coins className="w-2.5 h-2.5" />
                  ${meta.final_metrics.total_cost_usd.toFixed(3)}
                </span>
              )}
              {meta.final_metrics?.duration != null && meta.final_metrics.duration > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Timer className="w-2.5 h-2.5" />
                  {formatDuration(meta.final_metrics.duration)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[10px] text-muted">
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
          <div
            role="button"
            tabIndex={-1}
            onClick={handleDeleteClick}
            className={`opacity-0 group-hover:opacity-100 p-1 text-dimmed hover:text-accent-rose hover:bg-accent-rose-subtle rounded transition ${deleting ? "opacity-100" : ""}`}
          >
            {deleting ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Trash2 className="w-3 h-3" />
            )}
          </div>
        </div>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-panel/60">
            <Loader2 className="w-3.5 h-3.5 text-accent-teal animate-spin" />
          </div>
        )}
      </button>
      {showConfirm && (
        <ConfirmDialog
          title="Delete Analysis"
          message="This analysis result will be permanently deleted."
          confirmLabel="Delete"
          onConfirm={handleConfirmDelete}
          onCancel={() => setShowConfirm(false)}
        />
      )}
      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </>
  );
}

export function PersonalizationHistory({
  onSelect,
  refreshTrigger,
  filterMode,
  activeJobId,
  onStop,
}: {
  onSelect: (result: PersonalizationResult) => void;
  refreshTrigger: number;
  filterMode: PersonalizationMode | null;
  activeJobId?: string | null;
  onStop?: () => void;
}) {
  const { fetchWithToken } = useAppContext();
  const [analyses, setAnalyses] = useState<PersonalizationMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingId, setLoadingId] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const apiBase = filterMode ? MODE_API_BASE[filterMode] : "/api/recommendation";
      const api = analysisClient(fetchWithToken, apiBase);
      setAnalyses(await api.history<PersonalizationMeta>());
    } catch {
      // Silently ignore — sidebar is best-effort
    } finally {
      setLoading(false);
    }
  }, [fetchWithToken, filterMode]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, refreshTrigger]);

  const filteredAnalyses = useMemo(() => {
    if (!filterMode) return analyses;
    return analyses.filter((a) => a.mode === filterMode);
  }, [analyses, filterMode]);

  const handleSelect = useCallback(
    async (meta: PersonalizationMeta) => {
      setLoadingId(meta.id);
      try {
        const api = analysisClient(fetchWithToken, MODE_API_BASE[meta.mode]);
        onSelect(await api.load<PersonalizationResult>(meta.id));
      } catch {
        // Ignore load errors
      } finally {
        setLoadingId(null);
      }
    },
    [fetchWithToken, onSelect],
  );

  const handleDelete = useCallback(
    async (analysisId: string, mode: PersonalizationMode) => {
      try {
        const api = analysisClient(fetchWithToken, MODE_API_BASE[mode]);
        await api.remove(analysisId);
        setAnalyses((prev) => prev.filter((a) => a.id !== analysisId));
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
        <Loader2 className="w-4 h-4 text-dimmed animate-spin" />
      </div>
    );
  }

  if (!loading && filteredAnalyses.length === 0) {
    return (
      <div className="px-3 py-4 text-center">
        <Workflow className="w-5 h-5 mx-auto mb-2 text-faint" />
        <p className="text-xs text-dimmed">
          {modeLabel ? `No ${modeLabel.toLowerCase()} analyses yet` : "No analyses yet"}
        </p>
      </div>
    );
  }

  return (
    <div>
      {activeJobId && (
        <div className="px-3 py-2.5 border-b border-card">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 animate-pulse">
              <Loader2 className="w-3 h-3 text-muted animate-spin" />
              <span className="text-xs text-muted font-medium">Analysis running...</span>
            </div>
            {onStop && (
              <button
                onClick={onStop}
                className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] text-rose-600 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 dark:text-rose-300 dark:hover:text-white dark:bg-rose-900/30 dark:hover:bg-rose-800/50 dark:border-rose-700/50 rounded transition"
              >
                <Square className="w-2.5 h-2.5" />
                Stop
              </button>
            )}
          </div>
        </div>
      )}
      {filteredAnalyses.map((meta) => (
        <HistoryCard
          key={meta.id}
          meta={meta}
          isLoading={loadingId === meta.id}
          onSelect={() => handleSelect(meta)}
          onDelete={() => handleDelete(meta.id, meta.mode)}
        />
      ))}
    </div>
  );
}

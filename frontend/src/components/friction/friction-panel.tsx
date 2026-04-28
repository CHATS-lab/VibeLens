import {
  Activity,
  ArrowRight,
  ClipboardList,
  Compass,
  History,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Search,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type {
  FrictionAnalysisResult,
  FrictionMeta,
  LLMStatus,
} from "../../types";
import type { PersonalizationTab } from "../personalization/personalization-view";
import { errorMessage, formatCost } from "../../utils";
import { SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH } from "../../styles";
import { SHOW_ANALYSIS_DETAIL_SECTIONS } from "../../constants";
import { analysisClient } from "../../api/analysis";
import { llmClient } from "../../api/llm";
import { useCostEstimate } from "../../hooks/use-cost-estimate";
import { useJobPolling } from "../../hooks/use-job-polling";
import { AnalysisLoadingScreen } from "../analysis-loading-screen";
import { DemoBanner } from "../demo-banner";
import { AnalysisWelcomePage, TutorialBanner } from "../analysis-welcome";
import { CostEstimateDialog } from "../cost-estimate-dialog";
import { Tooltip } from "../ui/tooltip";
import { FrictionHistory } from "./friction-history";
import { WarningsBanner } from "../warnings-banner";
import { FRICTION_TUTORIAL } from "./friction-constants";
import { CopyAllDialog } from "./friction-copy-all-dialog";
import { MitigationsSection } from "./friction-mitigations";
import { FrictionTypesSection } from "./friction-types";

const TUTORIAL_DISMISS_KEY = "vibelens-tutorial-friction-dismissed";

interface FrictionPanelProps {
  checkedIds: Set<string>;
  selectedProjectCount: number;
  activeJobId: string | null;
  onJobIdChange: (id: string | null) => void;
  onNavigateToPersonalization?: (tab: PersonalizationTab) => void;
}

const FRICTION_API_BASE = "/api/analysis/friction";

export function FrictionPanel({ checkedIds, selectedProjectCount, activeJobId, onJobIdChange, onNavigateToPersonalization }: FrictionPanelProps) {
  const { fetchWithToken, appMode, maxSessions } = useAppContext();
  const api = useMemo(
    () => analysisClient(fetchWithToken, FRICTION_API_BASE),
    [fetchWithToken],
  );
  const llmApi = useMemo(() => llmClient(fetchWithToken), [fetchWithToken]);
  const [result, setResult] = useState<FrictionAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [showSidebar, setShowSidebar] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const draggingRef = useRef(false);

  const handleDragStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      draggingRef.current = true;
      const startX = e.clientX;
      const startWidth = sidebarWidth;

      const onMouseMove = (ev: MouseEvent) => {
        if (!draggingRef.current) return;
        const delta = startX - ev.clientX;
        const newWidth = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, startWidth + delta));
        setSidebarWidth(newWidth);
      };
      const onMouseUp = () => {
        draggingRef.current = false;
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [sidebarWidth],
  );

  const refreshLlmStatus = useCallback(async () => {
    try {
      setLlmStatus(await llmApi.status());
    } catch {
      /* best-effort */
    }
  }, [llmApi]);

  useEffect(() => {
    refreshLlmStatus();
  }, [refreshLlmStatus]);

  const { estimate, estimating, requestEstimate, clearEstimate } = useCostEstimate(
    fetchWithToken,
    setError,
  );

  const handleRequestAnalysis = useCallback(() => {
    if (checkedIds.size === 0) return;
    setError(null);
    requestEstimate(`${FRICTION_API_BASE}/estimate`, {
      session_ids: [...checkedIds],
    });
  }, [checkedIds, requestEstimate]);

  const handleConfirmAnalysis = useCallback(async () => {
    clearEstimate();
    setLoading(true);
    setError(null);
    try {
      const data = await api.submit({ session_ids: [...checkedIds] });
      if (data.status === "completed" && data.analysis_id) {
        const loaded = await api.load<FrictionAnalysisResult>(data.analysis_id);
        setResult(loaded);
        setHistoryRefresh((n) => n + 1);
        setLoading(false);
      } else {
        onJobIdChange(data.job_id);
      }
    } catch (err) {
      setError(errorMessage(err));
      setLoading(false);
    }
  }, [api, checkedIds, clearEstimate, onJobIdChange]);

  const handleHistorySelect = useCallback((loaded: FrictionAnalysisResult) => {
    setResult(loaded);
  }, []);

  // Auto-load the most recent analysis on mount so users see results immediately
  const autoLoadedRef = useRef(false);
  useEffect(() => {
    if (autoLoadedRef.current) return;
    autoLoadedRef.current = true;
    (async () => {
      try {
        const history = await api.history<FrictionMeta>();
        if (history.length === 0) return;
        handleHistorySelect(await api.load<FrictionAnalysisResult>(history[0].id));
      } catch {
        /* best-effort — fall back to welcome page */
      }
    })();
  }, [api, handleHistorySelect]);

  const handleNewAnalysis = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  useEffect(() => {
    if (activeJobId) setLoading(true);
  }, [activeJobId]);

  const handleJobCompleted = useCallback(
    async (analysisId: string) => {
      onJobIdChange(null);
      setLoading(false);
      try {
        const loaded = await api.load<FrictionAnalysisResult>(analysisId);
        setResult(loaded);
        setHistoryRefresh((n) => n + 1);
      } catch {
        /* best-effort */
      }
    },
    [api, onJobIdChange],
  );
  const handleJobFailed = useCallback(
    (message: string) => {
      onJobIdChange(null);
      setLoading(false);
      setError(message);
    },
    [onJobIdChange],
  );
  const handleJobCancelled = useCallback(() => {
    onJobIdChange(null);
    setLoading(false);
  }, [onJobIdChange]);

  useJobPolling(activeJobId, FRICTION_API_BASE, fetchWithToken, {
    onCompleted: handleJobCompleted,
    onFailed: handleJobFailed,
    onCancelled: handleJobCancelled,
  });

  const handleStopAnalysis = useCallback(async () => {
    if (!activeJobId) return;
    try {
      await api.cancelJob(activeJobId);
    } catch {
      /* best-effort */
    }
    onJobIdChange(null);
    setLoading(false);
  }, [activeJobId, api, onJobIdChange]);

  const sidebar = useMemo(() => (
    <>
      {showSidebar && (
        <>
          <div
            onMouseDown={handleDragStart}
            className="w-1 shrink-0 cursor-col-resize bg-control hover:bg-control-hover transition-colors"
          />
          <div
            className="shrink-0 border-l border-default bg-panel/50 flex flex-col"
            style={{ width: sidebarWidth }}
          >
            <div className="shrink-0 flex items-center justify-between px-3 pt-3 pb-2 border-b border-card">
              <div className="flex items-center gap-1.5">
                <History className="w-3.5 h-3.5 text-accent-cyan" />
                <span className="text-xs font-semibold text-secondary tracking-wide uppercase">History</span>
              </div>
              <Tooltip text="Hide history">
                <button
                  onClick={() => setShowSidebar(false)}
                  className="p-1 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
                >
                  <PanelRightClose className="w-3.5 h-3.5" />
                </button>
              </Tooltip>
            </div>
            <div className="flex-1 overflow-y-auto p-3 pt-1">
              <FrictionHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} activeJobId={activeJobId} activeResultId={result?.id ?? null} />
            </div>
          </div>
        </>
      )}
      {!showSidebar && (
        <div className="shrink-0 border-l border-default bg-panel/50 flex flex-col items-center pt-3 px-1">
          <Tooltip text="Show history">
            <button
              onClick={() => setShowSidebar(true)}
              className="p-1.5 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
            >
              <PanelRightOpen className="w-4 h-4" />
            </button>
          </Tooltip>
        </div>
      )}
    </>
  ), [showSidebar, sidebarWidth, handleDragStart, handleHistorySelect, historyRefresh, activeJobId, result?.id]);

  const estimateDialog = estimate && (
    <CostEstimateDialog
      estimate={estimate}
      sessionCount={checkedIds.size}
      onConfirm={handleConfirmAnalysis}
      onCancel={clearEstimate}
      backendId={llmStatus?.backend_id}
      multipleProjects={selectedProjectCount > 1}
    />
  );

  if (loading || estimating) {
    return (
      <div className="h-full flex flex-col">
        <div className="px-6 pt-5 pb-2">
          <TutorialBanner
            tutorial={FRICTION_TUTORIAL}
            accentColor="cyan"
            dismissKey={TUTORIAL_DISMISS_KEY}
          />
        </div>
        <AnalysisLoadingScreen
          accent="amber"
          title="Identifying patterns that slow you down"
          sublabel={estimating ? "Estimating cost..." : "Usually takes 2-5 minutes"}
          sessionCount={checkedIds.size}
          onStop={activeJobId ? handleStopAnalysis : undefined}
        />
      </div>
    );
  }

  if (!result) {
    return (
      <div className="h-full flex">
        <div className="flex-1 overflow-y-auto">
          <div className="px-6 pt-5 pb-2">
            <TutorialBanner
              tutorial={FRICTION_TUTORIAL}
              accentColor="cyan"
              dismissKey={TUTORIAL_DISMISS_KEY}
            />
          </div>
          <AnalysisWelcomePage
            icon={<Sparkles className="w-12 h-12 text-amber-600 dark:text-amber-400" />}
            title="Productivity Tips"
            description="Identify patterns that slow you down. Select sessions and run analysis to detect wasted effort, recurring mistakes, and get concrete improvement suggestions."
            accentColor="amber"
            llmStatus={llmStatus}
            fetchWithToken={fetchWithToken}
            onLlmConfigured={refreshLlmStatus}
            checkedCount={checkedIds.size}
            maxSessions={maxSessions}
            error={error}
            onRun={handleRequestAnalysis}
            isDemo={appMode === "demo"}
          />
        </div>
        {sidebar}
        {estimateDialog}
      </div>
    );
  }

  return (
    <div className="h-full flex">
      <div className="flex-1 overflow-y-auto">
        <div className="px-6 pt-5 pb-2">
          <TutorialBanner
            tutorial={FRICTION_TUTORIAL}
            accentColor="cyan"
            dismissKey={TUTORIAL_DISMISS_KEY}
          />
        </div>
        <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
          {result.backend === "mock" && <DemoBanner />}
          <ResultHeader result={result} onNew={handleNewAnalysis} />
          {result.warnings && result.warnings.length > 0 && (
            <WarningsBanner warnings={result.warnings} />
          )}
          {result.mitigations.length > 0 ? (
            <MitigationsSection mitigations={result.mitigations} frictionTypes={result.friction_types} />
          ) : (
            <NoIssuesEmptyState onNavigate={onNavigateToPersonalization} />
          )}
          {SHOW_ANALYSIS_DETAIL_SECTIONS && result.friction_types.length > 0 && (
            <FrictionTypesSection frictionTypes={result.friction_types} />
          )}
          <AnalysisMeta result={result} />
        </div>
      </div>
      {sidebar}
    </div>
  );
}

function ResultHeader({
  result,
  onNew,
}: {
  result: FrictionAnalysisResult;
  onNew: () => void;
}) {
  const tipCount = result.mitigations.length;
  const sessionCount = result.session_ids.length;
  const [copyAllOpen, setCopyAllOpen] = useState(false);

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <Activity className="w-6 h-6 text-accent-amber" />
        <div>
          <div className="flex items-center gap-2.5">
            {(result.is_example || result.backend === "mock") && (
              <span className="px-2 py-0.5 rounded border text-[11px] font-semibold bg-accent-amber-subtle border-accent-amber text-accent-amber">
                Example
              </span>
            )}
            <h2 className="text-xl font-bold text-primary">
              {result.title || "Productivity Tips"}
            </h2>
          </div>
          <p className="text-sm text-muted">
            {tipCount} productivity tip{tipCount !== 1 ? "s" : ""} across {sessionCount} session{sessionCount !== 1 ? "s" : ""}
            {result.skipped_session_ids.length > 0 && (
              <span className="text-dimmed">
                {" "}&middot; {result.skipped_session_ids.length} skipped
              </span>
            )}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {tipCount > 0 && (
          <Tooltip text="Copy all tips as a bullet list">
            <button
              onClick={() => setCopyAllOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold whitespace-nowrap text-accent-amber hover:text-amber-800 dark:hover:text-white bg-accent-amber-subtle hover:bg-amber-100 dark:hover:bg-amber-600/40 border border-accent-amber rounded-lg transition"
            >
              <ClipboardList className="w-3.5 h-3.5 shrink-0" />
              Copy All
            </button>
          </Tooltip>
        )}
        <Tooltip text="Analyze your own sessions">
          <button
            onClick={onNew}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold whitespace-nowrap text-accent-amber hover:text-amber-800 dark:hover:text-white bg-accent-amber-subtle hover:bg-amber-100 dark:hover:bg-amber-600/40 border border-accent-amber rounded-lg transition"
          >
            <Plus className="w-3.5 h-3.5 shrink-0" />
            New
          </button>
        </Tooltip>
      </div>
      {copyAllOpen && (
        <CopyAllDialog
          mitigations={result.mitigations}
          onClose={() => setCopyAllOpen(false)}
        />
      )}
    </div>
  );
}

function AnalysisMeta({ result }: { result: FrictionAnalysisResult }) {
  const computedDate = new Date(result.created_at);
  const dateStr = isNaN(computedDate.getTime())
    ? result.created_at
    : computedDate.toLocaleDateString();
  const timeStr = isNaN(computedDate.getTime())
    ? ""
    : computedDate.toLocaleTimeString();

  return (
    <Tooltip text="Inference backend, model, and estimated API cost for this analysis run">
      <div className="border-t border-card pt-4 text-xs text-dimmed flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{result.backend}/{result.model}</span>
          {result.final_metrics.total_cost_usd != null && (
            <span className="border-l border-card pl-2">
              {formatCost(result.final_metrics.total_cost_usd)}
            </span>
          )}
          {result.batch_count > 1 && (
            <span className="border-l border-card pl-2">
              {result.batch_count} batches
            </span>
          )}
        </div>
        <span className="shrink-0">{dateStr} {timeStr}</span>
      </div>
    </Tooltip>
  );
}

function NoIssuesEmptyState({
  onNavigate,
}: {
  onNavigate?: (tab: PersonalizationTab) => void;
}) {
  return (
    <div className="relative w-full rounded-lg border border-amber-300 dark:border-tutorial-amber-border bg-amber-50 dark:bg-tutorial-amber-bg px-6 py-8 overflow-hidden">
      <div className="flex flex-col items-center text-center gap-3 mb-6">
        <div className="shrink-0 p-3 rounded-xl bg-amber-100 dark:bg-amber-500/15 border border-amber-200 dark:border-amber-500/20">
          <Activity className="w-6 h-6 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="space-y-1.5 max-w-md">
          <h3 className="text-base font-semibold text-primary">
            No productivity tips found
          </h3>
          <p className="text-sm text-secondary leading-relaxed">
            Your sessions ran smoothly. Pick more or longer sessions for richer signal, or try the tools below.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl mx-auto">
        <EmptyStateAction
          icon={Compass}
          label="Browse Explore"
          description="Skills, sub-agents, and hooks from the community."
          onClick={() => onNavigate?.("explore")}
          disabled={!onNavigate}
        />
        <EmptyStateAction
          icon={Search}
          label="Try Recommend"
          description="Match your sessions to skills that fit your workflow."
          onClick={() => onNavigate?.("retrieve")}
          disabled={!onNavigate}
        />
      </div>
    </div>
  );
}

function EmptyStateAction({
  icon: Icon,
  label,
  description,
  onClick,
  disabled,
}: {
  icon: LucideIcon;
  label: string;
  description: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="group flex items-start gap-3 px-4 py-3 text-left rounded-lg border border-amber-200 dark:border-amber-500/20 bg-panel hover:border-amber-400 dark:hover:border-amber-400/40 hover:bg-amber-50/80 dark:hover:bg-amber-500/10 transition disabled:opacity-40 disabled:cursor-not-allowed"
    >
      <div className="shrink-0 p-2 rounded-lg bg-amber-100 dark:bg-amber-500/15 border border-amber-200 dark:border-amber-500/20">
        <Icon className="w-4 h-4 text-amber-600 dark:text-amber-400" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-semibold text-primary">{label}</span>
          <ArrowRight className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition" />
        </div>
        <p className="text-xs text-secondary mt-0.5 leading-relaxed">{description}</p>
      </div>
    </button>
  );
}

import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Clock,
  Coins,
  Footprints,
  History,
  Lightbulb,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Shield,
  Sparkles,
  Target,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type {
  AnalysisJobResponse,
  AnalysisJobStatus,
  CostEstimate,
  FrictionAnalysisResult,
  FrictionCost,
  FrictionType,
  LLMStatus,
  Mitigation,
} from "../../types";
import { formatCost, formatDuration, formatTokens } from "../../utils";
import { SEVERITY_COLORS, SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH } from "../../styles";
import { SHOW_ANALYSIS_DETAIL_SECTIONS } from "../../constants";
import { DemoBanner } from "../demo-banner";
import { AnalysisWelcomePage, TutorialBanner } from "../analysis-welcome";
import { LoadingSpinner, LoadingSpinnerRings } from "../loading-spinner";
import { CostEstimateDialog } from "../cost-estimate-dialog";
import { Tooltip } from "../tooltip";
import { FrictionHistory } from "./friction-history";
import { BulletText } from "../bullet-text";
import { CopyButton } from "../copy-button";
import { WarningsBanner } from "../warnings-banner";

const SEVERITY_LABELS: Record<number, string> = {
  1: "Minor",
  2: "Low",
  3: "Moderate",
  4: "High",
  5: "Critical",
};

const SEVERITY_DESCRIPTIONS: Record<number, string> = {
  1: "Minor — Small correction, resolved immediately",
  2: "Low — Needed to explain once more",
  3: "Moderate — Multiple corrections or visible frustration",
  4: "High — Had to take over or revert changes",
  5: "Critical — Gave up on the task entirely",
};

/** Convert kebab-case type_name to Title Case for display. */
function frictionTypeLabel(typeName: string): string {
  return typeName
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function confidenceLevel(c: number): "high" | "medium" | "low" {
  if (c >= 0.7) return "high";
  if (c >= 0.4) return "medium";
  return "low";
}

const POLL_INTERVAL_MS = 3000;

const FRICTION_TUTORIAL = {
  title: "How does this work?",
  description: "VibeLens reviews your coding sessions to find where things went wrong: getting stuck, repeating yourself, or fixing agent mistakes. You get practical tips to avoid those issues next time.",
};

interface FrictionPanelProps {
  checkedIds: Set<string>;
  activeJobId: string | null;
  onJobIdChange: (id: string | null) => void;
}

export function FrictionPanel({ checkedIds, activeJobId, onJobIdChange }: FrictionPanelProps) {
  const { fetchWithToken, appMode, maxAnalysisSessions } = useAppContext();
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
      const res = await fetchWithToken("/api/llm/status");
      if (res.ok) setLlmStatus(await res.json());
    } catch {
      /* ignore — status check is best-effort */
    }
  }, [fetchWithToken]);

  useEffect(() => {
    refreshLlmStatus();
  }, [refreshLlmStatus]);

  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);

  const handleRequestAnalysis = useCallback(async () => {
    if (checkedIds.size === 0) return;
    setEstimating(true);
    setError(null);
    try {
      const res = await fetchWithToken("/api/analysis/friction/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: [...checkedIds] }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      setEstimate(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setEstimating(false);
    }
  }, [checkedIds, fetchWithToken]);

  const handleConfirmAnalysis = useCallback(async () => {
    setEstimate(null);
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithToken("/api/analysis/friction", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: [...checkedIds] }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      const data: AnalysisJobResponse = await res.json();
      if (data.status === "completed" && data.analysis_id) {
        const loadRes = await fetchWithToken(`/api/analysis/friction/${data.analysis_id}`);
        if (loadRes.ok) {
          setResult(await loadRes.json());
          setHistoryRefresh((n) => n + 1);
        }
        setLoading(false);
      } else {
        onJobIdChange(data.job_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  }, [checkedIds, fetchWithToken, onJobIdChange]);

  const handleHistorySelect = useCallback((loaded: FrictionAnalysisResult) => {
    setResult(loaded);
  }, []);

  // In demo mode, auto-load the most recent analysis so users see results immediately
  const demoLoadedRef = useRef(false);
  useEffect(() => {
    if (appMode !== "demo" || demoLoadedRef.current) return;
    demoLoadedRef.current = true;
    (async () => {
      try {
        const res = await fetchWithToken("/api/analysis/friction/history");
        if (!res.ok) return;
        const history: { analysis_id: string }[] = await res.json();
        if (history.length === 0) return;
        const loadRes = await fetchWithToken(`/api/analysis/friction/${history[0].analysis_id}`);
        if (!loadRes.ok) return;
        handleHistorySelect(await loadRes.json());
      } catch {
        /* best-effort — fall back to welcome page */
      }
    })();
  }, [appMode, fetchWithToken, handleHistorySelect]);

  const handleNewAnalysis = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  useEffect(() => {
    if (!activeJobId) return;
    setLoading(true);
    const interval = setInterval(async () => {
      try {
        const res = await fetchWithToken(`/api/analysis/friction/jobs/${activeJobId}`);
        if (!res.ok) return;
        const status: AnalysisJobStatus = await res.json();
        if (status.status === "completed" && status.analysis_id) {
          onJobIdChange(null);
          setLoading(false);
          const loadRes = await fetchWithToken(`/api/analysis/friction/${status.analysis_id}`);
          if (loadRes.ok) {
            setResult(await loadRes.json());
            setHistoryRefresh((n) => n + 1);
          }
        } else if (status.status === "failed") {
          onJobIdChange(null);
          setLoading(false);
          setError(status.error_message || "Analysis failed");
        } else if (status.status === "cancelled") {
          onJobIdChange(null);
          setLoading(false);
        }
      } catch {
        /* polling is best-effort */
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [activeJobId, fetchWithToken, onJobIdChange]);

  const handleStopAnalysis = useCallback(async () => {
    if (!activeJobId) return;
    try {
      await fetchWithToken(`/api/analysis/friction/jobs/${activeJobId}/cancel`, {
        method: "POST",
      });
    } catch {
      /* best-effort */
    }
    onJobIdChange(null);
    setLoading(false);
  }, [activeJobId, fetchWithToken, onJobIdChange]);

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
              <FrictionHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} activeJobId={activeJobId} />
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
  ), [showSidebar, sidebarWidth, handleDragStart, handleHistorySelect, historyRefresh, activeJobId]);

  const estimateDialog = estimate && (
    <CostEstimateDialog
      estimate={estimate}
      sessionCount={checkedIds.size}
      onConfirm={handleConfirmAnalysis}
      onCancel={() => setEstimate(null)}
    />
  );

  if (loading || estimating) {
    if (activeJobId) {
      return (
        <div className="flex items-center justify-center h-full">
          <div className="flex flex-col items-center gap-5 max-w-md">
            <LoadingSpinnerRings color="amber" />
            <div className="text-center space-y-1.5">
              <p className="text-base font-semibold text-primary">
                Analyzing {checkedIds.size} session{checkedIds.size !== 1 ? "s" : ""} for friction
              </p>
              <p className="text-sm text-secondary">Identifying patterns that slow you down</p>
            </div>
            <TutorialBanner tutorial={FRICTION_TUTORIAL} accentColor="cyan" />
            <div className="flex flex-col items-center gap-3 mt-1">
              <button
                onClick={handleStopAnalysis}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs text-rose-600 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 dark:text-rose-300 dark:hover:text-white dark:bg-rose-900/30 dark:hover:bg-rose-800/50 dark:border-rose-700/50 rounded-md transition"
              >
                Stop
              </button>
              <div className="text-center space-y-1">
                <p className="text-sm text-muted">Usually takes 2-5 minutes</p>
                <p className="text-sm text-muted">Running in background — you can switch tabs</p>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return (
      <LoadingSpinner
        label={
          estimating
            ? `Estimating cost for ${checkedIds.size} session${checkedIds.size !== 1 ? "s" : ""}`
            : `Analyzing ${checkedIds.size} session${checkedIds.size !== 1 ? "s" : ""} for friction`
        }
        sublabel={estimating ? "Preparing batches..." : "This may take a moment"}
        color="amber"
      />
    );
  }

  if (!result) {
    return (
      <div className="h-full flex">
        <div className="flex-1">
          <AnalysisWelcomePage
            icon={<Sparkles className="w-12 h-12 text-amber-600 dark:text-amber-400" />}
            title="Productivity Tips"
            description="Identify patterns that slow you down. Select sessions and run analysis to detect wasted effort, recurring mistakes, and get concrete improvement suggestions."
            accentColor="amber"
            llmStatus={llmStatus}
            fetchWithToken={fetchWithToken}
            onLlmConfigured={refreshLlmStatus}
            checkedCount={checkedIds.size}
            maxSessions={maxAnalysisSessions}
            error={error}
            onRun={handleRequestAnalysis}
            isDemo={appMode === "demo"}
            tutorial={FRICTION_TUTORIAL}
            tutorialAccentColor="cyan"
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
        <div className="max-w-4xl mx-auto px-6 py-8 space-y-8">
          {result.backend_id === "mock" && <DemoBanner />}
          <ResultHeader result={result} onNew={handleNewAnalysis} />
          <TutorialBanner tutorial={FRICTION_TUTORIAL} accentColor="cyan" />
          {result.warnings && result.warnings.length > 0 && (
            <WarningsBanner warnings={result.warnings} />
          )}
          {result.mitigations.length > 0 && (
            <MitigationsSection mitigations={result.mitigations} frictionTypes={result.friction_types} />
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

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <Activity className="w-6 h-6 text-accent-amber" />
        <div>
          <div className="flex items-center gap-2.5">
            {(result.is_example || result.backend_id === "mock") && (
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
      <Tooltip text="Analyze your own sessions">
        <button
          onClick={onNew}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-accent-amber hover:text-amber-800 dark:hover:text-white bg-accent-amber-subtle hover:bg-amber-100 dark:hover:bg-amber-600/40 border border-accent-amber rounded-lg transition"
        >
          <Plus className="w-3.5 h-3.5" />
          New
        </button>
      </Tooltip>
    </div>
  );
}

function SectionHeader({
  icon,
  title,
  tooltip,
}: {
  icon: React.ReactNode;
  title: string;
  tooltip: string;
}) {
  return (
    <Tooltip text={tooltip}>
      <div className="flex items-center gap-2 mb-3 cursor-help">
        <span className="text-accent-amber">{icon}</span>
        <h3 className="text-lg font-semibold text-primary">{title}</h3>
      </div>
    </Tooltip>
  );
}

function MitigationsSection({ mitigations, frictionTypes }: { mitigations: Mitigation[]; frictionTypes: FrictionType[] }) {
  const sorted = [...mitigations].sort((a, b) => b.confidence - a.confidence);

  return (
    <div>
      <SectionHeader
        icon={<Lightbulb className="w-5 h-5" />}
        title="Productivity Tips"
        tooltip="Concrete steps you can take to avoid these issues in the future"
      />
      <div className="space-y-3">
        {sorted.map((m, i) => (
          <MitigationCard key={i} mitigation={m} frictionTypes={frictionTypes} />
        ))}
      </div>
    </div>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const level = confidenceLevel(confidence);
  const barColor = level === "high" ? "bg-amber-500" : level === "medium" ? "bg-amber-500" : "bg-control-hover";
  const textColor = level === "high" ? "text-accent-amber" : level === "medium" ? "text-accent-amber" : "text-dimmed";

  return (
    <Tooltip text={`${pct}% confidence`}>
      <div className="flex items-center gap-2 cursor-help">
        <div className="w-16 h-1.5 rounded-full bg-control-hover/60 overflow-hidden">
          <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-xs font-semibold ${textColor} tabular-nums`}>{pct}%</span>
      </div>
    </Tooltip>
  );
}

function MitigationCard({ mitigation, frictionTypes }: { mitigation: Mitigation; frictionTypes: FrictionType[] }) {
  const [rationaleExpanded, setRationaleExpanded] = useState(true);
  const [typesExpanded, setTypesExpanded] = useState(false);

  const addressedTypes = mitigation.addressed_friction_types ?? [];
  const matchedTypes = frictionTypes.filter((ft) =>
    addressedTypes.includes(ft.type_name)
  );

  return (
    <div className="border border-zinc-200 dark:border-zinc-700/30 rounded-xl bg-zinc-50/50 dark:bg-zinc-800/20 overflow-hidden">
      {/* Header: Title + Confidence */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="text-base font-bold text-primary">{mitigation.title}</span>
            {mitigation.confidence > 0 && <ConfidenceBar confidence={mitigation.confidence} />}
            <CopyButton text={mitigation.action} />
          </div>
        </div>
        <BulletText text={mitigation.action} className="text-sm text-secondary leading-relaxed mt-1.5" />
      </div>

      {/* Rationale */}
      {mitigation.rationale && (
        <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
          <button
            onClick={() => setRationaleExpanded(!rationaleExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {rationaleExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-amber" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-amber" />}
            <Lightbulb className="w-3.5 h-3.5 text-accent-amber" />
            <span className="text-sm font-semibold text-accent-amber uppercase tracking-wide">Why this helps</span>
          </button>
          {rationaleExpanded && (
            <BulletText text={mitigation.rationale} className="text-sm text-secondary leading-relaxed mt-1.5" />
          )}
        </div>
      )}

      {/* Addressed Friction Types */}
      {matchedTypes.length > 0 && (
        <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-700/20">
          <button
            onClick={() => setTypesExpanded(!typesExpanded)}
            className="flex items-center gap-1.5 text-xs hover:bg-control/40 rounded transition"
          >
            {typesExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-accent-amber" />
              : <ChevronRight className="w-3.5 h-3.5 text-accent-amber" />}
            <Target className="w-3.5 h-3.5 text-accent-amber" />
            <span className="text-sm font-semibold text-accent-amber uppercase tracking-wide">What this fixes</span>
            <span className="text-dimmed">({matchedTypes.length})</span>
          </button>
          {typesExpanded && (
            <div className="mt-2.5 space-y-3">
              {matchedTypes.map((ft) => (
                <div key={ft.type_name} className="border-l-2 border-amber-300 dark:border-amber-700/50 pl-3 space-y-1.5">
                  <h6 className="text-base font-semibold text-primary">
                    {frictionTypeLabel(ft.type_name)}
                  </h6>
                  <BulletText text={ft.description} className="text-sm text-secondary leading-relaxed" />
                  <FrictionRefList refs={ft.example_refs} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FrictionTypesSection({ frictionTypes }: { frictionTypes: FrictionType[] }) {
  const sorted = [...frictionTypes].sort((a, b) => b.severity - a.severity);

  return (
    <div>
      <SectionHeader
        icon={<AlertTriangle className="w-5 h-5" />}
        title="What Went Wrong"
        tooltip="Moments where things slowed you down or went off track"
      />
      <div className="space-y-3">
        {sorted.map((ft) => (
          <FrictionTypeCard key={ft.type_name} frictionType={ft} />
        ))}
      </div>
    </div>
  );
}

function FrictionTypeCard({ frictionType }: { frictionType: FrictionType }) {
  const [expanded, setExpanded] = useState(false);
  const label = frictionTypeLabel(frictionType.type_name);

  return (
    <div
      onClick={() => setExpanded((v) => !v)}
      className="border border-card rounded-xl overflow-hidden cursor-pointer hover:border-hover transition-all"
    >
      <div className="px-4 py-3 space-y-2.5">
        <div className="flex items-center gap-2.5 flex-wrap">
          <SeverityBadge severity={frictionType.severity} />
          <h6 className="text-base font-semibold text-primary">{label}</h6>
          <div className="ml-auto shrink-0">
            {expanded
              ? <ChevronDown className="w-4 h-4 text-dimmed" />
              : <ChevronRight className="w-4 h-4 text-dimmed" />}
          </div>
        </div>
        <BulletText text={frictionType.description} className="text-sm text-secondary leading-relaxed" />
      </div>
      {expanded && (
        <div className="px-4 pb-3.5 space-y-2.5 border-t border-card pt-3 mx-3 mb-1">
          <CostBadges cost={frictionType.friction_cost} />
          <FrictionRefList refs={frictionType.example_refs} />
        </div>
      )}
    </div>
  );
}

function FrictionRefList({ refs }: { refs: FrictionType["example_refs"] }) {
  if (refs.length === 0) return null;
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-1.5 text-sm">
        <BookOpen className="w-4 h-4 text-accent-cyan" />
        <span className="font-semibold text-accent-cyan">Reference:</span>
      </div>
      {refs.map((ref, i) => (
        <FrictionStepButton key={`${ref.session_id}-${ref.start_step_id}-${i}`} ref_={ref} />
      ))}
    </div>
  );
}

function FrictionStepButton({ ref_ }: { ref_: FrictionType["example_refs"][number] }) {
  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const url = `${window.location.origin}?session=${ref_.session_id}&step=${ref_.start_step_id}`;
      window.open(url, "_blank");
    },
    [ref_.session_id, ref_.start_step_id],
  );

  return (
    <Tooltip text="Open step in session viewer">
      <button
        onClick={handleClick}
        className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-control-hover/50 text-secondary hover:bg-amber-50 dark:hover:bg-amber-900/40 hover:text-accent-amber transition font-mono border border-hover/30 hover:border-accent-amber"
      >
        {ref_.start_step_id.slice(0, 8)}
        <ArrowUpRight className="w-3 h-3" />
      </button>
    </Tooltip>
  );
}

function CostBadges({ cost }: { cost: FrictionCost }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-1.5 text-sm">
        <Zap className="w-4 h-4 text-accent-amber" />
        <span className="font-semibold text-accent-amber">Impact:</span>
      </div>
      <Tooltip text="Steps affected by this issue">
        <span className="inline-flex items-center gap-1.5 text-sm text-muted cursor-help">
          <Footprints className="w-4 h-4 text-rose-600 dark:text-rose-400" />
          {cost.affected_steps} step{cost.affected_steps !== 1 ? "s" : ""}
        </span>
      </Tooltip>
      {cost.affected_time_seconds != null && (
        <Tooltip text="Duration affected">
          <span className="inline-flex items-center gap-1.5 text-sm text-muted cursor-help">
            <Clock className="w-4 h-4 text-sky-600 dark:text-sky-400" />
            {formatDuration(cost.affected_time_seconds)}
          </span>
        </Tooltip>
      )}
      {cost.affected_tokens != null && (
        <Tooltip text="Tokens affected">
          <span className="inline-flex items-center gap-1.5 text-sm text-muted cursor-help">
            <Coins className="w-4 h-4 text-accent-amber" />
            {formatTokens(cost.affected_tokens)}
          </span>
        </Tooltip>
      )}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: number }) {
  const colorClass = SEVERITY_COLORS[severity] ?? SEVERITY_COLORS[3];
  const label = SEVERITY_LABELS[severity] ?? "Unknown";
  return (
    <Tooltip text={SEVERITY_DESCRIPTIONS[severity] ?? "Impact severity rating"}>
      <span className={`inline-flex items-center justify-center gap-1.5 min-w-[6.5rem] px-2.5 py-1 rounded text-sm font-medium border shrink-0 ${colorClass}`}>
        <Shield className="w-4 h-4" />
        {label}
      </span>
    </Tooltip>
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
          <span>{result.backend_id}/{result.model}</span>
          {result.metrics.cost_usd != null && (
            <span className="border-l border-card pl-2">
              {formatCost(result.metrics.cost_usd)}
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

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
  User,
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
import { DemoBanner } from "../demo-banner";
import { AnalysisWelcomePage } from "../analysis-welcome";
import { LoadingSpinner, LoadingSpinnerRings } from "../loading-spinner";
import { CostEstimateDialog } from "../cost-estimate-dialog";
import { Tooltip } from "../tooltip";
import { FrictionHistory } from "./friction-history";
import { BulletText } from "../bullet-text";
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

const FRICTION_TYPE_LABELS: Record<string, string> = {
  "misunderstood-intent": "Misunderstood What You Wanted",
  "wrong-approach": "Wrong Approach Taken",
  "repeated-failure": "Kept Failing Despite Corrections",
  "quality-rejection": "Output Quality Not Accepted",
  "scope-violation": "Did Too Much or Too Little",
  "instruction-violation": "Ignored Your Rules",
  "stale-context": "Forgot What You Said",
  "destructive-action": "Made Unwanted Changes",
  "slow-progress": "Too Slow",
  "abandoned-task": "You Gave Up",
};

function confidenceLevel(c: number): "high" | "medium" | "low" {
  if (c >= 0.7) return "high";
  if (c >= 0.4) return "medium";
  return "low";
}

const POLL_INTERVAL_MS = 3000;

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
            className="w-1 shrink-0 cursor-col-resize bg-zinc-800 hover:bg-zinc-600 transition-colors"
          />
          <div
            className="shrink-0 border-l border-zinc-800 bg-zinc-900/50 flex flex-col"
            style={{ width: sidebarWidth }}
          >
            <div className="shrink-0 flex items-center justify-between px-3 pt-3 pb-1">
              <div className="flex items-center gap-1.5">
                <History className="w-3.5 h-3.5 text-zinc-500" />
                <span className="text-xs font-medium text-zinc-400">History</span>
              </div>
              <button
                onClick={() => setShowSidebar(false)}
                className="p-0.5 text-zinc-500 hover:text-zinc-300 transition"
                title="Hide history"
              >
                <PanelRightClose className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 pt-1">
              <FrictionHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} activeJobId={activeJobId} />
            </div>
          </div>
        </>
      )}
      {!showSidebar && (
        <div className="shrink-0 border-l border-zinc-800 bg-zinc-900/50 flex flex-col items-center pt-3 px-1">
          <button
            onClick={() => setShowSidebar(true)}
            className="p-1 text-zinc-500 hover:text-zinc-300 transition"
            title="Show history"
          >
            <PanelRightOpen className="w-4 h-4" />
          </button>
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
          <div className="flex flex-col items-center gap-5">
            <LoadingSpinnerRings color="amber" />
            <div className="text-center space-y-1.5">
              <p className="text-base font-semibold text-white">
                Analyzing {checkedIds.size} session{checkedIds.size !== 1 ? "s" : ""} for friction
              </p>
              <p className="text-sm text-zinc-300">Identifying patterns that slow you down</p>
            </div>
            <div className="flex flex-col items-center gap-3 mt-1">
              <div className="text-center space-y-1">
                <p className="text-sm text-zinc-400">Running in background — you can switch tabs</p>
                <p className="text-sm text-zinc-400">Usually takes 2-5 minutes</p>
              </div>
              <button
                onClick={handleStopAnalysis}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs text-rose-300 hover:text-white bg-rose-900/30 hover:bg-rose-800/50 border border-rose-700/50 rounded-md transition"
              >
                Stop
              </button>
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
            icon={<Sparkles className="w-12 h-12 text-amber-400/50" />}
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
          {result.warnings && result.warnings.length > 0 && (
            <WarningsBanner warnings={result.warnings} />
          )}
          <SummaryCard summary={result.summary} userProfile={result.user_profile} />
          {result.mitigations.length > 0 && (
            <MitigationsSection mitigations={result.mitigations} frictionTypes={result.friction_types} />
          )}
          {result.friction_types.length > 0 && (
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
        <Activity className="w-6 h-6 text-amber-400" />
        <div>
          <h2 className="text-xl font-bold text-zinc-100">
            {result.title || "Productivity Tips"}
          </h2>
          <p className="text-sm text-zinc-400">
            {tipCount} productivity tip{tipCount !== 1 ? "s" : ""} across {sessionCount} session{sessionCount !== 1 ? "s" : ""}
            {result.skipped_session_ids.length > 0 && (
              <span className="text-zinc-500">
                {" "}&middot; {result.skipped_session_ids.length} skipped
              </span>
            )}
          </p>
        </div>
      </div>
      <button
        onClick={onNew}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-amber-200 hover:text-white bg-amber-600/20 hover:bg-amber-600/40 border border-amber-500/40 rounded-lg transition"
      >
        <Plus className="w-3.5 h-3.5" />
        New
      </button>
    </div>
  );
}

function SummaryCard({
  summary,
  userProfile,
}: {
  summary: string;
  userProfile?: string | null;
}) {
  return (
    <div className="border border-zinc-700/40 rounded-xl bg-zinc-900/60 overflow-hidden">
      <div className="px-5 pt-4 pb-4">
        <div className="flex items-center gap-2 mb-2.5">
          <div className="p-1.5 rounded-lg bg-zinc-700/30">
            <Sparkles className="w-4 h-4 text-amber-400" />
          </div>
          <h3 className="text-sm font-semibold text-zinc-100">Summary</h3>
        </div>
        <BulletText text={summary} className="text-sm text-zinc-200 leading-relaxed pl-[2.375rem]" />
      </div>
      {userProfile && (
        <div className="px-5 pt-4 pb-4 border-t border-zinc-700/40">
          <div className="flex items-center gap-2 mb-2.5">
            <div className="p-1.5 rounded-lg bg-zinc-700/30">
              <User className="w-4 h-4 text-amber-400" />
            </div>
            <h3 className="text-sm font-semibold text-zinc-100">User Profile</h3>
          </div>
          <BulletText text={userProfile} className="text-sm text-zinc-300 leading-relaxed pl-[2.375rem]" />
        </div>
      )}
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
        <span className="text-amber-400">{icon}</span>
        <h3 className="text-base font-semibold text-zinc-100">{title}</h3>
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
  const barColor = level === "high" ? "bg-amber-500" : level === "medium" ? "bg-amber-500" : "bg-zinc-600";
  const textColor = level === "high" ? "text-amber-400" : level === "medium" ? "text-amber-400" : "text-zinc-500";

  return (
    <Tooltip text={`${pct}% confidence`}>
      <div className="flex items-center gap-2 cursor-help">
        <div className="w-16 h-1.5 rounded-full bg-zinc-700/60 overflow-hidden">
          <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-xs font-semibold ${textColor} tabular-nums`}>{pct}%</span>
      </div>
    </Tooltip>
  );
}

function MitigationCard({ mitigation, frictionTypes }: { mitigation: Mitigation; frictionTypes: FrictionType[] }) {
  const [typesExpanded, setTypesExpanded] = useState(false);

  const addressedTypes = mitigation.addressed_friction_types ?? [];
  const matchedTypes = frictionTypes.filter((ft) =>
    addressedTypes.includes(ft.type_name)
  );

  return (
    <div className="border border-amber-700/30 rounded-xl bg-amber-950/10 overflow-hidden">
      {/* Header: Title + Confidence */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="text-base font-bold text-zinc-100">{mitigation.title}</span>
            {mitigation.confidence > 0 && <ConfidenceBar confidence={mitigation.confidence} />}
          </div>
        </div>
        <BulletText text={mitigation.action} className="text-sm text-zinc-300 leading-relaxed mt-1.5" />
      </div>

      {/* Rationale */}
      {mitigation.rationale && (
        <div className="px-5 py-3 border-t border-amber-700/20">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Lightbulb className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-sm font-semibold text-amber-300 uppercase tracking-wide">Why This is Useful</span>
          </div>
          <BulletText text={mitigation.rationale} className="text-sm text-zinc-200 leading-relaxed" />
        </div>
      )}

      {/* Addressed Friction Types */}
      {matchedTypes.length > 0 && (
        <div className="px-5 py-3 border-t border-amber-700/20">
          <button
            onClick={() => setTypesExpanded(!typesExpanded)}
            className="flex items-center gap-1.5 text-xs hover:opacity-80 transition"
          >
            {typesExpanded
              ? <ChevronDown className="w-3.5 h-3.5 text-amber-400" />
              : <ChevronRight className="w-3.5 h-3.5 text-amber-400" />}
            <Target className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-sm font-semibold text-amber-300 uppercase tracking-wide">Addressed Issues</span>
            <span className="text-zinc-500">({matchedTypes.length})</span>
          </button>
          {typesExpanded && (
            <div className="mt-2.5 space-y-3">
              {matchedTypes.map((ft) => (
                <div key={ft.type_name} className="border-l-2 border-amber-700/30 pl-3 space-y-1.5">
                  <h6 className="text-base font-semibold text-zinc-100">
                    {FRICTION_TYPE_LABELS[ft.type_name] ?? ft.type_name}
                  </h6>
                  <BulletText text={ft.description} className="text-sm text-zinc-300 leading-relaxed" />
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
        title="Issues Found"
        tooltip="Moments where you were dissatisfied with the agent's behavior"
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
  const label = FRICTION_TYPE_LABELS[frictionType.type_name] ?? frictionType.type_name;

  return (
    <div
      onClick={() => setExpanded((v) => !v)}
      className="border border-zinc-700/60 rounded-xl overflow-hidden cursor-pointer hover:border-zinc-600/60 transition-all"
    >
      <div className="px-4 py-3 space-y-2.5">
        <div className="flex items-center gap-2.5 flex-wrap">
          <SeverityBadge severity={frictionType.severity} />
          <h6 className="text-base font-semibold text-zinc-100">{label}</h6>
          <div className="ml-auto shrink-0">
            {expanded
              ? <ChevronDown className="w-4 h-4 text-zinc-500" />
              : <ChevronRight className="w-4 h-4 text-zinc-500" />}
          </div>
        </div>
        <BulletText text={frictionType.description} className="text-sm text-zinc-300 leading-relaxed" />
      </div>
      {expanded && (
        <div className="px-4 pb-3.5 space-y-2.5 border-t border-zinc-700/30 pt-3 mx-3 mb-1">
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
        <BookOpen className="w-4 h-4 text-cyan-400" />
        <span className="font-semibold text-cyan-400">Reference:</span>
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
        className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-zinc-700/50 text-zinc-300 hover:bg-amber-900/40 hover:text-amber-300 transition font-mono border border-zinc-600/30 hover:border-amber-700/30"
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
        <Zap className="w-4 h-4 text-amber-400" />
        <span className="font-semibold text-amber-400">Impact:</span>
      </div>
      <Tooltip text="Steps affected by this issue">
        <span className="inline-flex items-center gap-1.5 text-sm text-zinc-400 cursor-help">
          <Footprints className="w-4 h-4 text-rose-400" />
          {cost.affected_steps} step{cost.affected_steps !== 1 ? "s" : ""}
        </span>
      </Tooltip>
      {cost.affected_time_seconds != null && (
        <Tooltip text="Duration affected">
          <span className="inline-flex items-center gap-1.5 text-sm text-zinc-400 cursor-help">
            <Clock className="w-4 h-4 text-sky-400" />
            {formatDuration(cost.affected_time_seconds)}
          </span>
        </Tooltip>
      )}
      {cost.affected_tokens != null && (
        <Tooltip text="Tokens affected">
          <span className="inline-flex items-center gap-1.5 text-sm text-zinc-400 cursor-help">
            <Coins className="w-4 h-4 text-amber-400" />
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
      <div className="border-t border-zinc-800 pt-4 text-xs text-zinc-500 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span>{result.backend_id}/{result.model}</span>
          {result.metrics.cost_usd != null && (
            <span className="border-l border-zinc-700 pl-2">
              {formatCost(result.metrics.cost_usd)}
            </span>
          )}
          {result.batch_count > 1 && (
            <span className="border-l border-zinc-700 pl-2">
              {result.batch_count} batches
            </span>
          )}
        </div>
        <span className="shrink-0">{dateStr} {timeStr}</span>
      </div>
    </Tooltip>
  );
}

import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
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
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type {
  AnalysisJobResponse,
  AnalysisJobStatus,
  CostEstimate,
  FrictionAnalysisResult,
  FrictionEvent,
  LLMStatus,
  Mitigation,
} from "../../types";
import { formatCost, formatDuration, formatTokens } from "../../utils";
import { SEVERITY_COLORS, SESSION_ID_SHORT, SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH } from "../../styles";
import { DemoBanner } from "../demo-banner";
import { AnalysisWelcomePage } from "../analysis-welcome";
import { LoadingSpinner, LoadingSpinnerRings } from "../loading-spinner";
import { CostEstimateDialog } from "../cost-estimate-dialog";
import { Tooltip } from "../tooltip";
import { FrictionHistory } from "./friction-history";
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

const CONFIDENCE_STYLES: Record<string, string> = {
  high: "bg-emerald-500/20 border-emerald-500/30",
  medium: "bg-amber-500/20 border-amber-500/30",
  low: "bg-zinc-500/20 border-zinc-500/30",
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
            <LoadingSpinnerRings />
            <div className="text-center space-y-1">
              <p className="text-sm font-medium text-zinc-200">
                Analyzing {checkedIds.size} session{checkedIds.size !== 1 ? "s" : ""} for friction
              </p>
              <p className="text-xs text-zinc-500">Running in background — you can switch tabs</p>
            </div>
            <button
              onClick={handleStopAnalysis}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs text-zinc-300 hover:text-white bg-zinc-700 hover:bg-zinc-600 border border-zinc-600 rounded-md transition"
            >
              Stop
            </button>
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
          <SummarySection summary={result.summary} userProfile={result.user_profile} />
          {result.mitigations.length > 0 && (
            <MitigationsSection mitigations={result.mitigations} />
          )}
          <EventsSection events={result.friction_events} />
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
  const eventCount = result.friction_events.length;
  const sessionCount = result.session_ids.length;

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <Activity className="w-6 h-6 text-amber-400" />
        <div>
          <h2 className="text-xl font-bold text-zinc-100">
            {result.title || "Friction Analysis"}
          </h2>
          <p className="text-sm text-zinc-400">
            {eventCount} issue{eventCount !== 1 ? "s" : ""} across {sessionCount} session{sessionCount !== 1 ? "s" : ""}
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
        className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 rounded-md transition"
      >
        <Plus className="w-3 h-3" />
        New
      </button>
    </div>
  );
}

function SummarySection({
  summary,
  userProfile,
}: {
  summary: string;
  userProfile?: string | null;
}) {
  return (
    <div className="bg-zinc-900/80 border border-zinc-700/60 rounded-xl p-5 space-y-3">
      <p className="text-sm text-zinc-200 leading-relaxed">{summary}</p>
      {userProfile && (
        <div className="flex items-start gap-2.5 border-t border-zinc-700/40 pt-3">
          <User className="w-4 h-4 text-violet-400 shrink-0 mt-0.5" />
          <p className="text-sm text-zinc-400 leading-relaxed">{userProfile}</p>
        </div>
      )}
    </div>
  );
}

function MitigationsSection({ mitigations }: { mitigations: Mitigation[] }) {
  const sorted = [...mitigations].sort((a, b) => b.confidence - a.confidence);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Lightbulb className="w-5 h-5 text-amber-400" />
        <Tooltip text="Concrete steps you can take to avoid these issues in the future">
          <h3 className="text-base font-semibold text-zinc-100">Recommended Actions</h3>
        </Tooltip>
      </div>
      <div className="space-y-2.5">
        {sorted.map((m, i) => (
          <MitigationCard key={i} mitigation={m} />
        ))}
      </div>
    </div>
  );
}

function MitigationCard({ mitigation }: { mitigation: Mitigation }) {
  const level = confidenceLevel(mitigation.confidence);
  const styleClass = CONFIDENCE_STYLES[level];
  const pct = Math.round(mitigation.confidence * 100);

  return (
    <div className={`rounded-xl border p-4 transition-all hover:border-zinc-600 ${styleClass}`}>
      <div className="flex items-start gap-3">
        <CheckCircle2 className={`w-5 h-5 shrink-0 mt-0.5 ${
          level === "high" ? "text-emerald-400" : level === "medium" ? "text-amber-400" : "text-zinc-400"
        }`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-zinc-200 leading-relaxed">{mitigation.action}</p>
          <div className="mt-2 flex items-center gap-2">
            <Tooltip text="How confident we are this will help">
              <div className="flex items-center gap-2">
                <div className="w-20 h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      level === "high" ? "bg-emerald-400" : level === "medium" ? "bg-amber-400" : "bg-zinc-500"
                    }`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs text-zinc-500">{pct}%</span>
              </div>
            </Tooltip>
          </div>
        </div>
      </div>
    </div>
  );
}

function EventsSection({ events }: { events: FrictionEvent[] }) {
  // Group events by friction_type
  const eventsByType = new Map<string, FrictionEvent[]>();
  for (const event of events) {
    const list = eventsByType.get(event.friction_type) ?? [];
    list.push(event);
    eventsByType.set(event.friction_type, list);
  }

  // Sort groups by max severity descending
  const sortedGroups = [...eventsByType.entries()].sort(([, a], [, b]) => {
    const maxA = Math.max(...a.map((e) => e.severity));
    const maxB = Math.max(...b.map((e) => e.severity));
    return maxB - maxA;
  });

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-5 h-5 text-amber-400" />
        <Tooltip text="Moments where you were dissatisfied with the agent's behavior">
          <h3 className="text-base font-semibold text-zinc-100">Issues Found</h3>
        </Tooltip>
      </div>
      <div className="space-y-3">
        {sortedGroups.map(([frictionType, evts], groupIndex) => (
          <FrictionTypeGroup key={frictionType} frictionType={frictionType} events={evts} isFirstGroup={groupIndex === 0} />
        ))}
      </div>
    </div>
  );
}

function FrictionTypeGroup({
  frictionType,
  events,
  isFirstGroup = false,
}: {
  frictionType: string;
  events: FrictionEvent[];
  isFirstGroup?: boolean;
}) {
  const [expanded, setExpanded] = useState(true);
  const sortedEvents = [...events].sort((a, b) => b.severity - a.severity);
  const maxSeverity = sortedEvents[0]?.severity ?? 0;
  const label = FRICTION_TYPE_LABELS[frictionType] ?? frictionType;

  return (
    <div className="border border-zinc-700/60 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 bg-zinc-800/50 hover:bg-zinc-800 transition text-left"
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-zinc-400 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-zinc-400 shrink-0" />
        )}
        <Target className="w-4 h-4 text-amber-400 shrink-0" />
        <span className="text-sm font-medium text-zinc-200">{label}</span>
        <SeverityBadge severity={maxSeverity} />
        <span className="text-xs text-zinc-500 ml-auto">
          {events.length} issue{events.length !== 1 ? "s" : ""}
        </span>
      </button>
      {expanded && (
        <div className="divide-y divide-zinc-700/60">
          {sortedEvents.map((event, i) => (
            <EventCard key={`${event.span_ref.session_id}-${event.span_ref.start_step_id}`} event={event} defaultExpanded={isFirstGroup && i === 0} />
          ))}
        </div>
      )}
    </div>
  );
}

function EventCard({ event, defaultExpanded = false }: { event: FrictionEvent; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const handleGoToStep = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const url = `${window.location.origin}?session=${event.span_ref.session_id}&step=${event.span_ref.start_step_id}`;
      window.open(url, "_blank");
    },
    [event.span_ref.session_id, event.span_ref.start_step_id]
  );

  return (
    <div className="px-4 py-3.5">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left"
      >
        <div className="flex items-start gap-2">
          <div className="mt-0.5 shrink-0">
            {expanded ? (
              <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5 text-zinc-500" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <SeverityBadge severity={event.severity} />
              <Tooltip text={`Session: ${event.span_ref.session_id}`} className="min-w-0">
                <span className="text-xs text-zinc-500 font-mono">
                  {event.span_ref.session_id.slice(0, SESSION_ID_SHORT)}
                </span>
              </Tooltip>
              <button
                onClick={handleGoToStep}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-sm text-zinc-400 hover:text-cyan-400 hover:bg-cyan-900/20 rounded transition"
                title="Open this step in a new tab"
              >
                <ArrowUpRight className="w-4 h-4" />
                <span>Jump</span>
              </button>
            </div>
            <p className="text-sm text-zinc-200 leading-relaxed font-medium">
              {event.user_intention}
            </p>
            {event.description && (
              <p className={`text-sm text-zinc-400 mt-1 leading-relaxed ${expanded ? "" : "line-clamp-2"}`}>
                {event.description}
              </p>
            )}
            {expanded && (
              <div className="mt-2">
                <CostBadges cost={event.friction_cost} />
              </div>
            )}
          </div>
        </div>
      </button>
    </div>
  );
}

function CostBadges({ cost }: { cost: FrictionEvent["friction_cost"] }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Tooltip text="Number of agent interactions affected by this issue">
        <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
          <Footprints className="w-3.5 h-3.5 text-rose-400" />
          {cost.affected_steps} step{cost.affected_steps !== 1 ? "s" : ""}
        </span>
      </Tooltip>
      {cost.affected_time_seconds != null && (
        <Tooltip text="How long this issue lasted">
          <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
            <Clock className="w-3.5 h-3.5 text-sky-400" />
            {formatDuration(cost.affected_time_seconds)}
          </span>
        </Tooltip>
      )}
      {cost.affected_tokens != null && (
        <Tooltip text="Tokens consumed during this issue">
          <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
            <Coins className="w-3.5 h-3.5 text-amber-400" />
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

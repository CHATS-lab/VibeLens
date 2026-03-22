import {
  Loader2,
  Download,
  Share2,
  Check,
  BarChart3,
  Bot,
  Clock,
  MessageSquare,
  Wrench,
  FolderOpen,
  Cpu,
  Calendar,
  Hash,
  Layers,
  Zap,
  GitBranch,
  List,
  ChevronUp,
  ChevronDown,
  ArrowUpRight,
  ArrowDownRight,
  Database,
  HardDrive,
  DollarSign,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type { Step, Trajectory, FlowData } from "../../types";
import { StepBlock } from "./message-block";
import { SubAgentBlock } from "./sub-agent-block";
import { StepTimeline } from "./step-timeline";
import { PromptNavPanel } from "./prompt-nav-panel";
import { FlowDiagram } from "./flow-diagram";
import { computeFlow, type FlowPhaseGroup } from "./flow-layout";
import { formatTokens, formatDuration, formatCost, extractUserText, baseProjectName } from "../../utils";
import { LoadingSpinner } from "../loading-spinner";
import { TOGGLE_ACTIVE, TOGGLE_INACTIVE, METRIC_LABEL } from "../../styles";

interface SessionViewProps {
  sessionId: string;
  sharedTrajectories?: Trajectory[];
  shareToken?: string;
}

export function SessionView({ sessionId, sharedTrajectories, shareToken }: SessionViewProps) {
  const { fetchWithToken } = useAppContext();
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeStepId, setActiveStepId] = useState<string | null>(null);
  const [promptNavWidth, setPromptNavWidth] = useState(224);
  const [sessionCost, setSessionCost] = useState<number | null>(null);
  const [shareStatus, setShareStatus] = useState<"idle" | "sharing" | "copied">("idle");
  const [viewMode, setViewMode] = useState<"timeline" | "flow">("timeline");
  const [flowData, setFlowData] = useState<FlowData | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);
  const [headerExpanded, setHeaderExpanded] = useState(true);
  const stepsRef = useRef<HTMLDivElement>(null);
  const isNavigatingRef = useRef(false);
  const isSharedView = !!sharedTrajectories;

  const MIN_PROMPT_NAV_WIDTH = 160;
  const MAX_PROMPT_NAV_WIDTH = 400;

  const handlePromptNavResize = useCallback((delta: number) => {
    setPromptNavWidth((w) =>
      Math.min(MAX_PROMPT_NAV_WIDTH, Math.max(MIN_PROMPT_NAV_WIDTH, w + delta))
    );
  }, []);

  useEffect(() => {
    setActiveStepId(null);
    setSessionCost(null);
    setFlowData(null);
    setViewMode("timeline");

    // When rendering shared data, skip the API fetch
    if (sharedTrajectories) {
      setTrajectories(sharedTrajectories);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");
    setTrajectories([]);

    fetchWithToken(`/api/sessions/${sessionId}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load session: ${res.status}`);
        return res.json();
      })
      .then((data: Trajectory[]) => {
        setTrajectories(data);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId, fetchWithToken, sharedTrajectories]);

  // Fetch session analytics for cost estimation (non-blocking, skip for shared views)
  useEffect(() => {
    if (!sessionId || loading || isSharedView) return;
    fetchWithToken(`/api/analysis/sessions/${sessionId}/stats`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.cost_usd != null) setSessionCost(data.cost_usd);
      })
      .catch(() => {});
  }, [sessionId, loading, fetchWithToken]);

  // Fetch flow data lazily when user toggles to flow view
  useEffect(() => {
    if (viewMode !== "flow" || flowData || flowLoading || !sessionId) return;
    setFlowLoading(true);
    const url = isSharedView && shareToken
      ? `/api/shares/${shareToken}/flow`
      : `/api/sessions/${sessionId}/flow`;
    fetchWithToken(url)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: FlowData | null) => {
        if (data) setFlowData(data);
      })
      .catch(() => {})
      .finally(() => setFlowLoading(false));
  }, [viewMode, flowData, flowLoading, sessionId, fetchWithToken, isSharedView, shareToken]);

  const main = useMemo(
    () => trajectories.find((t) => !t.parent_trajectory_ref) ?? trajectories[0] ?? null,
    [trajectories]
  );

  const subAgents = useMemo(
    () =>
      trajectories
        .filter((t) => !!t.parent_trajectory_ref)
        .sort((a, b) => {
          const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
          const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
          return ta - tb;
        }),
    [trajectories]
  );

  // Build a map: step_id -> sub-agent trajectories spawned from that step.
  // Phase 1 links via observation.subagent_trajectory_ref (explicit linkage).
  // Phase 2 places unlinked sub-agents (e.g. compaction) at the
  // chronologically correct position using timestamp heuristics.
  const subAgentsByStep = useMemo(() => {
    const map = new Map<string, Trajectory[]>();
    const orphans: Trajectory[] = [];
    const unlinked: Trajectory[] = [];

    for (const sub of subAgents) {
      let placed = false;
      if (main?.steps) {
        for (const step of main.steps) {
          if (!step.observation) continue;
          for (const result of step.observation.results) {
            if (!result.subagent_trajectory_ref) continue;
            for (const ref of result.subagent_trajectory_ref) {
              if (ref.session_id === sub.session_id) {
                const existing = map.get(step.step_id) || [];
                existing.push(sub);
                map.set(step.step_id, existing);
                placed = true;
                break;
              }
            }
            if (placed) break;
          }
          if (placed) break;
        }
      }
      if (!placed) unlinked.push(sub);
    }

    // Place unlinked sub-agents at the last main step whose timestamp
    // is <= the sub-agent's start timestamp. Falls back to orphans
    // only when no timestamp is available.
    for (const sub of unlinked) {
      const subTs = sub.timestamp ? new Date(sub.timestamp).getTime() : NaN;
      if (!isNaN(subTs) && main?.steps) {
        let bestStepId: string | null = null;
        for (const step of main.steps) {
          if (!step.timestamp) continue;
          const stepTs = new Date(step.timestamp).getTime();
          if (stepTs <= subTs) bestStepId = step.step_id;
          else break;
        }
        if (bestStepId) {
          const existing = map.get(bestStepId) || [];
          existing.push(sub);
          map.set(bestStepId, existing);
          continue;
        }
      }
      orphans.push(sub);
    }

    return { map, orphans };
  }, [main, subAgents]);

  const steps = (main?.steps || []) as Step[];

  const userStepIds = useMemo(() => {
    return steps
      .filter((s) => s.source === "user" && extractUserText(s))
      .map((s) => s.step_id);
  }, [steps]);

  // Compute flow phases for the nav panel when in flow mode
  const flowPhases: FlowPhaseGroup[] | undefined = useMemo(() => {
    if (!flowData || viewMode !== "flow") return undefined;
    const result = computeFlow(steps, flowData.tool_graph, flowData.phase_segments);
    return result.phases;
  }, [flowData, viewMode, steps]);

  const [activePhaseIdx, setActivePhaseIdx] = useState<number | null>(null);

  const SCROLL_SUPPRESS_MS = 800;

  const handlePhaseNavigate = useCallback((phaseIdx: number) => {
    const el = document.getElementById(`flow-phase-${phaseIdx}`);
    if (!el) return;
    setActivePhaseIdx(phaseIdx);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // IntersectionObserver to track which user prompt is currently visible
  useEffect(() => {
    if (!stepsRef.current || userStepIds.length < 2) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (isNavigatingRef.current) return;
        let topEntry: IntersectionObserverEntry | null = null;
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          if (!topEntry || entry.boundingClientRect.top < topEntry.boundingClientRect.top) {
            topEntry = entry;
          }
        }
        if (topEntry) {
          setActiveStepId(topEntry.target.id.replace("step-", ""));
        }
      },
      {
        root: stepsRef.current,
        rootMargin: "-10% 0px -80% 0px",
        threshold: 0,
      }
    );

    for (const stepId of userStepIds) {
      const el = document.getElementById(`step-${stepId}`);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, [userStepIds]);

  const handlePromptNavigate = useCallback((stepId: string) => {
    const el = document.getElementById(`step-${stepId}`);
    if (!el) return;
    isNavigatingRef.current = true;
    setActiveStepId(stepId);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => {
      isNavigatingRef.current = false;
    }, SCROLL_SUPPRESS_MS);
  }, []);

  if (loading) {
    return <LoadingSpinner label="Loading session" sublabel="Parsing trajectory data…" />;
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full p-4">
        <div className="text-center bg-rose-900/20 border border-rose-800 rounded-lg p-6 max-w-md">
          <p className="text-sm font-semibold text-rose-300 mb-2">Failed to load session</p>
          <p className="text-xs text-rose-400 mb-4 font-mono break-all">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-3 py-1 bg-rose-700/50 hover:bg-rose-700 rounded text-xs text-rose-200 transition"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const handleShare = async () => {
    setShareStatus("sharing");
    try {
      const res = await fetchWithToken("/api/shares", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`Failed to create share: ${res.status}`);
      const data = await res.json();
      await navigator.clipboard.writeText(data.url);
      setShareStatus("copied");
      setTimeout(() => setShareStatus("idle"), 2000);
    } catch (err) {
      console.error("Share failed:", err);
      setShareStatus("idle");
    }
  };

  if (!main) return null;

  const metrics = main.final_metrics;
  const promptCount = steps.filter(
    (s) => s.source === "user" && !s.extra?.is_skill_output && extractUserText(s)
  ).length;
  const skillCount = steps.filter(
    (s) => s.source === "user" && s.extra?.is_skill_output
  ).length;
  const totalTokens =
    (metrics?.total_prompt_tokens || 0) +
    (metrics?.total_completion_tokens || 0);

  const isVisibleStep = (s: Step): boolean => {
    if (s.source === "user") {
      if (typeof s.message === "string") return !!s.message.trim();
      return s.message.length > 0;
    }
    return s.source === "agent" || s.source === "system";
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Session Header */}
      <div className="shrink-0 bg-gradient-to-b from-zinc-900 to-zinc-900/80 border-b border-zinc-800 px-4 py-2">
        <div className="max-w-7xl mx-auto">
          {/* Row 1: Session ID + Title + Actions */}
          <div className="flex items-center justify-between mb-1 gap-3">
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <MetaPill
                icon={<Hash className="w-3 h-3" />}
                label={main.session_id.slice(0, 8)}
                color="text-zinc-300"
                tooltip={`Session ID: ${main.session_id}`}
              />
              <h2
                className="text-lg font-semibold text-zinc-100 truncate"
                title={main.first_message || "Session"}
              >
                {main.first_message || "Session"}
              </h2>
            </div>
            <div className="flex items-center gap-1 shrink-0 ml-3">
              {/* View mode toggle */}
              <div className="flex rounded-md border border-zinc-700 mr-2">
                <button
                  onClick={() => setViewMode("timeline")}
                  className={`flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-l-md transition ${
                    viewMode === "timeline" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE
                  }`}
                >
                  <List className="w-3 h-3" />
                  Timeline
                </button>
                <button
                  onClick={() => setViewMode("flow")}
                  className={`flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-r-md transition ${
                    viewMode === "flow" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE
                  }`}
                >
                  <GitBranch className="w-3 h-3" />
                  Flow
                </button>
              </div>
              {!isSharedView && (
                <button
                  onClick={handleShare}
                  disabled={shareStatus === "sharing"}
                  className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition text-xs disabled:opacity-50"
                  title={shareStatus === "copied" ? "Link copied!" : "Share session"}
                >
                  {shareStatus === "copied" ? (
                    <Check className="w-4 h-4 text-emerald-400" />
                  ) : shareStatus === "sharing" ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Share2 className="w-4 h-4" />
                  )}
                </button>
              )}
              <button
                onClick={() => {
                  const link = document.createElement("a");
                  link.href = `/api/sessions/${sessionId}/export`;
                  link.download = `vibelens-${sessionId.slice(0, 8)}.json`;
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                }}
                className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition text-xs"
                title="Download session"
              >
                <Download className="w-4 h-4" />
              </button>
              <button
                onClick={() => setHeaderExpanded((v) => !v)}
                className="p-2 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition text-xs"
                title={headerExpanded ? "Collapse header" : "Expand header"}
              >
                {headerExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {headerExpanded && <>
          {/* Row 2: Meta Pills (full width) */}
          <div className="flex flex-wrap items-center gap-1.5 mb-3">
            {main.agent.model_name && (
              <MetaPill
                icon={<Cpu className="w-3 h-3" />}
                label={`${main.agent.name}@${main.agent.model_name}`}
                color="text-amber-300"
                tooltip="Agent model used for this session"
              />
            )}
            {main.timestamp && (
              <MetaPill
                icon={<Calendar className="w-3 h-3" />}
                label={formatCreatedTime(main.timestamp)}
                color="text-zinc-200"
                tooltip="Session start time"
              />
            )}
            {metrics && (
              <MetaPill
                icon={<Clock className="w-3 h-3" />}
                label={formatDuration(metrics.duration)}
                color="text-cyan-400"
                tooltip="Total wall-clock duration of this session"
              />
            )}
            <MetaPill
              icon={<MessageSquare className="w-3 h-3" />}
              label={`${promptCount} prompt${promptCount !== 1 ? "s" : ""}`}
              color="text-blue-400"
              tooltip="User prompts — messages typed by the human operator"
            />
            {skillCount > 0 && (
              <MetaPill
                icon={<Zap className="w-3 h-3" />}
                label={`${skillCount} skill${skillCount !== 1 ? "s" : ""}`}
                color="text-amber-300"
                tooltip="Skill invocations — reusable prompts auto-injected by the agent"
              />
            )}
            {metrics && (
              <>
                <MetaPill
                  icon={<Wrench className="w-3 h-3" />}
                  label={`${metrics.tool_call_count} tools`}
                  color="text-amber-400"
                  tooltip="Total tool calls made by the agent (Bash, Read, Edit, etc.)"
                />
                {metrics.total_steps && (
                  <MetaPill
                    icon={<Layers className="w-3 h-3" />}
                    label={`${metrics.total_steps} steps`}
                    color="text-zinc-200"
                    tooltip="Total conversation steps including user, agent, and system turns"
                  />
                )}
              </>
            )}
            {subAgents.length > 0 && (
              <MetaPill
                icon={<Bot className="w-3 h-3" />}
                label={`${subAgents.length} sub-agent${subAgents.length !== 1 ? "s" : ""}`}
                color="text-violet-400"
                tooltip="Sub-agent tasks spawned during this session"
              />
            )}
            {main.project_path && (
              <MetaPill
                icon={<FolderOpen className="w-3 h-3" />}
                label={baseProjectName(main.project_path)}
                color="text-zinc-200"
                tooltip={main.project_path}
              />
            )}
          </div>

          {/* Row 3: Token Stats */}
          {metrics && (metrics.total_prompt_tokens != null || metrics.total_completion_tokens != null) && (
            <div className={`grid ${sessionCost != null ? "grid-cols-6" : "grid-cols-5"} gap-2 text-xs`}>
              <TokenStat icon={<ArrowUpRight className="w-3 h-3" />} label="Input" value={metrics.total_prompt_tokens || 0} color="text-cyan-300" tooltip="Prompt tokens sent to the model" />
              <TokenStat icon={<ArrowDownRight className="w-3 h-3" />} label="Output" value={metrics.total_completion_tokens || 0} color="text-cyan-300" tooltip="Completion tokens generated by the model" />
              <TokenStat icon={<Database className="w-3 h-3" />} label="Cache Read" value={metrics.total_cache_read || 0} color="text-green-300" tooltip="Tokens served from prompt cache (reduced cost)" />
              <TokenStat icon={<HardDrive className="w-3 h-3" />} label="Cache Write" value={metrics.total_cache_write || 0} color="text-violet-300" tooltip="Tokens written to prompt cache for future reuse" />
              <TokenStat icon={<BarChart3 className="w-3 h-3" />} label="Total" value={totalTokens} color="text-amber-300" tooltip="Total tokens (input + output)" />
              {sessionCost != null && (
                <CostStat value={sessionCost} />
              )}
            </div>
          )}
          </>}
        </div>
      </div>

      {/* Two-column body: Steps + Prompt Nav */}
      <div className="flex-1 flex min-h-0">
        {/* Steps / Flow */}
        <div ref={stepsRef} className="flex-1 overflow-y-auto">
          {viewMode === "timeline" ? (
            <div className="max-w-5xl mx-auto px-4 py-6 space-y-3">
              {steps.length === 0 ? (
                <div className="text-center text-zinc-500 text-sm py-8">
                  <BarChart3 className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p>No steps to display</p>
                </div>
              ) : (
                <>
                  <StepTimeline
                    entries={steps
                      .filter((step) => {
                        const visible = isVisibleStep(step);
                        const spawnedSubs = subAgentsByStep.map.get(step.step_id);
                        return visible || !!spawnedSubs;
                      })
                      .map((step) => {
                        const visible = isVisibleStep(step);
                        const spawnedSubs = subAgentsByStep.map.get(step.step_id);
                        return {
                          step,
                          content: (
                            <div id={`step-${step.step_id}`} style={{ scrollMarginTop: "1rem" }}>
                              {visible && <StepBlock step={step} />}
                              {spawnedSubs?.map((sub) => (
                                <div key={sub.session_id} id={`subagent-${sub.session_id}`} className="mt-2">
                                  <SubAgentBlock
                                    trajectory={sub}
                                    allTrajectories={trajectories}
                                  />
                                </div>
                              ))}
                            </div>
                          ),
                        };
                      })}
                    sessionStartMs={
                      main.timestamp
                        ? new Date(main.timestamp).getTime()
                        : null
                    }
                    sessionStartTimestamp={main.timestamp}
                  />
                  {subAgentsByStep.orphans.map((sub) => (
                    <div key={sub.session_id} id={`subagent-${sub.session_id}`}>
                      <SubAgentBlock
                        trajectory={sub}
                        allTrajectories={trajectories}
                      />
                    </div>
                  ))}
                </>
              )}
            </div>
          ) : flowLoading ? (
            <LoadingSpinner label="Building flow diagram" />
          ) : flowData ? (
            <div className="max-w-5xl mx-auto px-4 py-6">
              <FlowDiagram steps={steps} flowData={flowData} />
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-zinc-500">Flow data unavailable</p>
            </div>
          )}
        </div>

        {/* Prompt Navigation Sidebar */}
        <PromptNavPanel
          steps={steps}
          subAgents={subAgents}
          activeStepId={activeStepId}
          onNavigate={handlePromptNavigate}
          width={promptNavWidth}
          onResize={handlePromptNavResize}
          viewMode={viewMode}
          flowPhases={flowPhases}
          activePhaseIdx={activePhaseIdx}
          onPhaseNavigate={handlePhaseNavigate}
        />
      </div>
    </div>
  );
}

function MetaPill({
  icon,
  label,
  color,
  tooltip,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
  tooltip?: string;
}) {
  const [show, setShow] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  return (
    <span
      ref={ref}
      className={`relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-zinc-800 border border-zinc-700/50 text-[11px] hover:bg-zinc-700/80 transition-colors ${color}`}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {icon}
      <span>{label}</span>
      {tooltip && show && (
        <span className="absolute left-0 top-full mt-1.5 z-[100] px-2.5 py-1.5 rounded-md bg-zinc-950 border border-zinc-700 text-[11px] text-zinc-300 whitespace-nowrap shadow-lg pointer-events-none">
          {tooltip}
        </span>
      )}
    </span>
  );
}

function TokenStat({
  icon,
  label,
  value,
  color,
  tooltip,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: string;
  tooltip?: string;
}) {
  const [show, setShow] = useState(false);

  return (
    <div
      className="relative bg-zinc-800/50 rounded px-2 py-1.5"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <p className={`${METRIC_LABEL} flex items-center gap-1`}>{icon}{label}</p>
      <p className={`${color} font-mono`}>{formatTokens(value)}</p>
      {tooltip && show && (
        <span className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-[100] px-2.5 py-1.5 rounded-md bg-zinc-950 border border-zinc-700 text-[11px] text-zinc-300 whitespace-nowrap shadow-lg pointer-events-none">
          {tooltip}
        </span>
      )}
    </div>
  );
}

function CostStat({ value }: { value: number }) {
  const [show, setShow] = useState(false);

  return (
    <div
      className="relative bg-zinc-800/50 rounded px-2 py-1.5"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <p className={`${METRIC_LABEL} flex items-center gap-1`}><DollarSign className="w-3 h-3" />Est. Cost</p>
      <p className="text-emerald-300 font-mono">{formatCost(value)}</p>
      {show && (
        <span className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-[100] px-2.5 py-1.5 rounded-md bg-zinc-950 border border-zinc-700 text-[11px] text-zinc-300 whitespace-nowrap shadow-lg pointer-events-none">
          Estimated cost based on API pricing
        </span>
      )}
    </div>
  );
}

function formatCreatedTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return timestamp;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

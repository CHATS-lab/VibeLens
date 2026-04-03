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
  AlignLeft,
  ChevronUp,
  ChevronDown,
  ArrowUpRight,
  ArrowDownRight,
  Database,
  HardDrive,
  DollarSign,
  Link2,
  Shield,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type { Step, Trajectory, FlowData } from "../../types";
import { StepBlock } from "./message-block";
import { SubAgentBlock } from "./sub-agent-block";
import { StepTimeline } from "./step-timeline";
import { PromptNavPanel, type NavMode } from "./prompt-nav-panel";
import { FlowDiagram } from "./flow-diagram";
import { computeFlow } from "./flow-layout";
import { formatTokens, formatDuration, formatCost, extractUserText, baseProjectName } from "../../utils";
import { LoadingSpinner } from "../loading-spinner";
import { Tooltip } from "../tooltip";
import {
  METRIC_LABEL,
  SESSION_ID_SHORT, PREVIEW_SHORT, SHARE_STATUS_RESET_MS, SCROLL_SUPPRESS_MS,
  SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH,
} from "../../styles";

interface SessionViewProps {
  sessionId: string;
  sharedTrajectories?: Trajectory[];
  shareToken?: string;
  onNavigateSession?: (sessionId: string) => void;
  allSessions?: Trajectory[];
  pendingScrollStepId?: string | null;
  onScrollComplete?: () => void;
}

export function SessionView({ sessionId, sharedTrajectories, shareToken, onNavigateSession, allSessions, pendingScrollStepId, onScrollComplete }: SessionViewProps) {
  const { fetchWithToken } = useAppContext();
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeStepId, setActiveStepId] = useState<string | null>(null);
  const [promptNavWidth, setPromptNavWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [navCollapsed, setNavCollapsed] = useState(true);
  const [sessionCost, setSessionCost] = useState<number | null>(null);
  const [shareStatus, setShareStatus] = useState<"idle" | "sharing" | "copied">("idle");
  const [viewMode, setViewMode] = useState<"timeline" | "concise" | "flow">("concise");
  const [navMode, setNavMode] = useState<NavMode>("prompts");
  const [flowData, setFlowData] = useState<FlowData | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);
  const [headerExpanded, setHeaderExpanded] = useState(false);
  const stepsRef = useRef<HTMLDivElement>(null);
  const isNavigatingRef = useRef(false);
  const isSharedView = !!sharedTrajectories;

  const handlePromptNavResize = useCallback((delta: number) => {
    setPromptNavWidth((w) =>
      Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, w + delta))
    );
  }, []);

  useEffect(() => {
    setActiveStepId(null);
    setSessionCost(null);
    setFlowData(null);

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
      .catch((err) => console.error("Failed to load session stats:", err));
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
      .catch((err) => console.error("Failed to load flow data:", err))
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

  // Compute flow data for the nav panel when in flow mode
  const flowComputed = useMemo(() => {
    if (!flowData || viewMode !== "flow") return undefined;
    return computeFlow(steps, flowData.tool_graph, flowData.phase_segments);
  }, [flowData, viewMode, steps]);
  const flowPhases = flowComputed?.phases;
  const flowSections = flowComputed?.sections;

  const [activePhaseIdx, setActivePhaseIdx] = useState<number | null>(null);

  const handlePhaseNavigate = useCallback((phaseIdx: number) => {
    const el = document.getElementById(`flow-phase-${phaseIdx}`);
    if (!el) return;
    setActivePhaseIdx(phaseIdx);
    setActiveStepId(null);
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
    setActivePhaseIdx(null);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => {
      isNavigatingRef.current = false;
    }, SCROLL_SUPPRESS_MS);
  }, []);

  // Handle external navigation request (e.g. friction panel deep link → step)
  useEffect(() => {
    if (!pendingScrollStepId || loading) return;
    let cancelled = false;
    let attempt = 0;

    // Retry with backoff since DOM may not be ready immediately
    const tryScroll = () => {
      if (cancelled) return;
      const el = document.getElementById(`step-${pendingScrollStepId}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        setActiveStepId(pendingScrollStepId);
        el.classList.add("friction-highlight");
        setTimeout(() => el.classList.remove("friction-highlight"), 2000);
        onScrollComplete?.();
        return;
      }
      attempt++;
      if (attempt < 8) {
        setTimeout(tryScroll, 200 * attempt);
      } else {
        onScrollComplete?.();
      }
    };

    // Initial delay for DOM render
    const timer = setTimeout(tryScroll, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [pendingScrollStepId, loading, onScrollComplete]);

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
      setTimeout(() => setShareStatus("idle"), SHARE_STATUS_RESET_MS);
    } catch (err) {
      console.error("Share failed:", err);
      setShareStatus("idle");
    }
  };

  if (!main) return null;

  const metrics = main.final_metrics;
  const promptCount = steps.filter(
    (s) => s.source === "user" && !s.extra?.is_skill_output && !s.extra?.is_auto_prompt && extractUserText(s)
  ).length;
  const skillCount = steps.filter(
    (s) => s.source === "user" && s.extra?.is_skill_output
  ).length;
  const totalTokens =
    (metrics?.total_prompt_tokens || 0) +
    (metrics?.total_completion_tokens || 0);

  const isConcise = viewMode === "concise";

  const isVisibleStep = (s: Step): boolean => {
    if (s.source === "user") {
      if (typeof s.message === "string") return !!s.message.trim();
      return s.message.length > 0;
    }
    // In concise mode, hide agent steps that have no text message
    if (isConcise && s.source === "agent") {
      const text = typeof s.message === "string" ? s.message.trim() : "";
      return !!text;
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
                label={main.session_id.slice(0, SESSION_ID_SHORT)}
                color="text-cyan-300"
                bg="bg-cyan-950/50 border border-cyan-800/30"
                tooltip={`Session ID: ${main.session_id}`}
              />
              <Tooltip text={main.first_message || "Session"} className="min-w-0">
                <h2 className="text-lg font-semibold text-zinc-100 truncate">
                  {main.first_message || "Session"}
                </h2>
              </Tooltip>
            </div>
            <div className="flex items-center gap-1 shrink-0 ml-3">
              {/* View mode toggle */}
              <div data-tour="view-modes" className="flex rounded-md border border-cyan-700/40 bg-zinc-800/60 mr-2 w-[280px]">
                <button
                  onClick={() => setViewMode("concise")}
                  className={`flex-1 flex items-center justify-center gap-1 px-2.5 py-1.5 text-xs rounded-l-md transition ${
                    viewMode === "concise"
                      ? "bg-cyan-900/50 text-cyan-200 font-semibold"
                      : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/40"
                  }`}
                >
                  <AlignLeft className="w-3 h-3" />
                  Concise
                </button>
                <button
                  onClick={() => setViewMode("timeline")}
                  className={`flex-1 flex items-center justify-center gap-1 px-2.5 py-1.5 text-xs transition ${
                    viewMode === "timeline"
                      ? "bg-cyan-900/50 text-cyan-200 font-semibold"
                      : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/40"
                  }`}
                >
                  <List className="w-3 h-3" />
                  Detail
                </button>
                <button
                  onClick={() => setViewMode("flow")}
                  className={`flex-1 flex items-center justify-center gap-1 px-2.5 py-1.5 text-xs rounded-r-md transition ${
                    viewMode === "flow"
                      ? "bg-cyan-900/50 text-cyan-200 font-semibold"
                      : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/40"
                  }`}
                >
                  <GitBranch className="w-3 h-3" />
                  Workflow
                </button>
              </div>
              <div className="w-px h-6 bg-zinc-600/50 mx-1" />
              {!isSharedView && (
                <div className="relative flex items-center">
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
                  {shareStatus === "copied" && (
                    <span className="absolute right-full mr-1.5 whitespace-nowrap text-[11px] text-emerald-400 font-medium animate-fade-in">
                      Link copied!
                    </span>
                  )}
                </div>
              )}
              <button
                onClick={() => {
                  const link = document.createElement("a");
                  link.href = `/api/sessions/${sessionId}/export`;
                  link.download = `vibelens-${sessionId.slice(0, SESSION_ID_SHORT)}.json`;
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
            {!!main.extra?._anonymized && (
              <MetaPill
                icon={<Shield className="w-3 h-3" />}
                label="Redacted"
                color="text-emerald-400"
                tooltip={`Anonymized: ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.secrets_redacted ?? 0} secrets, ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.paths_anonymized ?? 0} paths, ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.pii_redacted ?? 0} PII`}
              />
            )}
          </div>

          {/* Row 2.5: Continuation Chain Nav */}
          {(main.last_trajectory_ref || main.continued_trajectory_ref || main.parent_trajectory_ref) && (
            <div className="flex flex-wrap items-center gap-1.5 mb-3">
              {main.parent_trajectory_ref && onNavigateSession && (
                <button
                  onClick={() => onNavigateSession(main.parent_trajectory_ref!.session_id)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-900/30 border border-violet-700/40 text-xs text-violet-300 hover:bg-violet-800/40 hover:border-violet-600/50 transition-colors"
                  title={`Navigate to parent session: ${main.parent_trajectory_ref.session_id}`}
                >
                  <Link2 className="w-3 h-3" />
                  <span>Spawned by</span>
                  <span className="text-violet-400 font-medium truncate max-w-[200px]">
                    {_lookupFirstMessage(main.parent_trajectory_ref.session_id, allSessions)}
                  </span>
                </button>
              )}
              {main.last_trajectory_ref && onNavigateSession && (
                <button
                  onClick={() => onNavigateSession(main.last_trajectory_ref!.session_id)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-900/30 border border-violet-700/40 text-xs text-violet-300 hover:bg-violet-800/40 hover:border-violet-600/50 transition-colors"
                  title={`Navigate to previous session: ${main.last_trajectory_ref.session_id}`}
                >
                  <ArrowUpRight className="w-3 h-3" />
                  <span>Continued from</span>
                  <span className="text-violet-400 font-medium truncate max-w-[200px]">
                    {_lookupFirstMessage(main.last_trajectory_ref.session_id, allSessions)}
                  </span>
                </button>
              )}
              {main.continued_trajectory_ref && onNavigateSession && (
                <button
                  onClick={() => onNavigateSession(main.continued_trajectory_ref!.session_id)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-violet-900/30 border border-violet-700/40 text-xs text-violet-300 hover:bg-violet-800/40 hover:border-violet-600/50 transition-colors"
                  title={`Navigate to next session: ${main.continued_trajectory_ref.session_id}`}
                >
                  <ArrowDownRight className="w-3 h-3" />
                  <span>Continues in</span>
                  <span className="text-violet-400 font-medium truncate max-w-[200px]">
                    {_lookupFirstMessage(main.continued_trajectory_ref.session_id, allSessions)}
                  </span>
                </button>
              )}
            </div>
          )}

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
          {viewMode === "timeline" || viewMode === "concise" ? (
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
                              {visible && <StepBlock step={step} concise={isConcise} />}
                              {spawnedSubs?.map((sub) => (
                                <div key={sub.session_id} id={`subagent-${sub.session_id}`} className="mt-2">
                                  <SubAgentBlock
                                    trajectory={sub}
                                    allTrajectories={trajectories}
                                    concise={isConcise}
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
                        concise={isConcise}
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
          flowSections={flowSections}
          activePhaseIdx={activePhaseIdx}
          onPhaseNavigate={handlePhaseNavigate}
          collapsed={navCollapsed}
          onCollapsedChange={setNavCollapsed}
          navMode={navMode}
          onNavModeChange={setNavMode}
        />
      </div>
    </div>
  );
}

function MetaPill({
  icon,
  label,
  color,
  bg,
  tooltip,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
  bg?: string;
  tooltip?: string;
}) {
  const bgClass = bg ?? "bg-zinc-800 border border-zinc-700/50";

  const pill = (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] hover:brightness-125 transition-colors ${bgClass} ${color}`}
    >
      {icon}
      <span>{label}</span>
    </span>
  );

  if (!tooltip) return pill;

  return <Tooltip text={tooltip}>{pill}</Tooltip>;
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

function _lookupFirstMessage(sessionId: string, sessions?: Trajectory[]): string {
  if (!sessions) return sessionId.slice(0, SESSION_ID_SHORT);
  const match = sessions.find((s) => s.session_id === sessionId);
  if (!match?.first_message) return sessionId.slice(0, SESSION_ID_SHORT);
  const msg = match.first_message;
  if (msg.length <= PREVIEW_SHORT) return msg;
  return msg.slice(0, PREVIEW_SHORT) + "…";
}

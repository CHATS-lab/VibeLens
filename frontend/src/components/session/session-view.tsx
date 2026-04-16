import {
  Loader2,
  Download,
  Share2,
  Check,
  Copy,
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
  ChevronRight,
  ChevronDown,
  ArrowUpRight,
  ArrowDownRight,
  Database,
  HardDrive,
  Link2,
  Shield,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type { Step, Trajectory, FlowData } from "../../types";
import { StepBlock } from "./step-block";
import { SubAgentBlock } from "./sub-agent-block";
import { StepTimeline } from "./step-timeline";
import { PromptNavPanel, type NavMode } from "./prompt-nav-panel";
import { FlowDiagram } from "./flow-diagram";
import { computeFlow } from "./flow-layout";
import { formatDuration, extractUserText, baseProjectName } from "../../utils";
import { LoadingSpinner } from "../loading-spinner";
import { Modal, ModalHeader, ModalBody } from "../modal";
import { Tooltip } from "../tooltip";
import { SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH } from "../../styles";
import { SESSION_ID_SHORT, SCROLL_SUPPRESS_MS } from "../../constants";
import { MetaPill, TokenStat, CostStat, formatCreatedTime, _lookupFirstMessage } from "./session-header";

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
  const { fetchWithToken, appMode } = useAppContext();
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeStepId, setActiveStepId] = useState<string | null>(null);
  const [promptNavWidth, setPromptNavWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [sessionCost, setSessionCost] = useState<number | null>(null);
  const [shareDialog, setShareDialog] = useState<
    { kind: "hidden" } | { kind: "demo-blocked" } | { kind: "sharing" } | { kind: "ready"; url: string; copied: boolean }
  >({ kind: "hidden" });

  const [viewMode, setViewMode] = useState<"concise" | "detail" | "workflow">(
    pendingScrollStepId ? "detail" : "concise",
  );
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
    if (viewMode !== "workflow" || flowData || flowLoading || !sessionId) return;
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

  // Map sub-agent session_id → 1-based display index (chronological order)
  const subAgentIndexMap = useMemo(() => {
    const map = new Map<string, number>();
    subAgents.forEach((sub, i) => map.set(sub.session_id, i + 1));
    return map;
  }, [subAgents]);

  const steps = (main?.steps || []) as Step[];

  const userStepIds = useMemo(() => {
    return steps
      .filter((s) => s.source === "user" && extractUserText(s))
      .map((s) => s.step_id);
  }, [steps]);

  // Compute flow data for the nav panel when in flow mode
  const flowComputed = useMemo(() => {
    if (!flowData || viewMode !== "workflow") return undefined;
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
        <div className="text-center bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-lg p-6 max-w-md">
          <p className="text-sm font-semibold text-rose-700 dark:text-rose-300 mb-2">Failed to load session</p>
          <p className="text-xs text-rose-600 dark:text-rose-400 mb-4 font-mono break-all">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-3 py-1 bg-rose-200 hover:bg-rose-300 dark:bg-rose-700/50 dark:hover:bg-rose-700 rounded text-xs text-rose-700 dark:text-rose-200 transition"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const handleShare = async () => {
    const isUploaded = trajectories.some((t) => !!t._upload_id);
    if (appMode === "demo" && isUploaded) {
      setShareDialog({ kind: "demo-blocked" });
      return;
    }
    setShareDialog({ kind: "sharing" });
    try {
      const res = await fetchWithToken("/api/shares", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (!res.ok) throw new Error(`Failed to create share: ${res.status}`);
      const data = await res.json();
      const shareUrl = `${window.location.origin}/?share=${data.session_id}`;
      setShareDialog({ kind: "ready", url: shareUrl, copied: false });
    } catch (err) {
      console.error("Share failed:", err);
      setShareDialog({ kind: "hidden" });
    }
  };

  const handleCopyShareUrl = async (url: string) => {
    await navigator.clipboard.writeText(url);
    setShareDialog({ kind: "ready", url, copied: true });
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
    <>
    <div className="h-full flex flex-col overflow-hidden">
      {/* Session Header */}
      <div className="shrink-0 bg-gradient-to-b from-panel to-panel/80 border-b border-default px-4 py-2">
        <div className="max-w-7xl mx-auto">
          {/* Row 1: Detail toggle + Session ID + Title + Actions */}
          <div className="flex items-center justify-between mb-1 gap-3">
            <div
              className="flex items-center gap-2.5 min-w-0 flex-1 cursor-pointer"
              onClick={() => setHeaderExpanded((v) => !v)}
            >
              <button
                className="flex items-center gap-0.5 shrink-0 text-xs text-dimmed hover:text-secondary hover:bg-control/30 rounded p-0.5 transition"
              >
                {headerExpanded
                  ? <ChevronDown className="w-3.5 h-3.5" />
                  : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
              <MetaPill
                icon={<Hash className="w-3 h-3" />}
                label={main.session_id.slice(0, SESSION_ID_SHORT)}
                color="text-accent-cyan"
                bg="bg-accent-cyan-muted border border-accent-cyan"
                tooltip={`Session ID: ${main.session_id}`}
              />
              <Tooltip text={main.first_message || "Session"} className="min-w-0">
                <h2 className="text-lg font-semibold text-primary truncate">
                  {main.first_message || "Session"}
                </h2>
              </Tooltip>
            </div>
            <div className="flex items-center gap-1 shrink-0 ml-3">
              {/* View mode toggle */}
              <div data-tour="view-modes" className="flex rounded-lg bg-control p-0.5 mr-2 w-[280px]">
                <Tooltip text="Messages only, tool calls hidden" className="flex-1">
                  <button
                    onClick={() => setViewMode("concise")}
                    className={`w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md transition ${
                      viewMode === "concise"
                        ? "bg-panel text-primary font-semibold shadow-sm"
                        : "text-muted hover:text-secondary"
                    }`}
                  >
                    <AlignLeft className="w-3 h-3" />
                    Concise
                  </button>
                </Tooltip>
                <Tooltip text="Full conversation with all tool calls" className="flex-1">
                  <button
                    onClick={() => setViewMode("detail")}
                    className={`w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md transition ${
                      viewMode === "detail"
                        ? "bg-panel text-primary font-semibold shadow-sm"
                        : "text-muted hover:text-secondary"
                    }`}
                  >
                    <List className="w-3 h-3" />
                    Detail
                  </button>
                </Tooltip>
                <Tooltip text="Visual diagram of the agent's steps" className="flex-1">
                  <button
                    onClick={() => setViewMode("workflow")}
                    className={`w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md transition ${
                      viewMode === "workflow"
                        ? "bg-panel text-primary font-semibold shadow-sm"
                        : "text-muted hover:text-secondary"
                    }`}
                  >
                    <GitBranch className="w-3 h-3" />
                    Workflow
                  </button>
                </Tooltip>
              </div>
              <div className="w-px h-6 bg-hover/50 mx-1" />
              {!isSharedView && (
                <Tooltip text="Share session link">
                  <button
                    onClick={handleShare}
                    disabled={shareDialog.kind === "sharing"}
                    className="p-2 text-muted hover:text-secondary hover:bg-control rounded transition text-xs disabled:opacity-50"
                  >
                    {shareDialog.kind === "sharing" ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Share2 className="w-4 h-4" />
                    )}
                  </button>
                </Tooltip>
              )}
              <Tooltip text="Download as JSON">
                <button
                  onClick={async () => {
                    try {
                      const res = await fetchWithToken(`/api/sessions/${sessionId}/export`);
                      if (!res.ok) {
                        console.error("Session download failed:", res.status, await res.text());
                        return;
                      }
                      const blob = await res.blob();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `vibelens-${sessionId.slice(0, SESSION_ID_SHORT)}.json`;
                      a.click();
                      URL.revokeObjectURL(url);
                    } catch (err) {
                      console.error("Session download failed:", err);
                    }
                  }}
                  className="p-2 text-muted hover:text-secondary hover:bg-control rounded transition text-xs"
                >
                  <Download className="w-4 h-4" />
                </button>
              </Tooltip>
            </div>
          </div>

          {headerExpanded && <>
          {/* Row 2: Meta Pills (full width) */}
          <div className="flex flex-wrap items-center gap-1.5 mb-3">
            {main.agent.model_name && (
              <MetaPill
                icon={<Cpu className="w-3 h-3" />}
                label={`${main.agent.name}@${main.agent.model_name}`}
                color="text-accent-amber"
                tooltip="Agent model used for this session"
              />
            )}
            {main.timestamp && (
              <MetaPill
                icon={<Calendar className="w-3 h-3" />}
                label={formatCreatedTime(main.timestamp)}
                color="text-secondary"
                tooltip="Session start time"
              />
            )}
            {metrics && (
              <MetaPill
                icon={<Clock className="w-3 h-3" />}
                label={formatDuration(metrics.duration)}
                color="text-accent-cyan"
                tooltip="Total wall-clock duration of this session"
              />
            )}
            <MetaPill
              icon={<MessageSquare className="w-3 h-3" />}
              label={`${promptCount} prompt${promptCount !== 1 ? "s" : ""}`}
              color="text-accent-blue"
              tooltip="User prompts — messages typed by the human operator"
            />
            {skillCount > 0 && (
              <MetaPill
                icon={<Zap className="w-3 h-3" />}
                label={`${skillCount} skill${skillCount !== 1 ? "s" : ""}`}
                color="text-accent-amber"
                tooltip="Skill invocations — reusable prompts auto-injected by the agent"
              />
            )}
            {metrics && (
              <>
                <MetaPill
                  icon={<Wrench className="w-3 h-3" />}
                  label={`${metrics.tool_call_count} tools`}
                  color="text-accent-amber"
                  tooltip="Total tool calls made by the agent (Bash, Read, Edit, etc.)"
                />
                {metrics.total_steps && (
                  <MetaPill
                    icon={<Layers className="w-3 h-3" />}
                    label={`${metrics.total_steps} steps`}
                    color="text-secondary"
                    tooltip="Total conversation steps including user, agent, and system turns"
                  />
                )}
              </>
            )}
            {subAgents.length > 0 && (
              <MetaPill
                icon={<Bot className="w-3 h-3" />}
                label={`${subAgents.length} sub-agent${subAgents.length !== 1 ? "s" : ""}`}
                color="text-accent-violet"
                tooltip="Sub-agent tasks spawned during this session"
              />
            )}
            {main.project_path && (
              <MetaPill
                icon={<FolderOpen className="w-3 h-3" />}
                label={baseProjectName(main.project_path)}
                color="text-secondary"
                tooltip={main.project_path}
              />
            )}
            {!!main.extra?._anonymized && (
              <MetaPill
                icon={<Shield className="w-3 h-3" />}
                label="Redacted"
                color="text-accent-emerald"
                tooltip={`Anonymized: ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.secrets_redacted ?? 0} secrets, ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.paths_anonymized ?? 0} paths, ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.pii_redacted ?? 0} PII`}
              />
            )}
          </div>

          {/* Row 2.5: Continuation Chain Nav */}
          {(main.prev_trajectory_ref || main.next_trajectory_ref || main.parent_trajectory_ref) && (
            <div className="flex flex-wrap items-center gap-1.5 mb-3">
              {main.parent_trajectory_ref && onNavigateSession && (
                <button
                  onClick={() => onNavigateSession(main.parent_trajectory_ref!.session_id)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent-violet-subtle border border-accent-violet text-xs text-accent-violet hover:bg-violet-100 dark:hover:bg-violet-800/40 hover:border-violet-300 dark:hover:border-violet-600/50 transition-colors"
                  title={`Navigate to parent session: ${main.parent_trajectory_ref.session_id}`}
                >
                  <Link2 className="w-3 h-3" />
                  <span>Spawned by</span>
                  <span className="text-accent-violet font-medium truncate max-w-[200px]">
                    {_lookupFirstMessage(main.parent_trajectory_ref.session_id, allSessions)}
                  </span>
                </button>
              )}
              {main.prev_trajectory_ref && onNavigateSession && (
                <button
                  onClick={() => onNavigateSession(main.prev_trajectory_ref!.session_id)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent-violet-subtle border border-accent-violet text-xs text-accent-violet hover:bg-violet-100 dark:hover:bg-violet-800/40 hover:border-violet-300 dark:hover:border-violet-600/50 transition-colors"
                  title={`Navigate to previous session: ${main.prev_trajectory_ref.session_id}`}
                >
                  <ArrowUpRight className="w-3 h-3" />
                  <span>Continued from</span>
                  <span className="text-accent-violet font-medium truncate max-w-[200px]">
                    {_lookupFirstMessage(main.prev_trajectory_ref.session_id, allSessions)}
                  </span>
                </button>
              )}
              {main.next_trajectory_ref && onNavigateSession && (
                <button
                  onClick={() => onNavigateSession(main.next_trajectory_ref!.session_id)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent-violet-subtle border border-accent-violet text-xs text-accent-violet hover:bg-violet-100 dark:hover:bg-violet-800/40 hover:border-violet-300 dark:hover:border-violet-600/50 transition-colors"
                  title={`Navigate to next session: ${main.next_trajectory_ref.session_id}`}
                >
                  <ArrowDownRight className="w-3 h-3" />
                  <span>Continues in</span>
                  <span className="text-accent-violet font-medium truncate max-w-[200px]">
                    {_lookupFirstMessage(main.next_trajectory_ref.session_id, allSessions)}
                  </span>
                </button>
              )}
            </div>
          )}

          {/* Row 3: Token Stats */}
          {metrics && (metrics.total_prompt_tokens != null || metrics.total_completion_tokens != null) && (
            <div className={`grid ${sessionCost != null ? "grid-cols-6" : "grid-cols-5"} gap-2 text-xs`}>
              <TokenStat icon={<ArrowUpRight className="w-3 h-3" />} label="Input" value={metrics.total_prompt_tokens || 0} color="text-accent-cyan" tooltip="Prompt tokens sent to the model" />
              <TokenStat icon={<ArrowDownRight className="w-3 h-3" />} label="Output" value={metrics.total_completion_tokens || 0} color="text-accent-cyan" tooltip="Completion tokens generated by the model" />
              <TokenStat icon={<Database className="w-3 h-3" />} label="Cache Read" value={metrics.total_cache_read || 0} color="text-accent-emerald" tooltip="Tokens served from prompt cache (reduced cost)" />
              <TokenStat icon={<HardDrive className="w-3 h-3" />} label="Cache Write" value={metrics.total_cache_write || 0} color="text-accent-violet" tooltip="Tokens written to prompt cache for future reuse" />
              <TokenStat icon={<BarChart3 className="w-3 h-3" />} label="Total" value={totalTokens} color="text-accent-amber" tooltip="Total tokens (input + output)" />
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
          {viewMode === "detail" || viewMode === "concise" ? (
            <div className="max-w-5xl mx-auto px-4 py-6 space-y-3">
              {steps.length === 0 ? (
                <div className="text-center text-dimmed text-sm py-8">
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
                                    index={subAgentIndexMap.get(sub.session_id)}
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
                        index={subAgentIndexMap.get(sub.session_id)}
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
              <p className="text-sm text-dimmed">Flow data unavailable</p>
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

    {/* Share link dialog */}
    {shareDialog.kind === "ready" && (
      <Modal onClose={() => setShareDialog({ kind: "hidden" })} maxWidth="max-w-lg">
        <ModalHeader onClose={() => setShareDialog({ kind: "hidden" })}>
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-md bg-accent-cyan-muted border border-accent-cyan">
              <Share2 className="w-4 h-4 text-accent-cyan" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-primary">Share session</h2>
              <p className="text-xs text-dimmed mt-0.5">Anyone with this link can view the session</p>
            </div>
          </div>
        </ModalHeader>
        <ModalBody>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={shareDialog.url}
              onFocus={(e) => e.target.select()}
              className="flex-1 bg-control border border-card rounded-lg px-3 py-2.5 text-sm text-secondary font-mono select-all focus:outline-none focus:border-accent-cyan-focus transition"
            />
            <button
              onClick={() => handleCopyShareUrl(shareDialog.url)}
              className={`shrink-0 flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-xs font-medium transition ${
                shareDialog.copied
                  ? "bg-emerald-700 text-white"
                  : "bg-cyan-700 hover:bg-cyan-600 text-white"
              }`}
            >
              {shareDialog.copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {shareDialog.copied ? "Copied!" : "Copy link"}
            </button>
          </div>
        </ModalBody>
      </Modal>
    )}

    {/* Demo mode: cannot share uploaded sessions */}
    {shareDialog.kind === "demo-blocked" && (
      <Modal onClose={() => setShareDialog({ kind: "hidden" })} maxWidth="max-w-md">
        <ModalBody>
          <div className="text-center bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-lg p-6">
            <p className="text-sm font-semibold text-rose-700 dark:text-rose-300 mb-2">Cannot share uploaded sessions</p>
            <p className="text-xs text-rose-600 dark:text-rose-400">
              Uploaded sessions are temporary and only visible in your browser tab.
              Install VibeLens locally to share sessions with a permanent link.
            </p>
            <a
              href="https://github.com/chats-lab/VibeLens"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block mt-4 px-4 py-2 rounded text-xs font-medium bg-rose-200 hover:bg-rose-300 dark:bg-rose-800/50 dark:hover:bg-rose-700/50 text-rose-700 dark:text-rose-200 transition"
            >
              Install VibeLens
            </a>
          </div>
        </ModalBody>
      </Modal>
    )}
    </>
  );
}

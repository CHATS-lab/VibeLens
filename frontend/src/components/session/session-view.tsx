import { ArrowDown, ArrowUp, BarChart3 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSessionData } from "../../hooks/use-session-data";
import { useShareSession } from "./session-share-dialog";
import { SessionViewHeader } from "./session-view-header";
import type { Step, Trajectory } from "../../types";
import { StepBlock } from "./step-block";
import { SubAgentBlock } from "./sub-agent-block";
import { StepTimeline } from "./step-timeline";
import { PromptNavPanel, type NavMode } from "./prompt-nav-panel";
import { FlowDiagram } from "./flow-diagram";
import { computeFlow } from "./flow-layout";
import { extractUserText } from "../../utils";
import { LoadingSpinner } from "../ui/loading-spinner";
import { SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH } from "../../styles";
import { SCROLL_SUPPRESS_MS } from "../../constants";

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
  const [activeStepId, setActiveStepId] = useState<string | null>(null);
  const [promptNavWidth, setPromptNavWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [navCollapsed, setNavCollapsed] = useState(false);

  const [viewMode, setViewMode] = useState<"concise" | "detail" | "workflow">(
    pendingScrollStepId ? "detail" : "concise",
  );
  const [navMode, setNavMode] = useState<NavMode>("prompts");
  const [headerExpanded, setHeaderExpanded] = useState(false);
  const stepsRef = useRef<HTMLDivElement>(null);
  const isNavigatingRef = useRef(false);
  const isSharedView = !!sharedTrajectories;

  const { trajectories, loading, error, sessionCost, flowData, flowLoading } = useSessionData({
    sessionId,
    sharedTrajectories,
    shareToken,
    loadFlow: viewMode === "workflow",
  });

  const share = useShareSession(sessionId, trajectories);

  // Clear any lingering step selection when the user navigates to a new session.
  useEffect(() => {
    setActiveStepId(null);
  }, [sessionId]);

  const handlePromptNavResize = useCallback((delta: number) => {
    setPromptNavWidth((w) =>
      Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, w + delta))
    );
  }, []);

  const main = useMemo(
    () => trajectories.find((t) => !t.parent_trajectory_ref) ?? trajectories[0] ?? null,
    [trajectories]
  );

  const subAgents = useMemo(
    () =>
      trajectories
        .filter((t) => !!t.parent_trajectory_ref)
        .sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
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
    // is <= the sub-agent's created_at. Falls back to orphans only when
    // no timestamp is available.
    for (const sub of unlinked) {
      const subTs = sub.created_at ? new Date(sub.created_at).getTime() : NaN;
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

  const scrollToTop = useCallback(() => {
    const el = stepsRef.current;
    if (!el) return;
    el.scrollTo({ top: 0, behavior: "smooth" });
  }, []);
  const scrollToBottom = useCallback(() => {
    const el = stepsRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

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

  if (!main) return null;

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
      <SessionViewHeader
        main={main}
        steps={steps}
        subAgents={subAgents}
        trajectories={trajectories}
        sessionCost={sessionCost}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        headerExpanded={headerExpanded}
        onHeaderExpandedToggle={() => setHeaderExpanded((v) => !v)}
        isSharedView={isSharedView}
        share={share}
        onNavigateSession={onNavigateSession}
        allSessions={allSessions}
      />


      {/* Two-column body: Steps + Prompt Nav */}
      <div className="flex-1 flex min-h-0">
        {/* Steps / Flow */}
        <div className="flex-1 relative min-w-0">
        <div ref={stepsRef} className="absolute inset-0 overflow-y-auto">
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
                      main.created_at
                        ? new Date(main.created_at).getTime()
                        : null
                    }
                    sessionStartTimestamp={main.created_at}
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
          <div className="absolute bottom-6 right-6 z-30 flex flex-col gap-2">
            <button
              type="button"
              onClick={scrollToTop}
              aria-label="Scroll to top"
              className="p-2.5 bg-panel hover:bg-control-hover border border-card rounded-full shadow-md text-muted hover:text-primary transition"
            >
              <ArrowUp className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={scrollToBottom}
              aria-label="Scroll to bottom"
              className="p-2.5 bg-panel hover:bg-control-hover border border-card rounded-full shadow-md text-muted hover:text-primary transition"
            >
              <ArrowDown className="w-4 h-4" />
            </button>
          </div>
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

    {share.dialogs}
    </>
  );
}

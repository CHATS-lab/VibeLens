import { History, PanelRightClose, PanelRightOpen, Search, Sparkles, Square, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type { AnalysisJobResponse, AnalysisJobStatus, CostEstimate, LLMStatus, SkillAnalysisResult, SkillMode } from "../../types";
import { SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH } from "../../styles";
import { AnalysisWelcomePage } from "../analysis-welcome";
import { CostEstimateDialog } from "../cost-estimate-dialog";
import { Tooltip } from "../tooltip";
import { ExploreSkillsTab } from "./explore-skills-tab";
import { LocalSkillsTab } from "./local-skills-tab";
import {
  AnalysisLoadingState,
  AnalysisResultView,
  type SkillTab,
} from "./skill-analysis-views";
import { SkillsHistory } from "./skills-history";

const TAB_CONFIG: { id: SkillTab; label: string; tooltip: string }[] = [
  { id: "local", label: "Local Skills", tooltip: "Manage installed SKILL.md files" },
  { id: "explore", label: "Explore", tooltip: "Browse community skills" },
  { id: "retrieve", label: "Recommend", tooltip: "Find skills matching your workflow" },
  { id: "create", label: "Customize", tooltip: "Generate skills from your patterns" },
  { id: "evolve", label: "Evolve", tooltip: "Improve existing skills from usage" },
];

const ACTIVE_TAB_STYLE = "bg-teal-600/20 text-teal-300 border border-teal-500/30";
const INACTIVE_TAB_STYLE = "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-transparent";

const MODE_MAP: Record<string, SkillMode> = {
  retrieve: "retrieval",
  create: "creation",
  evolve: "evolution",
};

const MODE_DESCRIPTIONS: Record<SkillMode, { title: string; desc: string; icon: React.ReactNode }> = {
  retrieval: {
    title: "Skill Recommendation",
    desc: "Detect workflow patterns and discover existing skills that match your coding style.",
    icon: <Search className="w-10 h-10 text-teal-400/50" />,
  },
  creation: {
    title: "Skill Customization",
    desc: "Generate new SKILL.md files from detected automation opportunities in your sessions.",
    icon: <Sparkles className="w-10 h-10 text-emerald-400/50" />,
  },
  evolution: {
    title: "Skill Evolution",
    desc: "Analyze installed skills against your usage data and suggest targeted improvements.",
    icon: <TrendingUp className="w-10 h-10 text-amber-400/50" />,
  },
};

const POLL_INTERVAL_MS = 3000;

interface SkillsPanelProps {
  checkedIds: Set<string>;
  activeJobId: string | null;
  onJobIdChange: (id: string | null) => void;
}

export function SkillsPanel({ checkedIds, activeJobId, onJobIdChange }: SkillsPanelProps) {
  const { fetchWithToken, appMode, maxAnalysisSessions } = useAppContext();
  const [activeTab, setActiveTab] = useState<SkillTab>("local");
  const [analysisResult, setAnalysisResult] = useState<SkillAnalysisResult | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);
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

  const pendingModeRef = useRef<SkillMode>("retrieval");

  const handleRequestEstimate = useCallback(
    async (mode: SkillMode) => {
      if (checkedIds.size === 0) return;
      pendingModeRef.current = mode;
      setEstimating(true);
      setAnalysisError(null);
      try {
        const res = await fetchWithToken("/api/skills/analysis/estimate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_ids: [...checkedIds], mode }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail || `HTTP ${res.status}`);
        }
        setEstimate(await res.json());
      } catch (err) {
        setAnalysisError(err instanceof Error ? err.message : String(err));
      } finally {
        setEstimating(false);
      }
    },
    [checkedIds, fetchWithToken],
  );

  const handleConfirmAnalysis = useCallback(async () => {
    const mode = pendingModeRef.current;
    setEstimate(null);
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const res = await fetchWithToken("/api/skills/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: [...checkedIds], mode }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      const data: AnalysisJobResponse = await res.json();
      if (data.status === "completed" && data.analysis_id) {
        const loadRes = await fetchWithToken(`/api/skills/analysis/${data.analysis_id}`);
        if (loadRes.ok) {
          setAnalysisResult(await loadRes.json());
          setHistoryRefresh((n) => n + 1);
        }
        setAnalysisLoading(false);
      } else {
        onJobIdChange(data.job_id);
      }
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : String(err));
      setAnalysisLoading(false);
    }
  }, [checkedIds, fetchWithToken, onJobIdChange]);

  const handleHistorySelect = useCallback((loaded: SkillAnalysisResult) => {
    setAnalysisResult(loaded);
    const tabMap: Record<SkillMode, SkillTab> = {
      retrieval: "retrieve",
      creation: "create",
      evolution: "evolve",
    };
    setActiveTab(tabMap[loaded.mode] || "retrieve");
  }, []);

  const handleNewAnalysis = useCallback(() => {
    setAnalysisResult(null);
    setAnalysisError(null);
  }, []);

  // Poll for job completion when activeJobId is set
  useEffect(() => {
    if (!activeJobId) return;
    setAnalysisLoading(true);
    const interval = setInterval(async () => {
      try {
        const res = await fetchWithToken(`/api/skills/analysis/jobs/${activeJobId}`);
        if (!res.ok) return;
        const status: AnalysisJobStatus = await res.json();
        if (status.status === "completed" && status.analysis_id) {
          onJobIdChange(null);
          setAnalysisLoading(false);
          const loadRes = await fetchWithToken(`/api/skills/analysis/${status.analysis_id}`);
          if (loadRes.ok) {
            setAnalysisResult(await loadRes.json());
            setHistoryRefresh((n) => n + 1);
          }
        } else if (status.status === "failed") {
          onJobIdChange(null);
          setAnalysisLoading(false);
          setAnalysisError(status.error_message || "Analysis failed");
        } else if (status.status === "cancelled") {
          onJobIdChange(null);
          setAnalysisLoading(false);
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
      await fetchWithToken(`/api/skills/analysis/jobs/${activeJobId}/cancel`, {
        method: "POST",
      });
    } catch {
      /* best-effort */
    }
    onJobIdChange(null);
    setAnalysisLoading(false);
  }, [activeJobId, fetchWithToken, onJobIdChange]);

  const isAnalysisTab = activeTab !== "local" && activeTab !== "explore";
  const currentMode = MODE_MAP[activeTab];

  return (
    <div className="h-full flex flex-col">
      {/* Sub-tab bar — unified teal accent, enlarged text */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-800 shrink-0">
        {TAB_CONFIG.map((tab) => (
          <Tooltip key={tab.id} text={tab.tooltip} className="flex-1 min-w-0">
            <button
              onClick={() => {
                // Clear stale analysis results when switching between analysis tabs
                if (tab.id !== activeTab && MODE_MAP[tab.id] && MODE_MAP[activeTab]) {
                  setAnalysisResult(null);
                  setAnalysisError(null);
                }
                setActiveTab(tab.id);
              }}
              className={`w-full px-3 py-1.5 text-sm font-semibold rounded-md transition text-center ${
                activeTab === tab.id ? ACTIVE_TAB_STYLE : INACTIVE_TAB_STYLE
              }`}
            >
              {tab.label}
            </button>
          </Tooltip>
        ))}
      </div>

      {/* Content area */}
      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 min-h-0 overflow-y-auto">
          {activeTab === "local" && <LocalSkillsTab />}
          {activeTab === "explore" && <ExploreSkillsTab onSwitchTab={setActiveTab} />}
          {isAnalysisTab && (analysisLoading || estimating) && (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-5">
                <AnalysisLoadingState mode={currentMode} sessionCount={checkedIds.size} />
                {activeJobId && (
                  <div className="flex flex-col items-center gap-2 mt-2">
                    <p className="text-xs text-zinc-300">Running in background — you can switch tabs</p>
                    <button
                      onClick={handleStopAnalysis}
                      className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs text-zinc-300 hover:text-white bg-zinc-700 hover:bg-zinc-600 border border-zinc-600 rounded-md transition"
                    >
                      <Square className="w-3 h-3" />
                      Stop
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
          {isAnalysisTab && !analysisLoading && !estimating && !analysisResult && (
            <AnalysisWelcomePage
              icon={MODE_DESCRIPTIONS[currentMode].icon}
              title={MODE_DESCRIPTIONS[currentMode].title}
              description={MODE_DESCRIPTIONS[currentMode].desc}
              accentColor="teal"
              llmStatus={llmStatus}
              fetchWithToken={fetchWithToken}
              onLlmConfigured={refreshLlmStatus}
              checkedCount={checkedIds.size}
              maxSessions={maxAnalysisSessions}
              error={analysisError}
              onRun={() => handleRequestEstimate(currentMode)}
              isDemo={appMode === "demo"}
            />
          )}
          {isAnalysisTab && !analysisLoading && analysisResult && (
            <AnalysisResultView
              result={analysisResult}
              activeTab={activeTab}
              onNew={handleNewAnalysis}
              fetchWithToken={fetchWithToken}
            />
          )}
        </div>

        {isAnalysisTab && showHistory && (
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
                  onClick={() => setShowHistory(false)}
                  className="p-0.5 text-zinc-500 hover:text-zinc-300 transition"
                  title="Hide history"
                >
                  <PanelRightClose className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-3 pt-1">
                <SkillsHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} filterMode={currentMode} activeJobId={activeJobId} />
              </div>
            </div>
          </>
        )}
        {isAnalysisTab && !showHistory && (
          <div className="shrink-0 border-l border-zinc-800 bg-zinc-900/50 flex flex-col items-center pt-3 px-1">
            <button
              onClick={() => setShowHistory(true)}
              className="p-1 text-zinc-500 hover:text-zinc-300 transition"
              title="Show history"
            >
              <PanelRightOpen className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
      {estimate && (
        <CostEstimateDialog
          estimate={estimate}
          sessionCount={checkedIds.size}
          onConfirm={handleConfirmAnalysis}
          onCancel={() => setEstimate(null)}
        />
      )}
    </div>
  );
}

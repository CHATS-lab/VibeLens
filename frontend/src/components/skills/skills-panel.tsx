import { History, PanelRightClose, PanelRightOpen, Search, Sparkles, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type { LLMStatus, SkillAnalysisResult, SkillMode } from "../../types";
import { SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH } from "../../styles";
import { AnalysisWelcomePage } from "../analysis-welcome";
import { ExploreSkillsTab } from "./explore-skills-tab";
import { LocalSkillsTab } from "./local-skills-tab";
import {
  AnalysisLoadingState,
  AnalysisResultView,
  type SkillTab,
} from "./skill-analysis-views";
import { SkillsHistory } from "./skills-history";

const TAB_CONFIG: { id: SkillTab; label: string }[] = [
  { id: "local", label: "Local Skills" },
  { id: "explore", label: "Explore" },
  { id: "retrieve", label: "Recommend" },
  { id: "create", label: "Create" },
  { id: "evolve", label: "Evolve" },
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
    title: "Skill Retrieval",
    desc: "Detect workflow patterns and recommend existing skills that match your coding style.",
    icon: <Search className="w-10 h-10 text-teal-400/50" />,
  },
  creation: {
    title: "Skill Creation",
    desc: "Generate new SKILL.md files from detected automation opportunities in your sessions.",
    icon: <Sparkles className="w-10 h-10 text-emerald-400/50" />,
  },
  evolution: {
    title: "Skill Evolution",
    desc: "Analyze installed skills against your usage data and suggest targeted improvements.",
    icon: <TrendingUp className="w-10 h-10 text-amber-400/50" />,
  },
};

interface SkillsPanelProps {
  checkedIds: Set<string>;
}

export function SkillsPanel({ checkedIds }: SkillsPanelProps) {
  const { fetchWithToken } = useAppContext();
  const [activeTab, setActiveTab] = useState<SkillTab>("local");
  const [analysisResult, setAnalysisResult] = useState<SkillAnalysisResult | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
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

  const handleRunAnalysis = useCallback(
    async (mode: SkillMode) => {
      if (checkedIds.size === 0) return;
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
        const data: SkillAnalysisResult = await res.json();
        setAnalysisResult(data);
        setHistoryRefresh((n) => n + 1);
      } catch (err) {
        setAnalysisError(err instanceof Error ? err.message : String(err));
      } finally {
        setAnalysisLoading(false);
      }
    },
    [checkedIds, fetchWithToken],
  );

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

  const isAnalysisTab = activeTab !== "local" && activeTab !== "explore";
  const currentMode = MODE_MAP[activeTab];

  return (
    <div className="h-full flex flex-col">
      {/* Sub-tab bar — unified teal accent, enlarged text */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-800 shrink-0">
        {TAB_CONFIG.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              // Clear stale analysis results when switching between analysis tabs
              if (tab.id !== activeTab && MODE_MAP[tab.id] && MODE_MAP[activeTab]) {
                setAnalysisResult(null);
                setAnalysisError(null);
              }
              setActiveTab(tab.id);
            }}
            className={`flex-1 px-3 py-1.5 text-sm font-semibold rounded-md transition text-center ${
              activeTab === tab.id ? ACTIVE_TAB_STYLE : INACTIVE_TAB_STYLE
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content area */}
      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 min-h-0 overflow-y-auto">
          {activeTab === "local" && <LocalSkillsTab />}
          {activeTab === "explore" && <ExploreSkillsTab />}
          {isAnalysisTab && analysisLoading && (
            <AnalysisLoadingState mode={currentMode} sessionCount={checkedIds.size} />
          )}
          {isAnalysisTab && !analysisLoading && !analysisResult && (
            <AnalysisWelcomePage
              icon={MODE_DESCRIPTIONS[currentMode].icon}
              title={MODE_DESCRIPTIONS[currentMode].title}
              description={MODE_DESCRIPTIONS[currentMode].desc}
              accentColor="teal"
              llmStatus={llmStatus}
              fetchWithToken={fetchWithToken}
              onLlmConfigured={refreshLlmStatus}
              checkedCount={checkedIds.size}
              error={analysisError}
              onRun={() => handleRunAnalysis(currentMode)}
            />
          )}
          {isAnalysisTab && !analysisLoading && analysisResult && (
            <AnalysisResultView
              result={analysisResult}
              activeTab={activeTab}
              onRerun={() => handleRunAnalysis(currentMode)}
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
                <SkillsHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} filterMode={currentMode} />
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
    </div>
  );
}

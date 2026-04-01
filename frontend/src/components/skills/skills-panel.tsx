import { History, Search, Sparkles, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAppContext } from "../../app";
import type { LLMStatus, SkillAnalysisResult, SkillMode } from "../../types";
import { SIDEBAR_DEFAULT_WIDTH } from "../../styles";
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
        {isAnalysisTab && (
          <button
            onClick={() => setShowHistory(!showHistory)}
            className={`ml-auto p-1.5 rounded transition ${
              showHistory
                ? "text-zinc-300 bg-zinc-800"
                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
            }`}
            title="Toggle history sidebar"
          >
            <History className="w-4 h-4" />
          </button>
        )}
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
          <div style={{ width: SIDEBAR_DEFAULT_WIDTH }} className="shrink-0 bg-zinc-900/50 overflow-y-auto">
            <SkillsHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} filterMode={currentMode} />
          </div>
        )}
      </div>
    </div>
  );
}

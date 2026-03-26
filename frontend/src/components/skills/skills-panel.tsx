import { History } from "lucide-react";
import { useCallback, useState } from "react";
import { useAppContext } from "../../app";
import type { SkillAnalysisResult, SkillMode } from "../../types";
import { ExploreSkillsTab } from "./explore-skills-tab";
import { LocalSkillsTab } from "./local-skills-tab";
import {
  AnalysisEmptyState,
  AnalysisLoadingState,
  AnalysisResultView,
  type SkillTab,
} from "./skill-analysis-views";
import { SkillsHistory } from "./skills-history";

const TAB_CONFIG: { id: SkillTab; label: string }[] = [
  { id: "local", label: "Local Skills" },
  { id: "explore", label: "Explore" },
  { id: "retrieve", label: "Retrieve" },
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
            <AnalysisEmptyState
              mode={currentMode}
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
          <div className="w-56 shrink-0 bg-zinc-900/50 overflow-y-auto">
            <SkillsHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} filterMode={currentMode} />
          </div>
        )}
      </div>
    </div>
  );
}

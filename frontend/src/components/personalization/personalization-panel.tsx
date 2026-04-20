import { Check, History, Info, PanelRightClose, PanelRightOpen, Search, Sparkles, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext, useExtensionsClient } from "../../app";
import { analysisClient } from "../../api/analysis";
import { llmClient } from "../../api/llm";
import { useJobPolling } from "../../hooks/use-job-polling";
import { useResetOnKey } from "../../hooks/use-reset-on-key";
import type { ExtensionItemSummary, LLMStatus, PersonalizationResult, Skill, PersonalizationMode } from "../../types";
import { SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH } from "../../styles";
import { useCostEstimate } from "../../hooks/use-cost-estimate";
import { AnalysisLoadingScreen } from "../analysis-loading-screen";
import { AnalysisWelcomePage, TutorialBanner } from "../analysis-welcome";
import { CostEstimateDialog } from "../cost-estimate-dialog";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../ui/modal";
import { Tooltip } from "../ui/tooltip";
import { ExtensionExploreTab } from "./extensions/extension-explore-tab";
import { LocalExtensionsTab } from "./local-extensions-tab";
import {
  AnalysisResultView,
  type PersonalizationTab,
} from "./personalization-view";
import { PersonalizationHistory } from "./personalization-history";

const TAB_CONFIG: { id: PersonalizationTab; label: string; tooltip: string }[] = [
  { id: "local", label: "Local", tooltip: "Manage installed skills, subagents, commands, and plugins" },
  { id: "explore", label: "Explore", tooltip: "Browse community skills" },
  { id: "retrieve", label: "Recommend", tooltip: "Find skills matching your workflow" },
  { id: "create", label: "Customize", tooltip: "Generate skills from your patterns" },
  { id: "evolve", label: "Evolve", tooltip: "Improve existing skills from usage" },
];

const ACTIVE_TAB_STYLE = "bg-control/70 text-primary";
const INACTIVE_TAB_STYLE = "text-muted hover:text-secondary hover:bg-control/40";

const MODE_MAP: Record<string, PersonalizationMode> = {
  retrieve: "recommendation",
  create: "creation",
  evolve: "evolution",
};

const API_BASE_MAP: Record<string, string> = {
  retrieve: "/api/recommendation",
  create: "/api/creation",
  evolve: "/api/evolution",
};

const MODE_DESCRIPTIONS: Record<PersonalizationMode, {
  title: string;
  desc: string;
  icon: React.ReactNode;
  tutorial: { title: string; description: string };
}> = {
  recommendation: {
    title: "Skill Recommendation",
    desc: "Detect workflow patterns and discover existing skills that match your coding style.",
    icon: <Search className="w-10 h-10 text-teal-600 dark:text-teal-400" />,
    tutorial: {
      title: "How does this work?",
      description: "VibeLens scans your sessions for patterns in how you work, then searches the community skill library for ready-made skills that match your workflow.",
    },
  },
  creation: {
    title: "Skill Customization",
    desc: "Generate new SKILL.md files from detected automation opportunities in your sessions.",
    icon: <Sparkles className="w-10 h-10 text-emerald-600 dark:text-emerald-400" />,
    tutorial: {
      title: "How does this work?",
      description: "VibeLens looks at your sessions and creates brand-new skill files written specifically for your workflow. These capture patterns unique to how you work that aren't covered by existing skills.",
    },
  },
  evolution: {
    title: "Skill Evolution",
    desc: "Analyze installed skills against your usage data and suggest targeted improvements.",
    icon: <TrendingUp className="w-10 h-10 text-teal-600 dark:text-teal-400" />,
    tutorial: {
      title: "How does this work?",
      description: "VibeLens compares your installed skills with how you actually use your agents. Where it finds gaps or outdated instructions, it suggests edits to make those skills work better for you.",
    },
  },
};

const MODE_LOADING_TITLES: Record<PersonalizationMode, string> = {
  recommendation: "Discovering skills that match your coding patterns",
  creation: "Generating custom skills from your workflow",
  evolution: "Checking installed skills against your usage",
};

interface PersonalizationPanelProps {
  checkedIds: Set<string>;
  activeJobId: string | null;
  onJobIdChange: (id: string | null) => void;
  resetKey?: number;
}

export function PersonalizationPanel({ checkedIds, activeJobId, onJobIdChange, resetKey = 0 }: PersonalizationPanelProps) {
  const { fetchWithToken, appMode, maxSessions } = useAppContext();
  const llmApi = useMemo(() => llmClient(fetchWithToken), [fetchWithToken]);
  const [activeTab, setActiveTab] = useState<PersonalizationTab>(() => {
    const stored = localStorage.getItem("vibelens-personalization-tab");
    if (stored && TAB_CONFIG.some((t) => t.id === stored)) return stored as PersonalizationTab;
    return "local";
  });
  const [analysisResult, setAnalysisResult] = useState<PersonalizationResult | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  const [analysisDetailItem, setAnalysisDetailItem] = useState<ExtensionItemSummary | null>(null);
  const [localDetailOpen, setLocalDetailOpen] = useState(false);
  const [exploreDetailOpen, setExploreDetailOpen] = useState(false);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [localRefresh, setLocalRefresh] = useState(0);
  const [exploreResetKey, setExploreResetKey] = useState(0);
  const [localResetKey, setLocalResetKey] = useState(0);
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null);
  const { estimate, estimating, requestEstimate, clearEstimate } = useCostEstimate(
    fetchWithToken,
    setAnalysisError,
  );
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const draggingRef = useRef(false);

  // Re-clicking the top-level Personalization nav: close any open detail page.
  useResetOnKey(resetKey, () => {
    setAnalysisDetailItem(null);
    setExploreResetKey((k) => k + 1);
    setLocalResetKey((k) => k + 1);
  });

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
      setLlmStatus(await llmApi.status());
    } catch {
      /* best-effort */
    }
  }, [llmApi]);

  useEffect(() => {
    refreshLlmStatus();
  }, [refreshLlmStatus]);

  const pendingModeRef = useRef<PersonalizationMode>("recommendation");
  const selectedSkillNamesRef = useRef<string[] | undefined>(undefined);
  const resolvedSessionIdsRef = useRef<string[]>([]);
  const [showSkillSelector, setShowSkillSelector] = useState(false);

  const fetchAllSessionIds = useCallback(async (): Promise<string[]> => {
    const res = await fetchWithToken("/api/sessions");
    if (!res.ok) throw new Error("Failed to load sessions");
    const sessions: { session_id: string }[] = await res.json();
    return sessions.map((s) => s.session_id);
  }, [fetchWithToken]);

  const proceedToEstimate = useCallback(
    (mode: PersonalizationMode, overrideSessionIds?: string[]) => {
      setAnalysisError(null);
      const sessionIds = overrideSessionIds ?? [...checkedIds];
      const body: Record<string, unknown> = { session_ids: sessionIds };
      if (selectedSkillNamesRef.current) body.skill_names = selectedSkillNamesRef.current;
      const tabKey = Object.entries(MODE_MAP).find(([, v]) => v === mode)?.[0] ?? "retrieve";
      requestEstimate(`${API_BASE_MAP[tabKey]}/estimate`, body);
    },
    [checkedIds, requestEstimate],
  );

  const handleConfirmAnalysis = useCallback(async () => {
    const mode = pendingModeRef.current;
    const tabKey = Object.entries(MODE_MAP).find(([, v]) => v === mode)?.[0] ?? "retrieve";
    const api = analysisClient(fetchWithToken, API_BASE_MAP[tabKey]);
    const isRecommend = mode === "recommendation";
    clearEstimate();
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const sessionIds = isRecommend ? resolvedSessionIdsRef.current : [...checkedIds];
      const body: Record<string, unknown> = { session_ids: sessionIds };
      if (selectedSkillNamesRef.current) body.skill_names = selectedSkillNamesRef.current;
      const data = await api.submit(body);
      if (data.status === "completed" && data.analysis_id) {
        setAnalysisResult(await api.load<PersonalizationResult>(data.analysis_id));
        setHistoryRefresh((n) => n + 1);
        setAnalysisLoading(false);
      } else {
        onJobIdChange(data.job_id);
      }
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : String(err));
      setAnalysisLoading(false);
    }
  }, [checkedIds, clearEstimate, fetchWithToken, onJobIdChange]);

  const handleRequestEstimate = useCallback(
    async (mode: PersonalizationMode) => {
      if (checkedIds.size === 0) return;
      pendingModeRef.current = mode;
      selectedSkillNamesRef.current = undefined;
      if (mode === "recommendation") {
        resolvedSessionIdsRef.current = [...checkedIds];
      }
      if (mode === "evolution") {
        setShowSkillSelector(true);
        return;
      }
      proceedToEstimate(mode);
    },
    [checkedIds, proceedToEstimate],
  );

  const handleRunAll = useCallback(async () => {
    pendingModeRef.current = "recommendation";
    selectedSkillNamesRef.current = undefined;
    setAnalysisError(null);
    try {
      const allIds = await fetchAllSessionIds();
      if (allIds.length === 0) {
        setAnalysisError("No sessions available for analysis.");
        return;
      }
      resolvedSessionIdsRef.current = allIds;
      proceedToEstimate("recommendation", allIds);
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : String(err));
    }
  }, [fetchAllSessionIds, proceedToEstimate]);

  const handleSkillSelectionConfirm = useCallback(
    (skillNames: string[]) => {
      setShowSkillSelector(false);
      selectedSkillNamesRef.current = skillNames;
      proceedToEstimate(pendingModeRef.current);
    },
    [proceedToEstimate],
  );

  const handleHistorySelect = useCallback((loaded: PersonalizationResult) => {
    const tabMap: Record<PersonalizationMode, PersonalizationTab> = {
      recommendation: "retrieve",
      creation: "create",
      evolution: "evolve",
    };
    const tab = tabMap[loaded.mode] || "retrieve";
    setAnalysisDetailItem(null);
    setAnalysisResult(loaded);
    setActiveTab(tab);
    localStorage.setItem("vibelens-personalization-tab", tab);
  }, []);

  // In demo mode, auto-load the most recent analysis for a given mode
  const demoHistoryRef = useRef<{ id: string; mode: PersonalizationMode }[] | null>(null);

  const loadDemoAnalysis = useCallback(
    async (mode: PersonalizationMode) => {
      if (appMode !== "demo") return;
      const tabKey = Object.entries(MODE_MAP).find(([, v]) => v === mode)?.[0] ?? "retrieve";
      const api = analysisClient(fetchWithToken, API_BASE_MAP[tabKey]);
      try {
        if (!demoHistoryRef.current) {
          demoHistoryRef.current = await api.history<{ id: string; mode: PersonalizationMode }>();
        }
        const match = demoHistoryRef.current?.find((h) => h.mode === mode);
        if (!match) return;
        setAnalysisResult(await api.load<PersonalizationResult>(match.id));
      } catch {
        /* best-effort — fall back to welcome page */
      }
    },
    [appMode, fetchWithToken],
  );

  // Auto-load on initial mount in demo mode, respecting stored tab preference
  const demoLoadedRef = useRef(false);
  useEffect(() => {
    if (appMode !== "demo" || demoLoadedRef.current) return;
    demoLoadedRef.current = true;

    // Only auto-load for analysis tabs (not local/explore)
    const storedTab = localStorage.getItem("vibelens-personalization-tab");
    const targetMode = storedTab && MODE_MAP[storedTab] ? MODE_MAP[storedTab] : null;
    if (!targetMode) return;

    const api = analysisClient(fetchWithToken, API_BASE_MAP[storedTab!]);

    (async () => {
      try {
        const history = await api.history<{ id: string; mode: PersonalizationMode }>();
        demoHistoryRef.current = history;
        if (history.length === 0) return;
        const match = history.find((h) => h.mode === targetMode) ?? history[0];
        handleHistorySelect(await api.load<PersonalizationResult>(match.id));
      } catch {
        /* best-effort */
      }
    })();
  }, [appMode, fetchWithToken, handleHistorySelect]);

  const handleNewAnalysis = useCallback(() => {
    setAnalysisResult(null);
    setAnalysisError(null);
    setAnalysisDetailItem(null);
  }, []);

  // Bump both counters after install/update so LocalExtensionsTab and PersonalizationHistory refresh.
  const handleSkillInstalled = useCallback(() => {
    setLocalRefresh((n) => n + 1);
    setHistoryRefresh((n) => n + 1);
  }, []);

  const pollApiBase = API_BASE_MAP[activeTab] ?? "/api/recommendation";
  useEffect(() => {
    if (activeJobId) setAnalysisLoading(true);
  }, [activeJobId]);

  const handleJobCompleted = useCallback(
    async (analysisId: string) => {
      onJobIdChange(null);
      setAnalysisLoading(false);
      try {
        const api = analysisClient(fetchWithToken, pollApiBase);
        setAnalysisResult(await api.load<PersonalizationResult>(analysisId));
      } catch {
        /* best-effort */
      }
      setHistoryRefresh((n) => n + 1);
    },
    [fetchWithToken, onJobIdChange, pollApiBase],
  );
  const handleJobFailed = useCallback(
    (message: string) => {
      onJobIdChange(null);
      setAnalysisLoading(false);
      setAnalysisError(message);
    },
    [onJobIdChange],
  );
  const handleJobCancelled = useCallback(() => {
    onJobIdChange(null);
    setAnalysisLoading(false);
  }, [onJobIdChange]);

  useJobPolling(activeJobId, pollApiBase, fetchWithToken, {
    onCompleted: handleJobCompleted,
    onFailed: handleJobFailed,
    onCancelled: handleJobCancelled,
  });

  const handleStopAnalysis = useCallback(async () => {
    if (!activeJobId) return;
    const api = analysisClient(fetchWithToken, API_BASE_MAP[activeTab] ?? "/api/recommendation");
    try {
      await api.cancelJob(activeJobId);
    } catch {
      /* best-effort */
    }
    onJobIdChange(null);
    setAnalysisLoading(false);
  }, [activeJobId, activeTab, fetchWithToken, onJobIdChange]);

  const isAnalysisTab = activeTab !== "local" && activeTab !== "explore";
  const currentMode = MODE_MAP[activeTab];
  const anyDetailOpen = localDetailOpen || exploreDetailOpen || analysisDetailItem !== null;

  return (
    <div className="h-full flex flex-col">
      {/* Sub-tab bar — hidden while viewing any extension detail page */}
      {!anyDetailOpen && (
      <div className="flex items-center gap-1 px-4 py-2 border-b border-card shrink-0">
        {TAB_CONFIG.map((tab) => (
          <Tooltip key={tab.id} text={tab.tooltip} className="flex-1 min-w-0">
            <button
              onClick={() => {
                if (tab.id === "explore" && activeTab === "explore") {
                  setExploreResetKey((k) => k + 1);
                }
                if (tab.id !== activeTab && MODE_MAP[tab.id] && MODE_MAP[activeTab]) {
                  setAnalysisResult(null);
                  setAnalysisError(null);
                  setAnalysisDetailItem(null);
                  if (appMode === "demo" && MODE_MAP[tab.id]) {
                    loadDemoAnalysis(MODE_MAP[tab.id]);
                  }
                }
                setActiveTab(tab.id);
                localStorage.setItem("vibelens-personalization-tab", tab.id);
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
      )}

      {/* Content area */}
      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 min-h-0 overflow-y-auto">
          {isAnalysisTab && !analysisDetailItem && (
            <div className="px-6 pt-5 pb-2">
              <TutorialBanner tutorial={MODE_DESCRIPTIONS[currentMode].tutorial} accentColor="teal" />
            </div>
          )}
          {activeTab === "local" && (
            <LocalExtensionsTab
              refreshTrigger={localRefresh}
              onDetailOpenChange={setLocalDetailOpen}
              resetKey={localResetKey}
            />
          )}
          {activeTab === "explore" && (
            <ExtensionExploreTab
              resetKey={exploreResetKey}
              onDetailOpenChange={setExploreDetailOpen}
              onSwitchToRecommend={() => {
                setActiveTab("retrieve");
                localStorage.setItem("vibelens-personalization-tab", "retrieve");
                setAnalysisResult(null);
                setAnalysisError(null);
                setAnalysisDetailItem(null);
                if (appMode === "demo") loadDemoAnalysis("recommendation");
              }}
            />
          )}
          {isAnalysisTab && (analysisLoading || estimating) && !analysisResult && (
            <AnalysisLoadingScreen
              accent="teal"
              title={MODE_LOADING_TITLES[currentMode]}
              sublabel={estimating ? "Estimating cost..." : "Usually takes 2-5 minutes"}
              sessionCount={activeTab === "retrieve" ? resolvedSessionIdsRef.current.length : checkedIds.size}
              onStop={activeJobId ? handleStopAnalysis : undefined}
            />
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
              maxSessions={maxSessions}
              error={analysisError}
              onRun={() => handleRequestEstimate(currentMode)}
              isDemo={appMode === "demo"}
              {...(activeTab === "retrieve" ? { onRunAll: handleRunAll } : {})}
            />
          )}
          {isAnalysisTab && analysisResult && (
            <AnalysisResultView
              result={analysisResult}
              activeTab={activeTab}
              onNew={handleNewAnalysis}
              onInstalled={handleSkillInstalled}
              detailItem={analysisDetailItem}
              onDetailChange={setAnalysisDetailItem}
              onSwitchTab={(tab) => {
                setActiveTab(tab);
                localStorage.setItem("vibelens-personalization-tab", tab);
                setAnalysisResult(null);
                setAnalysisError(null);
                setAnalysisDetailItem(null);
              }}
            />
          )}
        </div>

        {isAnalysisTab && !analysisDetailItem && showHistory && (
          <>
            <div
              onMouseDown={handleDragStart}
              className="w-1 shrink-0 cursor-col-resize bg-control hover:bg-control-hover transition-colors"
            />
            <div
              className="shrink-0 border-l border-default bg-panel/50 flex flex-col"
              style={{ width: sidebarWidth }}
            >
              <div className="shrink-0 flex items-center justify-between px-3 pt-3 pb-2 border-b border-card">
                <div className="flex items-center gap-1.5">
                  <History className="w-3.5 h-3.5 text-accent-cyan" />
                  <span className="text-xs font-semibold text-secondary tracking-wide uppercase">History</span>
                </div>
                <Tooltip text="Hide history">
                  <button
                    onClick={() => setShowHistory(false)}
                    className="p-1 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
                  >
                    <PanelRightClose className="w-3.5 h-3.5" />
                  </button>
                </Tooltip>
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto p-3 pt-1">
                <PersonalizationHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} filterMode={currentMode} activeJobId={activeJobId} onStop={handleStopAnalysis} />
              </div>
            </div>
          </>
        )}
        {isAnalysisTab && !analysisDetailItem && !showHistory && (
          <div className="shrink-0 border-l border-default bg-panel/50 flex flex-col items-center pt-3 px-1">
            <Tooltip text="Show history">
              <button
                onClick={() => setShowHistory(true)}
                className="p-1.5 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
              >
                <PanelRightOpen className="w-4 h-4" />
              </button>
            </Tooltip>
          </div>
        )}
      </div>
      {estimate && (
        <CostEstimateDialog
          estimate={estimate}
          sessionCount={activeTab === "retrieve" ? resolvedSessionIdsRef.current.length : checkedIds.size}
          onConfirm={handleConfirmAnalysis}
          onCancel={clearEstimate}
        />
      )}
      {showSkillSelector && (
        <SkillSelectionDialog
          onConfirm={handleSkillSelectionConfirm}
          onCancel={() => setShowSkillSelector(false)}
        />
      )}
    </div>
  );
}

function SkillSelectionDialog({
  onConfirm,
  onCancel,
}: {
  onConfirm: (skillNames: string[]) => void;
  onCancel: () => void;
}) {
  const client = useExtensionsClient();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.skills.list({ pageSize: 200 })
      .then((data) => {
        setSkills((data.items ?? []) as unknown as Skill[]);
        setSelected(new Set());
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setLoading(false));
  }, [client]);

  const allSelected = skills.length > 0 && selected.size === skills.length;

  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(skills.map((s) => s.name)));
  };

  const toggleSkill = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  return (
    <Modal onClose={onCancel} maxWidth="max-w-lg">
      <ModalHeader title="Select Skills to Evolve" onClose={onCancel} />
      <ModalBody>
        <div className="flex items-start gap-2 px-3 py-2 bg-teal-50 dark:bg-teal-950/20 border border-teal-200 dark:border-teal-700/30 rounded-lg mb-4">
          <Info className="w-4 h-4 text-teal-600 dark:text-teal-400 mt-0.5 shrink-0" />
          <p className="text-xs text-secondary leading-relaxed">
            Choose the skills that are relevant to the selected sessions. Only selected skills will be analyzed for improvements.
          </p>
        </div>
        {loading && <p className="text-sm text-muted text-center py-8">Loading installed skills...</p>}
        {error && <p className="text-sm text-rose-600 dark:text-rose-400 text-center py-4">{error}</p>}
        {!loading && skills.length === 0 && (
          <p className="text-sm text-muted text-center py-8">No installed skills found. Install skills first.</p>
        )}
        {!loading && skills.length > 0 && (
          <div className="space-y-1">
            <button
              onClick={toggleAll}
              className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg hover:bg-control/50 transition text-left"
            >
              <span className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                allSelected ? "bg-teal-600 border-teal-500" : "border-hover"
              }`}>
                {allSelected && <Check className="w-3 h-3 text-white" />}
              </span>
              <span className="text-sm font-semibold text-secondary">Select all</span>
              <span className="text-xs text-dimmed ml-auto">{selected.size}/{skills.length}</span>
            </button>
            <div className="border-t border-card my-1" />
            <div className="max-h-64 overflow-y-auto space-y-0.5">
              {skills.map((skill) => (
                <button
                  key={skill.name}
                  onClick={() => toggleSkill(skill.name)}
                  className="flex items-start gap-2.5 w-full px-3 py-2 rounded-lg hover:bg-control/50 transition text-left"
                >
                  <span className={`w-4 h-4 mt-0.5 rounded border flex items-center justify-center shrink-0 ${
                    selected.has(skill.name) ? "bg-teal-600 border-teal-500" : "border-hover"
                  }`}>
                    {selected.has(skill.name) && <Check className="w-3 h-3 text-white" />}
                  </span>
                  <div className="min-w-0">
                    <span className="text-sm font-mono font-semibold text-primary">{skill.name}</span>
                    {skill.description && (
                      <p className="text-xs text-muted mt-0.5 line-clamp-2">{skill.description}</p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm text-secondary hover:text-primary bg-control hover:bg-control-hover border border-card rounded-md transition"
        >
          Cancel
        </button>
        <button
          onClick={() => onConfirm([...selected])}
          disabled={selected.size === 0}
          className="px-4 py-2 text-sm font-semibold text-white bg-teal-600 hover:bg-teal-500 rounded-md transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Continue with {selected.size} skill{selected.size !== 1 ? "s" : ""}
        </button>
      </ModalFooter>
    </Modal>
  );
}

import { Check, History, Info, PanelRightClose, PanelRightOpen, Search, Sparkles, Square, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppContext } from "../../app";
import type { AnalysisJobResponse, AnalysisJobStatus, CostEstimate, LLMStatus, PersonalizationResult, Skill, PersonalizationMode } from "../../types";
import { SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH } from "../../styles";
import { AnalysisWelcomePage, TutorialBanner } from "../analysis-welcome";
import { CostEstimateDialog } from "../cost-estimate-dialog";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../modal";
import { Tooltip } from "../tooltip";
import { ExtensionExploreTab } from "./extensions/extension-explore-tab";
import { LocalExtensionsTab } from "./local-extensions-tab";
import {
  AnalysisLoadingState,
  AnalysisResultView,
  type PersonalizationTab,
} from "./personalization-view";
import { PersonalizationHistory } from "./personalization-history";

const TAB_CONFIG: { id: PersonalizationTab; label: string; tooltip: string }[] = [
  { id: "local", label: "Local Skills", tooltip: "Manage installed SKILL.md files" },
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

const POLL_INTERVAL_MS = 3000;

interface PersonalizationPanelProps {
  checkedIds: Set<string>;
  activeJobId: string | null;
  onJobIdChange: (id: string | null) => void;
}

export function PersonalizationPanel({ checkedIds, activeJobId, onJobIdChange }: PersonalizationPanelProps) {
  const { fetchWithToken, appMode, maxSessions } = useAppContext();
  const [activeTab, setActiveTab] = useState<PersonalizationTab>(() => {
    const stored = localStorage.getItem("vibelens-personalization-tab");
    if (stored && TAB_CONFIG.some((t) => t.id === stored)) return stored as PersonalizationTab;
    return "local";
  });
  const [analysisResult, setAnalysisResult] = useState<PersonalizationResult | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [localRefresh, setLocalRefresh] = useState(0);
  const [exploreResetKey, setExploreResetKey] = useState(0);
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
    async (mode: PersonalizationMode, overrideSessionIds?: string[]) => {
      setEstimating(true);
      setAnalysisError(null);
      try {
        const sessionIds = overrideSessionIds ?? [...checkedIds];
        const body: Record<string, unknown> = { session_ids: sessionIds };
        if (selectedSkillNamesRef.current) body.skill_names = selectedSkillNamesRef.current;
        const tabKey = Object.entries(MODE_MAP).find(([, v]) => v === mode)?.[0] ?? "retrieve";
        const apiBase = API_BASE_MAP[tabKey];
        const res = await fetchWithToken(`${apiBase}/estimate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          throw new Error(data?.detail || `HTTP ${res.status}`);
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
    const tabKey = Object.entries(MODE_MAP).find(([, v]) => v === mode)?.[0] ?? "retrieve";
    const apiBase = API_BASE_MAP[tabKey];
    const isRecommend = mode === "recommendation";
    setEstimate(null);
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const sessionIds = isRecommend
        ? resolvedSessionIdsRef.current
        : [...checkedIds];
      const body: Record<string, unknown> = { session_ids: sessionIds };
      if (selectedSkillNamesRef.current) body.skill_names = selectedSkillNamesRef.current;
      const res = await fetchWithToken(apiBase, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail || `HTTP ${res.status}`);
      }
      const data: AnalysisJobResponse = await res.json();
      if (data.status === "completed" && data.analysis_id) {
        const loadRes = await fetchWithToken(`${apiBase}/${data.analysis_id}`);
        if (loadRes.ok) {
          setAnalysisResult(await loadRes.json());
        }
        setHistoryRefresh((n) => n + 1);
        setAnalysisLoading(false);
      } else {
        onJobIdChange(data.job_id);
      }
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : String(err));
      setAnalysisLoading(false);
    }
  }, [checkedIds, fetchWithToken, onJobIdChange]);

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
      const apiBase = API_BASE_MAP[tabKey];
      try {
        if (!demoHistoryRef.current) {
          const res = await fetchWithToken(`${apiBase}/history`);
          if (!res.ok) return;
          demoHistoryRef.current = await res.json();
        }
        const match = demoHistoryRef.current?.find((h) => h.mode === mode);
        if (!match) return;
        const loadRes = await fetchWithToken(`${apiBase}/${match.id}`);
        if (!loadRes.ok) return;
        setAnalysisResult(await loadRes.json());
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

    const apiBase = API_BASE_MAP[storedTab!];

    (async () => {
      try {
        const res = await fetchWithToken(`${apiBase}/history`);
        if (!res.ok) return;
        const history: { id: string; mode: PersonalizationMode }[] = await res.json();
        demoHistoryRef.current = history;
        if (history.length === 0) return;
        const match = history.find((h) => h.mode === targetMode) ?? history[0];
        const loadRes = await fetchWithToken(`${apiBase}/${match.id}`);
        if (!loadRes.ok) return;
        const result: PersonalizationResult = await loadRes.json();
        handleHistorySelect(result);
      } catch {
        /* best-effort */
      }
    })();
  }, [appMode, fetchWithToken, handleHistorySelect]);

  const handleNewAnalysis = useCallback(() => {
    setAnalysisResult(null);
    setAnalysisError(null);
  }, []);

  // Bump both counters after install/update so LocalExtensionsTab and PersonalizationHistory refresh.
  const handleSkillInstalled = useCallback(() => {
    setLocalRefresh((n) => n + 1);
    setHistoryRefresh((n) => n + 1);
  }, []);

  // Poll for job completion when activeJobId is set
  useEffect(() => {
    if (!activeJobId) return;
    setAnalysisLoading(true);
    const apiBase = API_BASE_MAP[activeTab] ?? "/api/recommendation";
    const interval = setInterval(async () => {
      try {
        const res = await fetchWithToken(`${apiBase}/jobs/${activeJobId}`);
        if (!res.ok) return;
        const status: AnalysisJobStatus = await res.json();
        if (status.status === "completed" && status.analysis_id) {
          onJobIdChange(null);
          setAnalysisLoading(false);
          const loadRes = await fetchWithToken(`${apiBase}/${status.analysis_id}`);
          if (loadRes.ok) {
            setAnalysisResult(await loadRes.json());
          }
          setHistoryRefresh((n) => n + 1);
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
  }, [activeJobId, activeTab, fetchWithToken, onJobIdChange]);

  const handleStopAnalysis = useCallback(async () => {
    if (!activeJobId) return;
    const apiBase = API_BASE_MAP[activeTab] ?? "/api/recommendation";
    try {
      await fetchWithToken(`${apiBase}/jobs/${activeJobId}/cancel`, {
        method: "POST",
      });
    } catch {
      /* best-effort */
    }
    onJobIdChange(null);
    setAnalysisLoading(false);
  }, [activeJobId, activeTab, fetchWithToken, onJobIdChange]);

  const isAnalysisTab = activeTab !== "local" && activeTab !== "explore";
  const currentMode = MODE_MAP[activeTab];

  return (
    <div className="h-full flex flex-col">
      {/* Sub-tab bar — unified teal accent, enlarged text */}
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

      {/* Content area */}
      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 min-h-0 overflow-y-auto">
          {isAnalysisTab && (
            <div className="px-6 pt-5 pb-2">
              <TutorialBanner tutorial={MODE_DESCRIPTIONS[currentMode].tutorial} accentColor="teal" />
            </div>
          )}
          {activeTab === "local" && <LocalExtensionsTab refreshTrigger={localRefresh} />}
          {activeTab === "explore" && <ExtensionExploreTab resetKey={exploreResetKey} />}
          {isAnalysisTab && (analysisLoading || estimating) && (
            <div className="flex items-center justify-center pt-16">
              <div className="flex flex-col items-center gap-5 max-w-md">
                <AnalysisLoadingState mode={currentMode} sessionCount={activeTab === "retrieve" ? resolvedSessionIdsRef.current.length : checkedIds.size} />
                {activeJobId && (
                  <div className="flex flex-col items-center gap-3 mt-1">
                    <button
                      onClick={handleStopAnalysis}
                      className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs text-rose-600 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 dark:text-rose-300 dark:hover:text-white dark:bg-rose-900/30 dark:hover:bg-rose-800/50 dark:border-rose-700/50 rounded-md transition"
                    >
                      <Square className="w-3 h-3" />
                      Stop
                    </button>
                    <div className="text-center space-y-1">
                      <p className="text-sm text-muted">Usually takes 2-5 minutes</p>
                      <p className="text-sm text-muted">Running in background. You can switch tabs.</p>
                    </div>
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
              maxSessions={maxSessions}
              error={analysisError}
              onRun={() => handleRequestEstimate(currentMode)}
              isDemo={appMode === "demo"}
              {...(activeTab === "retrieve" ? { onRunAll: handleRunAll } : {})}
            />
          )}
          {isAnalysisTab && !analysisLoading && analysisResult && (
            <AnalysisResultView
              result={analysisResult}
              activeTab={activeTab}
              onNew={handleNewAnalysis}
              fetchWithToken={fetchWithToken}
              onInstalled={handleSkillInstalled}
            />
          )}
        </div>

        {isAnalysisTab && showHistory && (
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
                <PersonalizationHistory onSelect={handleHistorySelect} refreshTrigger={historyRefresh} filterMode={currentMode} activeJobId={activeJobId} />
              </div>
            </div>
          </>
        )}
        {isAnalysisTab && !showHistory && (
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
          onCancel={() => setEstimate(null)}
        />
      )}
      {showSkillSelector && (
        <SkillSelectionDialog
          fetchWithToken={fetchWithToken}
          onConfirm={handleSkillSelectionConfirm}
          onCancel={() => setShowSkillSelector(false)}
        />
      )}
    </div>
  );
}

function SkillSelectionDialog({
  fetchWithToken,
  onConfirm,
  onCancel,
}: {
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onConfirm: (skillNames: string[]) => void;
  onCancel: () => void;
}) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchWithToken("/api/skills?page_size=200");
        if (!res.ok) throw new Error("Failed to load skills");
        const data = await res.json();
        const items: Skill[] = data.items ?? [];
        setSkills(items);
        setSelected(new Set());
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [fetchWithToken]);

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

import {
  Menu,
  PanelLeftClose,
  RefreshCw,
  Settings,
  Share2,
} from "lucide-react";
import { useEffect, useRef, useState, useCallback, useMemo, createContext, useContext } from "react";
import { ConfirmDialog } from "./components/confirm-dialog";
import { DonateConsentDialog } from "./components/donate-consent-dialog";
import { ResizeHandle } from "./components/resize-handle";
import { SessionList, type ViewMode } from "./components/session/session-list";
import { SessionView } from "./components/session/session-view";
import { SharedSessionView } from "./components/session/shared-session-view";
import { RecommendationView } from "./components/personalization/recommendation-results-view";
import { UploadDialog } from "./components/upload/upload-dialog";
import { DashboardView } from "./components/dashboard/dashboard-view";
import { FrictionPanel } from "./components/friction/friction-panel";
import { PersonalizationPanel } from "./components/personalization/personalization-panel";
import { SettingsDialog } from "./components/settings-dialog";
import { Tooltip } from "./components/tooltip";
import { RecommendationWelcomeDialog } from "./components/recommendation-welcome-dialog";
import { SpotlightTour } from "./components/tutorial/spotlight-tour";
import { hasSeenTour } from "./components/tutorial/tour-steps";
import type { DashboardStats, DonateResult, ToolUsageStat, Trajectory } from "./types";

type MainView = "browse" | "analyze" | "friction" | "skills";

type AppMode = "self" | "demo";

type DialogState =
  | { kind: "hidden" }
  | { kind: "donate-confirm" }
  | { kind: "donating" }
  | { kind: "donate-result"; result: DonateResult };

interface AppContextValue {
  sessionToken: string;
  appMode: AppMode;
  maxZipBytes: number;
  maxSessions: number;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
}

const DEFAULT_MAX_ZIP_BYTES = 500 * 1024 * 1024;
const DEFAULT_MAX_SESSIONS = 30;

const AppContext = createContext<AppContextValue>({
  sessionToken: "",
  appMode: "self",
  maxZipBytes: DEFAULT_MAX_ZIP_BYTES,
  maxSessions: DEFAULT_MAX_SESSIONS,
  fetchWithToken: (url, init) => fetch(url, init),
});

export function useAppContext(): AppContextValue {
  return useContext(AppContext);
}

export function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<Trajectory[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [projects, setProjects] = useState<string[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("session") || null;
  });
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [dialog, setDialog] = useState<DialogState>({ kind: "hidden" });
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("project");
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [appMode, setAppMode] = useState<AppMode>("self");
  const [maxZipBytes, setMaxZipBytes] = useState(DEFAULT_MAX_ZIP_BYTES);
  const [maxSessions, setMaxSessions] = useState(DEFAULT_MAX_SESSIONS);
  const [agentFilter, setAgentFilter] = useState("all");
  const [mainView, setMainView] = useState<MainView>("browse");
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showRecWelcome, setShowRecWelcome] = useState(true);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [pendingScrollStepId, setPendingScrollStepId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("step") || null;
  });

  const [frictionJobId, setFrictionJobId] = useState<string | null>(null);
  const [skillJobId, setSkillJobId] = useState<string | null>(null);

  // Detect ?share={token} in URL for shared session viewing
  const [shareToken] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("share");
  });

  const [recommendationId, setRecommendationId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("recommendation") || null;
  });


  const SESSION_TOKEN_KEY = "vibelens-session-token";
  const [sessionToken] = useState(() => {
    const stored = localStorage.getItem(SESSION_TOKEN_KEY);
    if (stored) return stored;
    const token =
      crypto.randomUUID?.() ??
      Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
    localStorage.setItem(SESSION_TOKEN_KEY, token);
    return token;
  });

  const MIN_SIDEBAR_WIDTH = 240;
  const MAX_SIDEBAR_WIDTH = 600;

  const fetchWithToken = useCallback(
    (url: string, init?: RequestInit): Promise<Response> => {
      const headers = new Headers(init?.headers);
      headers.set("X-Session-Token", sessionToken);
      return fetch(url, { ...init, headers });
    },
    [sessionToken]
  );

  const contextValue: AppContextValue = {
    sessionToken,
    appMode,
    maxZipBytes,
    maxSessions,
    fetchWithToken,
  };

  const handleSidebarResize = useCallback((delta: number) => {
    setSidebarWidth((w) =>
      Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, w + delta))
    );
  }, []);

  // Fetch app mode on mount
  useEffect(() => {
    fetchWithToken("/api/settings")
      .then((r) => r.json())
      .then((data: { app_mode?: string; max_zip_bytes?: number; max_sessions?: number }) => {
        if (data.app_mode === "demo") setAppMode("demo");
        if (data.max_zip_bytes) setMaxZipBytes(data.max_zip_bytes);
        if (data.max_sessions) setMaxSessions(data.max_sessions);
        setSettingsLoaded(true);
      })
      .catch((err) => {
        console.error("Failed to load settings:", err);
        setSettingsLoaded(true);
      });
  }, [fetchWithToken]);

  // Show spotlight tour on first visit
  useEffect(() => {
    if (!settingsLoaded) return;
    if (hasSeenTour()) return;
    setShowOnboarding(true);
  }, [settingsLoaded]);


  useEffect(() => {
    fetchWithToken("/api/projects")
      .then((r) => r.json())
      .then((data: string[]) => setProjects(data))
      .catch((err) => console.error("Failed to load projects:", err));
  }, [fetchWithToken, refreshKey]);

  useEffect(() => {
    setSessionsLoading(true);
    fetchWithToken(`/api/sessions?refresh=true`)
      .then((r) => r.json())
      .then((data: Trajectory[]) => {
        setSessions(data);
        if (!selectedSessionId && data.length > 0) {
          setSelectedSessionId(data[0].session_id);
        }
      })
      .catch((err) => console.error("Failed to load sessions:", err))
      .finally(() => setSessionsLoading(false));
  }, [refreshKey, fetchWithToken]);

  // Derive unique agent names from loaded sessions
  const availableAgents = useMemo(() => {
    const names = new Set<string>();
    for (const s of sessions) {
      if (s.agent?.name) names.add(s.agent.name);
    }
    return [...names].sort();
  }, [sessions]);

  // Preload dashboard data after session list loads to avoid blocking it
  const [dashboardCache, setDashboardCache] = useState<{
    stats: DashboardStats;
    toolUsage: ToolUsageStat[];
  } | null>(null);
  const dashboardPreloaded = useRef(false);

  // Reset dashboard preload when data changes (e.g., after upload)
  useEffect(() => {
    if (refreshKey === 0) return;
    dashboardPreloaded.current = false;
    setDashboardCache(null);
  }, [refreshKey]);

  useEffect(() => {
    if (sessions.length === 0 || dashboardPreloaded.current) return;
    dashboardPreloaded.current = true;

    // Fetch stats first (fast, from metadata) so dashboard renders immediately.
    // Tool usage loads all sessions and arrives later.
    fetchWithToken("/api/analysis/dashboard")
      .then((r) => (r.ok ? r.json() : null))
      .then((stats: DashboardStats | null) => {
        if (stats) setDashboardCache({ stats, toolUsage: [] });
      })
      .catch((err) => console.error("Failed to preload dashboard:", err));

    fetchWithToken("/api/analysis/tool-usage")
      .then((r) => (r.ok ? r.json() : []))
      .then((toolUsage: ToolUsageStat[]) => {
        setDashboardCache((prev) =>
          prev ? { ...prev, toolUsage } : null
        );
      })
      .catch(() => {});
  }, [fetchWithToken, sessions]);

  const handleSelectSession = useCallback((id: string | null) => {
    setSelectedSessionId(id);
    if (id) setMainView("browse");
  }, []);


  const handleDownloadClick = async () => {
    if (checkedIds.size === 0) return;
    try {
      const res = await fetchWithToken("/api/sessions/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: [...checkedIds] }),
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "vibelens-export.zip";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed:", err);
    }
  };

  const handleDonateClick = () => {
    if (checkedIds.size === 0) return;
    setDialog({ kind: "donate-confirm" });
  };

  const handleDonateConfirm = useCallback(async () => {
    setDialog({ kind: "donating" });
    try {
      const res = await fetchWithToken("/api/sessions/donate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: [...checkedIds] }),
      });
      if (!res.ok) {
        let errorMsg = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          errorMsg = body.detail || JSON.stringify(body);
        } catch {
          errorMsg = await res.text().catch(() => errorMsg);
        }
        setDialog({
          kind: "donate-result",
          result: {
            total: checkedIds.size,
            donated: 0,
            donation_id: null,
            errors: [{ session_id: "", error: errorMsg }],
          },
        });
        return;
      }
      const result: DonateResult = await res.json();
      setDialog({ kind: "donate-result", result });
    } catch (err) {
      setDialog({
        kind: "donate-result",
        result: {
          total: checkedIds.size,
          donated: 0,
          donation_id: null,
          errors: [{ session_id: "", error: String(err) }],
        },
      });
    }
  }, [checkedIds, fetchWithToken]);

  const handleDialogClose = () => {
    if (dialog.kind === "donate-result" && dialog.result.donated > 0) {
      setCheckedIds(new Set());
    }
    setDialog({ kind: "hidden" });
  };

  const renderDialog = () => {
    switch (dialog.kind) {
      case "donate-confirm":
        return (
          <DonateConsentDialog
            sessionCount={checkedIds.size}
            onConfirm={handleDonateConfirm}
            onCancel={handleDialogClose}
          />
        );
      case "donating":
        return (
          <ConfirmDialog
            title="Donating..."
            message={`Donating ${checkedIds.size} session${checkedIds.size !== 1 ? "s" : ""}...`}
            onConfirm={() => {}}
            onCancel={() => {}}
            loading
          />
        );
      case "donate-result": {
        const dr = dialog.result;
        const hasDonateErrors = dr.errors.length > 0;
        const donateLines = [
          `Donated: ${dr.donated}`,
          `Total: ${dr.total}`,
        ];
        if (dr.donation_id) {
          donateLines.push("");
          donateLines.push(`Donation ID: ${dr.donation_id}`);
          donateLines.push(`Session Token: ${sessionToken}`);
        }
        if (hasDonateErrors) {
          donateLines.push("");
          donateLines.push(`Errors: ${dr.errors.length}`);
          for (const e of dr.errors.slice(0, 3)) {
            donateLines.push(`  ${e.session_id || "(unknown)"}: ${e.error}`);
          }
        }
        return (
          <ConfirmDialog
            title={hasDonateErrors ? "Completed with errors" : "Donation complete"}
            message={donateLines.join("\n")}
            confirmLabel="OK"
            cancelLabel="Close"
            onConfirm={handleDialogClose}
            onCancel={handleDialogClose}
          />
        );
      }
      default:
        return null;
    }
  };

  // Share mode: render shared session view without sidebar
  if (shareToken) {
    return (
      <AppContext.Provider value={contextValue}>
        <div className="flex flex-col h-full overflow-hidden bg-canvas text-primary">
          <div className="shrink-0 flex items-center justify-between px-4 py-2 bg-accent-violet-subtle border-b border-violet-200 dark:border-violet-700/40">
            <div className="flex items-center gap-2">
              <Share2 className="w-4 h-4 text-accent-violet" />
              <span className="text-sm text-accent-violet font-medium">Shared session</span>
            </div>
            <div className="flex items-center gap-2">
              <a href="https://github.com/CHATS-lab/VibeLens" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 hover:bg-control/30 rounded px-1 -mx-1 transition">
                <img src="/logo.svg" alt="VibeLens" className="w-6 h-6" />
                <span className="text-sm font-bold text-accent-cyan">VibeLens</span>
              </a>
            </div>
          </div>
          <div className="flex-1 min-h-0">
            <SharedSessionView shareToken={shareToken} />
          </div>
        </div>
      </AppContext.Provider>
    );
  }

  if (recommendationId) {
    const handleRecBack = () => {
      setRecommendationId(null);
      const url = new URL(window.location.href);
      url.searchParams.delete("recommendation");
      window.history.replaceState({}, "", url.toString());
    };
    return (
      <AppContext.Provider value={contextValue}>
        <div className="flex flex-col h-full overflow-hidden bg-canvas text-primary">
          <div className="px-6 pt-4 shrink-0">
            <button
              onClick={handleRecBack}
              className="flex items-center gap-1.5 text-sm text-dimmed hover:text-secondary transition-colors"
            >
              <span>&larr;</span> Back to sessions
            </button>
          </div>
          <RecommendationView analysisId={recommendationId} fetchWithToken={fetchWithToken} />
        </div>
      </AppContext.Provider>
    );
  }

  return (
    <AppContext.Provider value={contextValue}>
      <div className="flex h-full overflow-hidden bg-canvas text-primary">
        {/* Sidebar */}
        {sidebarOpen && (
          <aside
            style={{ width: sidebarWidth }}
            className="relative border-r border-default flex flex-col shrink-0 bg-panel"
          >
            <ResizeHandle side="left" onResize={handleSidebarResize} />
            <div data-tour="sidebar-header" className="flex items-center justify-between px-4 h-[75px] border-b border-default sticky top-0">
              <div className="flex items-center gap-3">
                <a href="https://github.com/CHATS-lab/VibeLens" target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 hover:bg-control/30 rounded px-1 -mx-1 transition">
                  <img src="/logo.svg" alt="VibeLens" className="w-12 h-12" />
                  <h1 className="text-2xl font-bold text-accent-cyan">VibeLens</h1>
                </a>
              </div>
              <div className="flex items-center gap-0.5">
                <Tooltip text="Refresh sessions">
                  <button
                    onClick={() => setRefreshKey((k) => k + 1)}
                    disabled={sessionsLoading}
                    className="p-1.5 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition disabled:opacity-50"
                  >
                    <RefreshCw className={`w-4 h-4 ${sessionsLoading ? "animate-spin" : ""}`} />
                  </button>
                </Tooltip>
                <Tooltip text="Collapse sidebar">
                  <button
                    onClick={() => setSidebarOpen(false)}
                    className="p-1.5 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
                  >
                    <PanelLeftClose className="w-4 h-4" />
                  </button>
                </Tooltip>
              </div>
            </div>

            <SessionList
              sessions={sessions}
              selectedId={selectedSessionId}
              onSelect={handleSelectSession}
              checkedIds={checkedIds}
              onCheckedChange={setCheckedIds}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              agentFilter={agentFilter}
              onAgentFilterChange={setAgentFilter}
              availableAgents={availableAgents}
              onUpload={appMode === "demo" ? () => setShowUploadDialog(true) : undefined}
              onDonate={handleDonateClick}
              donateDisabled={checkedIds.size === 0 || (appMode === "demo" && !sessions.some(s => checkedIds.has(s.session_id) && s._upload_id))}
              donateTooltip={
                checkedIds.size === 0
                  ? "Select sessions first to donate"
                  : appMode === "demo" && !sessions.some(s => checkedIds.has(s.session_id) && s._upload_id)
                    ? "Example sessions cannot be donated"
                    : undefined
              }
              onDownload={handleDownloadClick}
              downloadDisabled={checkedIds.size === 0}
              checkedCount={checkedIds.size}
              loading={sessionsLoading}
              isDemo={appMode === "demo"}
            />
          </aside>
        )}

        {/* Main Content */}
        <main className="flex-1 flex flex-col min-w-0 bg-canvas">
          {/* View Toggle */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-default bg-panel shadow-sm shadow-shadow">
            <div className="flex items-center gap-2">
              {!sidebarOpen && (
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="p-1.5 mr-1 text-dimmed hover:text-secondary bg-control hover:bg-control-hover border border-card rounded transition"
                >
                  <Menu className="w-4 h-4" />
                </button>
              )}
              <Tooltip text="Browse individual agent sessions step by step.">
                <button
                  data-tour="conversation-tab"
                  onClick={() => setMainView("browse")}
                  className={`min-w-[100px] text-center px-4 py-1.5 text-sm font-semibold rounded-md transition ${
                    mainView === "browse"
                      ? "bg-control/70 text-primary"
                      : "text-muted hover:text-secondary hover:bg-control/40"
                  }`}
                >
                  Conversation
                </button>
              </Tooltip>
              <Tooltip text="Stats across all sessions: usage, tools, and costs.">
                <button
                  data-tour="dashboard-tab"
                  onClick={() => setMainView("analyze")}
                  className={`min-w-[100px] text-center px-4 py-1.5 text-sm font-semibold rounded-md transition ${
                    mainView === "analyze"
                      ? "bg-control/70 text-primary"
                      : "text-muted hover:text-secondary hover:bg-control/40"
                  }`}
                >
                  Dashboard
                </button>
              </Tooltip>
              <Tooltip text="Create reusable skills from your coding patterns. Requires LLM call.">
                <button
                  data-tour="personalization-tab"
                  onClick={() => setMainView("skills")}
                  className={`min-w-[100px] text-center px-4 py-1.5 text-sm font-semibold rounded-md transition ${
                    mainView === "skills"
                      ? "bg-control/70 text-primary"
                      : "text-muted hover:text-secondary hover:bg-control/40"
                  }`}
                >
                  Personalization
                </button>
              </Tooltip>
              <Tooltip text="Spot wasted effort and get improvement tips. Requires LLM call.">
                <button
                  data-tour="productivity-tips-tab"
                  onClick={() => setMainView("friction")}
                  className={`min-w-[100px] text-center px-4 py-1.5 text-sm font-semibold rounded-md transition ${
                    mainView === "friction"
                      ? "bg-control/70 text-primary"
                      : "text-muted hover:text-secondary hover:bg-control/40"
                  }`}
                >
                  Productivity Tips
                </button>
              </Tooltip>
            </div>
            <Tooltip text="Settings">
              <button
                data-tour="settings-button"
                onClick={() => setShowSettingsDialog(true)}
                className="p-1.5 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
              >
                <Settings className="w-6 h-6" />
              </button>
            </Tooltip>
          </div>

          {/* Content Area */}
          <div className="flex-1 min-h-0 relative">
            {mainView === "skills" ? (
              <PersonalizationPanel checkedIds={checkedIds} activeJobId={skillJobId} onJobIdChange={setSkillJobId} />
            ) : mainView === "friction" ? (
              <FrictionPanel checkedIds={checkedIds} activeJobId={frictionJobId} onJobIdChange={setFrictionJobId} />
            ) : mainView === "analyze" ? (
              <DashboardView key={refreshKey} cache={dashboardCache} />
            ) : selectedSessionId ? (
              <SessionView
                sessionId={selectedSessionId}
                onNavigateSession={handleSelectSession}
                allSessions={sessions}
                pendingScrollStepId={pendingScrollStepId}
                onScrollComplete={() => setPendingScrollStepId(null)}
              />
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <div className="text-5xl mb-4 opacity-50">✨</div>
                  <p className="text-lg font-medium text-secondary mb-1">
                    Welcome to VibeLens
                  </p>
                  <p className="text-sm text-dimmed mb-6">
                    Select a session from the sidebar to explore agent
                    conversations
                  </p>
                  <div className="text-xs text-faint">
                    <p>{sessions.length} sessions loaded</p>
                    <p>{projects.length} projects available</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>

        {/* Dialog overlay */}
        {renderDialog()}

        {/* Upload dialog */}
        {showUploadDialog && (
          <UploadDialog
            onClose={() => setShowUploadDialog(false)}
            onComplete={() => setRefreshKey((k) => k + 1)}
          />
        )}

        {/* Settings dialog */}
        {showSettingsDialog && (
          <SettingsDialog
            onClose={() => setShowSettingsDialog(false)}
            onShowOnboarding={() => {
              setShowSettingsDialog(false);
              setShowOnboarding(true);
            }}
          />
        )}

        {showOnboarding && (
          <SpotlightTour appMode={appMode} onComplete={() => setShowOnboarding(false)} />
        )}

        {showRecWelcome && (
          <RecommendationWelcomeDialog
            onTryNow={() => {
              setShowRecWelcome(false);
              localStorage.setItem("vibelens-personalization-tab", "retrieve");
              setMainView("skills");
            }}
            onDismiss={() => setShowRecWelcome(false)}
          />
        )}
      </div>
    </AppContext.Provider>
  );
}

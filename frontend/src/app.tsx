import {
  Menu,
  PanelLeftClose,
  RefreshCw,
  Settings,
  Share2,
} from "lucide-react";
import { lazy, Suspense, useEffect, useRef, useState, useCallback, useMemo, createContext, useContext } from "react";
import { createExtensionsClient, type ExtensionsClient } from "./api/extensions";
import { donationClient } from "./api/donation";
import { ConfirmDialog } from "./components/ui/confirm-dialog";
import { DonationConsentDialog } from "./components/donation/donation-consent-dialog";
import { DonationResultDialog } from "./components/donation/donation-result-dialog";
import { DonationHistoryDialog } from "./components/donation/donation-history-dialog";
import { ResizeHandle } from "./components/ui/resize-handle";
import { SessionList, type ViewMode } from "./components/session/session-list";
import { LoadingSpinner } from "./components/ui/loading-spinner";
import { UploadDialog } from "./components/upload/upload-dialog";
import { SettingsDialog } from "./components/settings-dialog";

// Heavy route-level views. Code-split so the initial bundle only loads what
// the user lands on (session list + browse). Analysis panels pull in markdown,
// syntax highlighting, and domain-specific chart code.
const SessionView = lazy(() =>
  import("./components/session/session-view").then((m) => ({ default: m.SessionView })),
);
const SharedSessionView = lazy(() =>
  import("./components/session/shared-session-view").then((m) => ({ default: m.SharedSessionView })),
);
const DashboardView = lazy(() =>
  import("./components/dashboard/dashboard-view").then((m) => ({ default: m.DashboardView })),
);
const FrictionPanel = lazy(() =>
  import("./components/friction/friction-panel").then((m) => ({ default: m.FrictionPanel })),
);
const PersonalizationPanel = lazy(() =>
  import("./components/personalization/personalization-panel").then((m) => ({
    default: m.PersonalizationPanel,
  })),
);
import { Tooltip } from "./components/ui/tooltip";
import { RecommendationWelcomeDialog, shouldShowRecWelcome } from "./components/recommendation-welcome-dialog";
import { SpotlightTour } from "./components/tutorial/spotlight-tour";
import { hasSeenTour } from "./components/tutorial/tour-steps";
import type { DashboardStats, DonateResult, ToolUsageStat, Trajectory } from "./types";

type MainView = "browse" | "analyze" | "friction" | "skills";

type AppMode = "self" | "demo";

type DialogReturnTo = "hidden" | "donate-confirm";

type DialogState =
  | { kind: "hidden" }
  | { kind: "donate-confirm" }
  | { kind: "donating" }
  | { kind: "donate-result"; result: DonateResult }
  | { kind: "donation-history"; returnTo: DialogReturnTo };

interface AppContextValue {
  sessionToken: string;
  appMode: AppMode;
  maxZipBytes: number;
  maxSessions: number;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  extensionsClient: ExtensionsClient;
  setSidebarOpen: (open: boolean) => void;
}

const DEFAULT_MAX_ZIP_BYTES = 500 * 1024 * 1024;
const DEFAULT_MAX_SESSIONS = 30;
const LAST_SESSION_ID_KEY = "vibelens.lastSessionId";

const defaultFetch = (url: string, init?: RequestInit) => fetch(url, init);
const AppContext = createContext<AppContextValue>({
  sessionToken: "",
  appMode: "self",
  maxZipBytes: DEFAULT_MAX_ZIP_BYTES,
  maxSessions: DEFAULT_MAX_SESSIONS,
  fetchWithToken: defaultFetch,
  extensionsClient: createExtensionsClient(defaultFetch),
  setSidebarOpen: () => {},
});

export function useAppContext(): AppContextValue {
  return useContext(AppContext);
}

export function useExtensionsClient(): ExtensionsClient {
  return useContext(AppContext).extensionsClient;
}

export function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<Trajectory[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [projects, setProjects] = useState<string[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("session") || localStorage.getItem(LAST_SESSION_ID_KEY) || null;
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
  const [skillsResetKey, setSkillsResetKey] = useState(0);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showRecWelcome, setShowRecWelcome] = useState(shouldShowRecWelcome);
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

  const extensionsClient = useMemo(
    () => createExtensionsClient(fetchWithToken),
    [fetchWithToken],
  );
  const donationApi = useMemo(() => donationClient(fetchWithToken), [fetchWithToken]);

  const contextValue: AppContextValue = {
    sessionToken,
    appMode,
    maxZipBytes,
    maxSessions,
    fetchWithToken,
    extensionsClient,
    setSidebarOpen,
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
    fetchWithToken(`/api/sessions`)
      .then((r) => r.json())
      .then((data: Trajectory[]) => {
        setSessions(data);
        setSelectedSessionId((prev) => {
          if (prev && data.some((s) => s.session_id === prev)) return prev;
          return data.length > 0 ? data[0].session_id : null;
        });
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
    if (id) {
      localStorage.setItem(LAST_SESSION_ID_KEY, id);
      setMainView("browse");
    } else {
      localStorage.removeItem(LAST_SESSION_ID_KEY);
    }
  }, []);


  const handleDownloadClick = async () => {
    if (checkedIds.size === 0) return;
    try {
      const blob = await donationApi.download([...checkedIds]);
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
      const result = await donationApi.donate([...checkedIds]);
      setDialog({ kind: "donate-result", result });
    } catch (err) {
      setDialog({
        kind: "donate-result",
        result: {
          total: checkedIds.size,
          donated: 0,
          donation_id: null,
          errors: [{ session_id: "", error: err instanceof Error ? err.message : String(err) }],
        },
      });
    }
  }, [checkedIds, donationApi]);

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
          <DonationConsentDialog
            sessionCount={checkedIds.size}
            onConfirm={handleDonateConfirm}
            onCancel={handleDialogClose}
            onShowHistory={() =>
              setDialog({ kind: "donation-history", returnTo: "donate-confirm" })
            }
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
      case "donate-result":
        return (
          <DonationResultDialog result={dialog.result} onClose={handleDialogClose} />
        );
      case "donation-history": {
        const returnTo = dialog.returnTo;
        return (
          <DonationHistoryDialog
            fetchWithToken={fetchWithToken}
            onClose={() => {
              if (returnTo === "donate-confirm") {
                setDialog({ kind: "donate-confirm" });
              } else {
                setDialog({ kind: "hidden" });
              }
            }}
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
            <Suspense fallback={<LoadingSpinner label="Loading shared session" />}>
              <SharedSessionView shareToken={shareToken} />
            </Suspense>
          </div>
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
                  onClick={() => {
                    if (mainView === "skills") {
                      setSkillsResetKey((k) => k + 1);
                    } else {
                      setMainView("skills");
                    }
                  }}
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
            <div className="flex items-center gap-1">
              <Tooltip text="GitHub repository">
                <a
                  href="https://github.com/CHATS-lab/VibeLens"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
                >
                  <svg className="w-5 h-5" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
                  </svg>
                </a>
              </Tooltip>
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
          </div>

          {/* Content Area */}
          <div className="flex-1 min-h-0 relative">
            <Suspense fallback={<LoadingSpinner />}>
            {mainView === "skills" ? (
              <PersonalizationPanel checkedIds={checkedIds} activeJobId={skillJobId} onJobIdChange={setSkillJobId} resetKey={skillsResetKey} />
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
            </Suspense>
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

import {
  Menu,
  PanelLeftClose,
  Settings,
  Share2,
} from "lucide-react";
import { useEffect, useRef, useState, useCallback, useMemo, createContext, useContext } from "react";
import { ConfirmDialog } from "./components/confirm-dialog";
import { DonateConsentDialog } from "./components/donate-consent-dialog";
import { ResizeHandle } from "./components/resize-handle";
import { SessionList, type ViewMode } from "./components/session-list";
import { SessionView } from "./components/conversation/session-view";
import { SharedSessionView } from "./components/conversation/shared-session-view";
import { UploadDialog } from "./components/upload-dialog";
import { DashboardView } from "./components/analysis/dashboard-view";
import { FrictionPanel } from "./components/analysis/friction-panel";
import { SkillsPanel } from "./components/skills/skills-panel";
import { SettingsDialog } from "./components/settings-dialog";
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
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
}

const DEFAULT_MAX_ZIP_BYTES = 500 * 1024 * 1024;

const AppContext = createContext<AppContextValue>({
  sessionToken: "",
  appMode: "self",
  maxZipBytes: DEFAULT_MAX_ZIP_BYTES,
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
  const [agentFilter, setAgentFilter] = useState("all");
  const [visibleAgents, setVisibleAgents] = useState<string[]>(["all"]);
  const [mainView, setMainView] = useState<MainView>("browse");
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [pendingScrollStepId, setPendingScrollStepId] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("step") || null;
  });

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

  const contextValue: AppContextValue = {
    sessionToken,
    appMode,
    maxZipBytes,
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
      .then((data: { app_mode?: string; max_zip_bytes?: number; visible_agents?: string[] }) => {
        if (data.app_mode === "demo") setAppMode("demo");
        if (data.max_zip_bytes) setMaxZipBytes(data.max_zip_bytes);
        if (data.visible_agents) setVisibleAgents(data.visible_agents);
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
        if (!selectedSessionId && data.length > 0) {
          setSelectedSessionId(data[0].session_id);
        }
      })
      .catch((err) => console.error("Failed to load sessions:", err))
      .finally(() => setSessionsLoading(false));
  }, [refreshKey, fetchWithToken]);

  // Derive unique agent names from loaded sessions, filtered by config
  const availableAgents = useMemo(() => {
    const names = new Set<string>();
    for (const s of sessions) {
      if (s.agent?.name) names.add(s.agent.name);
    }
    const sorted = [...names].sort();
    // If config restricts to specific agents, only show those
    const isAllVisible = visibleAgents.length === 1 && visibleAgents[0] === "all";
    if (isAllVisible) return sorted;
    return sorted.filter((name) => visibleAgents.includes(name));
  }, [sessions, visibleAgents]);

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

    Promise.all([
      fetchWithToken("/api/analysis/dashboard")
        .then((r) => (r.ok ? r.json() : null)),
      fetchWithToken("/api/analysis/tool-usage")
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
    ])
      .then(([stats, toolUsage]: [DashboardStats | null, ToolUsageStat[]]) => {
        if (stats) setDashboardCache({ stats, toolUsage });
      })
      .catch((err) => console.error("Failed to preload dashboard:", err));
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
        if (hasDonateErrors) {
          donateLines.push("");
          donateLines.push(`Errors: ${dr.errors.length}`);
          for (const e of dr.errors.slice(0, 3)) {
            donateLines.push(`  ${e.session_id || "—"}: ${e.error}`);
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
        <div className="flex flex-col h-full overflow-hidden bg-zinc-950 text-zinc-100">
          <div className="shrink-0 flex items-center justify-between px-4 py-2 bg-violet-900/30 border-b border-violet-700/50">
            <div className="flex items-center gap-2">
              <Share2 className="w-4 h-4 text-violet-400" />
              <span className="text-sm text-violet-300 font-medium">Shared session</span>
            </div>
            <div className="flex items-center gap-2">
              <img src="/icon.png" alt="VibeLens" className="w-6 h-6" />
              <span className="text-sm font-bold text-cyan-400">VibeLens</span>
            </div>
          </div>
          <div className="flex-1 min-h-0">
            <SharedSessionView shareToken={shareToken} />
          </div>
        </div>
      </AppContext.Provider>
    );
  }

  return (
    <AppContext.Provider value={contextValue}>
      <div className="flex h-full overflow-hidden bg-zinc-950 text-zinc-100">
        {/* Sidebar */}
        {sidebarOpen && (
          <aside
            style={{ width: sidebarWidth }}
            className="relative border-r border-zinc-800 flex flex-col shrink-0 bg-zinc-900"
          >
            <ResizeHandle side="left" onResize={handleSidebarResize} />
            <div data-tour="sidebar-header" className="flex items-center justify-between px-4 h-[75px] border-b border-zinc-800 sticky top-0">
              <div className="flex items-center gap-3">
                <img src="/icon.png" alt="VibeLens" className="w-12 h-12" />
                <h1 className="text-2xl font-bold text-cyan-400">VibeLens</h1>
              </div>
              <button
                onClick={() => setSidebarOpen(false)}
                className="text-zinc-500 hover:text-zinc-300 transition"
                title="Collapse sidebar"
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
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
              donateDisabled={checkedIds.size === 0 || !sessions.some(s => checkedIds.has(s.session_id) && s._upload_id)}
              donateTooltip={
                checkedIds.size === 0
                  ? "Select sessions first to donate"
                  : !sessions.some(s => checkedIds.has(s.session_id) && s._upload_id)
                    ? "Example sessions cannot be donated"
                    : undefined
              }
              onDownload={handleDownloadClick}
              downloadDisabled={checkedIds.size === 0}
              checkedCount={checkedIds.size}
              loading={sessionsLoading}
            />
          </aside>
        )}

        {/* Main Content */}
        <main className="flex-1 flex flex-col min-w-0 bg-zinc-950">
          {/* View Toggle */}
          <div className="flex items-center justify-between px-4 py-2 border-b-2 border-zinc-700/60 bg-zinc-900 shadow-sm shadow-black/30">
            <div className="flex items-center gap-2">
              {!sidebarOpen && (
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="p-1.5 mr-1 text-zinc-500 hover:text-zinc-300 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 rounded transition"
                  title="Expand sidebar"
                >
                  <Menu className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={() => setMainView("browse")}
                title="Browse individual agent sessions — view step-by-step conversation flow, tool calls, and observations"
                className={`min-w-[100px] text-center px-4 py-1.5 text-sm font-semibold rounded-md transition ${
                  mainView === "browse"
                    ? "bg-indigo-600/30 text-indigo-200 border border-indigo-400/40 shadow-sm shadow-indigo-900/40"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                }`}
              >
                Conversation
              </button>
              <button
                data-tour="dashboard-tab"
                onClick={() => setMainView("analyze")}
                title="Aggregate analytics dashboard — session stats, tool usage patterns, cost breakdown, and timeline charts"
                className={`min-w-[100px] text-center px-4 py-1.5 text-sm font-semibold rounded-md transition ${
                  mainView === "analyze"
                    ? "bg-cyan-600/30 text-cyan-200 border border-cyan-400/40 shadow-sm shadow-cyan-900/40"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                }`}
              >
                Dashboard
              </button>
              <div data-tour="ai-tabs" className="flex items-center gap-2">
                <button
                  onClick={() => setMainView("friction")}
                  title="Analyze sessions to find wasted effort, recurring mistakes, and actionable tips to improve your workflow"
                  className={`min-w-[100px] text-center px-4 py-1.5 text-sm font-semibold rounded-md transition ${
                    mainView === "friction"
                      ? "bg-amber-600/30 text-amber-200 border border-amber-400/40 shadow-sm shadow-amber-900/40"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                  }`}
                >
                  Productivity Tips
                </button>
                <button
                  onClick={() => setMainView("skills")}
                  title="View and manage personalized skills extracted from your sessions"
                  className={`min-w-[100px] text-center px-4 py-1.5 text-sm font-semibold rounded-md transition ${
                    mainView === "skills"
                      ? "bg-teal-600/30 text-teal-200 border border-teal-400/40 shadow-sm shadow-teal-900/40"
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                  }`}
                >
                  Personalization
                </button>
              </div>
            </div>
            <button
              data-tour="settings-button"
              onClick={() => setShowSettingsDialog(true)}
              className="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded transition"
              title="Settings"
            >
              <Settings className="w-6 h-6" />
            </button>
          </div>

          {/* Content Area */}
          <div className="flex-1 min-h-0 relative">
            {mainView === "skills" ? (
              <SkillsPanel checkedIds={checkedIds} />
            ) : mainView === "friction" ? (
              <FrictionPanel checkedIds={checkedIds} />
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
                  <p className="text-lg font-medium text-zinc-300 mb-1">
                    Welcome to VibeLens
                  </p>
                  <p className="text-sm text-zinc-500 mb-6">
                    Select a session from the sidebar to explore agent
                    conversations
                  </p>
                  <div className="text-xs text-zinc-600">
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
      </div>
    </AppContext.Provider>
  );
}

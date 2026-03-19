import {
  Menu,
  PanelLeftClose,
  Copy,
  Check,
  ChevronUp,
  ChevronDown,
  Download,
  FileUp,
  Heart,
} from "lucide-react";
import { useEffect, useState, useCallback, createContext, useContext } from "react";
import { ConfirmDialog } from "./components/confirm-dialog";
import { DonateConsentDialog } from "./components/donate-consent-dialog";
import { ResizeHandle } from "./components/resize-handle";
import { SessionList, type ViewMode } from "./components/session-list";
import { SessionView } from "./components/session-view";
import { UploadDialog } from "./components/upload-dialog";
import type { DonateResult, Trajectory } from "./types";
import { baseProjectName } from "./utils";

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
  const [projects, setProjects] = useState<string[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null
  );
  const [copied, setCopied] = useState(false);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [dialog, setDialog] = useState<DialogState>({ kind: "hidden" });
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("project");
  const [sidebarWidth, setSidebarWidth] = useState(320);
  const [appMode, setAppMode] = useState<AppMode>("self");
  const [maxZipBytes, setMaxZipBytes] = useState(DEFAULT_MAX_ZIP_BYTES);
  const [resolvedFirstMessage, setResolvedFirstMessage] = useState<string | null>(null);

  // Ephemeral token: new on every page load, never persisted
  const [sessionToken] = useState(() =>
    crypto.randomUUID?.() ??
    Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("")
  );

  const MIN_SIDEBAR_WIDTH = 240;
  const MAX_SIDEBAR_WIDTH = 600;
  const SESSIONS_PER_PAGE = 100;

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
      .then((data: { app_mode?: string; max_zip_bytes?: number }) => {
        if (data.app_mode === "demo") setAppMode("demo");
        if (data.max_zip_bytes) setMaxZipBytes(data.max_zip_bytes);
      })
      .catch((err) => console.error("Failed to load settings:", err));
  }, [fetchWithToken]);

  useEffect(() => {
    fetchWithToken("/api/projects")
      .then((r) => r.json())
      .then((data: string[]) => setProjects(data))
      .catch((err) => console.error("Failed to load projects:", err));
  }, [fetchWithToken, refreshKey]);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set("limit", String(SESSIONS_PER_PAGE));
    params.set("offset", String(page * SESSIONS_PER_PAGE));

    fetchWithToken(`/api/sessions?${params}`)
      .then((r) => r.json())
      .then((data: Trajectory[]) => setSessions(data))
      .catch((err) => console.error("Failed to load sessions:", err))
      .finally(() => setLoading(false));
  }, [page, refreshKey, fetchWithToken]);

  const selectedSession = sessions.find(
    (s) => s.session_id === selectedSessionId
  );

  const handleSelectSession = useCallback((id: string | null) => {
    setSelectedSessionId(id);
    setResolvedFirstMessage(null);
  }, []);

  const handleFirstMessageResolved = useCallback((msg: string) => {
    setResolvedFirstMessage(msg);
  }, []);

  const displayFirstMessage = resolvedFirstMessage || selectedSession?.first_message || "";

  const handleCopyResume = () => {
    if (!selectedSessionId) return;
    navigator.clipboard.writeText(`claude --resume ${selectedSessionId}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

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

  const isDemo = appMode === "demo";

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

  return (
    <AppContext.Provider value={contextValue}>
      <div className="flex h-screen overflow-hidden bg-zinc-950 text-zinc-100">
        {/* Sidebar */}
        {sidebarOpen && (
          <aside
            style={{ width: sidebarWidth }}
            className="relative border-r border-zinc-800 flex flex-col shrink-0 bg-zinc-900"
          >
            <ResizeHandle side="left" onResize={handleSidebarResize} />
            <div className="flex items-center justify-between px-4 h-[75px] border-b border-zinc-800 sticky top-0">
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

            {/* Toolbar */}
            <div className="shrink-0 border-b border-zinc-800 px-3 py-2.5 grid grid-cols-3 gap-2 text-xs text-zinc-400">
              <button
                onClick={() => setShowUploadDialog(true)}
                className="flex items-center justify-center gap-1.5 py-1.5 text-xs font-medium bg-violet-600 hover:bg-violet-500 text-white rounded transition"
                title="Upload conversation files"
              >
                <FileUp className="w-3.5 h-3.5" />
                Upload
              </button>
              <button
                onClick={handleDownloadClick}
                disabled={checkedIds.size === 0}
                className="flex items-center justify-center gap-1.5 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
                title="Download selected sessions as zip"
              >
                <Download className="w-3.5 h-3.5" />
                Download
              </button>
              <button
                onClick={handleDonateClick}
                disabled={checkedIds.size === 0}
                className="flex items-center justify-center gap-1.5 py-1.5 text-xs font-medium bg-rose-600 hover:bg-rose-500 text-white rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
                title="Donate selected sessions for research"
              >
                <Heart className="w-3.5 h-3.5" />
                Donate
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
            />

            {/* Footer: Session count + Pagination */}
            <div className="shrink-0 border-t border-zinc-800 px-3 py-2 flex items-center justify-between text-xs text-zinc-400">
              <span>{sessions.length} sessions</span>
              {viewMode === "time" && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setPage(Math.max(0, page - 1))}
                    disabled={page === 0 || loading}
                    className="p-1 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed rounded transition"
                    title="Previous page"
                  >
                    <ChevronUp className="w-4 h-4" />
                  </button>
                  <span className="px-1 text-xs">{page + 1}</span>
                  <button
                    onClick={() => setPage(page + 1)}
                    disabled={sessions.length < SESSIONS_PER_PAGE || loading}
                    className="p-1 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed rounded transition"
                    title="Next page"
                  >
                    <ChevronDown className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          </aside>
        )}

        {/* Main Content */}
        <main className="flex-1 flex flex-col min-w-0 bg-zinc-950">
          {/* Header */}
          <header className="flex items-center gap-3 px-6 h-[50px] border-b border-zinc-800 shrink-0 bg-zinc-900/50 backdrop-blur-sm">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="text-zinc-500 hover:text-zinc-300 transition"
                title="Expand sidebar"
              >
                <Menu className="w-4 h-4" />
              </button>
            )}

            {selectedSession ? (
              <>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200 truncate font-medium">
                    {displayFirstMessage || "Session"}
                  </p>
                  <p className="text-[10px] text-zinc-500 mt-0.5">
                    <span title={selectedSession.project_path || ""}>
                      {baseProjectName(selectedSession.project_path || "")}
                    </span>
                    {selectedSession.agent?.model_name &&
                      ` • ${selectedSession.agent.name}@${selectedSession.agent.model_name}`}
                  </p>
                </div>

                {!isDemo && (
                  <button
                    onClick={handleCopyResume}
                    className="flex items-center gap-1.5 text-[10px] text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded px-2.5 py-1.5 transition whitespace-nowrap shrink-0"
                    title="Copy resume command to clipboard"
                  >
                    {copied ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-green-400" />
                        Copied!
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        Resume
                      </>
                    )}
                  </button>
                )}
              </>
            ) : (
              <div className="text-xs text-zinc-500">
                Select a session to view
              </div>
            )}
          </header>

          {/* Content Area */}
          <div className="flex-1 min-h-0">
            {selectedSessionId ? (
              <SessionView sessionId={selectedSessionId} onFirstMessageResolved={handleFirstMessageResolved} />
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <div className="text-5xl mb-4 opacity-50">✨</div>
                  <p className="text-lg font-medium text-zinc-300 mb-1">
                    Welcome to VibeLens
                  </p>
                  <p className="text-sm text-zinc-500 mb-6">
                    Select a session from the sidebar to explore Claude Code
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
      </div>
    </AppContext.Provider>
  );
}

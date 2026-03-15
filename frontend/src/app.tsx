import {
  Menu,
  PanelLeftClose,
  Copy,
  Check,
  ChevronUp,
  ChevronDown,
  Upload,
} from "lucide-react";
import { useEffect, useState, useCallback } from "react";
import { ConfirmDialog } from "./components/confirm-dialog";
import { SessionList } from "./components/session-list";
import { SessionView } from "./components/session-view";
import type { PushResult, SessionSummary } from "./types";

type DialogState =
  | { kind: "hidden" }
  | { kind: "confirm" }
  | { kind: "pushing" }
  | { kind: "result"; result: PushResult };

export function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null
  );
  const [copied, setCopied] = useState(false);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [dialog, setDialog] = useState<DialogState>({ kind: "hidden" });

  const SESSIONS_PER_PAGE = 100;

  useEffect(() => {
    fetch("/api/projects")
      .then((r) => r.json())
      .then((data: string[]) => setProjects(data))
      .catch((err) => console.error("Failed to load projects:", err));
  }, []);

  useEffect(() => {
    setLoading(true);
    setPage(0);
  }, [selectedProject]);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (selectedProject) params.set("project_name", selectedProject);
    params.set("limit", String(SESSIONS_PER_PAGE));
    params.set("offset", String(page * SESSIONS_PER_PAGE));

    fetch(`/api/sessions?${params}`)
      .then((r) => r.json())
      .then((data: SessionSummary[]) => setSessions(data))
      .catch((err) => console.error("Failed to load sessions:", err))
      .finally(() => setLoading(false));
  }, [selectedProject, page]);

  const selectedSession = sessions.find(
    (s) => s.session_id === selectedSessionId
  );

  const handleCopyResume = () => {
    if (!selectedSessionId) return;
    navigator.clipboard.writeText(`claude --resume ${selectedSessionId}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCollectClick = () => {
    if (checkedIds.size === 0) return;
    setDialog({ kind: "confirm" });
  };

  const handlePushConfirm = useCallback(async () => {
    setDialog({ kind: "pushing" });
    try {
      const res = await fetch("/api/push/mongodb", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_ids: [...checkedIds],
          target: "mongodb",
        }),
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
          kind: "result",
          result: {
            total: checkedIds.size,
            uploaded: 0,
            skipped: 0,
            errors: [{ session_id: "", error: errorMsg }],
          },
        });
        return;
      }
      const result: PushResult = await res.json();
      setDialog({ kind: "result", result });
    } catch (err) {
      setDialog({
        kind: "result",
        result: {
          total: checkedIds.size,
          uploaded: 0,
          skipped: 0,
          errors: [{ session_id: "", error: String(err) }],
        },
      });
    }
  }, [checkedIds]);

  const handleDialogClose = () => {
    if (dialog.kind === "result" && dialog.result.uploaded > 0) {
      setCheckedIds(new Set());
    }
    setDialog({ kind: "hidden" });
  };

  const renderDialog = () => {
    switch (dialog.kind) {
      case "confirm":
        return (
          <ConfirmDialog
            title="Send to MongoDB"
            message={`Send ${checkedIds.size} session${checkedIds.size !== 1 ? "s" : ""} to MongoDB?\n\nExisting sessions will be skipped automatically.`}
            confirmLabel="Send"
            onConfirm={handlePushConfirm}
            onCancel={handleDialogClose}
          />
        );
      case "pushing":
        return (
          <ConfirmDialog
            title="Sending..."
            message={`Uploading ${checkedIds.size} session${checkedIds.size !== 1 ? "s" : ""} to MongoDB...`}
            onConfirm={() => {}}
            onCancel={() => {}}
            loading
          />
        );
      case "result": {
        const r = dialog.result;
        const hasErrors = r.errors.length > 0;
        const lines = [
          `Uploaded: ${r.uploaded}`,
          `Skipped: ${r.skipped}`,
          `Total: ${r.total}`,
        ];
        if (hasErrors) {
          lines.push("");
          lines.push(`Errors: ${r.errors.length}`);
          for (const e of r.errors.slice(0, 3)) {
            lines.push(`  ${e.session_id || "—"}: ${e.error}`);
          }
        }
        return (
          <ConfirmDialog
            title={hasErrors ? "Completed with errors" : "Upload complete"}
            message={lines.join("\n")}
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
    <div className="flex h-screen bg-zinc-950 text-zinc-100">
      {/* Sidebar */}
      {sidebarOpen && (
        <aside className="w-80 border-r border-zinc-800 flex flex-col shrink-0 bg-zinc-900">
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

          {/* Toolbar: Collect + Pagination */}
          <div className="shrink-0 border-b border-zinc-800 px-3 py-2.5 flex items-center justify-between text-xs text-zinc-400">
            <div className="flex items-center gap-2.5">
              <button
                onClick={handleCollectClick}
                disabled={checkedIds.size === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-cyan-600 hover:bg-cyan-500 text-white rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
                title="Send selected sessions to MongoDB"
              >
                <Upload className="w-3.5 h-3.5" />
                Collect ({checkedIds.size})
              </button>
              <span className="text-xs text-zinc-400">{sessions.length} sessions</span>
            </div>
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
          </div>

          <SessionList
            sessions={sessions}
            selectedId={selectedSessionId}
            onSelect={setSelectedSessionId}
            projects={projects}
            selectedProject={selectedProject}
            onProjectChange={(project) => {
              setSelectedProject(project);
              setPage(0);
              setSelectedSessionId(null);
            }}
            checkedIds={checkedIds}
            onCheckedChange={setCheckedIds}
          />
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
                  {selectedSession.first_message || "Session"}
                </p>
                <p className="text-[10px] text-zinc-500 mt-0.5">
                  {selectedSession.project_name}
                  {selectedSession.models?.length > 0 &&
                    ` • ${selectedSession.models.join(", ")}`}
                </p>
              </div>

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
            <SessionView sessionId={selectedSessionId} />
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
    </div>
  );
}

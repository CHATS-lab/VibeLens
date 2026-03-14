import { Menu, PanelLeftClose, Copy, Check, ChevronUp, ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { SessionList } from "./components/session-list";
import { SessionView } from "./components/session-view";
import type { SessionSummary } from "./types";

export function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);

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

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100">
      {/* Sidebar */}
      {sidebarOpen && (
        <aside className="w-80 border-r border-zinc-800 flex flex-col shrink-0 bg-zinc-900">
          <div className="flex items-center justify-between px-4 h-[50px] border-b border-zinc-800 sticky top-0">
            <div>
              <h1 className="text-sm font-bold text-cyan-400">VibeLens</h1>
              <p className="text-[10px] text-zinc-500">Claude Code Sessions</p>
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
            onSelect={setSelectedSessionId}
            projects={projects}
            selectedProject={selectedProject}
            onProjectChange={(project) => {
              setSelectedProject(project);
              setPage(0);
              setSelectedSessionId(null);
            }}
          />

          {/* Pagination */}
          <div className="border-t border-zinc-800 px-3 py-3 flex items-center justify-between text-xs text-zinc-400">
            <span>{sessions.length} sessions</span>
            <div className="flex gap-1">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0 || loading}
                className="p-1 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed rounded transition"
                title="Previous page"
              >
                <ChevronUp className="w-3.5 h-3.5" />
              </button>
              <span className="px-2 py-1">
                {page + 1}
              </span>
              <button
                onClick={() => setPage(page + 1)}
                disabled={sessions.length < SESSIONS_PER_PAGE || loading}
                className="p-1 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed rounded transition"
                title="Next page"
              >
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </div>
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
                  {selectedSession.first_message || "Session"}
                </p>
                <p className="text-[10px] text-zinc-500 mt-0.5">
                  {selectedSession.project_name} •{" "}
                  {selectedSession.message_count} messages
                  {selectedSession.models?.length > 0 &&
                    ` • ${selectedSession.models.join(", ")}`}
                </p>
              </div>

              <button
                onClick={handleCopyResume}
                className="flex items-center gap-1.5 text-[10px] text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded px-2.5 py-1.5 transition whitespace-nowrap"
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
            <div className="text-xs text-zinc-500">Select a session to view</div>
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
                  Select a session from the sidebar to explore Claude Code conversations
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
    </div>
  );
}

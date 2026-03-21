import {
  Search,
  CheckSquare,
  Square,
  MinusSquare,
  Clock,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  Bot,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { Trajectory } from "../types";
import { formatTime, truncate, baseProjectName } from "../utils";

export type ViewMode = "time" | "project";

interface SessionListProps {
  sessions: Trajectory[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  checkedIds: Set<string>;
  onCheckedChange: (ids: Set<string>) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  agentFilter: string;
  onAgentFilterChange: (agent: string) => void;
  availableAgents: string[];
}

export function SessionList({
  sessions,
  selectedId,
  onSelect,
  checkedIds,
  onCheckedChange,
  viewMode,
  onViewModeChange,
  agentFilter,
  onAgentFilterChange,
  availableAgents,
}: SessionListProps) {
  const [search, setSearch] = useState("");
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(
    new Set()
  );

  const filtered = sessions.filter((s) => {
    if (agentFilter !== "all" && s.agent?.name !== agentFilter) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (s.first_message || "").toLowerCase().includes(q) ||
      (s.project_path || "").toLowerCase().includes(q)
    );
  });

  const filteredIds = new Set(filtered.map((s) => s.session_id));
  const checkedInView = [...checkedIds].filter((id) => filteredIds.has(id));
  const allChecked =
    filtered.length > 0 && checkedInView.length === filtered.length;
  const someChecked = checkedInView.length > 0 && !allChecked;

  const groupedByProject = useMemo(() => {
    const groups = new Map<string, Trajectory[]>();
    for (const session of filtered) {
      const key = session.project_path || "Unknown";
      const list = groups.get(key) || [];
      list.push(session);
      groups.set(key, list);
    }
    return groups;
  }, [filtered]);

  const handleSetViewMode = (mode: ViewMode) => {
    if (mode === "project" && viewMode !== "project") {
      setExpandedProjects(new Set());
    }
    onViewModeChange(mode);
  };

  const toggleProjectExpanded = (projectName: string) => {
    const next = new Set(expandedProjects);
    if (next.has(projectName)) {
      next.delete(projectName);
    } else {
      next.add(projectName);
    }
    setExpandedProjects(next);
  };

  const handleToggleAll = () => {
    if (allChecked) {
      const next = new Set(checkedIds);
      for (const s of filtered) next.delete(s.session_id);
      onCheckedChange(next);
    } else {
      const next = new Set(checkedIds);
      for (const s of filtered) next.add(s.session_id);
      onCheckedChange(next);
    }
  };

  const handleToggleOne = (sessionId: string) => {
    const next = new Set(checkedIds);
    if (next.has(sessionId)) {
      next.delete(sessionId);
    } else {
      next.add(sessionId);
    }
    onCheckedChange(next);
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="p-3 space-y-2 border-b border-zinc-800">
        {/* View Mode Toggle */}
        <div className="flex gap-0.5 bg-zinc-800 rounded p-0.5">
          <button
            onClick={() => handleSetViewMode("project")}
            className={`flex-1 flex items-center justify-center gap-1.5 text-xs py-1.5 rounded transition ${
              viewMode === "project"
                ? "bg-zinc-700 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <FolderOpen className="w-3.5 h-3.5" />
            By Project
          </button>
          <button
            onClick={() => handleSetViewMode("time")}
            className={`flex-1 flex items-center justify-center gap-1.5 text-xs py-1.5 rounded transition ${
              viewMode === "time"
                ? "bg-zinc-700 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            By Time
          </button>
        </div>

        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
          <input
            type="text"
            placeholder="Search sessions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-zinc-800 text-zinc-200 text-sm rounded pl-7 pr-2 py-1.5 border border-zinc-700 focus:outline-none focus:border-cyan-600 placeholder:text-zinc-500"
          />
        </div>

        {/* Agent Filter */}
        {availableAgents.length > 0 && (
          <div className="relative">
            <Bot className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
            <select
              value={agentFilter}
              onChange={(e) => onAgentFilterChange(e.target.value)}
              className="w-full bg-zinc-800 text-zinc-200 text-xs rounded pl-7 pr-2 py-1.5 border border-zinc-700 focus:outline-none focus:border-cyan-600 appearance-none cursor-pointer"
            >
              <option value="all">All agents</option>
              {availableAgents.map((agent) => (
                <option key={agent} value={agent}>
                  {agent}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Select All */}
        <button
          onClick={handleToggleAll}
          className="flex items-center gap-1.5 text-[11px] text-zinc-400 hover:text-zinc-200 transition"
        >
          {allChecked ? (
            <CheckSquare className="w-3.5 h-3.5 text-cyan-400" />
          ) : someChecked ? (
            <MinusSquare className="w-3.5 h-3.5 text-cyan-400" />
          ) : (
            <Square className="w-3.5 h-3.5" />
          )}
          Select all ({filtered.length})
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {viewMode === "time" ? (
          filtered.map((session) => (
            <SessionRow
              key={session.session_id}
              session={session}
              selectedId={selectedId}
              checkedIds={checkedIds}
              onSelect={onSelect}
              onToggle={handleToggleOne}
            />
          ))
        ) : (
          Array.from(groupedByProject.entries()).map(
            ([projectName, projectSessions]) => {
              const projectIds = projectSessions.map((s) => s.session_id);
              const allProjectChecked = projectIds.every((id) =>
                checkedIds.has(id)
              );
              const someProjectChecked =
                !allProjectChecked &&
                projectIds.some((id) => checkedIds.has(id));
              const handleToggleProject = (e: React.MouseEvent) => {
                e.stopPropagation();
                const next = new Set(checkedIds);
                if (allProjectChecked) {
                  for (const id of projectIds) next.delete(id);
                } else {
                  for (const id of projectIds) next.add(id);
                }
                onCheckedChange(next);
              };
              return (
              <div key={projectName}>
                <div className="sticky top-0 z-10 w-full flex items-center gap-1 bg-zinc-900 border-b border-zinc-800 text-xs text-zinc-300">
                  <button
                    onClick={handleToggleProject}
                    className="shrink-0 pl-3 pr-1 py-2 text-zinc-500 hover:text-cyan-400 transition"
                    title={allProjectChecked ? "Deselect project" : "Select project"}
                  >
                    {allProjectChecked ? (
                      <CheckSquare className="w-3.5 h-3.5 text-cyan-400" />
                    ) : someProjectChecked ? (
                      <MinusSquare className="w-3.5 h-3.5 text-cyan-400" />
                    ) : (
                      <Square className="w-3.5 h-3.5" />
                    )}
                  </button>
                  <button
                    onClick={() => toggleProjectExpanded(projectName)}
                    className="flex-1 flex items-center gap-2 pr-3 py-2 hover:text-zinc-100 transition min-w-0"
                  >
                    {expandedProjects.has(projectName) ? (
                      <ChevronDown className="w-3.5 h-3.5 shrink-0" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 shrink-0" />
                    )}
                    <FolderOpen className="w-3.5 h-3.5 shrink-0 text-zinc-500" />
                    <span className="truncate font-medium" title={projectName}>
                      {baseProjectName(projectName)}
                    </span>
                    <span className="ml-auto text-zinc-500 shrink-0">
                      {projectSessions.length}
                    </span>
                  </button>
                </div>
                {expandedProjects.has(projectName) &&
                  projectSessions.map((session) => (
                    <SessionRow
                      key={session.session_id}
                      session={session}
                      selectedId={selectedId}
                      checkedIds={checkedIds}
                      onSelect={onSelect}
                      onToggle={handleToggleOne}
                    />
                  ))}
              </div>
              );
            })
        )}
      </div>
    </div>
  );
}

function SessionRow({
  session,
  selectedId,
  checkedIds,
  onSelect,
  onToggle,
}: {
  session: Trajectory;
  selectedId: string | null;
  checkedIds: Set<string>;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
}) {
  return (
    <div
      className={`flex items-start border-b border-zinc-800/50 transition-all duration-200 ${
        selectedId === session.session_id
          ? "bg-cyan-600/15 border-l-2 border-l-cyan-400"
          : "hover:bg-zinc-800/50 border-l-2 border-l-transparent"
      }`}
    >
      {/* Checkbox */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onToggle(session.session_id);
        }}
        className="shrink-0 px-2 pt-3 text-zinc-500 hover:text-cyan-400 transition"
      >
        {checkedIds.has(session.session_id) ? (
          <CheckSquare className="w-3.5 h-3.5 text-cyan-400" />
        ) : (
          <Square className="w-3.5 h-3.5" />
        )}
      </button>

      {/* Session content */}
      <button
        onClick={() => onSelect(session.session_id)}
        className="flex-1 text-left pr-3 py-2.5 min-w-0"
      >
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[10px] text-zinc-500 uppercase tracking-wide" title={session.project_path || ""}>
            {baseProjectName(session.project_path || "")}
          </span>
          <span className="text-[10px] text-zinc-500">
            {formatTime(session.timestamp ?? null)}
          </span>
        </div>
        <p className="text-xs text-zinc-300 line-clamp-2 leading-relaxed">
          {truncate(session.first_message || "", 120) || "Empty session"}
        </p>
      </button>
    </div>
  );
}

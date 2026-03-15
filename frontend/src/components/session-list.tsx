import { Search, CheckSquare, Square, MinusSquare } from "lucide-react";
import { useState } from "react";
import type { SessionSummary } from "../types";
import { formatTime, truncate } from "../utils";

interface SessionListProps {
  sessions: SessionSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  projects: string[];
  selectedProject: string;
  onProjectChange: (project: string) => void;
  checkedIds: Set<string>;
  onCheckedChange: (ids: Set<string>) => void;
}

export function SessionList({
  sessions,
  selectedId,
  onSelect,
  projects,
  selectedProject,
  onProjectChange,
  checkedIds,
  onCheckedChange,
}: SessionListProps) {
  const [search, setSearch] = useState("");

  const filtered = sessions.filter((s) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      s.first_message.toLowerCase().includes(q) ||
      s.project_name.toLowerCase().includes(q)
    );
  });

  const filteredIds = new Set(filtered.map((s) => s.session_id));
  const checkedInView = [...checkedIds].filter((id) => filteredIds.has(id));
  const allChecked =
    filtered.length > 0 && checkedInView.length === filtered.length;
  const someChecked = checkedInView.length > 0 && !allChecked;

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
    <div className="flex flex-col h-full">
      <div className="p-3 space-y-2 border-b border-zinc-800">
        <select
          value={selectedProject}
          onChange={(e) => onProjectChange(e.target.value)}
          className="w-full bg-zinc-800 text-zinc-200 text-sm rounded px-2 py-1.5 border border-zinc-700 focus:outline-none focus:border-cyan-600"
        >
          <option value="">All Projects</option>
          {projects.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
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
        {filtered.map((session) => (
          <div
            key={session.session_id}
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
                handleToggleOne(session.session_id);
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
                <span className="text-[10px] text-zinc-500 uppercase tracking-wide">
                  {session.project_name}
                </span>
                <span className="text-[10px] text-zinc-500">
                  {formatTime(session.timestamp)}
                </span>
              </div>
              <p className="text-xs text-zinc-300 line-clamp-2 leading-relaxed">
                {truncate(session.first_message, 120) || "Empty session"}
              </p>
            </button>
          </div>
        ))}
      </div>

    </div>
  );
}

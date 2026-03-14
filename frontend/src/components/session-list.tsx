import { Search } from "lucide-react";
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
}

export function SessionList({
  sessions,
  selectedId,
  onSelect,
  projects,
  selectedProject,
  onProjectChange,
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
      </div>
      <div className="flex-1 overflow-y-auto">
        {filtered.map((session) => (
          <button
            key={session.session_id}
            onClick={() => onSelect(session.session_id)}
            className={`w-full text-left px-3 py-2.5 border-b border-zinc-800/50 hover:bg-zinc-800/50 transition-colors ${
              selectedId === session.session_id ? "bg-cyan-700/20" : ""
            }`}
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
        ))}
      </div>
      <div className="px-3 py-2 border-t border-zinc-800 text-[10px] text-zinc-500">
        {filtered.length} session{filtered.length !== 1 ? "s" : ""}
      </div>
    </div>
  );
}

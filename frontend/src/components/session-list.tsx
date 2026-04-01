import {
  Search,
  CheckSquare,
  Square,
  MinusSquare,
  Clock,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Bot,
  SlidersHorizontal,
  Loader2,
  Link2,
  Heart,
  Download,
  ArrowLeftRight,
  ShieldCheck,
  FileUp,
  Check,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../app";
import type { Trajectory } from "../types";
import { formatTime, truncate, baseProjectName } from "../utils";
import { SearchOptionsDialog } from "./search-options-dialog";
import { Tooltip } from "./tooltip";
import { SESSIONS_PER_PAGE, SEARCH_DEBOUNCE_MS } from "../styles";

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
  onUpload?: () => void;
  onDonate?: () => void;
  donateDisabled?: boolean;
  donateTooltip?: string;
  onDownload?: () => void;
  downloadDisabled?: boolean;
  checkedCount?: number;
  loading?: boolean;
  isDemo?: boolean;
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
  onUpload,
  onDonate,
  donateDisabled,
  donateTooltip,
  onDownload,
  downloadDisabled,
  checkedCount = 0,
  loading,
  isDemo = false,
}: SessionListProps) {
  const { fetchWithToken } = useAppContext();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(
    new Set()
  );
  const [searchResults, setSearchResults] = useState<Set<string> | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showSearchOptions, setShowSearchOptions] = useState(false);
  const [searchSources, setSearchSources] = useState<Set<string>>(
    () => new Set(["user_prompts", "session_id"])
  );
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasAutoExpanded = useRef(false);

  const DEFAULT_SOURCES = new Set(["user_prompts", "session_id"]);
  const hasNonDefaultSources =
    searchSources.size !== DEFAULT_SOURCES.size ||
    ![...DEFAULT_SOURCES].every((s) => searchSources.has(s));

  const runSearch = useCallback(
    (query: string, sources: Set<string>) => {
      if (!query.trim()) {
        setSearchResults(null);
        setSearchLoading(false);
        return;
      }

      setSearchLoading(true);
      const params = new URLSearchParams({
        q: query.trim(),
        sources: [...sources].join(","),
      });

      fetchWithToken(`/api/sessions/search?${params}`)
        .then((r) => r.json())
        .then((ids: string[]) => setSearchResults(new Set(ids)))
        .catch((err) => {
          console.error("Search failed:", err);
          setSearchResults(null);
        })
        .finally(() => setSearchLoading(false));
    },
    [fetchWithToken]
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(
      () => runSearch(search, searchSources),
      SEARCH_DEBOUNCE_MS
    );
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [search, searchSources, runSearch]);

  // Reset pagination when filters or view mode change
  useEffect(() => {
    setPage(0);
  }, [agentFilter, viewMode, searchResults]);

  const filtered = sessions.filter((s) => {
    if (agentFilter !== "all" && s.agent?.name !== agentFilter) return false;
    if (!search) return true;
    if (searchResults !== null) return searchResults.has(s.session_id);
    // While search is pending, keep showing all to avoid flash
    return true;
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

  // Auto-expand first project on initial load
  useEffect(() => {
    if (hasAutoExpanded.current || groupedByProject.size === 0) return;
    const firstProject = groupedByProject.keys().next().value;
    if (firstProject) {
      setExpandedProjects(new Set([firstProject]));
      hasAutoExpanded.current = true;
    }
  }, [groupedByProject]);

  // Client-side pagination for "time" view
  const paginatedFiltered = useMemo(() => {
    if (viewMode !== "time") return filtered;
    const start = page * SESSIONS_PER_PAGE;
    return filtered.slice(start, start + SESSIONS_PER_PAGE);
  }, [filtered, viewMode, page]);

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
    <div data-tour="session-list" className="flex flex-col flex-1 min-h-0">
      <div className="p-3 space-y-2 border-b border-zinc-800">
        {/* Upload + Donate row */}
        {onUpload && onDonate ? (
          <div className="flex items-stretch gap-1.5">
            <button
              data-tour="upload-button"
              onClick={onUpload}
              className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-sm font-semibold bg-violet-600 hover:bg-violet-500 text-white rounded border border-violet-500 transition"
            >
              <FileUp className="w-3.5 h-3.5" />
              Upload
            </button>
            <div className="flex-1 min-w-0">
              <DonateButton onClick={onDonate} disabled={!!donateDisabled} tooltip={donateTooltip} />
            </div>
          </div>
        ) : onDonate ? (
          <DonateButton onClick={onDonate} disabled={!!donateDisabled} tooltip={donateTooltip} />
        ) : null}

        <div className="relative">
          {searchLoading ? (
            <Loader2 className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-cyan-400 animate-spin" />
          ) : (
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
          )}
          <input
            type="text"
            placeholder="Search sessions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-zinc-800 text-zinc-200 text-sm rounded pl-7 pr-8 py-1.5 border border-zinc-700 focus:outline-none focus:border-cyan-600 placeholder:text-zinc-500"
          />
          <button
            onClick={() => setShowSearchOptions(true)}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 text-zinc-500 hover:text-zinc-300 transition"
            title="Search options"
          >
            <div className="relative">
              <SlidersHorizontal className="w-3.5 h-3.5" />
              {hasNonDefaultSources && (
                <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-cyan-400 rounded-full" />
              )}
            </div>
          </button>
        </div>

        {showSearchOptions && (
          <SearchOptionsDialog
            sources={searchSources}
            onApply={setSearchSources}
            onClose={() => setShowSearchOptions(false)}
          />
        )}

        {/* Agent Filter */}
        {availableAgents.length > 0 && (
          <AgentFilterDropdown
            value={agentFilter}
            agents={availableAgents}
            onChange={onAgentFilterChange}
          />
        )}

        {/* Select All + View Mode Switch */}
        <div className="flex items-center justify-between">
          <button
            onClick={handleToggleAll}
            className="flex items-center gap-1.5 text-xs text-zinc-300 hover:text-zinc-100 transition"
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
          <Tooltip text={viewMode === "project" ? "Switch to time view" : "Switch to project view"}>
            <button
              onClick={() => handleSetViewMode(viewMode === "project" ? "time" : "project")}
              className="flex items-center justify-center gap-1 w-[90px] px-2 py-1 text-[11px] font-medium text-cyan-300 hover:text-cyan-200 bg-cyan-900/30 hover:bg-cyan-800/40 border border-cyan-700/40 rounded-md transition"
            >
              {viewMode === "project" ? (
                <FolderOpen className="w-3 h-3 shrink-0" />
              ) : (
                <Clock className="w-3 h-3 shrink-0" />
              )}
              {viewMode === "project" ? "Project" : "Time"}
              <ArrowLeftRight className="w-3 h-3 text-cyan-500/60" />
            </button>
          </Tooltip>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-500">
            <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
            <span className="text-sm">Loading sessions…</span>
          </div>
        ) : viewMode === "time" ? (
          paginatedFiltered.map((session) => (
            <SessionRow
              key={session.session_id}
              session={session}
              selectedId={selectedId}
              checkedIds={checkedIds}
              onSelect={onSelect}
              onToggle={handleToggleOne}
              showProject
              isDemo={isDemo}
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
                <div className="sticky top-0 z-10 w-full flex items-center gap-1 bg-zinc-900 border-b border-zinc-800 text-sm text-zinc-200">
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
                      showProject={false}
                      isDemo={isDemo}
                    />
                  ))}
              </div>
              );
            })
        )}
      </div>

      {/* Footer: filtered count + pagination + download */}
      <div className="shrink-0 border-t border-zinc-800 px-3 py-2 flex items-center justify-between text-xs text-zinc-400">
        <span>{filtered.length} sessions</span>
        <div className="flex items-center gap-2">
          {viewMode === "time" && filtered.length > SESSIONS_PER_PAGE && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="p-1 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed rounded transition"
                title="Previous page"
              >
                <ChevronUp className="w-4 h-4" />
              </button>
              <span className="px-1 text-xs">{page + 1}</span>
              <button
                onClick={() => setPage(page + 1)}
                disabled={(page + 1) * SESSIONS_PER_PAGE >= filtered.length}
                className="p-1 hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed rounded transition"
                title="Next page"
              >
                <ChevronDown className="w-4 h-4" />
              </button>
            </div>
          )}
          {onDownload && (
            <button
              onClick={onDownload}
              disabled={downloadDisabled}
              className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium bg-cyan-600/80 hover:bg-cyan-500 text-white rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
              title={downloadDisabled ? "Select sessions to download" : `Download ${checkedCount} session${checkedCount !== 1 ? "s" : ""}`}
            >
              <Download className="w-3 h-3" />
              {checkedCount > 0 ? checkedCount : "Download"}
            </button>
          )}
        </div>
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
  showProject,
  isDemo,
}: {
  session: Trajectory;
  selectedId: string | null;
  checkedIds: Set<string>;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  showProject: boolean;
  isDemo: boolean;
}) {
  return (
    <div
      className={`flex items-center border-b border-zinc-800/50 transition-all duration-200 ${
        selectedId === session.session_id
          ? "bg-cyan-600/15 border-l-2 border-l-cyan-400"
          : "hover:bg-zinc-800/50 border-l-2 border-l-transparent"
      }`}
    >
      {/* Checkbox — indented under project header chevron when nested */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onToggle(session.session_id);
        }}
        className={`shrink-0 pr-1 text-zinc-500 hover:text-cyan-400 transition ${
          showProject ? "pl-3" : "pl-8"
        }`}
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
        {showProject && (
          <div className="flex items-center justify-between mb-0.5 min-w-0">
            <span className="text-xs text-zinc-400 uppercase tracking-wide truncate" title={session.project_path || ""}>
              {baseProjectName(session.project_path || "")}
            </span>
            <div className="flex items-center gap-1 shrink-0 ml-2">
              {isDemo && !session._upload_id && (
                <span className="px-1 py-0.5 text-[9px] font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded" title="Example session (not donatable)">Example</span>
              )}
              {!!session.extra?._anonymized && (
                <span title="Session anonymized"><ShieldCheck className="w-3 h-3 text-emerald-400" /></span>
              )}
              {(session.last_trajectory_ref || session.continued_trajectory_ref || session.parent_trajectory_ref) && (
                <span title="Part of continuation chain"><Link2 className="w-3 h-3 text-violet-400" /></span>
              )}
              <span className="text-xs text-zinc-400 whitespace-nowrap">
                {formatTime(session.timestamp ?? null)}
              </span>
            </div>
          </div>
        )}
        <div className="flex items-center gap-2 min-w-0">
          <p className="text-sm text-zinc-200 truncate flex-1 min-w-0" title={session.first_message || ""}>
            {truncate(session.first_message || "", 120) || "Empty session"}
          </p>
          <div className="flex items-center gap-1 shrink-0">
            {!showProject && isDemo && !session._upload_id && (
              <span className="px-1 py-0.5 text-[9px] font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded" title="Example session (not donatable)">Example</span>
            )}
            {!showProject && !!session.extra?._anonymized && (
              <span title="Session anonymized"><ShieldCheck className="w-3 h-3 text-emerald-400" /></span>
            )}
            {!showProject && (session.last_trajectory_ref || session.continued_trajectory_ref || session.parent_trajectory_ref) && (
              <span title="Part of continuation chain"><Link2 className="w-3 h-3 text-violet-400" /></span>
            )}
            {!showProject && (
              <span className="text-xs text-zinc-400 whitespace-nowrap">
                {formatTime(session.timestamp ?? null)}
              </span>
            )}
          </div>
        </div>
      </button>
    </div>
  );
}

function AgentFilterDropdown({ value, agents, onChange }: { value: string; agents: string[]; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const options = [{ value: "all", label: "All agents" }, ...agents.map((a) => ({ value: a, label: a }))];
  const activeLabel = options.find((o) => o.value === value)?.label ?? "All agents";

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 bg-zinc-800 text-zinc-200 text-sm rounded px-2.5 py-1.5 border border-zinc-700 hover:border-zinc-600 transition cursor-pointer"
      >
        <Bot className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
        <span className="flex-1 text-left truncate">{activeLabel}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-zinc-500 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-zinc-800 border border-zinc-700 rounded-md shadow-xl overflow-hidden">
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full flex items-center gap-2 px-2.5 py-1.5 text-sm transition ${
                value === opt.value
                  ? "bg-cyan-600/20 text-cyan-200"
                  : "text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100"
              }`}
            >
              {value === opt.value ? (
                <Check className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              ) : (
                <span className="w-3.5 shrink-0" />
              )}
              <span className="truncate">{opt.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function DonateButton({ onClick, disabled, tooltip }: { onClick: () => void; disabled: boolean; tooltip?: string }) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => disabled && setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <button
        onClick={disabled ? undefined : onClick}
        className={`w-full flex items-center justify-center gap-1.5 py-1.5 text-sm font-semibold rounded border transition ${
          disabled
            ? "bg-rose-600/40 text-rose-200 border-rose-500/30 cursor-not-allowed opacity-60"
            : "bg-rose-600 hover:bg-rose-500 text-white border-rose-500 shadow-sm shadow-rose-900/40"
        }`}
      >
        <Heart className="w-3.5 h-3.5" />
        Donate Data
      </button>
      {showTooltip && tooltip && (
        <div className="absolute left-1/2 -translate-x-1/2 top-full mt-1.5 z-50 px-2.5 py-1.5 rounded-md bg-zinc-950 border border-zinc-700 text-[11px] text-zinc-300 whitespace-nowrap shadow-lg pointer-events-none">
          {tooltip}
        </div>
      )}
    </div>
  );
}

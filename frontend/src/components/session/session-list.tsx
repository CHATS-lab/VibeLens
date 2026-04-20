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
  SlidersHorizontal,
  Loader2,
  Download,
  ArrowLeftRight,
  FileUp,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import { sessionsClient } from "../../api/sessions";
import type { Trajectory } from "../../types";
import { baseProjectName } from "../../utils";
import { SearchOptionsDialog } from "./search-options-dialog";
import { Tooltip } from "../ui/tooltip";
import { SESSIONS_PER_PAGE, SEARCH_DEBOUNCE_MS } from "../../constants";
import { SessionRow } from "./session-row";
import { AgentFilterDropdown, DonateButton } from "./session-list-controls";

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
  const api = useMemo(() => sessionsClient(fetchWithToken), [fetchWithToken]);
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
      api
        .search(query.trim(), [...sources])
        .then((ids) => setSearchResults(new Set(ids)))
        .catch((err) => {
          console.error("Search failed:", err);
          setSearchResults(null);
        })
        .finally(() => setSearchLoading(false));
    },
    [api]
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
      <div className="p-3 space-y-2 border-b border-card">
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
            <Loader2 className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-accent-cyan animate-spin" />
          ) : (
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-dimmed" />
          )}
          <input
            type="text"
            placeholder="Search sessions..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-control text-secondary text-sm rounded pl-7 pr-8 py-1.5 border border-card focus:outline-none focus:border-accent-cyan-focus placeholder:text-dimmed"
          />
          <button
            onClick={() => setShowSearchOptions(true)}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
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
            className="flex items-center gap-1.5 text-xs text-secondary hover:text-primary hover:bg-control/50 rounded px-1.5 py-0.5 transition"
          >
            {allChecked ? (
              <CheckSquare className="w-3.5 h-3.5 text-accent-cyan" />
            ) : someChecked ? (
              <MinusSquare className="w-3.5 h-3.5 text-accent-cyan" />
            ) : (
              <Square className="w-3.5 h-3.5" />
            )}
            Select all ({filtered.length})
          </button>
          <Tooltip text={viewMode === "project" ? "Switch to time view" : "Switch to project view"}>
            <button
              onClick={() => handleSetViewMode(viewMode === "project" ? "time" : "project")}
              className="flex items-center justify-center gap-1 w-[90px] px-2 py-1 text-[11px] font-medium text-accent-cyan bg-accent-cyan-subtle hover:bg-accent-cyan-muted border border-accent-cyan-border rounded-md transition"
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
          <div className="flex flex-col items-center justify-center h-full gap-3 text-dimmed">
            <Loader2 className="w-6 h-6 animate-spin text-accent-cyan" />
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
                <div className="sticky top-0 z-10 w-full flex items-center gap-1 bg-panel border-b border-card text-sm text-secondary">
                  <button
                    onClick={handleToggleProject}
                    className="shrink-0 pl-3 pr-1 py-2 text-dimmed hover:text-accent-cyan hover:bg-control/40 rounded transition"
                  >
                    {allProjectChecked ? (
                      <CheckSquare className="w-3.5 h-3.5 text-accent-cyan" />
                    ) : someProjectChecked ? (
                      <MinusSquare className="w-3.5 h-3.5 text-accent-cyan" />
                    ) : (
                      <Square className="w-3.5 h-3.5" />
                    )}
                  </button>
                  <button
                    onClick={() => toggleProjectExpanded(projectName)}
                    className="flex-1 flex items-center gap-2 pr-3 py-2 hover:text-primary hover:bg-control/40 rounded transition min-w-0"
                  >
                    {expandedProjects.has(projectName) ? (
                      <ChevronDown className="w-3.5 h-3.5 shrink-0" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 shrink-0" />
                    )}
                    <FolderOpen className="w-3.5 h-3.5 shrink-0 text-dimmed" />
                    <span className="truncate font-medium" title={projectName}>
                      {baseProjectName(projectName)}
                    </span>
                    <span className="ml-auto text-dimmed shrink-0">
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
      <div className="shrink-0 border-t border-card px-3 py-2 flex items-center justify-between text-xs text-muted">
        <span>{filtered.length} sessions</span>
        <div className="flex items-center gap-2">
          {viewMode === "time" && filtered.length > SESSIONS_PER_PAGE && (
            <div className="flex items-center gap-1">
              <Tooltip text="Previous page">
                <button
                  onClick={() => setPage(Math.max(0, page - 1))}
                  disabled={page === 0}
                  className="p-1 hover:bg-control-hover disabled:opacity-50 disabled:cursor-not-allowed rounded transition"
                >
                  <ChevronUp className="w-4 h-4" />
                </button>
              </Tooltip>
              <span className="px-1 text-xs">{page + 1}</span>
              <Tooltip text="Next page">
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={(page + 1) * SESSIONS_PER_PAGE >= filtered.length}
                  className="p-1 hover:bg-control-hover disabled:opacity-50 disabled:cursor-not-allowed rounded transition"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </Tooltip>
            </div>
          )}
          {onDownload && (
            <Tooltip text={downloadDisabled ? "Select sessions to download" : `Download ${checkedCount} session${checkedCount !== 1 ? "s" : ""}`}>
              <button
                onClick={onDownload}
                disabled={downloadDisabled}
                className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium bg-cyan-600/80 hover:bg-cyan-500 text-white rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Download className="w-3 h-3" />
                {checkedCount > 0 ? checkedCount : "Download"}
              </button>
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  );
}

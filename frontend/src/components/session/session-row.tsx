import { CheckSquare, Square, ShieldCheck, Link2 } from "lucide-react";
import type { Trajectory } from "../../types";
import { formatTime, truncate, baseProjectName, tildifyPath } from "../../utils";

export interface SessionRowProps {
  session: Trajectory;
  selectedId: string | null;
  checkedIds: Set<string>;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  showProject: boolean;
  isDemo: boolean;
}

export function SessionRow({
  session,
  selectedId,
  checkedIds,
  onSelect,
  onToggle,
  showProject,
  isDemo,
}: SessionRowProps) {
  return (
    <div
      className={`flex items-center border-b border-card transition-all duration-200 ${
        selectedId === session.session_id
          ? "bg-control border-l-2 border-l-accent-cyan"
          : "hover:bg-control border-l-2 border-l-transparent"
      }`}
    >
      {/* Checkbox — indented under project header chevron when nested */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onToggle(session.session_id);
        }}
        className={`shrink-0 pr-1 py-1 text-dimmed hover:text-accent-cyan hover:bg-control/40 rounded transition ${
          showProject ? "pl-3" : "pl-8"
        }`}
      >
        {checkedIds.has(session.session_id) ? (
          <CheckSquare className="w-3.5 h-3.5 text-accent-cyan" />
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
            <span className="text-xs text-muted uppercase tracking-wide truncate" title={tildifyPath(session.project_path || "")}>
              {baseProjectName(session.project_path || "")}
            </span>
            <div className="flex items-center gap-1 shrink-0 ml-2">
              {isDemo && !session._upload_id && (
                <span className="px-1 py-0.5 text-[9px] font-medium bg-amber-500/20 text-accent-amber border border-amber-500/30 rounded" title="Example session (not donatable)">Example</span>
              )}
              {!!session.extra?._anonymized && (
                <span title="Session anonymized"><ShieldCheck className="w-3 h-3 text-accent-emerald" /></span>
              )}
              {(session.prev_trajectory_ref || session.next_trajectory_ref || session.parent_trajectory_ref) && (
                <span title="Part of continuation chain"><Link2 className="w-3 h-3 text-accent-violet" /></span>
              )}
              <span className="text-xs text-muted whitespace-nowrap">
                {formatTime(session.updated_at ?? null)}
              </span>
            </div>
          </div>
        )}
        <div className="flex items-center gap-2 min-w-0">
          <p className="text-sm text-secondary truncate flex-1 min-w-0" title={session.first_message || ""}>
            {truncate(session.first_message || "", 120) || "Empty session"}
          </p>
          <div className="flex items-center gap-1 shrink-0">
            {!showProject && isDemo && !session._upload_id && (
              <span className="px-1 py-0.5 text-[9px] font-medium bg-amber-500/20 text-accent-amber border border-amber-500/30 rounded" title="Example session (not donatable)">Example</span>
            )}
            {!showProject && !!session.extra?._anonymized && (
              <span title="Session anonymized"><ShieldCheck className="w-3 h-3 text-accent-emerald" /></span>
            )}
            {!showProject && (session.prev_trajectory_ref || session.next_trajectory_ref || session.parent_trajectory_ref) && (
              <span title="Part of continuation chain"><Link2 className="w-3 h-3 text-accent-violet" /></span>
            )}
            {!showProject && (
              <span className="text-xs text-muted whitespace-nowrap">
                {formatTime(session.updated_at ?? null)}
              </span>
            )}
          </div>
        </div>
      </button>
    </div>
  );
}

import { Hash, BarChart3 } from "lucide-react";
import type { ProjectDetail } from "../../types";
import { baseProjectName, formatTokens, formatCost } from "../../utils";

export const DEFAULT_PROJECT_COUNT = 10;

interface ProjectRowProps {
  project: string;
  count: number;
  detail: ProjectDetail | undefined;
  max: number;
  totalSessions: number;
  onClick: () => void;
  onHover: (e: React.MouseEvent, text: string) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

export function ProjectRow({
  project,
  count,
  detail,
  max,
  totalSessions,
  onClick,
  onHover,
  onMove,
  onLeave,
}: ProjectRowProps) {
  const pct = max > 0 ? (count / max) * 100 : 0;
  const name = baseProjectName(project);
  const tooltipLines = [
    name,
    `${count} session${count !== 1 ? "s" : ""}`,
    `${((count / totalSessions) * 100).toFixed(1)}% of total`,
  ];
  if (detail) {
    tooltipLines.push(
      `${detail.messages.toLocaleString()} messages`,
      `${formatTokens(detail.tokens)} tokens`,
      `${formatCost(detail.cost_usd)} est. cost`,
    );
  }

  return (
    <button
      onClick={onClick}
      className="flex flex-col gap-1 w-full text-left hover:bg-control/60 px-3 py-2 rounded-lg transition group"
      onMouseEnter={(e) => onHover(e, tooltipLines.join("\n"))}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      <div className="flex items-center justify-between w-full">
        <span
          className="text-[13px] text-secondary group-hover:text-primary transition-colors truncate max-w-[60%]"
          title={name}
        >
          {name}
        </span>
        <span className="text-[13px] text-secondary tabular-nums font-medium">
          {count} session{count !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="w-full h-1.5 bg-control/60 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      {detail && (
        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="inline-flex items-center gap-1">
            <Hash className="w-3 h-3 text-cyan-500" />
            {detail.messages.toLocaleString()} msgs
          </span>
          <span className="inline-flex items-center gap-1">
            <BarChart3 className="w-3 h-3 text-amber-500" />
            {formatTokens(detail.tokens)}
          </span>
          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
            {formatCost(detail.cost_usd)}
          </span>
        </div>
      )}
    </button>
  );
}

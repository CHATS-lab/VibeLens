import { BarChart3, DollarSign } from "lucide-react";
import type { Trajectory } from "../../types";
import { formatTokens, formatCost, formatDuration } from "../../utils";
import { Tooltip } from "../ui/tooltip";
import { SESSION_ID_SHORT, PREVIEW_SHORT } from "../../constants";

export function MetaPill({
  icon,
  label,
  color,
  bg,
  tooltip,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
  bg?: string;
  tooltip?: React.ReactNode;
  /** Optional click handler. Presence makes the pill a real button. */
  onClick?: (event: React.MouseEvent) => void;
}) {
  const bgClass = bg ?? "bg-control border border-card";
  const sharedClass = `inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] hover:bg-control-hover transition-colors ${bgClass} ${color}`;

  const pill = onClick ? (
    <button type="button" onClick={onClick} className={`${sharedClass} cursor-pointer`}>
      {icon}
      <span>{label}</span>
    </button>
  ) : (
    <span className={sharedClass}>
      {icon}
      <span>{label}</span>
    </span>
  );

  if (!tooltip) return pill;

  return <Tooltip text={tooltip}>{pill}</Tooltip>;
}

interface MetricsPillProps {
  cost: number | null;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  totalTokens: number;
  durationSeconds?: number | null;
}

/** Compact pill that surfaces the session's cost (or total tokens when cost is
 * unavailable) and reveals the full input/output/cache breakdown on hover.
 */
export function MetricsPill({
  cost,
  inputTokens,
  outputTokens,
  cacheReadTokens,
  cacheWriteTokens,
  totalTokens,
  durationSeconds,
}: MetricsPillProps) {
  const tooltip = (
    <div className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 text-left font-mono tabular-nums">
      {durationSeconds != null && (
        <>
          <span className="text-muted">Duration</span>
          <span className="text-cyan-700 dark:text-cyan-300">{formatDuration(durationSeconds)}</span>
        </>
      )}
      <span className="text-muted">Input</span>
      <span className="text-cyan-700 dark:text-cyan-300">{formatTokens(inputTokens)}</span>
      <span className="text-muted">Output</span>
      <span className="text-cyan-700 dark:text-cyan-300">{formatTokens(outputTokens)}</span>
      <span className="text-muted">Cache read</span>
      <span className="text-emerald-700 dark:text-emerald-300">{formatTokens(cacheReadTokens)}</span>
      <span className="text-muted">Cache write</span>
      <span className="text-violet-700 dark:text-violet-300">{formatTokens(cacheWriteTokens)}</span>
      <span className="text-muted">Total</span>
      <span className="text-amber-700 dark:text-amber-300">{formatTokens(totalTokens)}</span>
      {cost != null && (
        <>
          <span className="text-muted">Est. cost</span>
          <span className="text-emerald-700 dark:text-emerald-300">{formatCost(cost)}</span>
        </>
      )}
    </div>
  );

  const showCost = cost != null;
  const icon = showCost ? (
    <DollarSign className="w-3 h-3" />
  ) : (
    <BarChart3 className="w-3 h-3" />
  );
  // Strip the leading $ from formatCost — the DollarSign icon already carries the unit.
  const label = showCost ? formatCost(cost).replace(/\$/g, "") : formatTokens(totalTokens);
  const colorClass = showCost
    ? "text-emerald-700 dark:text-emerald-300"
    : "text-amber-700 dark:text-amber-300";

  return (
    <Tooltip text={tooltip}>
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-mono tabular-nums bg-control border border-card hover:bg-control-hover transition-colors ${colorClass}`}
      >
        {icon}
        <span>{label}</span>
      </span>
    </Tooltip>
  );
}

export function formatCreatedTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return timestamp;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function _lookupFirstMessage(sessionId: string, sessions?: Trajectory[]): string {
  if (!sessions) return sessionId.slice(0, SESSION_ID_SHORT);
  const match = sessions.find((s) => s.session_id === sessionId);
  if (!match?.first_message) return sessionId.slice(0, SESSION_ID_SHORT);
  const msg = match.first_message;
  if (msg.length <= PREVIEW_SHORT) return msg;
  return msg.slice(0, PREVIEW_SHORT) + "…";
}

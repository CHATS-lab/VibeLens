import { DollarSign } from "lucide-react";
import { useState } from "react";
import type { Trajectory } from "../../types";
import { formatTokens, formatCost } from "../../utils";
import { Tooltip } from "../ui/tooltip";
import { METRIC_LABEL } from "../../styles";
import { SESSION_ID_SHORT, PREVIEW_SHORT } from "../../constants";

export function MetaPill({
  icon,
  label,
  color,
  bg,
  tooltip,
}: {
  icon: React.ReactNode;
  label: string;
  color: string;
  bg?: string;
  tooltip?: string;
}) {
  const bgClass = bg ?? "bg-control border border-card";

  const pill = (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] hover:bg-control-hover transition-colors ${bgClass} ${color}`}
    >
      {icon}
      <span>{label}</span>
    </span>
  );

  if (!tooltip) return pill;

  return <Tooltip text={tooltip}>{pill}</Tooltip>;
}

export function TokenStat({
  icon,
  label,
  value,
  color,
  tooltip,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  color: string;
  tooltip?: string;
}) {
  const [show, setShow] = useState(false);

  return (
    <div
      className="relative bg-subtle rounded px-2 py-1.5"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <p className={`${METRIC_LABEL} flex items-center gap-1`}>{icon}{label}</p>
      <p className={`${color} font-mono`}>{formatTokens(value)}</p>
      {tooltip && show && (
        <span className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-[100] px-2.5 py-1.5 rounded-md bg-canvas border border-card text-[11px] text-secondary whitespace-nowrap shadow-lg pointer-events-none">
          {tooltip}
        </span>
      )}
    </div>
  );
}

export function CostStat({ value }: { value: number }) {
  const [show, setShow] = useState(false);

  return (
    <div
      className="relative bg-subtle rounded px-2 py-1.5"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <p className={`${METRIC_LABEL} flex items-center gap-1`}><DollarSign className="w-3 h-3" />Est. Cost</p>
      <p className="text-emerald-700 dark:text-emerald-300 font-mono">{formatCost(value)}</p>
      {show && (
        <span className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-[100] px-2.5 py-1.5 rounded-md bg-canvas border border-card text-[11px] text-secondary whitespace-nowrap shadow-lg pointer-events-none">
          Estimated cost based on API pricing
        </span>
      )}
    </div>
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

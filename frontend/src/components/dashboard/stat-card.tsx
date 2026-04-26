import { CARD_DESCRIPTION } from "../../styles";
import type { TooltipContent } from "./chart-tooltip";

export interface StatCardRow {
  label: string;
  value: string;
  tooltipText?: TooltipContent;
}

export interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  description?: string;
  value: string;
  rows: StatCardRow[];
  tooltipText: TooltipContent;
  onHover: (e: React.MouseEvent, content: TooltipContent) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

export function StatCard({
  icon,
  label,
  description,
  value,
  rows,
  tooltipText,
  onHover,
  onMove,
  onLeave,
}: StatCardProps) {
  return (
    <div
      className="rounded-xl border border-card bg-panel/80 px-5 py-5 flex flex-col gap-3 hover:border-hover/60 transition-colors cursor-default shadow-card"
      onMouseEnter={(e) => onHover(e, tooltipText)}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      <div className="flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold text-secondary uppercase tracking-wider">
            {label}
          </span>
          {description && (
            <p className={CARD_DESCRIPTION}>
              {description}
            </p>
          )}
        </div>
        <div className="text-accent-cyan/70">{icon}</div>
      </div>
      <div className="text-3xl font-bold text-accent-cyan tabular-nums tracking-tight">
        {value}
      </div>
      <div className="border-t border-card pt-2.5 space-y-1.5">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between text-[13px]"
            onMouseEnter={(e) => {
              if (row.tooltipText) {
                e.stopPropagation();
                onHover(e, row.tooltipText);
              }
            }}
            onMouseMove={(e) => {
              if (row.tooltipText) {
                e.stopPropagation();
                onMove(e);
              }
            }}
            onMouseLeave={(e) => {
              if (row.tooltipText) {
                e.stopPropagation();
                onLeave();
              }
            }}
          >
            <span className="text-muted">{row.label}</span>
            <span className="text-secondary tabular-nums font-medium">
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export interface StatCardRow {
  label: string;
  value: string;
  tooltipText?: string;
}

export interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  description?: string;
  value: string;
  rows: StatCardRow[];
  tooltipText: string;
  onHover: (e: React.MouseEvent, text: string) => void;
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
      className="rounded-xl border border-zinc-700/60 bg-zinc-900/80 px-5 py-5 flex flex-col gap-3 hover:border-zinc-500/60 transition-colors cursor-default"
      onMouseEnter={(e) => onHover(e, tooltipText)}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      <div className="flex items-center justify-between">
        <div>
          <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
            {label}
          </span>
          {description && (
            <p className="text-[10px] text-zinc-500 mt-0.5 leading-tight">
              {description}
            </p>
          )}
        </div>
        <div className="text-cyan-400/70">{icon}</div>
      </div>
      <div className="text-3xl font-bold text-cyan-400 tabular-nums tracking-tight">
        {value}
      </div>
      <div className="border-t border-zinc-700/40 pt-2.5 space-y-1.5">
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
            <span className="text-zinc-400">{row.label}</span>
            <span className="text-zinc-200 tabular-nums font-medium">
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

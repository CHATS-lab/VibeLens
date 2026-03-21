export interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  rows: Array<{ label: string; value: string }>;
  tooltipText: string;
  onHover: (e: React.MouseEvent, text: string) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

export function StatCard({
  icon,
  label,
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
        <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
          {label}
        </span>
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

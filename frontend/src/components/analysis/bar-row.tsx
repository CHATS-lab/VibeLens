export interface BarRowProps {
  label: string;
  value: number;
  max: number;
  tooltipText: string;
  onClick?: () => void;
  onHover: (e: React.MouseEvent, text: string) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

export function BarRow({
  label,
  value,
  max,
  tooltipText,
  onClick,
  onHover,
  onMove,
  onLeave,
}: BarRowProps) {
  const pct = max > 0 ? (value / max) * 100 : 0;
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className="flex items-center gap-2.5 text-[13px] w-full text-left hover:bg-zinc-800/60 px-2.5 py-1.5 rounded-md transition disabled:cursor-default group"
      onMouseEnter={(e) => onHover(e, tooltipText)}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      <span
        className="w-32 truncate text-zinc-300 group-hover:text-zinc-100 transition-colors"
        title={label}
      >
        {label}
      </span>
      <div className="flex-1 h-5 bg-zinc-800/60 rounded-md overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-md transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 text-right text-zinc-300 tabular-nums font-medium">
        {value}
      </span>
    </button>
  );
}

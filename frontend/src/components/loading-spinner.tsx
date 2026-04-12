export type SpinnerColor = "cyan" | "amber" | "teal";

const SPINNER_COLORS: Record<SpinnerColor, {
  glow: string;
  outerA: string; outerB: string;
  midA: string; midB: string;
  innerA: string; innerB: string;
  dot: string;
}> = {
  cyan: {
    glow: "bg-cyan-500/8",
    outerA: "border-t-cyan-400/40", outerB: "border-r-cyan-400/10",
    midA: "border-t-cyan-400/70", midB: "border-l-cyan-400/20",
    innerA: "border-t-cyan-300", innerB: "border-r-cyan-300/30",
    dot: "bg-cyan-400",
  },
  amber: {
    glow: "bg-amber-500/8",
    outerA: "border-t-amber-400/40", outerB: "border-r-amber-400/10",
    midA: "border-t-amber-400/70", midB: "border-l-amber-400/20",
    innerA: "border-t-amber-300", innerB: "border-r-amber-300/30",
    dot: "bg-amber-400",
  },
  teal: {
    glow: "bg-teal-500/8",
    outerA: "border-t-teal-400/40", outerB: "border-r-teal-400/10",
    midA: "border-t-teal-400/70", midB: "border-l-teal-400/20",
    innerA: "border-t-teal-300", innerB: "border-r-teal-300/30",
    dot: "bg-teal-400",
  },
};

interface LoadingSpinnerProps {
  label?: string;
  sublabel?: string;
  color?: SpinnerColor;
}

export function LoadingSpinnerRings({ color = "cyan" }: { color?: SpinnerColor } = {}) {
  const c = SPINNER_COLORS[color];
  return (
    <div className="relative flex items-center justify-center w-20 h-20">
      <div className={`absolute w-28 h-28 ${c.glow} rounded-full blur-2xl animate-pulse`} />
      <div
        className={`absolute w-20 h-20 rounded-full border-2 border-transparent ${c.outerA} ${c.outerB}`}
        style={{ animation: "spin 3s linear infinite reverse" }}
      />
      <div
        className={`absolute w-14 h-14 rounded-full border-2 border-transparent ${c.midA} ${c.midB}`}
        style={{ animation: "spin 1.8s linear infinite" }}
      />
      <div
        className={`absolute w-8 h-8 rounded-full border-2 border-transparent ${c.innerA} ${c.innerB}`}
        style={{ animation: "spin 1s linear infinite" }}
      />
      <div className={`w-2 h-2 rounded-full ${c.dot} animate-pulse`} />
    </div>
  );
}

export function LoadingSpinner({ label, sublabel, color = "cyan" }: LoadingSpinnerProps) {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-5">
        <LoadingSpinnerRings color={color} />
        {label && (
          <div className="text-center space-y-1">
            <p className="text-sm font-medium text-secondary">{label}</p>
            {sublabel && <p className="text-xs text-dimmed">{sublabel}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

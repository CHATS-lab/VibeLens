interface LoadingSpinnerProps {
  label?: string;
  sublabel?: string;
}

export function LoadingSpinner({ label, sublabel }: LoadingSpinnerProps) {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-5">
        <div className="relative flex items-center justify-center w-20 h-20">
          {/* Ambient glow */}
          <div className="absolute w-28 h-28 bg-cyan-500/8 rounded-full blur-2xl animate-pulse" />

          {/* Outer ring — slow reverse spin */}
          <div
            className="absolute w-20 h-20 rounded-full border-2 border-transparent border-t-cyan-400/40 border-r-cyan-400/10"
            style={{ animation: "spin 3s linear infinite reverse" }}
          />

          {/* Middle ring — medium spin */}
          <div
            className="absolute w-14 h-14 rounded-full border-2 border-transparent border-t-cyan-400/70 border-l-cyan-400/20"
            style={{ animation: "spin 1.8s linear infinite" }}
          />

          {/* Inner ring — fast spin */}
          <div
            className="absolute w-8 h-8 rounded-full border-2 border-transparent border-t-cyan-300 border-r-cyan-300/30"
            style={{ animation: "spin 1s linear infinite" }}
          />

          {/* Center dot */}
          <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
        </div>

        {label && (
          <div className="text-center space-y-1">
            <p className="text-sm font-medium text-zinc-200">{label}</p>
            {sublabel && <p className="text-xs text-zinc-500">{sublabel}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

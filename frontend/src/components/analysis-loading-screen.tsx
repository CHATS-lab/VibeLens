import { Square } from "lucide-react";
import { LoadingSpinnerRings, type SpinnerColor } from "./ui/loading-spinner";

interface AnalysisLoadingScreenProps {
  accent: "teal" | "amber";
  title: string;
  sublabel: string;
  sessionCount: number;
  onStop?: () => void;
}

export function AnalysisLoadingScreen({
  accent,
  title,
  sublabel,
  sessionCount,
  onStop,
}: AnalysisLoadingScreenProps) {
  return (
    <div className="flex flex-col items-center text-center gap-4 py-12">
      <LoadingSpinnerRings color={accent as SpinnerColor} />

      <div className="space-y-1">
        <p className="text-base font-semibold text-primary">
          Analyzing {sessionCount} session{sessionCount !== 1 ? "s" : ""}
        </p>
        <p className="text-sm text-secondary">{title}</p>
        <p className="text-xs text-muted">{sublabel}</p>
      </div>

      {onStop && (
        <div className="flex flex-col items-center gap-2">
          <button
            onClick={onStop}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs text-rose-600 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 dark:text-rose-300 dark:hover:text-white dark:bg-rose-900/30 dark:hover:bg-rose-800/50 dark:border-rose-700/50 rounded-md transition"
          >
            <Square className="w-3 h-3" />
            Stop
          </button>
          <p className="text-xs text-dimmed">
            Running in background. You can switch tabs.
          </p>
        </div>
      )}
    </div>
  );
}

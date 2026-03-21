import type { ReactNode } from "react";
import type { Step } from "../../types";
import { formatElapsed } from "../../utils";

interface TimelineEntry {
  step: Step;
  content: ReactNode;
}

interface StepTimelineProps {
  entries: TimelineEntry[];
  sessionStartMs: number | null;
}

export function StepTimeline({ entries, sessionStartMs }: StepTimelineProps) {
  const hasTimestamps = entries.some((e) => e.step.timestamp);
  if (!hasTimestamps) {
    return (
      <>
        {entries.map((entry) => (
          <div key={entry.step.step_id}>{entry.content}</div>
        ))}
      </>
    );
  }

  const startMs =
    sessionStartMs ?? findFirstTimestampMs(entries.map((e) => e.step));

  return (
    <>
      {entries.map((entry, index) => {
        const stepMs = entry.step.timestamp
          ? new Date(entry.step.timestamp).getTime()
          : null;
        const elapsedSeconds =
          startMs != null && stepMs != null
            ? Math.max(0, Math.floor((stepMs - startMs) / 1000))
            : null;

        const nextEntry = entries[index + 1];
        const nextMs =
          nextEntry?.step.timestamp
            ? new Date(nextEntry.step.timestamp).getTime()
            : null;
        const gapSeconds =
          stepMs != null && nextMs != null
            ? Math.max(0, Math.floor((nextMs - stepMs) / 1000))
            : null;

        const hasNext = index < entries.length - 1;
        const dotColor =
          entry.step.source === "user"
            ? entry.step.extra?.is_skill_output ? "bg-amber-500" : "bg-indigo-500"
            : entry.step.source === "system"
              ? "bg-zinc-500"
              : "bg-cyan-500";

        return (
          <div key={entry.step.step_id} className="flex gap-3">
            {/* Left rail */}
            <div className="w-12 shrink-0 flex flex-col items-center">
              <span className="text-[10px] text-zinc-500 font-mono leading-tight">
                {elapsedSeconds != null ? formatElapsed(elapsedSeconds) : ""}
              </span>
              <div className={`w-2 h-2 rounded-full ${dotColor} mt-0.5`} />
              {hasNext && (
                <>
                  <div className="w-px flex-1 bg-zinc-700/50 min-h-[8px]" />
                  {gapSeconds != null && gapSeconds > 0 && (
                    <span className="text-[9px] text-zinc-600 font-mono my-0.5">
                      {formatElapsed(gapSeconds)}
                    </span>
                  )}
                  <div className="w-px flex-1 bg-zinc-700/50 min-h-[8px]" />
                </>
              )}
            </div>
            {/* Right: content */}
            <div className="flex-1 min-w-0">{entry.content}</div>
          </div>
        );
      })}
    </>
  );
}

function findFirstTimestampMs(steps: Step[]): number | null {
  for (const step of steps) {
    if (step.timestamp) {
      const ms = new Date(step.timestamp).getTime();
      if (!isNaN(ms)) return ms;
    }
  }
  return null;
}

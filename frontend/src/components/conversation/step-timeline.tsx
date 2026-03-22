import type { ReactNode } from "react";
import type { Step } from "../../types";
import { formatElapsed, formatStepTime, formatFullDateTime } from "../../utils";

interface TimelineEntry {
  step: Step;
  content: ReactNode;
}

interface StepTimelineProps {
  entries: TimelineEntry[];
  sessionStartMs: number | null;
  sessionStartTimestamp?: string | null;
}

export function StepTimeline({
  entries,
  sessionStartMs,
  sessionStartTimestamp,
}: StepTimelineProps) {
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

        const prevEntry = entries[index - 1];
        const prevMs = prevEntry?.step.timestamp
          ? new Date(prevEntry.step.timestamp).getTime()
          : null;
        const gapSeconds =
          prevMs != null && stepMs != null
            ? Math.max(0, Math.floor((stepMs - prevMs) / 1000))
            : null;

        const hasNext = index < entries.length - 1;
        const isFirst = index === 0;
        const dotColor =
          entry.step.source === "user"
            ? entry.step.extra?.is_skill_output
              ? "bg-amber-500"
              : "bg-indigo-500"
            : entry.step.source === "system"
              ? "bg-zinc-500"
              : "bg-cyan-500";

        const actualTime = entry.step.timestamp
          ? formatStepTime(entry.step.timestamp, sessionStartTimestamp)
          : "";
        const fullDateTime = entry.step.timestamp
          ? formatFullDateTime(entry.step.timestamp)
          : "";

        return (
          <div key={entry.step.step_id} className="flex gap-3">
            {/* Narrow rail: dot + connector */}
            <div className="flex flex-col items-center w-5 shrink-0">
              <div
                className={`w-2 h-2 rounded-full ${dotColor} mt-[7px] shrink-0`}
              />
              {hasNext && (
                <div className="w-px flex-1 bg-zinc-700/40 min-h-[16px]" />
              )}
            </div>

            {/* Content with inline time header */}
            <div
              className={`flex-1 min-w-0 pb-5 ${!isFirst ? "border-t border-zinc-700/40 pt-3" : ""}`}
            >
              <div
                className="flex items-baseline gap-1.5 mb-1.5 cursor-default"
                title={fullDateTime}
              >
                {elapsedSeconds != null && (
                  <span className="text-xs font-mono text-zinc-400">
                    {formatElapsed(elapsedSeconds)}
                  </span>
                )}
                {actualTime && (
                  <>
                    <span className="text-zinc-600 text-[11px]">&middot;</span>
                    <span className="text-[11px] font-mono text-zinc-500">
                      {actualTime}
                    </span>
                  </>
                )}
                {gapSeconds != null && gapSeconds > 0 && (
                  <span className="text-[10px] font-mono text-zinc-600 ml-auto">
                    +{formatElapsed(gapSeconds)}
                  </span>
                )}
              </div>
              {entry.content}
            </div>
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

import { useMemo } from "react";
import { MODEL_COLORS } from "./chart-constants";
import { displayModelName } from "./chart-utils";

interface ModelDistributionProps {
  data: Record<string, number>;
  onHover: (e: React.MouseEvent, text: string) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

export function ModelDistribution({
  data,
  onHover,
  onMove,
  onLeave,
}: ModelDistributionProps) {
  const entries = useMemo(
    () => Object.entries(data).sort(([, a], [, b]) => b - a),
    [data]
  );
  const total = entries.reduce((s, [, v]) => s + v, 0);

  const segments = entries.map(([model, count], i) => ({
    model,
    count,
    pct: total > 0 ? (count / total) * 100 : 0,
    color: MODEL_COLORS[i % MODEL_COLORS.length],
  }));

  return (
    <div className="space-y-3">
      <div className="h-4 rounded-full overflow-hidden flex bg-control">
        {segments.map((seg) => (
          <div
            key={seg.model}
            className={`h-full ${seg.color} cursor-default`}
            style={{ width: `${seg.pct}%` }}
            onMouseEnter={(e) =>
              onHover(
                e,
                `${displayModelName(seg.model)}\n${seg.count} session${seg.count !== 1 ? "s" : ""} (${seg.pct.toFixed(1)}%)`
              )
            }
            onMouseMove={onMove}
            onMouseLeave={onLeave}
          />
        ))}
      </div>

      <div className="space-y-1.5">
        {entries.map(([model, count], i) => {
          const pct =
            total > 0 ? ((count / total) * 100).toFixed(1) : "0";
          return (
            <div
              key={model}
              className="flex items-center gap-2.5 text-[13px] cursor-default"
              onMouseEnter={(e) =>
                onHover(
                  e,
                  `${displayModelName(model)}\n${count} session${count !== 1 ? "s" : ""} (${pct}%)`
                )
              }
              onMouseMove={onMove}
              onMouseLeave={onLeave}
            >
              <span
                className={`w-3 h-3 rounded-sm shrink-0 ${MODEL_COLORS[i % MODEL_COLORS.length]}`}
              />
              <span
                className="flex-1 text-secondary truncate"
                title={displayModelName(model)}
              >
                {displayModelName(model)}
              </span>
              <span className="text-muted tabular-nums">
                {count} ({pct}%)
              </span>
            </div>
          );
        })}
        {entries.length === 0 && (
          <p className="text-sm text-dimmed">No data</p>
        )}
      </div>
    </div>
  );
}

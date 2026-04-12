import { useMemo } from "react";
import { PEAK_HOUR_BINS } from "./chart-constants";

interface PeakHoursChartProps {
  data: Record<number, number>;
  onHover: (e: React.MouseEvent, text: string) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

export function PeakHoursChart({
  data,
  onHover,
  onMove,
  onLeave,
}: PeakHoursChartProps) {
  const bins = useMemo(() => {
    return Array.from({ length: PEAK_HOUR_BINS }, (_, i) => {
      const h1 = i * 2;
      const h2 = h1 + 1;
      const c1 = data[h1] ?? data[String(h1) as unknown as number] ?? 0;
      const c2 = data[h2] ?? data[String(h2) as unknown as number] ?? 0;
      return {
        label: `${String(h1).padStart(2, "0")}`,
        rangeLabel: `${String(h1).padStart(2, "0")}:00 – ${String(h2).padStart(2, "0")}:59`,
        count: c1 + c2,
      };
    });
  }, [data]);
  const maxVal = Math.max(1, ...bins.map((b) => b.count));

  return (
    <div>
      <div className="flex items-end gap-1.5 h-24">
        {bins.map((bin) => {
          const pct = (bin.count / maxVal) * 100;
          return (
            <div
              key={bin.label}
              className="flex-1 flex flex-col items-center justify-end h-full cursor-default"
              onMouseEnter={(e) =>
                onHover(
                  e,
                  `${bin.rangeLabel}\n${bin.count} session${bin.count !== 1 ? "s" : ""}`
                )
              }
              onMouseMove={onMove}
              onMouseLeave={onLeave}
            >
              <div
                className="w-full bg-gradient-to-t from-cyan-600 to-cyan-400 rounded-t transition-all"
                style={{
                  height: `${Math.max(pct, bin.count > 0 ? 4 : 0)}%`,
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex gap-1.5 mt-1.5">
        {bins.map((bin, i) => (
          <div key={bin.label} className="flex-1 text-center text-[10px] text-muted">
            {i % 2 === 0 ? bin.label : ""}
          </div>
        ))}
      </div>
    </div>
  );
}

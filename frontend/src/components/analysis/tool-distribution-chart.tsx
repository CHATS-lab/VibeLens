import { useMemo } from "react";
import type { ToolUsageStat } from "../../types";
import { TOOL_COLORS } from "./chart-constants";

const MAX_TOOLS = 12;

interface ToolDistributionProps {
  data: ToolUsageStat[];
  totalCalls: number;
  onHover: (e: React.MouseEvent, text: string) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

export function ToolDistribution({
  data,
  totalCalls,
  onHover,
  onMove,
  onLeave,
}: ToolDistributionProps) {
  const { visible, otherCount } = useMemo(() => {
    const top = data.slice(0, MAX_TOOLS);
    const rest = data.slice(MAX_TOOLS).reduce((s, t) => s + t.call_count, 0);
    return { visible: top, otherCount: rest };
  }, [data]);

  const total = totalCalls || data.reduce((s, t) => s + t.call_count, 0);

  const segments = useMemo(() => {
    const segs = visible.map((tool, i) => ({
      name: tool.tool_name,
      count: tool.call_count,
      pct: total > 0 ? (tool.call_count / total) * 100 : 0,
      avgPerSession: tool.avg_per_session,
      errorRate: tool.error_rate,
      color: TOOL_COLORS[i % TOOL_COLORS.length],
    }));
    if (otherCount > 0) {
      segs.push({
        name: "Other",
        count: otherCount,
        pct: total > 0 ? (otherCount / total) * 100 : 0,
        avgPerSession: 0,
        errorRate: 0,
        color: "bg-zinc-600",
      });
    }
    return segs;
  }, [visible, otherCount, total]);

  const buildTooltip = (seg: (typeof segments)[0]) => {
    const lines = [
      seg.name,
      `${seg.count.toLocaleString()} calls (${seg.pct.toFixed(1)}%)`,
    ];
    if (seg.avgPerSession > 0) {
      lines.push(`Avg ${seg.avgPerSession}/session`);
    }
    if (seg.errorRate > 0) {
      lines.push(`Error rate: ${(seg.errorRate * 100).toFixed(1)}%`);
    }
    return lines.join("\n");
  };

  if (data.length === 0) {
    return <p className="text-sm text-zinc-500">No data</p>;
  }

  return (
    <div className="space-y-3">
      <div className="h-4 rounded-full overflow-hidden flex bg-zinc-800">
        {segments.map((seg) => (
          <div
            key={seg.name}
            className={`h-full ${seg.color} cursor-default`}
            style={{ width: `${seg.pct}%` }}
            onMouseEnter={(e) => onHover(e, buildTooltip(seg))}
            onMouseMove={onMove}
            onMouseLeave={onLeave}
          />
        ))}
      </div>

      <div className="space-y-1.5">
        {segments.map((seg, i) => (
          <div
            key={seg.name}
            className="flex items-center gap-2.5 text-[13px] cursor-default"
            onMouseEnter={(e) => onHover(e, buildTooltip(seg))}
            onMouseMove={onMove}
            onMouseLeave={onLeave}
          >
            <span
              className={`w-3 h-3 rounded-sm shrink-0 ${seg.name === "Other" ? "bg-zinc-600" : TOOL_COLORS[i % TOOL_COLORS.length]}`}
            />
            <span className="flex-1 text-zinc-300 truncate" title={seg.name}>
              {seg.name}
            </span>
            <span className="text-zinc-400 tabular-nums">
              {seg.count.toLocaleString()} ({seg.pct.toFixed(1)}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

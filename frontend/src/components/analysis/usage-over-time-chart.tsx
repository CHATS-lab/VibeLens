import { useState, useMemo, useCallback, useRef } from "react";
import type { DailyStat } from "../../types";
import { formatTokens, formatCost } from "../../utils";
import { TOGGLE_ACTIVE, TOGGLE_INACTIVE } from "../../styles";
import type { ChartMetric, TimeGroup } from "./chart-utils";
import { fillDateGaps, groupDailyStats } from "./chart-utils";

interface UsageOverTimeChartProps {
  data: DailyStat[];
  onHover: (e: React.MouseEvent, text: string) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

const W = 800;
const H = 200;
const ML = 55;
const MR = 15;
const MT = 12;
const MB = 28;
const PW = W - ML - MR;
const PH = H - MT - MB;

export function UsageOverTimeChart({
  data,
  onHover,
  onMove,
  onLeave,
}: UsageOverTimeChartProps) {
  const [metric, setMetric] = useState<ChartMetric>("sessions");
  const [timeGroup, setTimeGroup] = useState<TimeGroup>("day");
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const filled = useMemo(() => fillDateGaps(data), [data]);
  const grouped = useMemo(
    () => groupDailyStats(filled, timeGroup),
    [filled, timeGroup]
  );

  const values = useMemo(() => {
    return grouped.map((d) => {
      switch (metric) {
        case "sessions":
          return d.session_count;
        case "messages":
          return d.total_messages;
        case "tokens":
          return d.total_tokens;
        case "cost":
          return d.total_cost_usd;
      }
    });
  }, [grouped, metric]);

  const maxVal = Math.max(1, ...values);
  const isSinglePoint = grouped.length === 1;

  const points = useMemo(
    () =>
      values.map((v, i) => ({
        x:
          ML +
          (grouped.length > 1 ? (i / (grouped.length - 1)) * PW : PW / 2),
        y: MT + PH - (v / maxVal) * PH,
      })),
    [values, maxVal, grouped.length]
  );

  const lineD = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`)
    .join(" ");
  const areaD =
    lineD +
    ` L${points[points.length - 1].x},${MT + PH} L${points[0].x},${MT + PH} Z`;

  const gridFractions = [0.25, 0.5, 0.75, 1];
  const gridLines = gridFractions.map((f) => MT + PH * (1 - f));

  const formatY = (val: number) => {
    if (metric === "tokens") return formatTokens(val);
    if (metric === "cost") return formatCost(val);
    return String(Math.round(val));
  };

  const labelInterval = Math.max(1, Math.ceil(grouped.length / 7));

  const formatXLabel = (date: string) => {
    if (timeGroup === "year") return date;
    if (timeGroup === "month") return date;
    return date.slice(5);
  };

  const findNearestIndex = useCallback(
    (clientX: number): number | null => {
      const svg = svgRef.current;
      if (!svg || points.length === 0) return null;
      const rect = svg.getBoundingClientRect();
      const svgX = ((clientX - rect.left) / rect.width) * W;

      let nearest = 0;
      let minDist = Math.abs(svgX - points[0].x);
      for (let i = 1; i < points.length; i++) {
        const dist = Math.abs(svgX - points[i].x);
        if (dist < minDist) {
          minDist = dist;
          nearest = i;
        }
      }
      return nearest;
    },
    [points]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const idx = findNearestIndex(e.clientX);
      if (idx === null) return;
      setActiveIndex(idx);
      const d = grouped[idx];
      const lines = [
        d.date,
        `Sessions: ${d.session_count}`,
        `Messages: ${d.total_messages.toLocaleString()}`,
        `Tokens: ${d.total_tokens.toLocaleString()}`,
        `Cost: ${formatCost(d.total_cost_usd)}`,
      ];
      onHover(e, lines.join("\n"));
      onMove(e);
    },
    [findNearestIndex, grouped, onHover, onMove]
  );

  const handleMouseLeave = useCallback(() => {
    setActiveIndex(null);
    onLeave();
  }, [onLeave]);

  const metricButtons: Array<{ key: ChartMetric; label: string }> = [
    { key: "sessions", label: "Sessions" },
    { key: "messages", label: "Messages" },
    { key: "tokens", label: "Tokens" },
    { key: "cost", label: "Cost" },
  ];

  const timeGroupButtons: Array<{ key: TimeGroup; label: string }> = [
    { key: "day", label: "Day" },
    { key: "month", label: "Month" },
    { key: "year", label: "Year" },
  ];

  if (grouped.length < 1) {
    return (
      <div>
        <h3 className="text-base font-medium text-zinc-200 mb-3">
          Usage Over Time
        </h3>
        <p className="text-sm text-zinc-400 py-8 text-center">
          No data available
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-medium text-zinc-200">
          Usage Over Time
        </h3>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {timeGroupButtons.map((g) => (
              <button
                key={g.key}
                onClick={() => setTimeGroup(g.key)}
                className={`px-2 py-1 text-xs font-medium rounded-md transition ${
                  timeGroup === g.key
                    ? TOGGLE_ACTIVE
                    : `${TOGGLE_INACTIVE} hover:bg-zinc-800`
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>
          <div className="w-px h-4 bg-zinc-700" />
          <div className="flex gap-1">
            {metricButtons.map((m) => (
              <button
                key={m.key}
                onClick={() => setMetric(m.key)}
                className={`px-2.5 py-1 text-xs font-medium rounded-md transition ${
                  metric === m.key
                    ? "bg-cyan-600 text-white"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(34,211,238,0.3)" />
            <stop offset="100%" stopColor="rgba(34,211,238,0.02)" />
          </linearGradient>
        </defs>

        {gridLines.map((y, i) => (
          <g key={i}>
            <line
              x1={ML}
              y1={y}
              x2={W - MR}
              y2={y}
              stroke="rgba(255,255,255,0.06)"
            />
            <text
              x={ML - 8}
              y={y + 4}
              fill="#a1a1aa"
              fontSize={10}
              textAnchor="end"
            >
              {formatY(maxVal * gridFractions[i])}
            </text>
          </g>
        ))}

        <line
          x1={ML}
          y1={MT + PH}
          x2={W - MR}
          y2={MT + PH}
          stroke="rgba(255,255,255,0.08)"
        />

        {isSinglePoint ? (
          <rect
            x={points[0].x - 30}
            y={points[0].y}
            width={60}
            height={MT + PH - points[0].y}
            fill="url(#areaGrad)"
            stroke="rgb(34,211,238)"
            strokeWidth={2}
            rx={4}
          />
        ) : (
          <>
            <path d={areaD} fill="url(#areaGrad)" />
            <path
              d={lineD}
              fill="none"
              stroke="rgb(34,211,238)"
              strokeWidth={2}
            />
          </>
        )}

        {/* Small dots on each data point */}
        {!isSinglePoint &&
          points.map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={activeIndex === i ? 5 : 3}
              fill="rgb(34,211,238)"
              className="pointer-events-none transition-all"
            />
          ))}

        {/* Vertical crosshair line at active point */}
        {activeIndex !== null && points[activeIndex] && (
          <line
            x1={points[activeIndex].x}
            y1={MT}
            x2={points[activeIndex].x}
            y2={MT + PH}
            stroke="rgba(34,211,238,0.4)"
            strokeWidth={1}
            strokeDasharray="4 3"
            className="pointer-events-none"
          />
        )}

        {/* Invisible overlay for mouse tracking across entire chart area */}
        <rect
          x={ML}
          y={MT}
          width={PW}
          height={PH}
          fill="transparent"
          className="cursor-crosshair"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        />

        {grouped.map((d, i) => {
          if (i % labelInterval !== 0 && i !== grouped.length - 1) return null;
          return (
            <text
              key={d.date}
              x={points[i].x}
              y={H - 6}
              fill="#a1a1aa"
              fontSize={10}
              textAnchor="middle"
            >
              {formatXLabel(d.date)}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

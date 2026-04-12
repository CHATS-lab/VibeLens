import { useMemo } from "react";
import {
  HEATMAP_WEEKS,
  HEATMAP_COLORS,
  CELL_SIZE,
  CELL_GAP,
  LABEL_WIDTH,
  HEADER_HEIGHT,
  DAY_LABELS,
  MONTH_NAMES,
} from "./chart-constants";
import { getHeatmapColor } from "./chart-utils";

function toLocalDateStr(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

interface ActivityHeatmapProps {
  data: Record<string, number>;
  onHover: (e: React.MouseEvent, text: string) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}

export function ActivityHeatmap({
  data,
  onHover,
  onMove,
  onLeave,
}: ActivityHeatmapProps) {
  const { weeks, monthLabels, maxVal, yearTotal } = useMemo(() => {
    const today = new Date();
    const weeksData: Array<
      Array<{ date: string; count: number; dayOfWeek: number }>
    > = [];
    const labels: Array<{ month: string; weekIndex: number }> = [];

    // Monday of the current week, then back (HEATMAP_WEEKS - 1) full weeks
    const daysToMonday = (today.getDay() + 6) % 7;
    const startDate = new Date(today);
    startDate.setDate(today.getDate() - daysToMonday - (HEATMAP_WEEKS - 1) * 7);

    let lastMonth = -1;
    let total = 0;
    for (let w = 0; w < HEATMAP_WEEKS; w++) {
      const week: Array<{
        date: string;
        count: number;
        dayOfWeek: number;
      }> = [];
      for (let d = 0; d < 7; d++) {
        const current = new Date(startDate);
        current.setDate(startDate.getDate() + w * 7 + d);
        if (current > today) {
          week.push({ date: "", count: 0, dayOfWeek: d });
          continue;
        }
        const dateStr = toLocalDateStr(current);
        const count = data[dateStr] || 0;
        total += count;
        week.push({ date: dateStr, count, dayOfWeek: d });

        if (d === 0 && current.getMonth() !== lastMonth) {
          lastMonth = current.getMonth();
          labels.push({ month: MONTH_NAMES[lastMonth], weekIndex: w });
        }
      }
      weeksData.push(week);
    }

    const allCounts = Object.values(data);
    const max = Math.max(1, ...allCounts);

    return { weeks: weeksData, monthLabels: labels, maxVal: max, yearTotal: total };
  }, [data]);

  const width = LABEL_WIDTH + HEATMAP_WEEKS * (CELL_SIZE + CELL_GAP) + 10;
  const height = HEADER_HEIGHT + 7 * (CELL_SIZE + CELL_GAP) + 10;

  const formatDate = (dateStr: string) => {
    if (!dateStr) return "";
    const d = new Date(dateStr + "T00:00:00");
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const months = [
      "Jan", "Feb", "Mar", "Apr", "May", "Jun",
      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    return `${days[d.getDay()]}, ${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p
          className="text-[13px] text-secondary cursor-default"
          onMouseEnter={(e) =>
            onHover(e, "GitHub-style heatmap showing daily session activity over the past year")
          }
          onMouseMove={onMove}
          onMouseLeave={onLeave}
        >
          <span className="text-accent-cyan font-semibold">
            {yearTotal.toLocaleString()}
          </span>{" "}
          sessions in the last year
        </p>
        <div className="flex items-center gap-1.5 text-xs text-muted">
          <span>Less</span>
          {HEATMAP_COLORS.slice(1).map((color, i) => (
            <div
              key={i}
              className="w-2.5 h-2.5 rounded-sm"
              style={{ backgroundColor: color }}
            />
          ))}
          <span>More</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <svg width={width} height={height} className="text-muted">
          {monthLabels.map(({ month, weekIndex }, i) => (
            <text
              key={`${month}-${i}`}
              x={LABEL_WIDTH + weekIndex * (CELL_SIZE + CELL_GAP)}
              y={12}
              fill="currentColor"
              fontSize={11}
            >
              {month}
            </text>
          ))}

          {DAY_LABELS.map(
            (label, dayIdx) =>
              label && (
                <text
                  key={label}
                  x={0}
                  y={
                    HEADER_HEIGHT +
                    dayIdx * (CELL_SIZE + CELL_GAP) +
                    CELL_SIZE / 2 +
                    4
                  }
                  fill="currentColor"
                  fontSize={10}
                >
                  {label}
                </text>
              )
          )}

          {weeks.map((week, wIdx) =>
            week.map((day) =>
              day.date ? (
                <rect
                  key={day.date}
                  x={LABEL_WIDTH + wIdx * (CELL_SIZE + CELL_GAP)}
                  y={HEADER_HEIGHT + day.dayOfWeek * (CELL_SIZE + CELL_GAP)}
                  width={CELL_SIZE}
                  height={CELL_SIZE}
                  rx={2}
                  fill={getHeatmapColor(day.count, maxVal)}
                  onMouseEnter={(e) =>
                    onHover(
                      e,
                      `${formatDate(day.date)}\n${day.count} session${day.count !== 1 ? "s" : ""}`
                    )
                  }
                  onMouseMove={onMove}
                  onMouseLeave={onLeave}
                  className="cursor-default"
                />
              ) : null
            )
          )}
        </svg>
      </div>
    </div>
  );
}

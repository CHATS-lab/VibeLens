import type { DailyStat } from "../../types";
import { HEATMAP_COLORS } from "./chart-constants";

export type ChartMetric = "sessions" | "messages" | "tokens" | "cost";
export type TimeGroup = "day" | "month" | "year";

export function fillDateGaps(data: DailyStat[]): DailyStat[] {
  if (data.length < 2) return data;
  const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
  const result: DailyStat[] = [];
  const start = new Date(sorted[0].date + "T00:00:00");
  const end = new Date(sorted[sorted.length - 1].date + "T00:00:00");
  const dataMap = new Map(sorted.map((d) => [d.date, d]));

  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const key = d.toISOString().slice(0, 10);
    result.push(
      dataMap.get(key) || {
        date: key,
        session_count: 0,
        total_messages: 0,
        total_tokens: 0,
        total_duration: 0,
        total_duration_hours: 0,
        total_cost_usd: 0,
      }
    );
  }
  return result;
}

export function groupDailyStats(data: DailyStat[], group: TimeGroup): DailyStat[] {
  if (group === "day") return data;

  const buckets = new Map<string, DailyStat>();
  for (const d of data) {
    const key = group === "month" ? d.date.slice(0, 7) : d.date.slice(0, 4);
    const existing = buckets.get(key);
    if (existing) {
      existing.session_count += d.session_count;
      existing.total_messages += d.total_messages;
      existing.total_tokens += d.total_tokens;
      existing.total_duration += d.total_duration;
      existing.total_duration_hours += d.total_duration_hours;
      existing.total_cost_usd += d.total_cost_usd;
    } else {
      buckets.set(key, { ...d, date: key });
    }
  }
  return [...buckets.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function displayModelName(name: string): string {
  if (name === "unknown") return "Unknown";
  return name;
}

export function getHeatmapColor(count: number, maxVal: number): string {
  if (count === 0) return HEATMAP_COLORS[0];
  const ratio = count / maxVal;
  if (ratio <= 0.25) return HEATMAP_COLORS[1];
  if (ratio <= 0.5) return HEATMAP_COLORS[2];
  if (ratio <= 0.75) return HEATMAP_COLORS[3];
  return HEATMAP_COLORS[4];
}

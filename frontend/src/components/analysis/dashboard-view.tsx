import {
  MessageSquare,
  Hash,
  Wrench,
  Clock,
  BarChart3,
  Download,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useAppContext } from "../../app";
import type { DashboardStats } from "../../types";
import { formatTokens, formatDuration, baseProjectName } from "../../utils";
import { ActivityHeatmap } from "./activity-heatmap";
import { BarRow } from "./bar-row";
import { ModelDistribution } from "./model-distribution-chart";
import { PeakHoursChart } from "./peak-hours-chart";
import { StatCard } from "./stat-card";
import { Tooltip, useTooltip } from "./tooltip";
import { UsageOverTimeChart } from "./usage-over-time-chart";

export function DashboardView() {
  const { fetchWithToken } = useAppContext();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null);
  const { tip, show, move, hide } = useTooltip();

  useEffect(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (selectedProject) params.set("project_path", selectedProject);

    fetchWithToken(`/api/analysis/dashboard?${params}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: DashboardStats) => setStats(data))
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [fetchWithToken, selectedProject]);

  const handleExport = async (format: "csv" | "json") => {
    setExporting(format);
    const params = new URLSearchParams({ format });
    if (selectedProject) params.set("project_path", selectedProject);
    try {
      const res = await fetchWithToken(
        `/api/analysis/dashboard/export?${params}`
      );
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vibelens-dashboard.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
    } finally {
      setExporting(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-400">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
          <span className="text-sm">Loading dashboard...</span>
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="flex items-center justify-center h-full text-red-400">
        {error || "Failed to load dashboard"}
      </div>
    );
  }

  const projectEntries = Object.entries(stats.project_distribution)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 10);
  const maxProjectCount = projectEntries[0]?.[1] ?? 0;

  const agentEntries = Object.entries(stats.agent_distribution)
    .sort(([, a], [, b]) => b - a);
  const maxAgentCount = agentEntries[0]?.[1] ?? 0;

  return (
    <div className="h-full overflow-y-auto">
      <Tooltip state={tip} />

      <div className="max-w-[1400px] mx-auto p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {selectedProject ? (
              <>
                <button
                  onClick={() => setSelectedProject(null)}
                  className="text-sm text-cyan-400 hover:text-cyan-300 transition font-medium"
                >
                  All Sessions
                </button>
                <span className="text-zinc-600">/</span>
                <span className="text-sm text-zinc-200 font-medium">
                  {baseProjectName(selectedProject)}
                </span>
              </>
            ) : (
              <h2 className="text-xl font-semibold text-zinc-100">
                Analytics Dashboard
              </h2>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => handleExport("csv")}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-zinc-100 bg-zinc-800/80 hover:bg-zinc-700 rounded-lg border border-zinc-700/50 transition disabled:opacity-50 disabled:cursor-not-allowed"
              onMouseEnter={(e) =>
                show(e, "Export all dashboard data as CSV")
              }
              onMouseMove={move}
              onMouseLeave={hide}
            >
              {exporting === "csv" ? (
                <div className="w-3.5 h-3.5 border-2 border-zinc-400/30 border-t-zinc-300 rounded-full animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              {exporting === "csv" ? "Exporting..." : "CSV"}
            </button>
            <button
              onClick={() => handleExport("json")}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:text-zinc-100 bg-zinc-800/80 hover:bg-zinc-700 rounded-lg border border-zinc-700/50 transition disabled:opacity-50 disabled:cursor-not-allowed"
              onMouseEnter={(e) =>
                show(e, "Export all dashboard data as JSON")
              }
              onMouseMove={move}
              onMouseLeave={hide}
            >
              {exporting === "json" ? (
                <div className="w-3.5 h-3.5 border-2 border-zinc-400/30 border-t-zinc-300 rounded-full animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              {exporting === "json" ? "Exporting..." : "JSON"}
            </button>
          </div>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-5 gap-4">
          <StatCard
            icon={<MessageSquare className="w-4 h-4" />}
            label="Sessions"
            value={stats.total_sessions.toLocaleString()}
            rows={[
              {
                label: "This Year",
                value: stats.this_year.sessions.toLocaleString(),
              },
              {
                label: "This Month",
                value: stats.this_month.sessions.toLocaleString(),
              },
              {
                label: "This Week",
                value: stats.this_week.sessions.toLocaleString(),
              },
            ]}
            tooltipText={[
              `Total: ${stats.total_sessions} sessions`,
              `${stats.project_count} projects`,
              `This Year: ${stats.this_year.sessions}`,
              `This Month: ${stats.this_month.sessions}`,
              `This Week: ${stats.this_week.sessions}`,
            ].join("\n")}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
          <StatCard
            icon={<Hash className="w-4 h-4" />}
            label="Messages"
            value={stats.total_messages.toLocaleString()}
            rows={[
              {
                label: "This Year",
                value: stats.this_year.messages.toLocaleString(),
              },
              {
                label: "This Month",
                value: stats.this_month.messages.toLocaleString(),
              },
              {
                label: "Avg/Session",
                value: stats.avg_messages_per_session.toFixed(1),
              },
            ]}
            tooltipText={[
              `Total: ${stats.total_messages.toLocaleString()} messages`,
              `This Year: ${stats.this_year.messages.toLocaleString()}`,
              `Avg: ${stats.avg_messages_per_session.toFixed(1)} per session`,
            ].join("\n")}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
          <StatCard
            icon={<BarChart3 className="w-4 h-4" />}
            label="Tokens"
            value={formatTokens(stats.total_tokens)}
            rows={[
              {
                label: "This Year",
                value: formatTokens(stats.this_year.tokens),
              },
              {
                label: "Input",
                value: formatTokens(stats.total_input_tokens),
              },
              {
                label: "Output",
                value: formatTokens(stats.total_output_tokens),
              },
            ]}
            tooltipText={[
              `Total: ${stats.total_tokens.toLocaleString()}`,
              `This Year: ${stats.this_year.tokens.toLocaleString()}`,
              `Input: ${stats.total_input_tokens.toLocaleString()}`,
              `Output: ${stats.total_output_tokens.toLocaleString()}`,
              `Cache: ${stats.total_cache_tokens.toLocaleString()}`,
              `Avg/Session: ${Math.round(stats.avg_tokens_per_session).toLocaleString()}`,
            ].join("\n")}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
          <StatCard
            icon={<Wrench className="w-4 h-4" />}
            label="Tool Calls"
            value={stats.total_tool_calls.toLocaleString()}
            rows={[
              {
                label: "This Year",
                value: stats.this_year.tool_calls.toLocaleString(),
              },
              {
                label: "This Month",
                value: stats.this_month.tool_calls.toLocaleString(),
              },
              {
                label: "Avg/Session",
                value: stats.avg_tool_calls_per_session.toFixed(1),
              },
            ]}
            tooltipText={[
              `Total: ${stats.total_tool_calls.toLocaleString()}`,
              `This Year: ${stats.this_year.tool_calls.toLocaleString()}`,
              `Avg: ${stats.avg_tool_calls_per_session.toFixed(1)} per session`,
            ].join("\n")}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
          <StatCard
            icon={<Clock className="w-4 h-4" />}
            label="Duration"
            value={formatDuration(stats.total_duration)}
            rows={[
              {
                label: "This Year",
                value: formatDuration(stats.this_year.duration),
              },
              {
                label: "This Month",
                value: formatDuration(stats.this_month.duration),
              },
              {
                label: "Avg/Session",
                value: formatDuration(stats.avg_duration_per_session),
              },
            ]}
            tooltipText={[
              `Total: ${formatDuration(stats.total_duration)}`,
              `This Year: ${formatDuration(stats.this_year.duration)}`,
              `This Month: ${formatDuration(stats.this_month.duration)}`,
              `Avg/Session: ${formatDuration(stats.avg_duration_per_session)}`,
            ].join("\n")}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
        </div>

        {/* Usage Over Time */}
        <div className="rounded-xl border border-zinc-700/60 bg-zinc-900/80 p-5">
          <UsageOverTimeChart
            data={stats.daily_stats}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
        </div>

        {/* Activity Heatmap */}
        <div className="rounded-xl border border-zinc-700/60 bg-zinc-900/80 p-5">
          <ActivityHeatmap
            data={stats.daily_activity}
            totalSessions={stats.total_sessions}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
        </div>

        {/* Bottom grid: Project Activity | Model Distribution + Peak Hours */}
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-xl border border-zinc-700/60 bg-zinc-900/80 p-5">
            <h3
              className="text-base font-medium text-zinc-200 mb-4 cursor-default"
              onMouseEnter={(e) =>
                show(e, "Session count per project (top 10). Click a project to filter.")
              }
              onMouseMove={move}
              onMouseLeave={hide}
            >
              Project Activity
            </h3>
            <div className="space-y-1">
              {projectEntries.map(([project, count]) => (
                <BarRow
                  key={project}
                  label={baseProjectName(project)}
                  value={count}
                  max={maxProjectCount}
                  tooltipText={[
                    baseProjectName(project),
                    `${count} session${count !== 1 ? "s" : ""}`,
                    `${((count / stats.total_sessions) * 100).toFixed(1)}% of total`,
                  ].join("\n")}
                  onClick={() => setSelectedProject(project)}
                  onHover={show}
                  onMove={move}
                  onLeave={hide}
                />
              ))}
              {projectEntries.length === 0 && (
                <p className="text-sm text-zinc-500">No data</p>
              )}
            </div>
          </div>

          <div className="space-y-4">
            {agentEntries.length > 1 && (
              <div className="rounded-xl border border-zinc-700/60 bg-zinc-900/80 p-5">
                <h3
                  className="text-base font-medium text-zinc-200 mb-4 cursor-default"
                  onMouseEnter={(e) =>
                    show(e, "Session count breakdown by agent (Claude Code, Codex, Gemini)")
                  }
                  onMouseMove={move}
                  onMouseLeave={hide}
                >
                  Agent Distribution
                </h3>
                <div className="space-y-1">
                  {agentEntries.map(([agent, count]) => (
                    <BarRow
                      key={agent}
                      label={agent}
                      value={count}
                      max={maxAgentCount}
                      tooltipText={[
                        agent,
                        `${count} session${count !== 1 ? "s" : ""}`,
                        `${((count / stats.total_sessions) * 100).toFixed(1)}% of total`,
                      ].join("\n")}
                      onHover={show}
                      onMove={move}
                      onLeave={hide}
                    />
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-xl border border-zinc-700/60 bg-zinc-900/80 p-5">
              <h3
                className="text-base font-medium text-zinc-200 mb-4 cursor-default"
                onMouseEnter={(e) =>
                  show(e, "Session count breakdown by AI model")
                }
                onMouseMove={move}
                onMouseLeave={hide}
              >
                Model Distribution
              </h3>
              <ModelDistribution
                data={stats.model_distribution}
                onHover={show}
                onMove={move}
                onLeave={hide}
              />
            </div>

            <div className="rounded-xl border border-zinc-700/60 bg-zinc-900/80 p-5">
              <div className="flex items-center gap-2 mb-3">
                <h3
                  className="text-base font-medium text-zinc-200 cursor-default"
                  onMouseEnter={(e) =>
                    show(e, "Distribution of session starts by hour of day")
                  }
                  onMouseMove={move}
                  onMouseLeave={hide}
                >
                  Peak Hours
                </h3>
                <span
                  className="text-xs text-zinc-500 cursor-default"
                  onMouseEnter={(e) =>
                    show(e, `All times shown in ${stats.timezone} timezone`)
                  }
                  onMouseMove={move}
                  onMouseLeave={hide}
                >
                  ({stats.timezone})
                </span>
              </div>
              <PeakHoursChart
                data={stats.hourly_distribution}
                onHover={show}
                onMove={move}
                onLeave={hide}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

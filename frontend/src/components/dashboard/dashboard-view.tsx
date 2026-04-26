import {
  MessageSquare,
  Hash,
  Clock,
  BarChart3,
  Download,
  DollarSign,
  FolderOpen,
  Bot,
  Cpu,
  Loader2,
  RefreshCw,
  Wrench,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../../app";
import { dashboardClient } from "../../api/dashboard";
import { DASHBOARD_POLL_INTERVAL_MS } from "../../constants";
import { useDashboardData } from "../../hooks/use-dashboard-data";
import { useDashboardExport } from "../../hooks/use-dashboard-export";
import type { DashboardStats, ToolUsageStat } from "../../types";
import { formatTokens, formatDuration, formatCost, baseProjectName } from "../../utils";
import { LoadingSpinnerRings } from "../ui/loading-spinner";
import { ActivityHeatmap } from "./activity-heatmap";
import { BarChartRow } from "./bar-chart-row";
import { ModelDistribution } from "./model-distribution-chart";
import { PeakHoursChart } from "./peak-hours-chart";
import { StatCard } from "./stat-card";
import { ToolDistribution, totalToolCalls } from "./tool-distribution-chart";
import { MetricList, Tooltip, useTooltip } from "./chart-tooltip";
import { UsageOverTimeChart } from "./usage-over-time-chart";
import { ProjectRow, DEFAULT_PROJECT_COUNT } from "./project-row";

interface DashboardViewProps {
  cache: { stats: DashboardStats; toolUsage: ToolUsageStat[] } | null;
}

export function DashboardView({ cache }: DashboardViewProps) {
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [showAllProjects, setShowAllProjects] = useState(false);
  const { tip, show, move, hide } = useTooltip();

  const { stats, toolUsage, loading, error, refreshing, refresh, restoreFromCache } =
    useDashboardData({ cache, selectedProject, selectedAgent });
  const { exporting, exportDashboard } = useDashboardExport();

  const handleClearFilters = useCallback(() => {
    setSelectedProject(null);
    setSelectedAgent(null);
    restoreFromCache();
  }, [restoreFromCache]);

  const handleRefresh = useCallback(async () => {
    await refresh();
    setSelectedProject(null);
    setSelectedAgent(null);
  }, [refresh]);

  const handleExport = (format: "csv" | "json") =>
    exportDashboard(format, { project: selectedProject, agent: selectedAgent });

  if (loading) {
    return <WarmingProgressBar />;
  }

  if (error || !stats) {
    return (
      <div className="flex items-center justify-center h-full text-red-600 dark:text-red-400">
        {error || "Failed to load dashboard"}
      </div>
    );
  }

  const allProjectEntries = Object.entries(stats.project_distribution)
    .sort(([, a], [, b]) => b - a);
  const projectEntries = showAllProjects
    ? allProjectEntries
    : allProjectEntries.slice(0, DEFAULT_PROJECT_COUNT);
  const hasMoreProjects = allProjectEntries.length > DEFAULT_PROJECT_COUNT;
  const maxProjectCount = allProjectEntries[0]?.[1] ?? 0;

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
            {selectedProject || selectedAgent ? (
              <>
                <button
                  onClick={handleClearFilters}
                  className="text-sm text-accent-cyan hover:text-accent-cyan hover:bg-control/30 rounded px-1 -mx-1 transition font-medium"
                >
                  All Sessions
                </button>
                {selectedAgent && (
                  <>
                    <span className="text-faint">/</span>
                    {selectedProject ? (
                      <button
                        onClick={() => setSelectedProject(null)}
                        className="text-sm text-accent-cyan hover:text-accent-cyan hover:bg-control/30 rounded px-1 -mx-1 transition font-medium"
                      >
                        {selectedAgent}
                      </button>
                    ) : (
                      <span className="text-sm text-secondary font-medium">
                        {selectedAgent}
                      </span>
                    )}
                  </>
                )}
                {selectedProject && (
                  <>
                    <span className="text-faint">/</span>
                    <span className="text-sm text-secondary font-medium">
                      {baseProjectName(selectedProject)}
                    </span>
                  </>
                )}
              </>
            ) : (
              <h2 className="text-xl font-semibold text-primary">
                Analytics Dashboard
              </h2>
            )}
          </div>
          <div className="flex items-center gap-3">
            {stats.cached_at && (
              <span className="flex items-center gap-1.5 text-xs text-dimmed">
                Updated {new Date(stats.cached_at).toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-secondary hover:text-primary bg-control/80 hover:bg-control-hover rounded-lg border border-card transition disabled:opacity-50 disabled:cursor-not-allowed"
              onMouseEnter={(e) => show(e, "Refresh dashboard data")}
              onMouseMove={move}
              onMouseLeave={hide}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
            <button
              onClick={() => handleExport("csv")}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-secondary hover:text-primary bg-control/80 hover:bg-control-hover rounded-lg border border-card transition disabled:opacity-50 disabled:cursor-not-allowed"
              onMouseEnter={(e) =>
                show(e, "Export all dashboard data as CSV")
              }
              onMouseMove={move}
              onMouseLeave={hide}
            >
              {exporting === "csv" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              {exporting === "csv" ? "Exporting..." : "CSV"}
            </button>
            <button
              onClick={() => handleExport("json")}
              disabled={exporting !== null}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-secondary hover:text-primary bg-control/80 hover:bg-control-hover rounded-lg border border-card transition disabled:opacity-50 disabled:cursor-not-allowed"
              onMouseEnter={(e) =>
                show(e, "Export all dashboard data as JSON")
              }
              onMouseMove={move}
              onMouseLeave={hide}
            >
              {exporting === "json" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
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
            description="All agent sessions"
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
            tooltipText={
              <MetricList
                header="Sessions"
                rows={[
                  { label: "All time", value: stats.total_sessions.toLocaleString(), tone: "total" },
                  { label: "This year", value: stats.this_year.sessions.toLocaleString() },
                  { label: "This month", value: stats.this_month.sessions.toLocaleString() },
                  { label: "This week", value: stats.this_week.sessions.toLocaleString() },
                  { label: "Projects", value: stats.project_count.toLocaleString(), tone: "muted" },
                ]}
              />
            }
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
          <StatCard
            icon={<Hash className="w-4 h-4" />}
            label="Messages"
            description="User + agent turns"
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
            tooltipText={
              <MetricList
                header="Messages"
                rows={[
                  { label: "All time", value: stats.total_messages.toLocaleString(), tone: "total" },
                  { label: "This year", value: stats.this_year.messages.toLocaleString() },
                  { label: "This month", value: stats.this_month.messages.toLocaleString() },
                  { label: "Avg / session", value: stats.avg_messages_per_session.toFixed(1), tone: "muted" },
                ]}
              />
            }
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
          <StatCard
            icon={<BarChart3 className="w-4 h-4" />}
            label="Tokens"
            description="Input + output tokens"
            value={formatTokens(stats.total_tokens)}
            rows={[
              {
                label: "This Year",
                value: formatTokens(stats.this_year.tokens),
                tooltipText: (
                  <MetricList
                    header="Tokens — this year"
                    rows={[
                      { label: "Input", value: stats.this_year.input_tokens.toLocaleString(), tone: "input" },
                      { label: "Output", value: stats.this_year.output_tokens.toLocaleString(), tone: "output" },
                      { label: "Cache read", value: stats.this_year.cache_read_tokens.toLocaleString(), tone: "cache_read" },
                      { label: "Cache write", value: stats.this_year.cache_write_tokens.toLocaleString(), tone: "cache_write" },
                      { label: "Total", value: stats.this_year.tokens.toLocaleString(), tone: "total" },
                    ]}
                  />
                ),
              },
              {
                label: "This Month",
                value: formatTokens(stats.this_month.tokens),
                tooltipText: (
                  <MetricList
                    header="Tokens — this month"
                    rows={[
                      { label: "Input", value: stats.this_month.input_tokens.toLocaleString(), tone: "input" },
                      { label: "Output", value: stats.this_month.output_tokens.toLocaleString(), tone: "output" },
                      { label: "Cache read", value: stats.this_month.cache_read_tokens.toLocaleString(), tone: "cache_read" },
                      { label: "Cache write", value: stats.this_month.cache_write_tokens.toLocaleString(), tone: "cache_write" },
                      { label: "Total", value: stats.this_month.tokens.toLocaleString(), tone: "total" },
                    ]}
                  />
                ),
              },
              {
                label: "Avg/Session",
                value: formatTokens(Math.round(stats.avg_tokens_per_session)),
                tooltipText: (
                  <MetricList
                    header="Tokens — all time"
                    rows={[
                      { label: "Input", value: stats.total_input_tokens.toLocaleString(), tone: "input" },
                      { label: "Output", value: stats.total_output_tokens.toLocaleString(), tone: "output" },
                      { label: "Cache read", value: stats.total_cache_read_tokens.toLocaleString(), tone: "cache_read" },
                      { label: "Cache write", value: stats.total_cache_write_tokens.toLocaleString(), tone: "cache_write" },
                      { label: "Total", value: stats.total_tokens.toLocaleString(), tone: "total" },
                      { label: "Avg / session", value: Math.round(stats.avg_tokens_per_session).toLocaleString(), tone: "muted" },
                    ]}
                  />
                ),
              },
            ]}
            tooltipText={
              <MetricList
                header="Tokens — all time"
                rows={[
                  { label: "Input", value: stats.total_input_tokens.toLocaleString(), tone: "input" },
                  { label: "Output", value: stats.total_output_tokens.toLocaleString(), tone: "output" },
                  { label: "Cache read", value: stats.total_cache_read_tokens.toLocaleString(), tone: "cache_read" },
                  { label: "Cache write", value: stats.total_cache_write_tokens.toLocaleString(), tone: "cache_write" },
                  { label: "Total", value: stats.total_tokens.toLocaleString(), tone: "total" },
                ]}
              />
            }
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
          <StatCard
            icon={<Clock className="w-4 h-4" />}
            label="Duration"
            description="Total session time"
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
            tooltipText={
              <MetricList
                header="Session wall-clock duration"
                rows={[
                  { label: "All time", value: formatDuration(stats.total_duration), tone: "total" },
                  { label: "This year", value: formatDuration(stats.this_year.duration) },
                  { label: "This month", value: formatDuration(stats.this_month.duration) },
                  { label: "Avg / session", value: formatDuration(stats.avg_duration_per_session), tone: "muted" },
                ]}
              />
            }
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
          <StatCard
            icon={<DollarSign className="w-4 h-4" />}
            label="Estimated Cost"
            description="API pricing estimate"
            value={formatCost(stats.total_cost_usd)}
            rows={[
              {
                label: "This Year",
                value: formatCost(stats.this_year.cost_usd),
              },
              {
                label: "This Month",
                value: formatCost(stats.this_month.cost_usd),
              },
              {
                label: "Avg/Session",
                value: formatCost(stats.avg_cost_per_session),
              },
            ]}
            tooltipText={
              <MetricList
                header="Estimated cost (USD)"
                rows={[
                  { label: "All time", value: formatCost(stats.total_cost_usd), tone: "cost" },
                  { label: "This year", value: formatCost(stats.this_year.cost_usd) },
                  { label: "This month", value: formatCost(stats.this_month.cost_usd) },
                  { label: "Avg / session", value: formatCost(stats.avg_cost_per_session), tone: "muted" },
                ]}
              />
            }
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
        </div>

        {/* Usage Over Time */}
        <div className="rounded-xl border border-card bg-panel/80 p-5">
          <UsageOverTimeChart
            data={stats.daily_stats ?? []}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
        </div>

        {/* Activity Heatmap */}
        <div className="rounded-xl border border-card bg-panel/80 p-5">
          <ActivityHeatmap
            data={stats.daily_activity}
            onHover={show}
            onMove={move}
            onLeave={hide}
          />
        </div>

        {/* Bottom grid: Peak Hours + Project | Agent + Model + Tools */}
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-4">
            <div className="rounded-xl border border-card bg-panel/80 p-5">
              <div className="flex items-center gap-2 mb-3">
                <Clock className="w-4 h-4 text-accent-cyan" />
                <h3
                  className="text-base font-medium text-secondary cursor-default"
                  onMouseEnter={(e) =>
                    show(e, "Distribution of session starts by hour of day")
                  }
                  onMouseMove={move}
                  onMouseLeave={hide}
                >
                  Peak Hours
                </h3>
                <span
                  className="text-xs text-dimmed cursor-default"
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

            <div className="rounded-xl border border-card bg-panel/80 p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <FolderOpen className="w-4 h-4 text-accent-cyan" />
                  <div>
                    <h3
                      className="text-base font-medium text-secondary cursor-default"
                      onMouseEnter={(e) =>
                        show(e, `Per-project breakdown (${allProjectEntries.length} total). Click to filter.`)
                      }
                      onMouseMove={move}
                      onMouseLeave={hide}
                    >
                      Project Activity
                    </h3>
                    <p className="text-xs text-muted mt-0.5">
                      Click a project to view its dedicated dashboard analysis
                    </p>
                  </div>
                </div>
                {hasMoreProjects && (
                  <button
                    onClick={() => setShowAllProjects((v) => !v)}
                    className="px-2.5 py-1 text-xs font-medium text-accent-cyan hover:text-accent-cyan bg-accent-cyan-subtle hover:bg-accent-cyan-muted rounded-md border border-accent-cyan-border transition"
                  >
                    {showAllProjects
                      ? "Top 10"
                      : `All ${allProjectEntries.length}`}
                  </button>
                )}
              </div>
              <div className="space-y-1.5">
                {projectEntries.map(([project, count]) => {
                  const detail = stats.project_details?.[project];
                  return (
                    <ProjectRow
                      key={project}
                      project={project}
                      count={count}
                      detail={detail}
                      max={maxProjectCount}
                      totalSessions={stats.total_sessions}
                      onClick={() => setSelectedProject(project)}
                      onHover={show}
                      onMove={move}
                      onLeave={hide}
                    />
                  );
                })}
                {projectEntries.length === 0 && (
                  <p className="text-sm text-dimmed">No data</p>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            {agentEntries.length > 1 && (
              <div className="rounded-xl border border-card bg-panel/80 p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Bot className="w-4 h-4 text-accent-cyan" />
                  <div>
                    <h3
                      className="text-base font-medium text-secondary cursor-default"
                      onMouseEnter={(e) =>
                        show(e, "Session count breakdown by agent. Click to filter.")
                      }
                      onMouseMove={move}
                      onMouseLeave={hide}
                    >
                      Agent Distribution
                    </h3>
                    <p className="text-xs text-muted mt-0.5">
                      Click an agent to view its dedicated dashboard analysis
                    </p>
                  </div>
                </div>
                <div className="space-y-1">
                  {agentEntries.map(([agent, count]) => (
                    <BarChartRow
                      key={agent}
                      label={agent}
                      value={count}
                      max={maxAgentCount}
                      tooltipText={
                        <MetricList
                          header={agent}
                          rows={[
                            { label: "Sessions", value: count.toLocaleString(), tone: "total" },
                            {
                              label: "Share",
                              value: `${((count / stats.total_sessions) * 100).toFixed(1)}%`,
                              tone: "percent",
                            },
                          ]}
                        />
                      }
                      onClick={() => setSelectedAgent(agent)}
                      onHover={show}
                      onMove={move}
                      onLeave={hide}
                    />
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-xl border border-card bg-panel/80 p-5">
              <div className="flex items-center gap-2 mb-4">
                <Cpu className="w-4 h-4 text-accent-cyan" />
                <h3
                  className="text-base font-medium text-secondary cursor-default"
                  onMouseEnter={(e) =>
                    show(e, "Session count breakdown by AI model")
                  }
                  onMouseMove={move}
                  onMouseLeave={hide}
                >
                  Model Distribution
                </h3>
              </div>
              <ModelDistribution
                data={stats.model_distribution}
                onHover={show}
                onMove={move}
                onLeave={hide}
              />
            </div>

            <div className="rounded-xl border border-card bg-panel/80 p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Wrench className="w-4 h-4 text-accent-cyan" />
                  <h3
                    className="text-base font-medium text-secondary cursor-default"
                    onMouseEnter={(e) =>
                      show(e, toolUsage.length > 0
                        ? `Tool call distribution (${totalToolCalls(toolUsage).toLocaleString()} total, avg ${stats.avg_tool_calls_per_session.toFixed(1)}/session)`
                        : "Loading tool usage data...")
                    }
                    onMouseMove={move}
                    onMouseLeave={hide}
                  >
                    Tool Distribution
                  </h3>
                </div>
                {toolUsage.length > 0 ? (
                  <span className="text-xs text-dimmed">
                    {totalToolCalls(toolUsage).toLocaleString()} total
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-xs text-dimmed">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Loading
                  </span>
                )}
              </div>
              {toolUsage.length > 0 ? (
                <ToolDistribution
                  data={toolUsage}
                  onHover={show}
                  onMove={move}
                  onLeave={hide}
                />
              ) : (
                <div className="flex items-center justify-center py-8 text-xs text-dimmed">
                  Loading tool usage across all sessions...
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Warming progress bar shown while cache is loading ── */

function WarmingProgressBar() {
  const { fetchWithToken } = useAppContext();
  const api = useMemo(() => dashboardClient(fetchWithToken), [fetchWithToken]);
  const [status, setStatus] = useState<Awaited<ReturnType<typeof api.warmingStatus>>>(null);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    const poll = () => {
      api.warmingStatus().then((data) => {
        if (data) setStatus(data);
      }).catch(() => {});
    };
    poll();
    timerRef.current = setInterval(poll, DASHBOARD_POLL_INTERVAL_MS);
    return () => clearInterval(timerRef.current);
  }, [api]);

  const total = status?.total ?? 0;
  const loaded = status?.loaded ?? 0;
  const pct = total > 0 ? Math.round((loaded / total) * 100) : 0;

  return (
    <div className="flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-5 w-72">
        <LoadingSpinnerRings color="cyan" />
        <div className="w-full space-y-2">
          <div className="flex items-center justify-between text-xs text-secondary">
            <span>Loading sessions</span>
            {total > 0 && (
              <span className="tabular-nums">
                {loaded}/{total} ({pct}%)
              </span>
            )}
          </div>
          <div className="h-1.5 w-full rounded-full bg-control overflow-hidden">
            <div
              className="h-full rounded-full bg-accent-cyan transition-all duration-500 ease-out"
              style={{ width: total > 0 ? `${pct}%` : "0%" }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

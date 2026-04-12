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
import { useCallback, useEffect, useState } from "react";
import { useAppContext } from "../../app";
import type { DashboardStats, ToolUsageStat } from "../../types";
import { formatTokens, formatDuration, formatCost, baseProjectName } from "../../utils";
import { LoadingSpinner } from "../loading-spinner";
import { ActivityHeatmap } from "./activity-heatmap";
import { BarRow } from "./bar-row";
import { ModelDistribution } from "./model-distribution-chart";
import { PeakHoursChart } from "./peak-hours-chart";
import { StatCard } from "./stat-card";
import { ToolDistribution, totalToolCalls } from "./tool-distribution-chart";
import { Tooltip, useTooltip } from "./chart-tooltip";
import { UsageOverTimeChart } from "./usage-over-time-chart";
import { ProjectRow, DEFAULT_PROJECT_COUNT } from "./project-row";

interface DashboardViewProps {
  cache: { stats: DashboardStats; toolUsage: ToolUsageStat[] } | null;
}

export function DashboardView({ cache }: DashboardViewProps) {
  const { fetchWithToken } = useAppContext();
  const [stats, setStats] = useState<DashboardStats | null>(cache?.stats ?? null);
  const [toolUsage, setToolUsage] = useState<ToolUsageStat[]>(cache?.toolUsage ?? []);
  const [loading, setLoading] = useState(!cache);
  const [error, setError] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null);
  const [showAllProjects, setShowAllProjects] = useState(false);
  const { tip, show, move, hide } = useTooltip();

  // Populate from cache when it arrives (background preload)
  useEffect(() => {
    if (cache && !stats) {
      setStats(cache.stats);
      setToolUsage(cache.toolUsage);
      setLoading(false);
    }
  }, [cache, stats]);

  // Fallback: fetch directly if cache hasn't arrived after mount
  useEffect(() => {
    if (cache || stats || selectedProject || selectedAgent) return;
    Promise.all([
      fetchWithToken("/api/analysis/dashboard")
        .then((r) => (r.ok ? r.json() : null)),
      fetchWithToken("/api/analysis/tool-usage")
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
    ])
      .then(([dashData, toolData]: [DashboardStats | null, ToolUsageStat[]]) => {
        if (dashData) {
          setStats(dashData);
          setToolUsage(toolData);
        } else {
          setError("Failed to load dashboard data");
        }
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [cache, stats, fetchWithToken, selectedProject]);

  // Fetch on-demand when filtering by project or agent
  useEffect(() => {
    if (!selectedProject && !selectedAgent) return;

    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (selectedProject) params.set("project_path", selectedProject);
    if (selectedAgent) params.set("agent_name", selectedAgent);

    Promise.all([
      fetchWithToken(`/api/analysis/dashboard?${params}`)
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        }),
      fetchWithToken(`/api/analysis/tool-usage?${params}`)
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
    ])
      .then(([dashData, toolData]: [DashboardStats, ToolUsageStat[]]) => {
        setStats(dashData);
        setToolUsage(toolData);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [fetchWithToken, selectedProject, selectedAgent]);

  // Restore cached global data when clearing filters
  const handleClearFilters = useCallback(() => {
    setSelectedProject(null);
    setSelectedAgent(null);
    if (cache) {
      setStats(cache.stats);
      setToolUsage(cache.toolUsage);
    }
  }, [cache]);


  const handleExport = async (format: "csv" | "json") => {
    setExporting(format);
    const params = new URLSearchParams({ format });
    if (selectedProject) params.set("project_path", selectedProject);
    if (selectedAgent) params.set("agent_name", selectedAgent);
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
    return <LoadingSpinner label="Loading dashboard" />;
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
              <span
                className="flex items-center gap-1.5 text-xs text-dimmed"
                onMouseEnter={(e) =>
                  show(e, "Stats are cached for 1 hour. Data reflects sessions available at this time.")
                }
                onMouseMove={move}
                onMouseLeave={hide}
              >
                <RefreshCw className="w-3 h-3" />
                Updated {new Date(stats.cached_at).toLocaleTimeString()}
              </span>
            )}
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
            description="Input + output tokens"
            value={formatTokens(stats.total_tokens)}
            rows={[
              {
                label: "This Year",
                value: formatTokens(stats.this_year.tokens),
                tooltipText: [
                  `This Year: ${stats.this_year.tokens.toLocaleString()}`,
                  `Input: ${stats.this_year.input_tokens.toLocaleString()}`,
                  `Output: ${stats.this_year.output_tokens.toLocaleString()}`,
                  `Cache Read: ${stats.this_year.cache_read_tokens.toLocaleString()}`,
                  `Cache Write: ${stats.this_year.cache_creation_tokens.toLocaleString()}`,
                ].join("\n"),
              },
              {
                label: "This Month",
                value: formatTokens(stats.this_month.tokens),
                tooltipText: [
                  `This Month: ${stats.this_month.tokens.toLocaleString()}`,
                  `Input: ${stats.this_month.input_tokens.toLocaleString()}`,
                  `Output: ${stats.this_month.output_tokens.toLocaleString()}`,
                  `Cache Read: ${stats.this_month.cache_read_tokens.toLocaleString()}`,
                  `Cache Write: ${stats.this_month.cache_creation_tokens.toLocaleString()}`,
                ].join("\n"),
              },
              {
                label: "Avg/Session",
                value: formatTokens(Math.round(stats.avg_tokens_per_session)),
                tooltipText: [
                  `Avg/Session: ${Math.round(stats.avg_tokens_per_session).toLocaleString()}`,
                  `Total Input: ${stats.total_input_tokens.toLocaleString()}`,
                  `Total Output: ${stats.total_output_tokens.toLocaleString()}`,
                  `Total Cache Read: ${stats.total_cache_read_tokens.toLocaleString()}`,
                  `Total Cache Write: ${stats.total_cache_creation_tokens.toLocaleString()}`,
                ].join("\n"),
              },
            ]}
            tooltipText={[
              `Total: ${stats.total_tokens.toLocaleString()}`,
              `Input: ${stats.total_input_tokens.toLocaleString()}`,
              `Output: ${stats.total_output_tokens.toLocaleString()}`,
              `Cache: ${stats.total_cache_tokens.toLocaleString()}`,
            ].join("\n")}
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
            tooltipText={[
              `Total: ${formatCost(stats.total_cost_usd)}`,
              `This Year: ${formatCost(stats.this_year.cost_usd)}`,
              `This Month: ${formatCost(stats.this_month.cost_usd)}`,
              `Avg/Session: ${formatCost(stats.avg_cost_per_session)}`,
            ].join("\n")}
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

            {toolUsage.length > 0 && (
              <div className="rounded-xl border border-card bg-panel/80 p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Wrench className="w-4 h-4 text-accent-cyan" />
                    <h3
                      className="text-base font-medium text-secondary cursor-default"
                      onMouseEnter={(e) =>
                        show(e, `Tool call distribution (${totalToolCalls(toolUsage).toLocaleString()} total, avg ${stats.avg_tool_calls_per_session.toFixed(1)}/session)`)
                      }
                      onMouseMove={move}
                      onMouseLeave={hide}
                    >
                      Tool Distribution
                    </h3>
                  </div>
                  <span className="text-xs text-dimmed">
                    {totalToolCalls(toolUsage).toLocaleString()} total
                  </span>
                </div>
                <ToolDistribution
                  data={toolUsage}
                  onHover={show}
                  onMove={move}
                  onLeave={hide}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

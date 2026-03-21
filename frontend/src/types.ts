export type AgentType = "claude_code" | "codex" | "gemini";
export type OSPlatform = "macos" | "linux" | "windows";

export interface Agent {
  name: string;
  version?: string | null;
  model_name?: string | null;
}

export interface FinalMetrics {
  duration: number;
  total_steps?: number | null;
  tool_call_count: number;
  total_prompt_tokens?: number | null;
  total_completion_tokens?: number | null;
  total_cache_write: number;
  total_cache_read: number;
  total_cost_usd?: number | null;
}

export interface TrajectoryRef {
  session_id: string;
  step_id?: string | null;
  tool_call_id?: string | null;
}

export interface Metrics {
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  cache_creation_tokens: number;
  cost_usd?: number | null;
}

export interface ToolCall {
  tool_call_id: string;
  function_name: string;
  arguments: unknown;
}

export interface ObservationResult {
  source_call_id?: string | null;
  content?: string | null;
  subagent_trajectory_ref?: TrajectoryRef[] | null;
}

export interface Observation {
  results: ObservationResult[];
}

export interface Step {
  step_id: string;
  timestamp?: string | null;
  source: "user" | "agent" | "system";
  model_name?: string | null;
  message: string;
  reasoning_content?: string | null;
  tool_calls: ToolCall[];
  observation?: Observation | null;
  metrics?: Metrics | null;
  is_copied_context?: boolean | null;
  extra?: Record<string, unknown> | null;
}

export interface Trajectory {
  schema_version: string;
  session_id: string;
  project_path?: string | null;
  first_message?: string | null;
  agent: Agent;
  final_metrics?: FinalMetrics | null;
  last_trajectory_ref?: TrajectoryRef | null;
  parent_trajectory_ref?: TrajectoryRef | null;
  extra?: Record<string, unknown> | null;
  steps?: Step[];
  timestamp?: string | null;
}

export interface UploadCommands {
  command: string;
  description: string;
}

export interface UploadResult {
  files_received: number;
  sessions_parsed: number;
  steps_stored: number;
  skipped: number;
  errors: Array<{ filename: string; error: string }>;
}

export interface ToolUsageStat {
  tool_name: string;
  call_count: number;
  avg_per_session: number;
  error_rate: number;
}

export interface TimePattern {
  hour_distribution: Record<number, number>;
  weekday_distribution: Record<number, number>;
  avg_session_duration: number;
  avg_steps_per_session: number;
}

export interface UserPreferenceResult {
  source_name: string;
  session_count: number;
  tool_usage: ToolUsageStat[];
  time_pattern: TimePattern;
  model_distribution: Record<string, number>;
  project_distribution: Record<string, number>;
  top_tool_sequences: string[][];
}

export interface DonateResult {
  total: number;
  donated: number;
  errors: Array<{ session_id: string; error: string }>;
}

export interface DailyStat {
  date: string;
  session_count: number;
  total_messages: number;
  total_tokens: number;
  total_duration: number;
  total_duration_hours: number;
}

export interface PeriodStats {
  sessions: number;
  messages: number;
  tokens: number;
  tool_calls: number;
  duration: number;
}

export interface DashboardStats {
  total_sessions: number;
  total_messages: number;
  total_tokens: number;
  total_tool_calls: number;
  total_duration: number;
  total_duration_hours: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_tokens: number;
  this_year: PeriodStats;
  this_month: PeriodStats;
  this_week: PeriodStats;
  avg_messages_per_session: number;
  avg_tokens_per_session: number;
  avg_tool_calls_per_session: number;
  avg_duration_per_session: number;
  project_count: number;
  daily_activity: Record<string, number>;
  daily_stats: DailyStat[];
  model_distribution: Record<string, number>;
  agent_distribution: Record<string, number>;
  project_distribution: Record<string, number>;
  hourly_distribution: Record<number, number>;
  weekday_hour_heatmap: Record<string, number>;
  timezone: string;
}

export type ToolType =
  | "bash"
  | "edit"
  | "read"
  | "search"
  | "communication"
  | "task"
  | "think"
  | "other";

export const TOOL_TYPE_COLORS: Record<ToolType, string> = {
  bash: "bg-yellow-400",
  edit: "bg-green-500",
  read: "bg-blue-600",
  search: "bg-sky-300",
  communication: "bg-orange-400",
  task: "bg-purple-400",
  think: "bg-gray-400",
  other: "bg-gray-300",
};

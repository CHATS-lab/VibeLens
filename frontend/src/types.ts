export type DataSourceType = "local" | "huggingface" | "mongodb";
export type DataTargetType = "mongodb" | "huggingface";

export interface ToolCall {
  id: string;
  name: string;
  input: unknown;
  output?: string;
  is_error: boolean;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
}

export interface ContentBlock {
  type: "text" | "thinking" | "tool_use" | "tool_result";
  text?: string;
  thinking?: string;
  id?: string;
  name?: string;
  input?: unknown;
  tool_use_id?: string;
  content?: string | ContentBlock[];
  is_error?: boolean;
}

export interface Message {
  uuid: string;
  session_id: string;
  parent_uuid: string;
  role: "user" | "assistant" | "system";
  type: string;
  content: string | ContentBlock[];
  thinking?: string;
  model: string;
  timestamp: string;
  is_sidechain: boolean;
  usage?: TokenUsage;
  tool_calls: ToolCall[];
}

export interface SessionSummary {
  session_id: string;
  project_id: string;
  project_name: string;
  timestamp: string;
  duration: number;
  message_count: number;
  tool_call_count: number;
  models: string[];
  first_message: string;
  source_type: DataSourceType;
  source_name?: string;
  source_host?: string;
  total_input_tokens?: number;
  total_output_tokens?: number;
  total_cache_read?: number;
  total_cache_write?: number;
}

export interface SessionDetail {
  summary: SessionSummary;
  messages: Message[];
}

export interface PushResult {
  total: number;
  uploaded: number;
  skipped: number;
  errors: Array<{ session_id: string; error: string }>;
}

export interface PullResult {
  repo_id: string;
  sessions_imported: number;
  messages_imported: number;
  skipped: number;
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
  avg_messages_per_session: number;
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

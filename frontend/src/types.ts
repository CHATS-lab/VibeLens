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

export interface ContentPart {
  type: "text" | "image" | "pdf";
  text?: string | null;
  source?: { media_type: string; base64: string; path?: string } | null;
}

export interface ObservationResult {
  source_call_id?: string | null;
  content?: string | ContentPart[] | null;
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
  message: string | ContentPart[];
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
  continued_trajectory_ref?: TrajectoryRef | null;
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
  total_cost_usd: number;
}

export interface PeriodStats {
  sessions: number;
  messages: number;
  tokens: number;
  tool_calls: number;
  duration: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cost_usd: number;
}

export interface ProjectDetail {
  sessions: number;
  messages: number;
  tokens: number;
  cost_usd: number;
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
  total_cache_read_tokens: number;
  total_cache_creation_tokens: number;
  this_year: PeriodStats;
  this_month: PeriodStats;
  this_week: PeriodStats;
  avg_messages_per_session: number;
  avg_tokens_per_session: number;
  avg_tool_calls_per_session: number;
  avg_duration_per_session: number;
  total_cost_usd: number;
  cost_by_model: Record<string, number>;
  avg_cost_per_session: number;
  project_count: number;
  daily_activity: Record<string, number>;
  daily_stats: DailyStat[];
  model_distribution: Record<string, number>;
  agent_distribution: Record<string, number>;
  project_distribution: Record<string, number>;
  project_details: Record<string, ProjectDetail>;
  hourly_distribution: Record<number, number>;
  weekday_hour_heatmap: Record<string, number>;
  timezone: string;
}

export interface ToolEdge {
  source_tool_call_id: string;
  target_tool_call_id: string;
  relation: string;
  shared_resource: string;
}

export interface ToolDependencyGraph {
  session_id: string;
  nodes: string[];
  edges: ToolEdge[];
  root_nodes: string[];
}

export interface PhaseSegment {
  start_index: number;
  end_index: number;
  phase: string;
  dominant_tool_category: string;
  tool_call_count: number;
}

export interface FlowData {
  session_id: string;
  tool_graph: ToolDependencyGraph;
  phase_segments: PhaseSegment[];
}

export interface FrictionCost {
  affected_steps: number;
  affected_tokens: number | null;
  affected_time_seconds: number | null;
}

export interface StepRef {
  session_id: string;
  start_step_id: string;
  end_step_id: string | null;
}

export interface Mitigation {
  action_type: string;
  target: string;
  content: string;
}

export interface FrictionEvent {
  friction_id: string;
  friction_type: string;
  span_ref: StepRef;
  severity: number;
  user_intention: string;
  friction_detail: string;
  claude_helpfulness: number;
  mitigations: Mitigation[];
  estimated_cost: FrictionCost;
}

export interface TypeSummary {
  friction_type: string;
  count: number;
  affected_sessions: number;
  avg_severity: number;
  total_estimated_cost: FrictionCost;
  description?: string | null;
}

export interface FrictionAnalysisResult {
  analysis_id: string | null;
  title?: string | null;
  events: FrictionEvent[];
  summary: string;
  top_mitigation: Mitigation | null;
  type_summary: TypeSummary[];
  cross_batch_patterns?: string[];
  session_ids: string[];
  sessions_skipped: string[];
  batch_count: number;
  backend_id: string;
  model: string;
  cost_usd: number | null;
  created_at: string;
}

export interface FrictionMeta {
  analysis_id: string;
  title?: string | null;
  session_ids: string[];
  event_count: number;
  summary_preview: string;
  created_at: string;
  model: string;
  cost_usd: number | null;
  batch_count: number;
}

export interface LLMStatus {
  available: boolean;
  backend_id: string;
  model: string | null;
  api_key_masked: string | null;
  base_url: string | null;
  timeout: number;
  max_tokens: number;
}

export interface SkillSource {
  source_type: string;
  source_path: string;
}

export interface SkillSourceInfo {
  key: string;
  label: string;
  skill_count: number;
  skills_dir: string;
}

export interface SkillInfo {
  name: string;
  description: string;
  sources: SkillSource[];
  central_path: string | null;
  content_hash: string;
  metadata: Record<string, unknown>;
  skill_targets: string[];
}

export interface FeaturedSkill {
  slug: string;
  name: string;
  summary: string;
  downloads: number;
  stars: number;
  category: string;
  tags: string[];
  source_url: string;
  updated_at: string;
}

export interface FeaturedSkillsResponse {
  updated_at: string | null;
  total: number;
  categories: string[];
  skills: FeaturedSkill[];
}

export type SkillMode = "retrieval" | "creation" | "evolution";

export interface WorkflowPattern {
  title: string;
  description: string;
  pain_point: string;
  example_refs: StepRef[];
  frequency: number;
}

export interface SkillRecommendation {
  skill_name: string;
  match_reason: string;
  confidence: number;
}

export interface SkillCreation {
  name: string;
  description: string;
  skill_md_content: string;
  rationale: string;
}

export interface SkillEdit {
  kind: string;
  target: string;
  replacement: string | null;
  rationale: string;
}

export interface SkillEvolutionSuggestion {
  skill_name: string;
  edits: SkillEdit[];
  rationale: string;
}

export interface SkillAnalysisResult {
  analysis_id: string | null;
  mode: SkillMode;
  workflow_patterns: WorkflowPattern[];
  recommendations: SkillRecommendation[];
  generated_skills: SkillCreation[];
  evolution_suggestions: SkillEvolutionSuggestion[];
  summary: string;
  user_profile: string;
  session_ids: string[];
  sessions_skipped: string[];
  backend_id: string;
  model: string;
  cost_usd: number | null;
  created_at: string;
}

export interface SkillAnalysisMeta {
  analysis_id: string;
  mode: SkillMode;
  session_ids: string[];
  pattern_count: number;
  summary_preview: string;
  created_at: string;
  model: string;
  cost_usd: number | null;
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

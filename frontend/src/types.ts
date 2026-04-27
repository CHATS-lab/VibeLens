export type AgentType =
  | "claude"
  | "claude_web"
  | "codebuddy"
  | "codex"
  | "copilot"
  | "cursor"
  | "dataclaw"
  | "gemini"
  | "hermes"
  | "kilo"
  | "kiro"
  | "openclaw"
  | "opencode";
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
  total_cache_write_tokens: number;
  total_cache_read_tokens: number;
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
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd?: number | null;
}

export interface ToolCall {
  tool_call_id: string;
  function_name: string;
  arguments: unknown;
  // True when the tool call invokes a packaged Skill (claude/codebuddy
  // 'Skill', gemini 'activate_skill', opencode/kilo 'skill'). VibeLens
  // extension; absent on agents whose Skills are system-prompt injections
  // (cursor, kiro).
  is_skill?: boolean | null;
}

export interface ContentPart {
  type: "text" | "image" | "pdf";
  text?: string | null;
  source?: { media_type: string; base64: string; path?: string } | null;
}

export interface ObservationResult {
  source_call_id?: string | null;
  content?: string | ContentPart[] | null;
  is_error?: boolean;
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
  // True when this step marks an in-stream context-compaction or
  // truncation boundary. Set by codex / copilot / gemini / opencode /
  // codebuddy / cursor / kiro parsers. The renderer surfaces a divider
  // so the user can see where context was summarised.
  is_compaction?: boolean | null;
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
  prev_trajectory_ref?: TrajectoryRef | null;
  next_trajectory_ref?: TrajectoryRef | null;
  parent_trajectory_ref?: TrajectoryRef | null;
  extra?: Record<string, unknown> | null;
  steps?: Step[];
  created_at?: string | null;
  updated_at?: string | null;
  _upload_id?: string;
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
  secrets_redacted: number;
  paths_anonymized: number;
  pii_redacted: number;
  errors: Array<{ filename: string; error: string }>;
  upload_id?: string;
  zip_sha256?: string;
  deduplicated?: boolean;
  original_upload_id?: string | null;
  original_uploaded_at?: string | null;
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

export interface DonateResult {
  total: number;
  donated: number;
  donation_id: string | null;
  errors: Array<{ session_id: string; error: string }>;
}

export interface DonationHistoryEntry {
  donation_id: string;
  session_count: number;
  donated_at: string;
}

export interface DonationHistoryResponse {
  entries: DonationHistoryEntry[];
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
  cache_write_tokens: number;
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
  total_cache_write_tokens: number;
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
  cached_at: string | null;
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
  title: string;
  action: string;
  rationale: string;
  confidence: number;
  addressed_friction_types?: string[];
}

export interface FrictionType {
  type_name: string;
  description: string;
  severity: number;
  example_refs: StepRef[];
  friction_cost: FrictionCost;
}

export interface FrictionAnalysisResult {
  id: string;
  title?: string | null;
  mitigations: Mitigation[];
  friction_types: FrictionType[];
  session_ids: string[];
  skipped_session_ids: string[];
  warnings?: string[];
  backend: string;
  model: string;
  batch_count: number;
  batch_metrics: Metrics[];
  final_metrics: FinalMetrics;
  created_at: string;
  is_example?: boolean;
}

export interface FrictionMeta {
  id: string;
  title?: string | null;
  session_count: number;
  batch_count: number;
  item_count: number;
  backend: string;
  model: string;
  created_at: string;
  final_metrics: FinalMetrics;
  is_example?: boolean;
}

export interface CostEstimate {
  model: string;
  batch_count: number;
  total_input_tokens: number;
  total_output_tokens_budget: number;
  cost_min_usd: number;
  cost_max_usd: number;
  pricing_found: boolean;
  formatted_cost: string;
}


export interface LLMStatus {
  available: boolean;
  backend_id: string;
  model: string | null;
  api_key_masked: string | null;
  base_url: string | null;
  timeout: number;
  max_output_tokens: number;
  pricing: { input_per_mtok: number; output_per_mtok: number } | null;
}

export interface CliModelInfo {
  name: string;
  input_per_mtok?: number;
  output_per_mtok?: number;
}

export interface CliBackendModels {
  models: CliModelInfo[];
  default_model: string | null;
  supports_freeform: boolean;
  available?: boolean;
}

export interface LiteLLMPreset {
  name: string;
  input_per_mtok?: number;
  output_per_mtok?: number;
}

export interface SkillSyncTarget {
  agent: string;
  skill_count: number;
  skills_dir: string;
}

/**
 * Normalized sync-target for any extension type (skill/subagent/command/hook).
 * Per-type endpoints return different field names; the frontend normalizes
 * them to this shape so dialogs and cards can work across types uniformly.
 */
export interface ExtensionSyncTarget {
  agent: string;
  count: number;
  dir: string;
}

/** One entry in an extension's on-disk or remote-GitHub file tree. */
export interface ExtensionTreeEntry {
  path: string;
  kind: "file" | "dir";
  size?: number | null;
}

/** File tree response used by both local (factory) and catalog endpoints. */
export interface ExtensionTreeResponse {
  name: string;
  root: string;
  entries: ExtensionTreeEntry[];
  truncated: boolean;
}

/** Single file content response. */
export interface ExtensionFileResponse {
  path: string;
  content: string;
  truncated: boolean;
}

export interface Skill {
  name: string;
  description: string;
  topics: string[];
  allowed_tools: string[];
  content_hash: string;
  installed_in: string[];
}

export type PersonalizationMode = "recommendation" | "creation" | "evolution";

export interface WorkflowPattern {
  title: string;
  description: string;
  example_refs: StepRef[];
  frequency: number;
}

export interface RecommendationItem {
  extension_id: string;
  extension_type: string;
  name: string;
  repo_name: string;
  source_url: string;
  updated_at: string;
  description: string;
  topics: string[];
  stars: number;
  forks: number;
  license: string;
  language: string;
  install_command: string | null;
}

export interface RankedRecommendationItem {
  item: RecommendationItem;
  rationale: string;
  scores: Record<string, number>;
}

export interface Creation {
  element_type: string;
  element_name: string;
  description: string;
  skill_md_content: string;
  rationale: string;
  tools_used: string[];
  addressed_patterns: string[];
  confidence: number;
}

export interface CreationEdit {
  old_string: string;
  new_string: string;
  replace_all: boolean;
}

export interface Evolution {
  element_type: string;
  element_name: string;
  description: string;
  edits: CreationEdit[];
  rationale: string;
  addressed_patterns: string[];
  confidence: number;
}

export interface PersonalizationResult {
  id: string | null;
  mode: PersonalizationMode;
  title: string;
  workflow_patterns: WorkflowPattern[];
  recommendations: RankedRecommendationItem[];
  user_profile?: UserProfile | null;
  creations: Creation[];
  evolutions: Evolution[];
  session_ids: string[];
  skipped_session_ids: string[];
  warnings?: string[];
  backend: string;
  model: string;
  batch_count?: number;
  final_metrics: PersonalizationFinalMetrics;
  created_at: string;
  is_example?: boolean;
}


export interface PersonalizationFinalMetrics {
  duration: number;
  total_cost_usd: number | null;
  total_prompt_tokens: number | null;
  total_completion_tokens: number | null;
}

export interface PersonalizationMeta {
  id: string;
  mode: PersonalizationMode;
  session_count: number;
  title: string;
  item_count: number;
  backend: string;
  model: string;
  created_at: string;
  batch_count: number;
  final_metrics: PersonalizationFinalMetrics;
  is_example?: boolean;
}

export interface AnalysisJobResponse {
  job_id: string;
  status: "running" | "completed";
  analysis_id?: string | null;
}

export interface AnalysisJobStatus {
  job_id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  analysis_id?: string | null;
  error_message?: string | null;
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

export interface UserProfile {
  domains: string[];
  languages: string[];
  frameworks: string[];
  agent_platforms: string[];
  bottlenecks: string[];
  workflow_style: string;
  search_keywords: string[];
}


export interface ExtensionItemSummary {
  extension_id: string;
  extension_type: string;
  name: string;
  description: string | null;
  topics: string[];
  platforms: string[] | null;
  quality_score: number;
  popularity: number;
  updated_at: string | null;
  source_url: string;
  repo_full_name: string;
  path_in_repo: string | null;
  discovery_source: string;
  stars: number;
  forks: number;
  language: string | null;
  license: string | null;
  install_command: string | null;
  is_file_based: boolean;
}

export interface ExtensionDetail extends ExtensionItemSummary {
  readme_description: string | null;
  repo_description: string | null;
  author: string | null;
  scores: Record<string, number> | null;
  item_metadata: Record<string, string> | null;
  validation_errors: string[] | null;
  author_followers: number | null;
  contributors_count: number | null;
  created_at: string | null;
  discovery_origin: string | null;
}

export interface ExtensionListResponse {
  items: ExtensionItemSummary[];
  total: number;
  page: number;
  per_page: number;
}

export interface ExtensionInstallResponse {
  success: boolean;
  installed_path: string;
  message: string;
}

export interface ExtensionMetaResponse {
  topics: string[];
  has_profile: boolean;
}

import {
  AlignLeft,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  Calendar,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Cpu,
  Database,
  Download,
  FolderOpen,
  GitBranch,
  HardDrive,
  Hash,
  Layers,
  Link2,
  List,
  MessageSquare,
  Shield,
  Wrench,
  Zap,
} from "lucide-react";
import { useMemo } from "react";
import { useAppContext } from "../../app";
import { sessionsClient } from "../../api/sessions";
import { SESSION_ID_SHORT } from "../../constants";
import { useCopyFeedback } from "../../hooks/use-copy-feedback";
import type { Step, Trajectory } from "../../types";
import { baseProjectName, extractUserText, formatDuration } from "../../utils";
import { Tooltip } from "../ui/tooltip";
import {
  CostStat,
  MetaPill,
  TokenStat,
  _lookupFirstMessage,
  formatCreatedTime,
} from "./session-header";
import type { useShareSession } from "./session-share-dialog";

type ViewMode = "concise" | "detail" | "workflow";

interface SessionViewHeaderProps {
  main: Trajectory;
  steps: Step[];
  subAgents: Trajectory[];
  trajectories: Trajectory[];
  sessionCost: number | null;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  headerExpanded: boolean;
  onHeaderExpandedToggle: () => void;
  isSharedView: boolean;
  share: ReturnType<typeof useShareSession>;
  onNavigateSession?: (sessionId: string) => void;
  allSessions?: Trajectory[];
}

export function SessionViewHeader({
  main,
  steps,
  subAgents,
  sessionCost,
  viewMode,
  onViewModeChange,
  headerExpanded,
  onHeaderExpandedToggle,
  isSharedView,
  share,
  onNavigateSession,
  allSessions,
}: SessionViewHeaderProps) {
  const { fetchWithToken } = useAppContext();
  const api = useMemo(() => sessionsClient(fetchWithToken), [fetchWithToken]);
  const { copy: copySessionId, copied: sessionIdCopied } = useCopyFeedback();

  const metrics = main.final_metrics;
  const promptCount = steps.filter(
    (s) =>
      s.source === "user" &&
      !s.extra?.is_skill_output &&
      !s.extra?.is_auto_prompt &&
      extractUserText(s),
  ).length;
  const skillCount = steps.filter(
    (s) => s.source === "user" && s.extra?.is_skill_output,
  ).length;
  const totalTokens =
    (metrics?.total_prompt_tokens || 0) + (metrics?.total_completion_tokens || 0);

  const handleDownload = async () => {
    try {
      const blob = await api.exportJson(main.session_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `vibelens-${main.session_id.slice(0, SESSION_ID_SHORT)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Session download failed:", err);
    }
  };

  return (
    <div className="shrink-0 bg-gradient-to-b from-panel to-panel/80 border-b border-default px-4 py-2">
      <div className="max-w-7xl mx-auto">
        {/* Row 1: Detail toggle + Session ID + Title + Actions */}
        <div className="flex items-center justify-between mb-1 gap-3">
          <div
            className="flex items-center gap-2.5 min-w-0 flex-1 cursor-pointer"
            onClick={onHeaderExpandedToggle}
          >
            <button className="flex items-center gap-0.5 shrink-0 text-xs text-dimmed hover:text-secondary hover:bg-control/30 rounded p-0.5 transition">
              {headerExpanded ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
            </button>
            <MetaPill
              icon={
                sessionIdCopied ? (
                  <Check className="w-3 h-3" />
                ) : (
                  <Hash className="w-3 h-3" />
                )
              }
              label={main.session_id.slice(0, SESSION_ID_SHORT)}
              color="text-accent-cyan"
              bg="bg-accent-cyan-muted border border-accent-cyan"
              tooltip={
                sessionIdCopied ? "Copied!" : `Click to copy: ${main.session_id}`
              }
              onClick={(event) => {
                // Stop the outer "expand header" click from firing too.
                event.stopPropagation();
                void copySessionId(main.session_id);
              }}
            />
            <Tooltip text={main.first_message || "Session"} className="min-w-0">
              <h2 className="text-lg font-semibold text-primary truncate">
                {main.first_message || "Session"}
              </h2>
            </Tooltip>
          </div>
          <div className="flex items-center gap-1 shrink-0 ml-3">
            <ViewModeToggle viewMode={viewMode} onChange={onViewModeChange} />
            <div className="w-px h-6 bg-hover/50 mx-1" />
            {!isSharedView && (
              <Tooltip text="Share session link">
                <button
                  {...share.buttonProps}
                  className="p-2 text-muted hover:text-secondary hover:bg-control rounded transition text-xs disabled:opacity-50"
                />
              </Tooltip>
            )}
            <Tooltip text="Download as JSON">
              <button
                onClick={handleDownload}
                className="p-2 text-muted hover:text-secondary hover:bg-control rounded transition text-xs"
              >
                <Download className="w-4 h-4" />
              </button>
            </Tooltip>
          </div>
        </div>

        {headerExpanded && (
          <>
            {/* Row 2: Meta Pills */}
            <div className="flex flex-wrap items-center gap-1.5 mb-3">
              {main.agent.model_name && (
                <MetaPill
                  icon={<Cpu className="w-3 h-3" />}
                  label={`${main.agent.name}@${main.agent.model_name}`}
                  color="text-accent-amber"
                  tooltip="Agent model used for this session"
                />
              )}
              {main.timestamp && (
                <MetaPill
                  icon={<Calendar className="w-3 h-3" />}
                  label={formatCreatedTime(main.timestamp)}
                  color="text-secondary"
                  tooltip="Session start time"
                />
              )}
              {metrics && (
                <MetaPill
                  icon={<Clock className="w-3 h-3" />}
                  label={formatDuration(metrics.duration)}
                  color="text-accent-cyan"
                  tooltip="Total wall-clock duration of this session"
                />
              )}
              <MetaPill
                icon={<MessageSquare className="w-3 h-3" />}
                label={`${promptCount} prompt${promptCount !== 1 ? "s" : ""}`}
                color="text-accent-blue"
                tooltip="User prompts: messages typed by the human operator"
              />
              {skillCount > 0 && (
                <MetaPill
                  icon={<Zap className="w-3 h-3" />}
                  label={`${skillCount} skill${skillCount !== 1 ? "s" : ""}`}
                  color="text-accent-amber"
                  tooltip="Skill invocations: reusable prompts auto-injected by the agent"
                />
              )}
              {metrics && (
                <>
                  <MetaPill
                    icon={<Wrench className="w-3 h-3" />}
                    label={`${metrics.tool_call_count} tools`}
                    color="text-accent-amber"
                    tooltip="Total tool calls made by the agent (Bash, Read, Edit, etc.)"
                  />
                  {metrics.total_steps && (
                    <MetaPill
                      icon={<Layers className="w-3 h-3" />}
                      label={`${metrics.total_steps} steps`}
                      color="text-secondary"
                      tooltip="Total conversation steps including user, agent, and system turns"
                    />
                  )}
                </>
              )}
              {subAgents.length > 0 && (
                <MetaPill
                  icon={<Bot className="w-3 h-3" />}
                  label={`${subAgents.length} sub-agent${subAgents.length !== 1 ? "s" : ""}`}
                  color="text-accent-violet"
                  tooltip="Sub-agent tasks spawned during this session"
                />
              )}
              {main.project_path && (
                <MetaPill
                  icon={<FolderOpen className="w-3 h-3" />}
                  label={baseProjectName(main.project_path)}
                  color="text-secondary"
                  tooltip={main.project_path}
                />
              )}
              {!!main.extra?._anonymized && (
                <MetaPill
                  icon={<Shield className="w-3 h-3" />}
                  label="Redacted"
                  color="text-accent-emerald"
                  tooltip={`Anonymized: ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.secrets_redacted ?? 0} secrets, ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.paths_anonymized ?? 0} paths, ${(main.extra?._anonymize_stats as Record<string, number> | undefined)?.pii_redacted ?? 0} PII`}
                />
              )}
            </div>

            {(main.prev_trajectory_ref ||
              main.next_trajectory_ref ||
              main.parent_trajectory_ref) && (
              <ContinuationChainNav
                main={main}
                onNavigateSession={onNavigateSession}
                allSessions={allSessions}
              />
            )}

            {metrics &&
              (metrics.total_prompt_tokens != null ||
                metrics.total_completion_tokens != null) && (
                <div
                  className={`grid ${
                    sessionCost != null ? "grid-cols-6" : "grid-cols-5"
                  } gap-2 text-xs`}
                >
                  <TokenStat
                    icon={<ArrowUpRight className="w-3 h-3" />}
                    label="Input"
                    value={metrics.total_prompt_tokens || 0}
                    color="text-accent-cyan"
                    tooltip="Prompt tokens sent to the model"
                  />
                  <TokenStat
                    icon={<ArrowDownRight className="w-3 h-3" />}
                    label="Output"
                    value={metrics.total_completion_tokens || 0}
                    color="text-accent-cyan"
                    tooltip="Completion tokens generated by the model"
                  />
                  <TokenStat
                    icon={<Database className="w-3 h-3" />}
                    label="Cache Read"
                    value={metrics.total_cache_read || 0}
                    color="text-accent-emerald"
                    tooltip="Tokens served from prompt cache (reduced cost)"
                  />
                  <TokenStat
                    icon={<HardDrive className="w-3 h-3" />}
                    label="Cache Write"
                    value={metrics.total_cache_write || 0}
                    color="text-accent-violet"
                    tooltip="Tokens written to prompt cache for future reuse"
                  />
                  <TokenStat
                    icon={<BarChart3 className="w-3 h-3" />}
                    label="Total"
                    value={totalTokens}
                    color="text-accent-amber"
                    tooltip="Total tokens (input + output)"
                  />
                  {sessionCost != null && <CostStat value={sessionCost} />}
                </div>
              )}
          </>
        )}
      </div>
    </div>
  );
}

function ViewModeToggle({
  viewMode,
  onChange,
}: {
  viewMode: ViewMode;
  onChange: (mode: ViewMode) => void;
}) {
  const options: { mode: ViewMode; icon: typeof AlignLeft; label: string; tooltip: string }[] = [
    { mode: "concise", icon: AlignLeft, label: "Concise", tooltip: "Messages only, tool calls hidden" },
    { mode: "detail", icon: List, label: "Detail", tooltip: "Full conversation with all tool calls" },
    { mode: "workflow", icon: GitBranch, label: "Workflow", tooltip: "Visual diagram of the agent's steps" },
  ];
  return (
    <div data-tour="view-modes" className="flex rounded-lg bg-control p-0.5 mr-2 w-[280px]">
      {options.map(({ mode, icon: Icon, label, tooltip }) => (
        <Tooltip key={mode} text={tooltip} className="flex-1">
          <button
            onClick={() => onChange(mode)}
            className={`w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md transition ${
              viewMode === mode
                ? "bg-panel text-primary font-semibold shadow-sm"
                : "text-muted hover:text-secondary"
            }`}
          >
            <Icon className="w-3 h-3" />
            {label}
          </button>
        </Tooltip>
      ))}
    </div>
  );
}

function ContinuationChainNav({
  main,
  onNavigateSession,
  allSessions,
}: {
  main: Trajectory;
  onNavigateSession?: (sessionId: string) => void;
  allSessions?: Trajectory[];
}) {
  const pillClass =
    "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-accent-violet-subtle border border-accent-violet text-xs text-accent-violet hover:bg-violet-100 dark:hover:bg-violet-800/40 hover:border-violet-300 dark:hover:border-violet-600/50 transition-colors";
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-3">
      {main.parent_trajectory_ref && onNavigateSession && (
        <button
          onClick={() => onNavigateSession(main.parent_trajectory_ref!.session_id)}
          className={pillClass}
          title={`Navigate to parent session: ${main.parent_trajectory_ref.session_id}`}
        >
          <Link2 className="w-3 h-3" />
          <span>Spawned by</span>
          <span className="text-accent-violet font-medium truncate max-w-[200px]">
            {_lookupFirstMessage(main.parent_trajectory_ref.session_id, allSessions)}
          </span>
        </button>
      )}
      {main.prev_trajectory_ref && onNavigateSession && (
        <button
          onClick={() => onNavigateSession(main.prev_trajectory_ref!.session_id)}
          className={pillClass}
          title={`Navigate to previous session: ${main.prev_trajectory_ref.session_id}`}
        >
          <ArrowUpRight className="w-3 h-3" />
          <span>Continued from</span>
          <span className="text-accent-violet font-medium truncate max-w-[200px]">
            {_lookupFirstMessage(main.prev_trajectory_ref.session_id, allSessions)}
          </span>
        </button>
      )}
      {main.next_trajectory_ref && onNavigateSession && (
        <button
          onClick={() => onNavigateSession(main.next_trajectory_ref!.session_id)}
          className={pillClass}
          title={`Navigate to next session: ${main.next_trajectory_ref.session_id}`}
        >
          <ArrowDownRight className="w-3 h-3" />
          <span>Continues in</span>
          <span className="text-accent-violet font-medium truncate max-w-[200px]">
            {_lookupFirstMessage(main.next_trajectory_ref.session_id, allSessions)}
          </span>
        </button>
      )}
    </div>
  );
}

import { useState } from "react";
import { Bot, GitBranch, MessageSquare } from "lucide-react";
import { extractUserText, truncate } from "../../utils";
import { ResizeHandle } from "../resize-handle";
import type { Step, Trajectory } from "../../types";
import type { FlowPhaseGroup } from "./flow-layout";
import { TOGGLE_CONTAINER, TOGGLE_BUTTON_BASE, TOGGLE_ACTIVE, TOGGLE_INACTIVE } from "../../styles";

const PREVIEW_MAX_CHARS = 80;
const MIN_PROMPTS_FOR_NAV = 1;

type NavMode = "prompts" | "sub-agents";

interface PromptEntry {
  turnNumber: number;
  stepId: string;
  preview: string;
}

const PHASE_NAV_STYLE: Record<string, { dot: string; text: string }> = {
  exploration: { dot: "bg-blue-400", text: "text-blue-400" },
  implementation: { dot: "bg-emerald-400", text: "text-emerald-400" },
  debugging: { dot: "bg-red-400", text: "text-red-400" },
  verification: { dot: "bg-amber-400", text: "text-amber-400" },
  planning: { dot: "bg-violet-400", text: "text-violet-400" },
  mixed: { dot: "bg-zinc-500", text: "text-zinc-400" },
};

const CATEGORY_LABELS: Record<string, string> = {
  file_read: "read",
  file_write: "write",
  shell: "shell",
  search: "search",
  web: "web",
  agent: "agent",
  task: "task",
  other: "other",
};

interface PromptNavPanelProps {
  steps: Step[];
  subAgents: Trajectory[];
  activeStepId: string | null;
  onNavigate: (stepId: string) => void;
  width: number;
  onResize: (delta: number) => void;
  viewMode: "timeline" | "flow";
  flowPhases?: FlowPhaseGroup[];
  activePhaseIdx?: number | null;
  onPhaseNavigate?: (phaseIdx: number) => void;
}

function buildPromptEntries(steps: Step[]): PromptEntry[] {
  const entries: PromptEntry[] = [];
  let turnNumber = 0;

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    if (step.source !== "user") continue;
    if (step.extra?.is_skill_output) continue;

    const text = extractUserText(step);
    if (!text) continue;

    turnNumber++;

    entries.push({
      turnNumber,
      stepId: step.step_id,
      preview: truncate(text.replace(/\n/g, " "), PREVIEW_MAX_CHARS),
    });
  }

  return entries;
}

export function PromptNavPanel({
  steps,
  subAgents,
  activeStepId,
  onNavigate,
  width,
  onResize,
  viewMode,
  flowPhases,
  activePhaseIdx,
  onPhaseNavigate,
}: PromptNavPanelProps) {
  const entries = buildPromptEntries(steps);
  const hasPrompts = entries.length >= MIN_PROMPTS_FOR_NAV;
  const hasSubAgents = subAgents.length > 0;
  const hasFlowPhases = viewMode === "flow" && flowPhases && flowPhases.length > 0;

  const [navMode, setNavMode] = useState<NavMode>("prompts");

  if (!hasPrompts && !hasSubAgents && !hasFlowPhases) return null;

  const handleSubAgentNavigate = (sessionId: string) => {
    const el = document.getElementById(`subagent-${sessionId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Flow mode: show phases panel
  if (hasFlowPhases) {
    return (
      <div
        style={{ width }}
        className="hidden xl:flex relative shrink-0 h-full flex-col border-l border-zinc-800 bg-zinc-900/50"
      >
        <ResizeHandle side="right" onResize={onResize} />
        <div className="shrink-0 px-3 pt-3 pb-2">
          <div className="flex items-center gap-1.5 text-sm text-zinc-300">
            <GitBranch className="w-3.5 h-3.5" />
            <span className="font-medium">Phases</span>
            <span className="text-zinc-500">({flowPhases!.length})</span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <div className="space-y-1">
            {flowPhases!.map((phase, idx) => {
              const isActive = activePhaseIdx === idx;
              const style = PHASE_NAV_STYLE[phase.phase] || PHASE_NAV_STYLE.mixed;
              const catLabel = CATEGORY_LABELS[phase.dominantCategory] || phase.dominantCategory;
              return (
                <button
                  key={idx}
                  onClick={() => onPhaseNavigate?.(idx)}
                  className={`w-full text-left px-2 py-2 rounded-md transition-colors text-sm group ${
                    isActive
                      ? "bg-cyan-500/15 border border-cyan-500/30"
                      : "hover:bg-zinc-800/60 border border-transparent"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`w-2 h-2 rounded-full ${style.dot}`} />
                    <span
                      className={`text-[11px] font-bold uppercase tracking-wider ${
                        isActive ? "text-cyan-300" : style.text
                      }`}
                    >
                      {phase.phase}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-zinc-400 pl-4">
                    <span>{phase.cards.length} step{phase.cards.length !== 1 ? "s" : ""}</span>
                    <span className="text-zinc-600">·</span>
                    <span>{phase.toolCount} tool{phase.toolCount !== 1 ? "s" : ""}</span>
                    {phase.toolCount > 0 && (
                      <>
                        <span className="text-zinc-600">·</span>
                        <span className="text-zinc-500">{catLabel}</span>
                      </>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{ width }}
      className="hidden xl:flex relative shrink-0 h-full flex-col border-l border-zinc-800 bg-zinc-900/50"
    >
      <ResizeHandle side="right" onResize={onResize} />

      {/* Mode Toggle */}
      {hasPrompts && hasSubAgents && (
        <div className="shrink-0 px-3 pt-3 pb-2">
          <div className={TOGGLE_CONTAINER}>
            <button
              onClick={() => setNavMode("prompts")}
              className={`${TOGGLE_BUTTON_BASE} ${
                navMode === "prompts" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE
              }`}
            >
              <MessageSquare className="w-3 h-3" />
              Prompts
            </button>
            <button
              onClick={() => setNavMode("sub-agents")}
              className={`${TOGGLE_BUTTON_BASE} ${
                navMode === "sub-agents" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE
              }`}
            >
              <Bot className="w-3 h-3" />
              Agents
            </button>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {/* Prompts view (default, or only view when no sub-agents) */}
        {(navMode === "prompts" || !hasSubAgents) && hasPrompts && (
          <div>
            {!hasSubAgents && (
              <div className="flex items-center gap-1.5 text-sm text-zinc-300 mb-3">
                <MessageSquare className="w-3.5 h-3.5" />
                <span className="font-medium">Prompts</span>
                <span className="text-zinc-500">({entries.length})</span>
              </div>
            )}
            <div className="space-y-1">
              {entries.map((entry) => {
                const isActive = entry.stepId === activeStepId;
                return (
                  <button
                    key={entry.stepId}
                    onClick={() => onNavigate(entry.stepId)}
                    className={`w-full text-left px-2 py-1.5 rounded-md transition-colors text-sm group ${
                      isActive
                        ? "bg-cyan-500/15 border border-cyan-500/30"
                        : "hover:bg-zinc-800/60 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span
                        className={`font-mono font-semibold ${
                          isActive ? "text-cyan-400" : "text-zinc-400 group-hover:text-zinc-300"
                        }`}
                      >
                        #{entry.turnNumber}
                      </span>
                    </div>
                    <p
                      className={`line-clamp-2 leading-snug ${
                        isActive ? "text-cyan-200/80" : "text-zinc-400 group-hover:text-zinc-300"
                      }`}
                    >
                      {entry.preview}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Sub-Agents view */}
        {navMode === "sub-agents" && hasSubAgents && (
          <div>
            <div className="space-y-1">
              {subAgents.map((sub, idx) => {
                const stepCount = sub.steps?.length ?? 0;
                const toolCount = sub.final_metrics?.tool_call_count ?? 0;
                return (
                  <button
                    key={sub.session_id}
                    onClick={() => handleSubAgentNavigate(sub.session_id)}
                    className="w-full text-left px-2 py-1.5 rounded-md transition-colors text-sm group hover:bg-zinc-800/60 border border-transparent"
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="font-mono font-semibold text-violet-400">
                        #{idx + 1}
                      </span>
                      <span className="text-zinc-400 truncate">
                        {sub.session_id.slice(0, 12)}
                      </span>
                    </div>
                    <p className="text-zinc-400 group-hover:text-zinc-300 leading-snug">
                      {stepCount} steps · {toolCount} tools
                    </p>
                    {sub.first_message && (
                      <p className="text-zinc-500 group-hover:text-zinc-400 line-clamp-1 leading-snug mt-0.5">
                        {truncate(sub.first_message, 60)}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Only sub-agents, no prompts — show sub-agents directly without toggle */}
        {!hasPrompts && hasSubAgents && (
          <div>
            <div className="flex items-center gap-1.5 text-sm text-zinc-300 mb-3">
              <Bot className="w-3.5 h-3.5" />
              <span className="font-medium">Sub-Agents</span>
              <span className="text-zinc-500">({subAgents.length})</span>
            </div>
            <div className="space-y-1">
              {subAgents.map((sub, idx) => {
                const stepCount = sub.steps?.length ?? 0;
                const toolCount = sub.final_metrics?.tool_call_count ?? 0;
                return (
                  <button
                    key={sub.session_id}
                    onClick={() => handleSubAgentNavigate(sub.session_id)}
                    className="w-full text-left px-2 py-1.5 rounded-md transition-colors text-sm group hover:bg-zinc-800/60 border border-transparent"
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="font-mono font-semibold text-violet-400">
                        #{idx + 1}
                      </span>
                      <span className="text-zinc-400 truncate">
                        {sub.session_id.slice(0, 12)}
                      </span>
                    </div>
                    <p className="text-zinc-400 group-hover:text-zinc-300 leading-snug">
                      {stepCount} steps · {toolCount} tools
                    </p>
                    {sub.first_message && (
                      <p className="text-zinc-500 group-hover:text-zinc-400 line-clamp-1 leading-snug mt-0.5">
                        {truncate(sub.first_message, 60)}
                      </p>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

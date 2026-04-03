import { useState } from "react";
import { Bot, Compass, MessageSquare, ScrollText, User, PanelRightClose, PanelRightOpen, Wrench } from "lucide-react";
import { Tooltip } from "../tooltip";
import { extractMessageText, extractUserText, truncate } from "../../utils";
import { ResizeHandle } from "../resize-handle";
import type { Step, Trajectory } from "../../types";
import type { FlowPhaseGroup, FlowSection } from "./flow-layout";
import {
  PHASE_STYLE, CATEGORY_LABELS, PREVIEW_MEDIUM, PREVIEW_LONG,
} from "../../styles";

const MIN_PROMPTS_FOR_NAV = 1;
const COLLAPSED_WIDTH = 40;
const NAV_BG = "bg-zinc-900";

export type NavMode = "prompts" | "sub-agents";

interface PromptEntry {
  turnNumber: number;
  stepId: string;
  preview: string;
  isPlan: boolean;
}

interface PromptNavPanelProps {
  steps: Step[];
  subAgents: Trajectory[];
  activeStepId: string | null;
  onNavigate: (stepId: string) => void;
  width: number;
  onResize: (delta: number) => void;
  viewMode: "timeline" | "concise" | "flow";
  flowPhases?: FlowPhaseGroup[];
  flowSections?: FlowSection[];
  activePhaseIdx?: number | null;
  onPhaseNavigate?: (phaseIdx: number) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  navMode: NavMode;
  onNavModeChange: (mode: NavMode) => void;
}

function buildPromptEntries(steps: Step[]): PromptEntry[] {
  const entries: PromptEntry[] = [];
  let turnNumber = 0;
  let planNumber = 0;

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    if (step.source !== "user") continue;
    if (step.extra?.is_skill_output) continue;

    if (step.extra?.is_auto_prompt) {
      const text = extractMessageText(step.message);
      if (!text) continue;
      planNumber++;
      entries.push({
        turnNumber: planNumber,
        stepId: step.step_id,
        preview: truncate(text.replace(/\n/g, " "), PREVIEW_LONG),
        isPlan: true,
      });
      continue;
    }

    const text = extractUserText(step);
    if (!text) continue;
    turnNumber++;
    entries.push({
      turnNumber,
      stepId: step.step_id,
      preview: truncate(text.replace(/\n/g, " "), PREVIEW_LONG),
      isPlan: false,
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
  flowSections,
  activePhaseIdx,
  onPhaseNavigate,
  collapsed,
  onCollapsedChange,
  navMode,
  onNavModeChange,
}: PromptNavPanelProps) {
  const entries = buildPromptEntries(steps);
  const hasPrompts = entries.length >= MIN_PROMPTS_FOR_NAV;
  const hasSubAgents = subAgents.length > 0;
  const hasFlowPhases = viewMode === "flow" && flowPhases && flowPhases.length > 0;
  const [activeSubAgentId, setActiveSubAgentId] = useState<string | null>(null);

  if (!hasPrompts && !hasSubAgents && !hasFlowPhases) return null;

  const handleSubAgentNavigate = (sessionId: string) => {
    const el = document.getElementById(`subagent-${sessionId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Collapsed strip
  if (collapsed) {
    return (
      <div
        style={{ width: COLLAPSED_WIDTH }}
        className={`hidden xl:flex relative shrink-0 h-full flex-col items-center border-l border-cyan-900/30 ${NAV_BG} py-3`}
      >
        <button
          onClick={() => onCollapsedChange(false)}
          className="p-1.5 text-cyan-600 hover:text-cyan-400 hover:bg-cyan-950/40 rounded transition"
          title="Expand navigation"
        >
          <PanelRightOpen className="w-4 h-4" />
        </button>
      </div>
    );
  }

  // Flow mode: interleaved user prompts + phases
  const hasFlowSections = viewMode === "flow" && flowSections && flowSections.length > 0;
  if (hasFlowPhases || hasFlowSections) {
    const sections = flowSections ?? [];
    let phaseIdx = 0;

    return (
      <div
        style={{ width }}
        className={`hidden xl:flex relative shrink-0 h-full flex-col border-l border-cyan-900/30 ${NAV_BG}`}
      >
        <ResizeHandle side="right" onResize={onResize} />
        <NavHeader onCollapse={() => onCollapsedChange(true)} />
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <div className="divide-y divide-zinc-800/60">
            {sections.map((section, i) => {
              if (section.type === "anchor") {
                const anchor = section.data;
                const isAuto = anchor.isAutoPrompt;
                const isActive = anchor.id === activeStepId;
                const iconColor = isAuto
                  ? (isActive ? "text-teal-400" : "text-teal-400/60 group-hover:text-teal-400")
                  : (isActive ? "text-cyan-400" : "text-cyan-400/60 group-hover:text-cyan-400");
                const labelColor = isAuto
                  ? (isActive ? "text-teal-300" : "text-teal-400/70 group-hover:text-teal-300")
                  : (isActive ? "text-cyan-300" : "text-cyan-400/70 group-hover:text-cyan-300");
                const previewColor = isActive
                  ? "text-zinc-200"
                  : "text-zinc-300 group-hover:text-zinc-200";

                return (
                  <button
                    key={`anchor-${anchor.id}`}
                    onClick={() => onNavigate(anchor.id)}
                    className={`w-full text-left px-2.5 py-2.5 transition-colors text-sm group ${
                      isActive ? "bg-zinc-800/50" : "hover:bg-zinc-800/40"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <User className={`w-3.5 h-3.5 shrink-0 ${iconColor}`} />
                      <span className={`font-mono font-semibold text-xs ${labelColor}`}>
                        Prompt #{anchor.promptIndex}
                      </span>
                      {isAuto && (
                        <span className="text-[9px] uppercase tracking-wider text-amber-500/50 font-semibold">
                          auto
                        </span>
                      )}
                    </div>
                    <p className={`line-clamp-2 leading-snug ${previewColor}`}>
                      {truncate(anchor.label, PREVIEW_LONG)}
                    </p>
                  </button>
                );
              }

              // Phase section
              const phase = section.data;
              const currentPhaseIdx = phaseIdx++;
              const isActive = activePhaseIdx === currentPhaseIdx;
              const style = PHASE_STYLE[phase.phase] || PHASE_STYLE.mixed;
              const catLabel = CATEGORY_LABELS[phase.dominantCategory] || phase.dominantCategory;
              return (
                <button
                  key={`phase-${i}`}
                  onClick={() => onPhaseNavigate?.(currentPhaseIdx)}
                  className={`w-full text-left px-2.5 py-2.5 transition-colors text-sm group ${
                    isActive ? "bg-zinc-800/50" : "hover:bg-zinc-800/40"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`w-2 h-2 rounded-full ${style.dot}`} />
                    <span
                      className={`text-[11px] font-bold uppercase tracking-wider ${
                        isActive ? "text-cyan-300" : style.label
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
      className={`hidden xl:flex relative shrink-0 h-full flex-col border-l border-cyan-900/30 ${NAV_BG}`}
    >
      <ResizeHandle side="right" onResize={onResize} />
      <NavHeader onCollapse={() => onCollapsedChange(true)} />

      {/* Mode Toggle */}
      {hasPrompts && hasSubAgents && (
        <div className="shrink-0 px-3 pb-2">
          <div className="flex gap-1 bg-cyan-950/30 rounded-md p-1">
            <Tooltip text="Navigate user prompts and plan entries" className="flex-1 min-w-0">
              <button
                onClick={() => onNavModeChange("prompts")}
                className={`w-full flex items-center justify-center text-xs py-1.5 rounded transition ${
                  navMode === "prompts"
                    ? "bg-cyan-600/25 text-cyan-200 font-semibold"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                User ({entries.length})
              </button>
            </Tooltip>
            <Tooltip text="Navigate sub-agent trajectories spawned by this session" className="flex-1 min-w-0">
              <button
                onClick={() => onNavModeChange("sub-agents")}
                className={`w-full flex items-center justify-center text-xs py-1.5 rounded transition ${
                  navMode === "sub-agents"
                    ? "bg-cyan-600/25 text-cyan-200 font-semibold"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                Sub-Agents ({subAgents.length})
              </button>
            </Tooltip>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {/* Prompts view: all entries interleaved (user prompts + plans) */}
        {(navMode === "prompts" || !hasSubAgents) && hasPrompts && (
          <div className="divide-y divide-zinc-800/60">
            {entries.map((entry) => {
              const isActive = entry.stepId === activeStepId;
              if (entry.isPlan) {
                return (
                  <button
                    key={entry.stepId}
                    onClick={() => onNavigate(entry.stepId)}
                    className={`w-full text-left px-2.5 py-2.5 transition-colors text-sm group ${
                      isActive ? "bg-zinc-800/50" : "hover:bg-zinc-800/40"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <ScrollText
                        className={`w-3.5 h-3.5 shrink-0 ${
                          isActive ? "text-teal-400" : "text-teal-500/70 group-hover:text-teal-400"
                        }`}
                      />
                      <span
                        className={`font-mono font-semibold text-xs shrink-0 ${
                          isActive ? "text-teal-300" : "text-teal-400/70 group-hover:text-teal-300"
                        }`}
                      >
                        Plan #{entry.turnNumber}
                      </span>
                    </div>
                    <p
                      className={`line-clamp-2 leading-snug ${
                        isActive ? "text-zinc-200" : "text-zinc-300 group-hover:text-zinc-200"
                      }`}
                    >
                      {entry.preview}
                    </p>
                  </button>
                );
              }
              return (
                <button
                  key={entry.stepId}
                  onClick={() => onNavigate(entry.stepId)}
                  className={`w-full text-left px-2.5 py-2.5 transition-colors text-sm group ${
                    isActive ? "bg-zinc-800/50" : "hover:bg-zinc-800/40"
                  }`}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <User
                      className={`w-3.5 h-3.5 shrink-0 ${
                        isActive ? "text-cyan-400" : "text-cyan-500/60 group-hover:text-cyan-400"
                      }`}
                    />
                    <span
                      className={`font-mono font-semibold text-xs shrink-0 ${
                        isActive ? "text-cyan-300" : "text-cyan-400/70 group-hover:text-cyan-300"
                      }`}
                    >
                      Prompt #{entry.turnNumber}
                    </span>
                  </div>
                  <p
                    className={`line-clamp-2 leading-snug ${
                      isActive ? "text-zinc-200" : "text-zinc-300 group-hover:text-zinc-200"
                    }`}
                  >
                    {entry.preview}
                  </p>
                </button>
              );
            })}
          </div>
        )}

        {/* Sub-Agents view */}
        {navMode === "sub-agents" && hasSubAgents && (
          <div className="divide-y divide-zinc-800/60">
            {subAgents.map((sub, idx) => {
              const stepCount = sub.steps?.length ?? 0;
              const toolCount = sub.final_metrics?.tool_call_count ?? 0;
              const isActive = activeSubAgentId === sub.session_id;
              return (
                <button
                  key={sub.session_id}
                  onClick={() => {
                    setActiveSubAgentId(sub.session_id);
                    handleSubAgentNavigate(sub.session_id);
                  }}
                  className={`w-full text-left px-2.5 py-2.5 transition-colors text-sm group ${
                    isActive ? "bg-zinc-800/50" : "hover:bg-zinc-800/40"
                  }`}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <Bot
                      className={`w-3.5 h-3.5 shrink-0 ${
                        isActive ? "text-violet-400" : "text-violet-500/70 group-hover:text-violet-400"
                      }`}
                    />
                    <span
                      className={`font-mono font-semibold text-xs shrink-0 ${
                        isActive ? "text-violet-300" : "text-violet-400/70 group-hover:text-violet-300"
                      }`}
                    >
                      Sub-Agent #{idx + 1}
                    </span>
                  </div>
                  <div className={`flex items-center gap-2 text-[11px] ${isActive ? "text-zinc-300" : "text-zinc-400"}`}>
                    <span className="inline-flex items-center gap-0.5">
                      <MessageSquare className="w-3 h-3" />
                      {stepCount} steps
                    </span>
                    <span className="inline-flex items-center gap-0.5">
                      <Wrench className="w-3 h-3" />
                      {toolCount} tools
                    </span>
                  </div>
                  {sub.first_message && (
                    <p
                      className={`line-clamp-2 leading-snug ${
                        isActive ? "text-zinc-200" : "text-zinc-300 group-hover:text-zinc-200"
                      }`}
                    >
                      {truncate(sub.first_message, PREVIEW_MEDIUM)}
                    </p>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Only sub-agents, no prompts */}
        {!hasPrompts && hasSubAgents && (
          <div>
            <div className="flex items-center gap-1.5 text-sm text-zinc-300 mb-3">
              <Bot className="w-3.5 h-3.5" />
              <span className="font-medium">Agents</span>
              <span className="text-zinc-500">({subAgents.length})</span>
            </div>
            <div className="divide-y divide-zinc-800/60">
              {subAgents.map((sub, idx) => {
                const stepCount = sub.steps?.length ?? 0;
                const toolCount = sub.final_metrics?.tool_call_count ?? 0;
                const isActive = activeSubAgentId === sub.session_id;
                return (
                  <button
                    key={sub.session_id}
                    onClick={() => {
                      setActiveSubAgentId(sub.session_id);
                      handleSubAgentNavigate(sub.session_id);
                    }}
                    className={`w-full text-left px-2.5 py-2.5 transition-colors text-sm group ${
                      isActive ? "bg-zinc-800/50" : "hover:bg-zinc-800/40"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <Bot
                        className={`w-3.5 h-3.5 shrink-0 ${
                          isActive ? "text-violet-400" : "text-violet-500/70 group-hover:text-violet-400"
                        }`}
                      />
                      <span
                        className={`font-mono font-semibold text-xs shrink-0 ${
                          isActive ? "text-violet-300" : "text-violet-400/70 group-hover:text-violet-300"
                        }`}
                      >
                        Sub-Agent #{idx + 1}
                      </span>
                      <span className={`text-[11px] ${isActive ? "text-zinc-400" : "text-zinc-500"}`}>
                        {stepCount} steps · {toolCount} tools
                      </span>
                    </div>
                    {sub.first_message && (
                      <p
                        className={`line-clamp-2 leading-snug ${
                          isActive ? "text-zinc-200" : "text-zinc-300 group-hover:text-zinc-200"
                        }`}
                      >
                        {truncate(sub.first_message, PREVIEW_MEDIUM)}
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

function NavHeader({ onCollapse }: { onCollapse: () => void }) {
  return (
    <div className="shrink-0 flex items-center justify-between px-3 pt-3 pb-2 border-b border-cyan-900/20">
      <div className="flex items-center gap-1.5">
        <Compass className="w-3.5 h-3.5 text-cyan-500" />
        <span className="text-[11px] uppercase tracking-wider text-cyan-400 font-semibold">
          Navigation
        </span>
      </div>
      <button
        onClick={onCollapse}
        className="p-1 text-cyan-600 hover:text-cyan-400 hover:bg-cyan-950/40 rounded transition"
        title="Collapse navigation"
      >
        <PanelRightClose className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

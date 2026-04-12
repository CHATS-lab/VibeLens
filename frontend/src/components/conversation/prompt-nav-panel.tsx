import { useState } from "react";
import { Bot, Compass, Layers, MessageSquare, ScrollText, User, PanelRightClose, PanelRightOpen, Wrench } from "lucide-react";
import { Tooltip } from "../tooltip";
import { extractMessageText, extractUserText, truncate } from "../../utils";
import { ResizeHandle } from "../resize-handle";
import type { Step, Trajectory } from "../../types";
import type { FlowPhaseGroup, FlowSection } from "./flow-layout";
import { PHASE_STYLE, CATEGORY_LABELS } from "../../styles";
import { PREVIEW_MEDIUM, PREVIEW_LONG } from "../../constants";

const MIN_PROMPTS_FOR_NAV = 1;
const COLLAPSED_WIDTH = 40;
const NAV_BG = "bg-panel/50";

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
  viewMode: "concise" | "detail" | "workflow";
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
  const hasFlowPhases = viewMode === "workflow" && flowPhases && flowPhases.length > 0;
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
        className={`hidden xl:flex relative shrink-0 h-full flex-col items-center border-l border-default ${NAV_BG} py-3`}
      >
        <Tooltip text="Expand navigation">
          <button
            onClick={() => onCollapsedChange(false)}
            className="p-1.5 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
          >
            <PanelRightOpen className="w-4 h-4" />
          </button>
        </Tooltip>
      </div>
    );
  }

  // Flow mode: interleaved user prompts + phases
  const hasFlowSections = viewMode === "workflow" && flowSections && flowSections.length > 0;
  if (hasFlowPhases || hasFlowSections) {
    const sections = flowSections ?? [];
    let phaseIdx = 0;

    return (
      <div
        style={{ width }}
        className={`hidden xl:flex relative shrink-0 h-full flex-col border-l border-default ${NAV_BG}`}
      >
        <ResizeHandle side="right" onResize={onResize} />
        <NavHeader onCollapse={() => onCollapsedChange(true)} />
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <div className="divide-y divide-card">
            {sections.map((section, i) => {
              if (section.type === "anchor") {
                const anchor = section.data;
                const isAuto = anchor.isAutoPrompt;
                const isActive = anchor.id === activeStepId;
                const iconColor = isAuto
                  ? (isActive ? "text-accent-teal" : "text-accent-teal/60 group-hover:text-accent-teal")
                  : (isActive ? "text-accent-cyan" : "text-accent-cyan/60 group-hover:text-accent-cyan");
                const labelColor = isAuto
                  ? (isActive ? "text-accent-teal" : "text-accent-teal/70 group-hover:text-accent-teal")
                  : (isActive ? "text-accent-cyan" : "text-accent-cyan/70 group-hover:text-accent-cyan");
                const previewColor = isActive
                  ? "text-secondary"
                  : "text-secondary group-hover:text-secondary";

                return (
                  <button
                    key={`anchor-${anchor.id}`}
                    onClick={() => onNavigate(anchor.id)}
                    className={`w-full text-left px-2.5 py-2.5 transition-colors text-sm group ${
                      isActive ? "bg-control" : "hover:bg-control"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <User className={`w-3.5 h-3.5 shrink-0 ${iconColor}`} />
                      <span className={`font-mono font-semibold text-xs ${labelColor}`}>
                        User #{anchor.promptIndex}
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
                    isActive ? "bg-control" : "hover:bg-control"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`w-2 h-2 rounded-full ${style.dot}`} />
                    <span
                      className={`text-[11px] font-bold uppercase tracking-wider ${
                        isActive ? "text-accent-cyan" : style.label
                      }`}
                    >
                      {phase.phase}
                    </span>
                  </div>
                  <div className="flex items-center gap-2.5 text-[11px] text-muted pl-4">
                    <span className="inline-flex items-center gap-1">
                      <Layers className="w-3 h-3" />
                      {phase.cards.length} step{phase.cards.length !== 1 ? "s" : ""}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Wrench className="w-3 h-3" />
                      {phase.toolCount} tool{phase.toolCount !== 1 ? "s" : ""}
                    </span>
                    {phase.toolCount > 0 && (
                      <span className="text-dimmed">{catLabel}</span>
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
      className={`hidden xl:flex relative shrink-0 h-full flex-col border-l border-default ${NAV_BG}`}
    >
      <ResizeHandle side="right" onResize={onResize} />
      <NavHeader onCollapse={() => onCollapsedChange(true)} />

      {/* Mode Toggle */}
      {hasPrompts && hasSubAgents && (
        <div className="shrink-0 px-3 pb-2">
          <div className="flex rounded-lg bg-zinc-100 dark:bg-zinc-800/60 p-0.5">
            <Tooltip text="Navigate user prompts and plan entries" className="flex-1 min-w-0">
              <button
                onClick={() => onNavModeChange("prompts")}
                className={`w-full flex items-center justify-center text-xs py-1.5 rounded-md transition ${
                  navMode === "prompts"
                    ? "bg-white dark:bg-zinc-700 text-primary font-semibold shadow-sm"
                    : "text-muted hover:text-secondary"
                }`}
              >
                User ({entries.length})
              </button>
            </Tooltip>
            <Tooltip text="Navigate sub-agent trajectories spawned by this session" className="flex-1 min-w-0">
              <button
                onClick={() => onNavModeChange("sub-agents")}
                className={`w-full flex items-center justify-center text-xs py-1.5 rounded-md transition ${
                  navMode === "sub-agents"
                    ? "bg-white dark:bg-zinc-700 text-primary font-semibold shadow-sm"
                    : "text-muted hover:text-secondary"
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
          <div className="divide-y divide-card">
            {entries.map((entry) => {
              const isActive = entry.stepId === activeStepId;
              if (entry.isPlan) {
                return (
                  <button
                    key={entry.stepId}
                    onClick={() => onNavigate(entry.stepId)}
                    className={`w-full text-left px-2.5 py-2.5 transition-colors text-sm group ${
                      isActive ? "bg-control" : "hover:bg-control"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <ScrollText
                        className={`w-3.5 h-3.5 shrink-0 ${
                          isActive ? "text-accent-teal" : "text-accent-teal/70 group-hover:text-accent-teal"
                        }`}
                      />
                      <span
                        className={`font-mono font-semibold text-xs shrink-0 ${
                          isActive ? "text-accent-teal" : "text-accent-teal/70 group-hover:text-accent-teal"
                        }`}
                      >
                        Plan #{entry.turnNumber}
                      </span>
                    </div>
                    <p
                      className={`line-clamp-2 leading-snug ${
                        isActive ? "text-secondary" : "text-secondary group-hover:text-secondary"
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
                    isActive ? "bg-control" : "hover:bg-control"
                  }`}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <User
                      className={`w-3.5 h-3.5 shrink-0 ${
                        isActive ? "text-accent-cyan" : "text-accent-cyan/60 group-hover:text-accent-cyan"
                      }`}
                    />
                    <span
                      className={`font-mono font-semibold text-xs shrink-0 ${
                        isActive ? "text-accent-cyan" : "text-accent-cyan/70 group-hover:text-accent-cyan"
                      }`}
                    >
                      User #{entry.turnNumber}
                    </span>
                  </div>
                  <p
                    className={`line-clamp-2 leading-snug ${
                      isActive ? "text-secondary" : "text-secondary group-hover:text-secondary"
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
          <div className="divide-y divide-card">
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
                    isActive ? "bg-control" : "hover:bg-control"
                  }`}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <Bot
                      className={`w-3.5 h-3.5 shrink-0 ${
                        isActive ? "text-accent-violet" : "text-accent-violet/70 group-hover:text-accent-violet"
                      }`}
                    />
                    <span
                      className={`font-mono font-semibold text-xs shrink-0 ${
                        isActive ? "text-accent-violet" : "text-accent-violet/70 group-hover:text-accent-violet"
                      }`}
                    >
                      Sub-Agent #{idx + 1}
                    </span>
                  </div>
                  <div className={`flex items-center gap-2 text-[11px] ${isActive ? "text-secondary" : "text-muted"}`}>
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
                        isActive ? "text-secondary" : "text-secondary group-hover:text-secondary"
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
            <div className="flex items-center gap-1.5 text-sm text-secondary mb-3">
              <Bot className="w-3.5 h-3.5" />
              <span className="font-medium">Agents</span>
              <span className="text-dimmed">({subAgents.length})</span>
            </div>
            <div className="divide-y divide-card">
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
                      isActive ? "bg-control" : "hover:bg-control"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <Bot
                        className={`w-3.5 h-3.5 shrink-0 ${
                          isActive ? "text-accent-violet" : "text-accent-violet/70 group-hover:text-accent-violet"
                        }`}
                      />
                      <span
                        className={`font-mono font-semibold text-xs shrink-0 ${
                          isActive ? "text-accent-violet" : "text-accent-violet/70 group-hover:text-accent-violet"
                        }`}
                      >
                        Sub-Agent #{idx + 1}
                      </span>
                      <span className={`text-[11px] ${isActive ? "text-muted" : "text-dimmed"}`}>
                        {stepCount} steps · {toolCount} tools
                      </span>
                    </div>
                    {sub.first_message && (
                      <p
                        className={`line-clamp-2 leading-snug ${
                          isActive ? "text-secondary" : "text-secondary group-hover:text-secondary"
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
    <div className="shrink-0 flex items-center justify-between px-3 pt-3 pb-2 border-b border-card">
      <div className="flex items-center gap-1.5">
        <Compass className="w-3.5 h-3.5 text-accent-cyan" />
        <span className="text-xs font-semibold text-secondary tracking-wide uppercase">
          Navigation
        </span>
      </div>
      <Tooltip text="Collapse navigation">
        <button
          onClick={onCollapse}
          className="p-1 text-dimmed hover:text-secondary hover:bg-control-hover rounded transition"
        >
          <PanelRightClose className="w-3.5 h-3.5" />
        </button>
      </Tooltip>
    </div>
  );
}

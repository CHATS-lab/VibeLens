import { useState } from "react";
import { Bot, MessageSquare } from "lucide-react";
import { extractUserText, truncate } from "../../utils";
import { ResizeHandle } from "../resize-handle";
import type { Step, Trajectory } from "../../types";

const PREVIEW_MAX_CHARS = 80;
const MIN_PROMPTS_FOR_NAV = 1;

type NavMode = "prompts" | "sub-agents";

interface PromptEntry {
  turnNumber: number;
  stepId: string;
  preview: string;
}

interface PromptNavPanelProps {
  steps: Step[];
  subAgents: Trajectory[];
  activeStepId: string | null;
  onNavigate: (stepId: string) => void;
  width: number;
  onResize: (delta: number) => void;
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
}: PromptNavPanelProps) {
  const entries = buildPromptEntries(steps);
  const hasPrompts = entries.length >= MIN_PROMPTS_FOR_NAV;
  const hasSubAgents = subAgents.length > 0;

  const [navMode, setNavMode] = useState<NavMode>("prompts");

  if (!hasPrompts && !hasSubAgents) return null;

  const handleSubAgentNavigate = (sessionId: string) => {
    const el = document.getElementById(`subagent-${sessionId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div
      style={{ width }}
      className="hidden xl:flex relative shrink-0 h-full flex-col border-l border-zinc-800 bg-zinc-900/50"
    >
      <ResizeHandle side="right" onResize={onResize} />

      {/* Mode Toggle */}
      {hasPrompts && hasSubAgents && (
        <div className="shrink-0 px-3 pt-3 pb-2">
          <div className="flex gap-0.5 bg-zinc-800 rounded p-0.5">
            <button
              onClick={() => setNavMode("prompts")}
              className={`flex-1 flex items-center justify-center gap-1.5 text-[11px] py-1.5 rounded transition ${
                navMode === "prompts"
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              <MessageSquare className="w-3 h-3" />
              Prompts
            </button>
            <button
              onClick={() => setNavMode("sub-agents")}
              className={`flex-1 flex items-center justify-center gap-1.5 text-[11px] py-1.5 rounded transition ${
                navMode === "sub-agents"
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
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
              <div className="flex items-center gap-1.5 text-xs text-zinc-400 mb-3">
                <MessageSquare className="w-3.5 h-3.5" />
                <span className="font-medium">Prompts</span>
                <span className="text-zinc-600">({entries.length})</span>
              </div>
            )}
            <div className="space-y-1">
              {entries.map((entry) => {
                const isActive = entry.stepId === activeStepId;
                return (
                  <button
                    key={entry.stepId}
                    onClick={() => onNavigate(entry.stepId)}
                    className={`w-full text-left px-2 py-1.5 rounded-md transition-colors text-xs group ${
                      isActive
                        ? "bg-cyan-500/15 border border-cyan-500/30"
                        : "hover:bg-zinc-800/60 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span
                        className={`font-mono font-semibold ${
                          isActive ? "text-cyan-400" : "text-zinc-500 group-hover:text-zinc-400"
                        }`}
                      >
                        #{entry.turnNumber}
                      </span>
                    </div>
                    <p
                      className={`line-clamp-2 leading-snug ${
                        isActive ? "text-cyan-200/80" : "text-zinc-500 group-hover:text-zinc-400"
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
                    className="w-full text-left px-2 py-1.5 rounded-md transition-colors text-xs group hover:bg-zinc-800/60 border border-transparent"
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="font-mono font-semibold text-violet-400">
                        #{idx + 1}
                      </span>
                      <span className="text-zinc-500 truncate">
                        {sub.session_id.slice(0, 12)}
                      </span>
                    </div>
                    <p className="text-zinc-500 group-hover:text-zinc-400 leading-snug">
                      {stepCount} steps · {toolCount} tools
                    </p>
                    {sub.first_message && (
                      <p className="text-zinc-600 group-hover:text-zinc-500 line-clamp-1 leading-snug mt-0.5">
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
            <div className="flex items-center gap-1.5 text-xs text-zinc-400 mb-3">
              <Bot className="w-3.5 h-3.5" />
              <span className="font-medium">Sub-Agents</span>
              <span className="text-zinc-600">({subAgents.length})</span>
            </div>
            <div className="space-y-1">
              {subAgents.map((sub, idx) => {
                const stepCount = sub.steps?.length ?? 0;
                const toolCount = sub.final_metrics?.tool_call_count ?? 0;
                return (
                  <button
                    key={sub.session_id}
                    onClick={() => handleSubAgentNavigate(sub.session_id)}
                    className="w-full text-left px-2 py-1.5 rounded-md transition-colors text-xs group hover:bg-zinc-800/60 border border-transparent"
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="font-mono font-semibold text-violet-400">
                        #{idx + 1}
                      </span>
                      <span className="text-zinc-500 truncate">
                        {sub.session_id.slice(0, 12)}
                      </span>
                    </div>
                    <p className="text-zinc-500 group-hover:text-zinc-400 leading-snug">
                      {stepCount} steps · {toolCount} tools
                    </p>
                    {sub.first_message && (
                      <p className="text-zinc-600 group-hover:text-zinc-500 line-clamp-1 leading-snug mt-0.5">
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

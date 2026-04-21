import {
  Lightbulb,
  ChevronDown,
  ChevronRight,
  Layers,
  Monitor,
  Zap,
  ScrollText,
} from "lucide-react";
import { useState } from "react";
import type { Step, ToolCall, ObservationResult, ContentPart } from "../../types";
import { sanitizeText, extractMessageText } from "../../utils";
import { PREVIEW_LONG } from "../../constants";
import { CopyButton } from "../ui/copy-button";
import { MarkdownRenderer } from "../ui/markdown-renderer";
import { ContentRenderer } from "./content-renderer";
import { ToolUseBlock } from "./tool-input-renderers";
import { ToolResultBlock } from "./tool-output-renderers";

const USER_PROMPT_COLLAPSE_LINE_THRESHOLD = 15;

interface StepBlockProps {
  step: Step;
  concise?: boolean;
}

export function StepBlock({ step, concise }: StepBlockProps) {
  if (step.source === "system") {
    return <SystemStep step={step} />;
  }
  if (step.source === "user") {
    if (step.extra?.is_skill_output) {
      return <SkillStep step={step} />;
    }
    if (step.extra?.is_auto_prompt) {
      return <AutoPromptStep step={step} />;
    }
    return <UserStep step={step} />;
  }
  if (step.source === "agent") {
    return <AgentStep step={step} concise={concise} />;
  }
  return null;
}

/** @deprecated Use StepBlock instead. Kept for backward compatibility during migration. */
export const MessageBlock = StepBlock;

function UserStep({ step }: { step: Step }) {
  const text = extractMessageText(step.message);
  if (!text && typeof step.message === "string") return null;
  if (!text && Array.isArray(step.message) && step.message.length === 0) return null;

  const lineCount = text ? text.split("\n").length : 0;
  const isLong = lineCount > USER_PROMPT_COLLAPSE_LINE_THRESHOLD;
  const [expanded, setExpanded] = useState(!isLong);

  return (
    <div className="flex justify-end">
      <div className="group relative max-w-[85%] bg-blue-50/80 dark:bg-white/[0.06] text-primary rounded-2xl rounded-br-md px-4 py-2.5 text-sm overflow-hidden break-words">
        <div className="absolute top-1 left-1 opacity-0 group-hover:opacity-100 transition-opacity bg-blue-50/80 dark:bg-[#2a2b2e] rounded">
          <CopyButton text={text} />
        </div>
        {!expanded ? (
          <>
            <div className="line-clamp-4">
              <ContentRenderer content={step.message} className="user-markdown" />
            </div>
            <button
              onClick={() => setExpanded(true)}
              className="mt-1.5 text-xs text-accent-cyan hover:text-accent-cyan hover:bg-control/30 rounded px-1 -mx-1 transition"
            >
              Show full prompt ({lineCount} lines)
            </button>
          </>
        ) : (
          <>
            <ContentRenderer content={step.message} className="user-markdown" />
            {isLong && (
              <button
                onClick={() => setExpanded(false)}
                className="mt-1.5 text-xs text-accent-cyan hover:text-accent-cyan hover:bg-control/30 rounded px-1 -mx-1 transition"
              >
                Collapse
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function SystemStep({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  const text = extractMessageText(step.message);
  if (!text) return null;
  const previewSnippet = text.split("\n")[0].slice(0, PREVIEW_LONG);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm border transition-colors bg-subtle hover:bg-control/80 text-muted border-hover"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Monitor className="w-4 h-4" />
        <span className="font-medium">System</span>
        {!open && (
          <span className="text-dimmed truncate max-w-[250px] ml-0.5">{previewSnippet}</span>
        )}
      </button>
      {open && (
        <div className="mt-1 bg-panel/30 border border-card rounded-lg p-3">
          <pre className="text-xs text-secondary whitespace-pre-wrap break-words overflow-x-auto max-h-96 overflow-y-auto">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

function extractSkillName(text: string): string | null {
  const match = text.match(/\/skills\/([^/\s]+)/);
  return match ? match[1] : null;
}

function SkillStep({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  const text = extractMessageText(step.message);
  if (!text) return null;
  const skillName = extractSkillName(text);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm border transition-colors bg-amber-500/10 hover:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/25"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Zap className="w-4 h-4" />
        <span className="font-medium">Skill</span>
        {skillName && <span className="text-amber-600 dark:text-amber-400 ml-0.5">/{skillName}</span>}
      </button>
      {open && (
        <div className="mt-1 bg-amber-50/50 dark:bg-amber-500/[0.04] border border-amber-500/20 rounded-lg p-3">
          <pre className="text-xs text-amber-800 dark:text-amber-200 whitespace-pre-wrap overflow-x-auto max-h-96 overflow-y-auto">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

function AutoPromptStep({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  const text = extractMessageText(step.message);
  if (!text) return null;
  const firstLine = text.split("\n")[0].slice(0, PREVIEW_LONG);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm border transition-colors bg-teal-500/15 hover:bg-teal-500/20 text-teal-700 dark:text-teal-200 border-teal-400/30"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <ScrollText className="w-4 h-4" />
        <span className="font-medium">Plan</span>
        {!open && (
          <span className="text-teal-600/80 dark:text-teal-300/80 truncate max-w-[250px] ml-0.5">{firstLine}</span>
        )}
      </button>
      {open && (
        <div className="group relative mt-1 bg-teal-50/60 dark:bg-teal-950/20 border border-teal-200/50 dark:border-teal-500/25 rounded-lg p-3">
          <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-teal-50/80 dark:bg-teal-950/60 rounded">
            <CopyButton text={text} />
          </div>
          <pre className="text-xs text-teal-800 dark:text-teal-100 whitespace-pre-wrap overflow-x-auto max-h-96 overflow-y-auto">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

function AgentStep({ step, concise }: { step: Step; concise?: boolean }) {
  // Concise mode: render only the text message, skip thinking/tools
  if (concise) {
    if (!step.message || (typeof step.message === "string" && !step.message.trim())) {
      return null;
    }
    return (
      <div className="space-y-1">
        <TextBlock content={step.message} />
      </div>
    );
  }

  // Build observation results indexed by source_call_id for pairing
  const obsMap = new Map<string, ObservationResult>();
  if (step.observation) {
    for (const r of step.observation.results) {
      if (r.source_call_id) {
        obsMap.set(r.source_call_id, r);
      }
    }
  }

  const orphanResults = step.observation?.results.filter(
    (r) => !r.source_call_id || !step.tool_calls.some((tc) => tc.tool_call_id === r.source_call_id)
  ) ?? [];

  const hasConcurrentCalls = step.tool_calls.length > 1;

  return (
    <div className="space-y-1">
      {step.reasoning_content && <ThinkingBlock text={step.reasoning_content} />}
      {step.message && (typeof step.message !== "string" || step.message.trim()) && (
        <TextBlock content={step.message} />
      )}
      {(step.tool_calls.length > 0 || orphanResults.length > 0) && (
        <div className="flex flex-col gap-1 mt-1.5">
          {hasConcurrentCalls ? (
            <ConcurrentToolsBlock toolCalls={step.tool_calls} obsMap={obsMap} />
          ) : (
            step.tool_calls.map((tc, i) => {
              const result = obsMap.get(tc.tool_call_id);
              return (
                <div key={`tc-${i}`}>
                  <ToolUseBlock toolCall={tc} />
                  {result && <ToolResultBlock result={result} />}
                </div>
              );
            })
          )}
          {orphanResults.map((r, i) => (
            <ToolResultBlock key={`orphan-${i}`} result={r} />
          ))}
        </div>
      )}
    </div>
  );
}

function ConcurrentToolsBlock({
  toolCalls,
  obsMap,
}: {
  toolCalls: ToolCall[];
  obsMap: Map<string, ObservationResult>;
}) {
  const [open, setOpen] = useState(true);
  const toolNames = toolCalls.map((tc) => tc.function_name || "unknown");
  const uniqueNames = [...new Set(toolNames)];
  const preview = uniqueNames.length <= 3
    ? uniqueNames.join(", ")
    : `${uniqueNames.slice(0, 2).join(", ")} +${uniqueNames.length - 2}`;

  return (
    <div className="max-w-[85%] rounded-lg border bg-cyan-500/5 border-cyan-500/20 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-cyan-700 dark:text-cyan-300 hover:bg-control dark:hover:bg-white/5 transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 shrink-0" />}
        <Layers className="w-4 h-4" />
        <span className="font-medium">{toolCalls.length} parallel calls</span>
        {!open && (
          <span className="text-dimmed truncate ml-1">{preview}</span>
        )}
      </button>
      {open && (
        <div className="border-t border-cyan-500/20">
          <div className="ml-3 pl-3 py-2 space-y-1">
            {toolCalls.map((tc, i) => {
              const result = obsMap.get(tc.tool_call_id);
              return (
                <div key={`tc-${i}`}>
                  <ToolUseBlock toolCall={tc} />
                  {result && <ToolResultBlock result={result} />}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function TextBlock({ content }: { content: string | ContentPart[] }) {
  const copyText = extractMessageText(content);
  if (typeof content === "string") {
    const cleaned = sanitizeText(content);
    if (!cleaned) return null;
    return (
      <div className="group relative max-w-[85%] text-primary text-sm break-words overflow-hidden">
        <div className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 transition-opacity bg-canvas rounded">
          <CopyButton text={copyText} />
        </div>
        <MarkdownRenderer content={cleaned} />
      </div>
    );
  }
  return (
    <div className="group relative max-w-[85%] text-primary text-sm break-words overflow-hidden">
      <div className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <CopyButton text={copyText} />
      </div>
      <ContentRenderer content={content} />
    </div>
  );
}

function ThinkingBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (!text.trim()) return null;
  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/15 text-sm text-amber-700 dark:text-amber-400 border border-amber-500/25 transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Lightbulb className="w-4 h-4" />
        <span className="font-medium">Thinking</span>
      </button>
      {open && (
        <div className="mt-1 bg-amber-50/40 dark:bg-white/[0.03] border border-default rounded-lg p-3">
          <pre className="text-xs text-amber-700 dark:text-amber-200 whitespace-pre-wrap overflow-x-auto">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

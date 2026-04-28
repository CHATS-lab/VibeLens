import { Check, ChevronDown, ChevronRight, Hourglass, Lightbulb, X } from "lucide-react";
import { useState } from "react";
import type { ContentPart, ObservationResult, ToolCall } from "../../types";
import { ContentRenderer } from "./content-renderer";
import {
  ToolInputRenderer,
  getSkillName,
  getToolIconAndColor,
  getToolPreview,
} from "./tool-input-renderers";
import { ToolOutput } from "./tool-output-renderers";

interface ToolCallBlockProps {
  toolCall: ToolCall;
  result: ObservationResult | undefined;
}

const SKILL_PILL =
  "bg-amber-500/10 hover:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/25";
const ERROR_PILL =
  "bg-rose-500/10 hover:bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/25";

/** Merged ToolCall + ObservationResult — one collapsible pill per tool invocation.
 *
 * Replaces the prior two-pill rendering. The collapsed pill carries the tool
 * name + status (success / error / in-flight) + a short preview of the
 * arguments. Expanding shows arguments AND result stacked, since debugging
 * usually needs both.
 *
 * - Skill activations get the amber treatment (overrides the per-tool color).
 * - Errors get a red border on the collapsed pill so failures stand out at
 *   a glance without expanding.
 * - In-flight calls (no result yet) show an hourglass icon.
 * - The expanded sections rely on the per-tool input renderers and on
 *   ``ToolOutput`` for the result body — those carry their own integrated
 *   headers + copy buttons, so we don't need a redundant outer label.
 */
export function ToolCallBlock({ toolCall, result }: ToolCallBlockProps) {
  const [open, setOpen] = useState(false);
  const name = toolCall.function_name || "unknown";
  const isSkill = !!toolCall.is_skill;
  const isError = !!result?.is_error;
  const inFlight = result === undefined;
  const hasArguments =
    toolCall.arguments != null
    && (typeof toolCall.arguments !== "object"
        || Object.keys(toolCall.arguments as Record<string, unknown>).length > 0);

  const baseColor = isSkill
    ? SKILL_PILL
    : isError
    ? ERROR_PILL
    : getToolIconAndColor(name).color;

  const toolIcon = isSkill
    ? <Lightbulb className="w-4 h-4" />
    : getToolIconAndColor(name).icon;

  const statusIcon = inFlight
    ? <Hourglass className="w-3.5 h-3.5 text-dimmed" />
    : isError
    ? <X className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400" />
    : <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />;

  const skillName = isSkill ? getSkillName(toolCall.arguments) : "";
  const preview = isSkill ? "" : getToolPreview(name, toolCall.arguments);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm border transition-colors ${baseColor}`}
      >
        {open
          ? <ChevronDown className="w-3.5 h-3.5" />
          : <ChevronRight className="w-3.5 h-3.5" />}
        {toolIcon}
        <span className="font-medium">{isSkill ? "Skill" : name}</span>
        {isSkill && skillName && (
          <span className="text-amber-600 dark:text-amber-400 ml-0.5">/{skillName}</span>
        )}
        {statusIcon}
        {preview && (
          <span className="text-muted truncate max-w-[200px] ml-0.5">{preview}</span>
        )}
      </button>
      {open && (
        <div className="mt-1 space-y-1.5">
          {hasArguments && (
            <ToolInputRenderer name={name} input={toolCall.arguments} />
          )}
          {result && <ResultBlock result={result} />}
        </div>
      )}
    </div>
  );
}

function ResultBlock({ result }: { result: ObservationResult }) {
  const rawContent = result.content;
  if (!rawContent) return null;
  const isError = result.is_error ?? false;
  const label = isError ? "error" : "result";

  if (Array.isArray(rawContent)) {
    return (
      <div className="bg-panel/30 border border-default rounded-lg overflow-hidden">
        <div className="flex items-center px-3 py-1 bg-control/40 border-b border-card">
          <span className="text-[10px] font-medium text-dimmed uppercase tracking-wider">
            {label}
          </span>
        </div>
        <div className="p-3">
          <ContentRenderer content={rawContent as ContentPart[]} />
        </div>
      </div>
    );
  }

  return (
    <div
      className={`border rounded-lg overflow-hidden ${
        isError
          ? "bg-rose-500/5 border-rose-500/25"
          : "bg-panel/30 border-default"
      }`}
    >
      <ToolOutput text={rawContent} isError={isError} headerLabel={label} />
    </div>
  );
}

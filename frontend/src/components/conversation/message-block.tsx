import {
  Terminal,
  FileCode,
  FilePlus2,
  Search,
  FolderOpen,
  Check,
  X,
  Lightbulb,
  Bot,
  Wrench,
  Pencil,
  ChevronDown,
  ChevronRight,
  Layers,
  Monitor,
  Zap,
  ScrollText,
} from "lucide-react";
import { useState } from "react";
import { createTwoFilesPatch } from "diff";
import type { Step, ToolCall, ObservationResult, ContentPart } from "../../types";
import { sanitizeText, extractMessageText } from "../../utils";
import { PREVIEW_LONG } from "../../constants";
import { MarkdownRenderer } from "../markdown-renderer";
import { ContentRenderer } from "./content-renderer";
import { CopyButton } from "../copy-button";

const MAX_COLLAPSED_LINES = 8;
const WRITE_PREVIEW_MAX_CHARS = 500;
const AUTO_EXPAND_LINE_THRESHOLD = 20;
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
      <div className="max-w-[85%] bg-blue-100 dark:bg-gradient-to-br dark:from-slate-600/70 dark:to-slate-700/60 text-primary rounded-2xl rounded-br-md px-4 py-2.5 text-sm overflow-hidden break-words">
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
        <div className="mt-1 bg-panel/60 border border-card rounded-lg p-3">
          <pre className="text-xs text-dimmed whitespace-pre-wrap break-words overflow-x-auto max-h-96 overflow-y-auto">
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
        <div className="mt-1 bg-amber-500/5 border border-amber-500/20 rounded-lg p-3">
          <pre className="text-xs text-amber-600 dark:text-amber-200/70 whitespace-pre-wrap overflow-x-auto max-h-96 overflow-y-auto">
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
        <div className="mt-1 bg-teal-50 dark:bg-teal-950/40 border border-teal-200/50 dark:border-teal-500/25 rounded-lg p-3">
          <pre className="text-xs text-teal-800/80 dark:text-teal-100/80 whitespace-pre-wrap overflow-x-auto max-h-96 overflow-y-auto">
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
  if (typeof content === "string") {
    const cleaned = sanitizeText(content);
    if (!cleaned) return null;
    return (
      <div className="max-w-[85%] text-primary text-sm break-words overflow-hidden">
        <MarkdownRenderer content={cleaned} />
      </div>
    );
  }
  return (
    <div className="max-w-[85%] text-primary text-sm break-words overflow-hidden">
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
        <div className="mt-1 bg-panel/80 border border-default rounded-lg p-3">
          <pre className="text-xs text-amber-600 dark:text-amber-200/80 whitespace-pre-wrap overflow-x-auto">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

function ToolUseBlock({ toolCall }: { toolCall: ToolCall }) {
  const [open, setOpen] = useState(false);
  const name = toolCall.function_name || "unknown";
  const { icon, color } = getToolIconAndColor(name);
  const preview = getToolPreview(name, toolCall.arguments);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm border transition-colors ${color}`}
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        {icon}
        <span className="font-medium">{name}</span>
        {!open && preview && (
          <span className="text-muted truncate max-w-[200px] ml-0.5">{preview}</span>
        )}
      </button>
      {open && (
        <div className="mt-1">
          <ToolInputRenderer name={name} input={toolCall.arguments} />
        </div>
      )}
    </div>
  );
}

const ERROR_PREFIX = "[ERROR] ";

function ToolResultBlock({ result }: { result: ObservationResult }) {
  const rawContent = result.content;
  if (!rawContent) return null;

  // Handle multimodal content (images in tool results)
  if (Array.isArray(rawContent)) {
    return (
      <div className="max-w-[85%] mt-1 bg-panel/60 border border-default rounded-lg overflow-hidden p-3">
        <ContentRenderer content={rawContent} />
      </div>
    );
  }

  const isError = rawContent.startsWith(ERROR_PREFIX);
  const content = isError ? rawContent.slice(ERROR_PREFIX.length) : rawContent;
  if (!content) return null;

  const lineCount = content.split("\n").length;
  const isShort = lineCount <= AUTO_EXPAND_LINE_THRESHOLD;
  const [open, setOpen] = useState(isShort);

  if (isShort) {
    return (
      <div className="max-w-[85%] mt-1 bg-panel/60 border border-default rounded-lg overflow-hidden">
        <ToolOutput text={content} isError={isError} />
      </div>
    );
  }

  const previewSnippet = content.split("\n")[0].slice(0, PREVIEW_LONG);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm border transition-colors ${
          isError
            ? "bg-rose-500/10 hover:bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/25"
            : "bg-teal-500/10 hover:bg-teal-500/15 text-teal-700 dark:text-teal-300 border-teal-500/25"
        }`}
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        {isError ? <X className="w-4 h-4" /> : <Check className="w-4 h-4" />}
        <span className="font-medium">{isError ? "Error" : "Result"}</span>
        {!open && (
          <span className="text-muted truncate max-w-[250px] ml-0.5">{previewSnippet}</span>
        )}
      </button>
      {open && (
        <div className="mt-1 bg-panel/60 border border-default rounded-lg overflow-hidden">
          <ToolOutput text={content} isError={isError} />
        </div>
      )}
    </div>
  );
}

function ToolInputRenderer({
  name,
  input,
}: {
  name: string;
  input: unknown;
}) {
  const data = input as Record<string, unknown> | undefined;
  if (!data) return null;

  const n = name.toLowerCase();

  if (n === "bash") {
    return <BashRenderer command={String(data.command || "")} />;
  }

  if (n === "edit") {
    return (
      <EditRenderer
        filePath={String(data.file_path || "")}
        oldString={String(data.old_string || "")}
        newString={String(data.new_string || "")}
      />
    );
  }

  if (n === "write") {
    return (
      <WriteRenderer
        filePath={String(data.file_path || "")}
        content={String(data.content || "")}
      />
    );
  }

  if (n === "read") {
    const filePath = String(data.file_path || "");
    const lang = filePath.split(".").pop() || "";
    return (
      <div className="bg-panel/60 border border-default rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-control/60 border-b border-card">
          <FileCode className="w-3.5 h-3.5 text-sky-600 dark:text-sky-400" />
          <span className="text-[11px] font-mono text-secondary truncate flex-1">{filePath}</span>
          {lang && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-control-hover/60 text-muted uppercase">{lang}</span>
          )}
          <CopyButton text={filePath} />
        </div>
      </div>
    );
  }

  if (n === "grep") {
    return (
      <div className="bg-panel/60 border border-default rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 bg-control/60">
          <Search className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
          <span className="text-[11px] font-mono text-secondary">
            {Boolean(data.pattern) && <span className="text-amber-700 dark:text-amber-300">{String(data.pattern)}</span>}
            {Boolean(data.path) && <span className="text-dimmed ml-2">in {String(data.path)}</span>}
          </span>
        </div>
      </div>
    );
  }

  if (n === "glob") {
    return (
      <div className="bg-panel/60 border border-default rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 bg-control/60">
          <FolderOpen className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
          <span className="text-[11px] font-mono text-secondary">
            {Boolean(data.pattern) && <span className="text-cyan-700 dark:text-cyan-300">{String(data.pattern)}</span>}
            {Boolean(data.path) && <span className="text-dimmed ml-2">in {String(data.path)}</span>}
          </span>
        </div>
      </div>
    );
  }

  const jsonStr = JSON.stringify(data, null, 2);
  return (
    <div className="bg-panel/60 border border-default rounded-lg overflow-hidden">
      <MarkdownRenderer
        content={`\`\`\`json\n${jsonStr}\n\`\`\``}
        className="[&>div]:my-0 [&>div]:border-0 [&>div]:rounded-none"
      />
    </div>
  );
}

function BashRenderer({ command }: { command: string }) {
  return (
    <div className="bg-panel/60 border border-default rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-control/60 border-b border-card">
        <div className="flex items-center gap-1.5">
          <Terminal className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
          <span className="text-[10px] font-medium text-muted uppercase tracking-wider">Command</span>
        </div>
        <CopyButton text={command} />
      </div>
      <pre className="p-3 overflow-x-auto text-[12px] font-mono text-green-700 dark:text-green-300 leading-relaxed">
        <span className="text-dimmed">$ </span>{command}
      </pre>
    </div>
  );
}

function EditRenderer({
  filePath,
  oldString,
  newString,
}: {
  filePath: string;
  oldString: string;
  newString: string;
}) {
  const fileName = filePath.split("/").pop() || filePath;
  const addCount = newString ? newString.split("\n").length : 0;
  const removeCount = oldString ? oldString.split("\n").length : 0;

  let diffLines: string[] = [];
  if (oldString || newString) {
    const patch = createTwoFilesPatch(fileName, fileName, oldString, newString, "", "", {
      context: 3,
    });
    diffLines = patch.split("\n").slice(4);
  }

  return (
    <div className="bg-panel/60 border border-default rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-control/60 border-b border-card">
        <Pencil className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
        <span className="text-[11px] font-mono text-secondary truncate flex-1">{filePath}</span>
        {addCount > 0 && (
          <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono" title={`${addCount} line${addCount !== 1 ? "s" : ""} added`}>+{addCount}</span>
        )}
        {removeCount > 0 && (
          <span className="text-[10px] text-rose-600 dark:text-rose-400 font-mono" title={`${removeCount} line${removeCount !== 1 ? "s" : ""} removed`}>-{removeCount}</span>
        )}
      </div>
      {diffLines.length > 0 && (
        <div className="overflow-x-auto text-[11px] font-mono leading-[1.6]">
          {diffLines.map((line, i) => (
            <DiffLine key={i} line={line} />
          ))}
        </div>
      )}
    </div>
  );
}

function DiffLine({ line }: { line: string }) {
  if (line.startsWith("+")) {
    return (
      <div className="px-3 bg-emerald-500/8 text-emerald-700 dark:text-emerald-300 border-l-2 border-emerald-500/50">
        {line}
      </div>
    );
  }
  if (line.startsWith("-")) {
    return (
      <div className="px-3 bg-rose-500/8 text-rose-700 dark:text-rose-300 border-l-2 border-rose-500/50">
        {line}
      </div>
    );
  }
  if (line.startsWith("@@")) {
    return (
      <div className="px-3 text-dimmed bg-control/40">
        {line}
      </div>
    );
  }
  return <div className="px-3 text-muted">{line}</div>;
}

function WriteRenderer({
  filePath,
  content,
}: {
  filePath: string;
  content: string;
}) {
  const lineCount = content ? content.split("\n").length : 0;
  const previewContent =
    content.length > WRITE_PREVIEW_MAX_CHARS
      ? content.slice(0, WRITE_PREVIEW_MAX_CHARS) + "\n..."
      : content;

  return (
    <div className="bg-panel/60 border border-default rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-control/60 border-b border-card">
        <FilePlus2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
        <span className="text-[11px] font-mono text-secondary truncate flex-1">{filePath}</span>
        <span className="text-[10px] text-dimmed">{lineCount} lines</span>
      </div>
      {content && (
        <pre className="p-3 overflow-x-auto text-[11px] font-mono text-muted max-h-48 overflow-y-auto leading-relaxed">
          {previewContent}
        </pre>
      )}
    </div>
  );
}

function tryFormatJson(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    const parsed = JSON.parse(trimmed);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return null;
  }
}

function ToolOutput({ text, isError }: { text: string; isError: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const formattedJson = tryFormatJson(text);
  const displayText = formattedJson || text;
  const lines = displayText.split("\n");
  const shouldTruncate = lines.length > MAX_COLLAPSED_LINES;
  const displayed =
    !expanded && shouldTruncate
      ? lines.slice(0, MAX_COLLAPSED_LINES).join("\n") + "\n..."
      : displayText;

  if (formattedJson) {
    return (
      <div className="relative">
        <div className="flex items-center justify-between px-3 py-1 bg-control/60 border-b border-card">
          <span className="text-[10px] font-medium text-dimmed uppercase tracking-wider">json</span>
          <CopyButton text={formattedJson} />
        </div>
        <MarkdownRenderer
          content={`\`\`\`json\n${displayed}\n\`\`\``}
          className="tool-output-json [&>div]:my-0 [&>div]:border-0 [&>div]:rounded-none [&_pre]:max-h-96 [&_pre]:overflow-y-auto"
        />
        {shouldTruncate && !expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="text-[10px] text-muted hover:text-secondary hover:bg-control/30 rounded px-3 pb-2"
          >
            Show all ({lines.length} lines)
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="relative">
      <pre
        className={`text-xs p-3 overflow-x-auto whitespace-pre-wrap break-words max-h-96 overflow-y-auto ${
          isError ? "text-rose-700 dark:text-rose-300" : "text-teal-700 dark:text-teal-200/80"
        }`}
      >
        {displayed}
      </pre>
      {shouldTruncate && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="text-[10px] text-muted hover:text-secondary hover:bg-control/30 rounded px-3 pb-2"
        >
          Show all ({lines.length} lines)
        </button>
      )}
    </div>
  );
}

const TOOL_PILL_BASE = "bg-slate-500/10 hover:bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-400/25 dark:border-slate-500/20";

function getToolIconAndColor(name: string): { icon: React.ReactNode; color: string } {
  const n = name.toLowerCase();
  if (n === "bash") {
    return {
      icon: <Terminal className="w-4 h-4 text-green-600 dark:text-green-400" />,
      color: TOOL_PILL_BASE,
    };
  }
  if (n === "edit") {
    return {
      icon: <Pencil className="w-4 h-4 text-blue-600 dark:text-blue-400" />,
      color: TOOL_PILL_BASE,
    };
  }
  if (n === "read") {
    return {
      icon: <FileCode className="w-4 h-4 text-sky-600 dark:text-sky-400" />,
      color: TOOL_PILL_BASE,
    };
  }
  if (n === "write") {
    return {
      icon: <FilePlus2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />,
      color: TOOL_PILL_BASE,
    };
  }
  if (n === "grep") {
    return {
      icon: <Search className="w-4 h-4 text-amber-600 dark:text-amber-400" />,
      color: TOOL_PILL_BASE,
    };
  }
  if (n === "glob") {
    return {
      icon: <FolderOpen className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />,
      color: TOOL_PILL_BASE,
    };
  }
  if (n === "agent" || n.includes("task") || n.includes("agent")) {
    return {
      icon: <Bot className="w-4 h-4 text-violet-600 dark:text-violet-400" />,
      color: "bg-violet-500/10 hover:bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-400/25 dark:border-violet-500/20",
    };
  }
  return {
    icon: <Wrench className="w-4 h-4 text-muted" />,
    color: TOOL_PILL_BASE,
  };
}

function getToolPreview(name: string, input: unknown): string {
  const data = input as Record<string, unknown> | undefined;
  if (!data) return "";
  const n = name.toLowerCase();
  if (n === "bash") return String(data.command || "").slice(0, 60);
  if (n === "edit" || n === "read" || n === "write") {
    const fp = String(data.file_path || "");
    return fp.split("/").slice(-2).join("/");
  }
  if (n === "grep" || n === "glob") return String(data.pattern || "").slice(0, 40);
  return "";
}

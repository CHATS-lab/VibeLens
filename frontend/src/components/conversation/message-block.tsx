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
} from "lucide-react";
import { useState } from "react";
import { createTwoFilesPatch } from "diff";
import type { Step, ToolCall, ObservationResult } from "../../types";
import { sanitizeText } from "../../utils";
import { MarkdownRenderer } from "../markdown-renderer";
import { CopyButton } from "../copy-button";

const MAX_COLLAPSED_LINES = 8;
const WRITE_PREVIEW_MAX_CHARS = 500;
const AUTO_EXPAND_LINE_THRESHOLD = 20;

interface StepBlockProps {
  step: Step;
}

export function StepBlock({ step }: StepBlockProps) {
  if (step.source === "system") {
    return <SystemStep step={step} />;
  }
  if (step.source === "user") {
    if (step.extra?.is_skill_output) {
      return <SkillStep step={step} />;
    }
    return <UserStep step={step} />;
  }
  if (step.source === "agent") {
    return <AgentStep step={step} />;
  }
  return null;
}

/** @deprecated Use StepBlock instead. Kept for backward compatibility during migration. */
export const MessageBlock = StepBlock;

function UserStep({ step }: { step: Step }) {
  const text = sanitizeText(step.message);
  if (!text) return null;
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] bg-indigo-600/80 text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm overflow-hidden break-words">
        <MarkdownRenderer content={text} className="user-markdown" />
      </div>
    </div>
  );
}

function SystemStep({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  const text = sanitizeText(step.message);
  if (!text) return null;
  const previewSnippet = text.split("\n")[0].slice(0, 80);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] border transition-colors bg-zinc-800/50 hover:bg-zinc-800/80 text-zinc-500 border-zinc-700"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Monitor className="w-3.5 h-3.5" />
        <span className="font-medium">System</span>
        {!open && (
          <span className="text-zinc-600 truncate max-w-[250px] ml-0.5">{previewSnippet}</span>
        )}
      </button>
      {open && (
        <div className="mt-1 bg-zinc-900/60 border border-zinc-700 rounded-lg p-3">
          <pre className="text-xs text-zinc-500 whitespace-pre-wrap break-words overflow-x-auto max-h-96 overflow-y-auto">
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
  const text = sanitizeText(step.message);
  if (!text) return null;
  const skillName = extractSkillName(text);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] border transition-colors bg-amber-500/10 hover:bg-amber-500/15 text-amber-300 border-amber-500/20"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Zap className="w-3.5 h-3.5" />
        <span className="font-medium">Skill</span>
        {skillName && <span className="text-amber-400/70 ml-0.5">/{skillName}</span>}
      </button>
      {open && (
        <div className="mt-1 bg-amber-500/5 border border-amber-500/20 rounded-lg p-3">
          <pre className="text-xs text-amber-200/70 whitespace-pre-wrap overflow-x-auto max-h-96 overflow-y-auto">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}

function AgentStep({ step }: { step: Step }) {
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
      {step.message && <TextBlock text={step.message} />}
      {step.reasoning_content && <ThinkingBlock text={step.reasoning_content} />}
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
        className="flex items-center gap-2 w-full px-3 py-2 text-xs text-cyan-300 hover:bg-white/5 transition-colors"
      >
        {open ? <ChevronDown className="w-3 h-3 shrink-0" /> : <ChevronRight className="w-3 h-3 shrink-0" />}
        <Layers className="w-3.5 h-3.5" />
        <span className="font-medium">{toolCalls.length} parallel calls</span>
        {!open && (
          <span className="text-zinc-500 truncate ml-1">{preview}</span>
        )}
      </button>
      {open && (
        <div className="border-t border-cyan-500/20">
          <div className="border-l-2 border-cyan-500/30 ml-3 pl-3 py-2 space-y-1">
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

function TextBlock({ text }: { text: string }) {
  const cleaned = sanitizeText(text);
  if (!cleaned) return null;
  return (
    <div className="max-w-[85%] text-zinc-100 text-sm break-words overflow-hidden">
      <MarkdownRenderer content={cleaned} />
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
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/15 text-[11px] text-amber-400/90 border border-amber-500/20 transition-colors"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Lightbulb className="w-3.5 h-3.5" />
        <span className="font-medium">Thinking</span>
      </button>
      {open && (
        <div className="mt-1 bg-zinc-900/80 border border-zinc-800 rounded-lg p-3">
          <pre className="text-xs text-amber-200/80 whitespace-pre-wrap overflow-x-auto">
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
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] border transition-colors ${color}`}
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {icon}
        <span className="font-medium">{name}</span>
        {!open && preview && (
          <span className="text-zinc-500 truncate max-w-[200px] ml-0.5">{preview}</span>
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
  const rawContent = result.content || "";
  const isError = typeof rawContent === "string" && rawContent.startsWith(ERROR_PREFIX);
  const content = isError ? rawContent.slice(ERROR_PREFIX.length) : rawContent;
  if (!content) return null;

  const lineCount = content.split("\n").length;
  const isShort = lineCount <= AUTO_EXPAND_LINE_THRESHOLD;
  const [open, setOpen] = useState(isShort);

  if (isShort) {
    return (
      <div className="max-w-[85%] mt-1 bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
        <ToolOutput text={content} isError={isError} />
      </div>
    );
  }

  const previewSnippet = content.split("\n")[0].slice(0, 80);

  return (
    <div className="max-w-[85%]">
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] border transition-colors ${
          isError
            ? "bg-rose-500/10 hover:bg-rose-500/15 text-rose-300 border-rose-500/20"
            : "bg-teal-500/10 hover:bg-teal-500/15 text-teal-300 border-teal-500/20"
        }`}
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {isError ? <X className="w-3.5 h-3.5" /> : <Check className="w-3.5 h-3.5" />}
        <span className="font-medium">{isError ? "Error" : "Result"}</span>
        {!open && (
          <span className="text-zinc-500 truncate max-w-[250px] ml-0.5">{previewSnippet}</span>
        )}
      </button>
      {open && (
        <div className="mt-1 bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
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
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-800/60 border-b border-zinc-700/40">
          <FileCode className="w-3.5 h-3.5 text-sky-400" />
          <span className="text-[11px] font-mono text-zinc-300 truncate flex-1">{filePath}</span>
          {lang && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-700/60 text-zinc-400 uppercase">{lang}</span>
          )}
          <CopyButton text={filePath} />
        </div>
      </div>
    );
  }

  if (n === "grep") {
    return (
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 bg-zinc-800/60">
          <Search className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-[11px] font-mono text-zinc-300">
            {Boolean(data.pattern) && <span className="text-amber-300">{String(data.pattern)}</span>}
            {Boolean(data.path) && <span className="text-zinc-500 ml-2">in {String(data.path)}</span>}
          </span>
        </div>
      </div>
    );
  }

  if (n === "glob") {
    return (
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 bg-zinc-800/60">
          <FolderOpen className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-[11px] font-mono text-zinc-300">
            {Boolean(data.pattern) && <span className="text-cyan-300">{String(data.pattern)}</span>}
            {Boolean(data.path) && <span className="text-zinc-500 ml-2">in {String(data.path)}</span>}
          </span>
        </div>
      </div>
    );
  }

  const jsonStr = JSON.stringify(data, null, 2);
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
      <MarkdownRenderer
        content={`\`\`\`json\n${jsonStr}\n\`\`\``}
        className="[&>div]:my-0 [&>div]:border-0 [&>div]:rounded-none"
      />
    </div>
  );
}

function BashRenderer({ command }: { command: string }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-800/60 border-b border-zinc-700/40">
        <div className="flex items-center gap-1.5">
          <Terminal className="w-3.5 h-3.5 text-green-400" />
          <span className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider">Command</span>
        </div>
        <CopyButton text={command} />
      </div>
      <pre className="p-3 overflow-x-auto text-[12px] font-mono text-green-300 leading-relaxed">
        <span className="text-zinc-500">$ </span>{command}
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
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-800/60 border-b border-zinc-700/40">
        <Pencil className="w-3.5 h-3.5 text-blue-400" />
        <span className="text-[11px] font-mono text-zinc-300 truncate flex-1">{filePath}</span>
        {addCount > 0 && (
          <span className="text-[10px] text-emerald-400 font-mono" title={`${addCount} line${addCount !== 1 ? "s" : ""} added`}>+{addCount}</span>
        )}
        {removeCount > 0 && (
          <span className="text-[10px] text-rose-400 font-mono" title={`${removeCount} line${removeCount !== 1 ? "s" : ""} removed`}>-{removeCount}</span>
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
      <div className="px-3 bg-emerald-500/8 text-emerald-300 border-l-2 border-emerald-500/50">
        {line}
      </div>
    );
  }
  if (line.startsWith("-")) {
    return (
      <div className="px-3 bg-rose-500/8 text-rose-300 border-l-2 border-rose-500/50">
        {line}
      </div>
    );
  }
  if (line.startsWith("@@")) {
    return (
      <div className="px-3 text-zinc-500 bg-zinc-800/40">
        {line}
      </div>
    );
  }
  return <div className="px-3 text-zinc-400">{line}</div>;
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
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-800/60 border-b border-zinc-700/40">
        <FilePlus2 className="w-3.5 h-3.5 text-emerald-400" />
        <span className="text-[11px] font-mono text-zinc-300 truncate flex-1">{filePath}</span>
        <span className="text-[10px] text-zinc-500">{lineCount} lines</span>
      </div>
      {content && (
        <pre className="p-3 overflow-x-auto text-[11px] font-mono text-zinc-400 max-h-48 overflow-y-auto leading-relaxed">
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
        <div className="flex items-center justify-between px-3 py-1 bg-zinc-800/60 border-b border-zinc-700/40">
          <span className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">json</span>
          <CopyButton text={formattedJson} />
        </div>
        <MarkdownRenderer
          content={`\`\`\`json\n${displayed}\n\`\`\``}
          className="tool-output-json [&>div]:my-0 [&>div]:border-0 [&>div]:rounded-none [&_pre]:max-h-96 [&_pre]:overflow-y-auto"
        />
        {shouldTruncate && !expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="text-[10px] text-zinc-400 hover:text-zinc-200 px-3 pb-2"
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
          isError ? "text-rose-300" : "text-teal-200/80"
        }`}
      >
        {displayed}
      </pre>
      {shouldTruncate && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="text-[10px] text-zinc-400 hover:text-zinc-200 px-3 pb-2"
        >
          Show all ({lines.length} lines)
        </button>
      )}
    </div>
  );
}

function getToolIconAndColor(name: string): { icon: React.ReactNode; color: string } {
  const n = name.toLowerCase();
  if (n === "bash") {
    return {
      icon: <Terminal className="w-3.5 h-3.5 text-green-400" />,
      color: "bg-slate-500/10 hover:bg-slate-500/15 text-slate-300 border-slate-500/20",
    };
  }
  if (n === "edit") {
    return {
      icon: <Pencil className="w-3.5 h-3.5 text-blue-400" />,
      color: "bg-slate-500/10 hover:bg-slate-500/15 text-slate-300 border-slate-500/20",
    };
  }
  if (n === "read") {
    return {
      icon: <FileCode className="w-3.5 h-3.5 text-sky-400" />,
      color: "bg-slate-500/10 hover:bg-slate-500/15 text-slate-300 border-slate-500/20",
    };
  }
  if (n === "write") {
    return {
      icon: <FilePlus2 className="w-3.5 h-3.5 text-emerald-400" />,
      color: "bg-slate-500/10 hover:bg-slate-500/15 text-slate-300 border-slate-500/20",
    };
  }
  if (n === "grep") {
    return {
      icon: <Search className="w-3.5 h-3.5 text-amber-400" />,
      color: "bg-slate-500/10 hover:bg-slate-500/15 text-slate-300 border-slate-500/20",
    };
  }
  if (n === "glob") {
    return {
      icon: <FolderOpen className="w-3.5 h-3.5 text-cyan-400" />,
      color: "bg-slate-500/10 hover:bg-slate-500/15 text-slate-300 border-slate-500/20",
    };
  }
  if (n === "agent" || n.includes("task") || n.includes("agent")) {
    return {
      icon: <Bot className="w-3.5 h-3.5 text-violet-400" />,
      color: "bg-violet-500/10 hover:bg-violet-500/15 text-violet-300 border-violet-500/20",
    };
  }
  return {
    icon: <Wrench className="w-3.5 h-3.5 text-zinc-400" />,
    color: "bg-slate-500/10 hover:bg-slate-500/15 text-slate-300 border-slate-500/20",
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

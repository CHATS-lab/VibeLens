import {
  Terminal,
  FileCode,
  FilePlus2,
  Search,
  FolderOpen,
  Bot,
  Wrench,
  Pencil,
  ChevronDown,
  ChevronRight,
  Lightbulb,
} from "lucide-react";
import { useState } from "react";
import { createTwoFilesPatch } from "diff";
import type { ToolCall } from "../../types";
import { MarkdownRenderer } from "../ui/markdown-renderer";
import { CopyButton } from "../ui/copy-button";

const WRITE_PREVIEW_MAX_CHARS = 500;

const TOOL_PILL_BASE =
  "bg-slate-500/10 hover:bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-400/25 dark:border-slate-500/20";

export function getToolIconAndColor(name: string): { icon: React.ReactNode; color: string } {
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
      color:
        "bg-violet-500/10 hover:bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-400/25 dark:border-violet-500/20",
    };
  }
  return {
    icon: <Wrench className="w-4 h-4 text-muted" />,
    color: TOOL_PILL_BASE,
  };
}

/** Pull a skill name out of a Skill-shaped tool call's arguments.
 *
 * Each agent uses its own argument key (Claude: ``skill``, OpenCode: ``name``,
 * Hermes/Gemini may pass a path). We try the obvious keys, then fall back to
 * extracting the directory name from any path argument that points at a
 * SKILL.md file.
 */
export function getSkillName(input: unknown): string {
  const data = input as Record<string, unknown> | undefined;
  if (!data) return "";
  const direct = data.skill ?? data.skill_name ?? data.name;
  if (direct) return String(direct);
  const path = data.path ?? data.file_path;
  if (path) {
    const parts = String(path).split("/").filter(Boolean);
    const idx = parts.findIndex((p) => p.toLowerCase() === "skill.md");
    if (idx > 0) return parts[idx - 1];
    return parts[parts.length - 1] || "";
  }
  return "";
}

export function getToolPreview(name: string, input: unknown): string {
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

export function ToolUseBlock({ toolCall }: { toolCall: ToolCall }) {
  const [open, setOpen] = useState(false);
  const name = toolCall.function_name || "unknown";
  // Skill tool calls (claude/codebuddy 'Skill', gemini 'activate_skill',
  // opencode 'skill') get an amber highlight to distinguish them from
  // generic tool invocations. The is_skill flag is the typed signal set
  // by parsers via helpers.is_skill_tool — see ToolCall.is_skill in the
  // backend model.
  const isSkill = !!toolCall.is_skill;
  const { icon, color } = isSkill
    ? {
        icon: <Lightbulb className="w-4 h-4" />,
        color:
          "bg-amber-500/10 hover:bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/25",
      }
    : getToolIconAndColor(name);
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
        {isSkill && <span className="text-[10px] uppercase tracking-wide opacity-70">skill</span>}
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

export function ToolInputRenderer({
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
      <div className="bg-panel/30 border border-default rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-control/40 border-b border-card">
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
      <div className="bg-panel/30 border border-default rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 bg-control/40">
          <Search className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
          <span className="text-[11px] font-mono text-secondary">
            {Boolean(data.pattern) && (
              <span className="text-amber-700 dark:text-amber-300">{String(data.pattern)}</span>
            )}
            {Boolean(data.path) && (
              <span className="text-dimmed ml-2">in {String(data.path)}</span>
            )}
          </span>
        </div>
      </div>
    );
  }

  if (n === "glob") {
    return (
      <div className="bg-panel/30 border border-default rounded-lg overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 bg-control/40">
          <FolderOpen className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
          <span className="text-[11px] font-mono text-secondary">
            {Boolean(data.pattern) && (
              <span className="text-cyan-700 dark:text-cyan-300">{String(data.pattern)}</span>
            )}
            {Boolean(data.path) && (
              <span className="text-dimmed ml-2">in {String(data.path)}</span>
            )}
          </span>
        </div>
      </div>
    );
  }

  const jsonStr = JSON.stringify(data, null, 2);
  return (
    <div className="bg-panel/30 border border-default rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1 bg-control/40 border-b border-card">
        <span className="text-[10px] font-medium text-dimmed uppercase tracking-wider">
          arguments
        </span>
        <CopyButton text={jsonStr} />
      </div>
      <MarkdownRenderer
        content={`\`\`\`json\n${jsonStr}\n\`\`\``}
        className="[&>div]:my-0 [&>div]:border-0 [&>div]:rounded-none"
      />
    </div>
  );
}

function BashRenderer({ command }: { command: string }) {
  return (
    <div className="bg-panel/30 border border-default rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-control/40 border-b border-card">
        <div className="flex items-center gap-1.5">
          <Terminal className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
          <span className="text-[10px] font-medium text-muted uppercase tracking-wider">Command</span>
        </div>
        <CopyButton text={command} />
      </div>
      <pre className="p-3 overflow-x-auto text-[12px] font-mono text-green-800 dark:text-green-200 leading-relaxed">
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
    <div className="bg-panel/30 border border-default rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-control/40 border-b border-card">
        <Pencil className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
        <span className="text-[11px] font-mono text-secondary truncate flex-1">{filePath}</span>
        {addCount > 0 && (
          <span
            className="text-[10px] text-emerald-600 dark:text-emerald-400 font-mono"
            title={`${addCount} line${addCount !== 1 ? "s" : ""} added`}
          >
            +{addCount}
          </span>
        )}
        {removeCount > 0 && (
          <span
            className="text-[10px] text-rose-600 dark:text-rose-400 font-mono"
            title={`${removeCount} line${removeCount !== 1 ? "s" : ""} removed`}
          >
            -{removeCount}
          </span>
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
    <div className="bg-panel/30 border border-default rounded-lg overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 bg-control/40 border-b border-card">
        <FilePlus2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
        <span className="text-[11px] font-mono text-secondary truncate flex-1">{filePath}</span>
        <span className="text-[10px] text-dimmed">{lineCount} lines</span>
      </div>
      {content && (
        <pre className="p-3 overflow-x-auto text-[11px] font-mono text-secondary max-h-48 overflow-y-auto leading-relaxed">
          {previewContent}
        </pre>
      )}
    </div>
  );
}

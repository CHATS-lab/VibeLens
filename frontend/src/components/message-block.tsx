import {
  ChevronDown,
  ChevronRight,
  Terminal,
  FileEdit,
  FileText,
  Search,
  AlertCircle,
  CheckCircle2,
  Brain,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ContentBlock, Message } from "../types";
import { sanitizeText } from "../utils";

const MAX_COLLAPSED_LINES = 8;

interface MessageBlockProps {
  message: Message;
}

export function MessageBlock({ message }: MessageBlockProps) {
  if (message.role === "user") {
    return <UserMessage message={message} />;
  }
  if (message.role === "assistant") {
    return <AssistantMessage message={message} />;
  }
  return null;
}

function UserMessage({ message }: { message: Message }) {
  const content = message.content;
  if (typeof content === "string") {
    const text = sanitizeText(content);
    if (!text) return null;
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] bg-indigo-600/80 text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm whitespace-pre-wrap">
          {text}
        </div>
      </div>
    );
  }
  // User messages with tool_result blocks are rendered inline with tool calls
  const textBlocks = (content as ContentBlock[]).filter(
    (b) => b.type === "text" && b.text
  );
  if (textBlocks.length === 0) return null;
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] bg-indigo-600/80 text-white rounded-2xl rounded-br-md px-4 py-2.5 text-sm whitespace-pre-wrap">
        {textBlocks.map((b, i) => (
          <span key={i}>{sanitizeText(b.text || "")}</span>
        ))}
      </div>
    </div>
  );
}

function AssistantMessage({ message }: { message: Message }) {
  const blocks =
    typeof message.content === "string"
      ? [{ type: "text", text: message.content } as ContentBlock]
      : (message.content as ContentBlock[]);

  return (
    <div className="space-y-2">
      {blocks.map((block, i) => (
        <ContentBlockRenderer key={i} block={block} />
      ))}
    </div>
  );
}

function ContentBlockRenderer({ block }: { block: ContentBlock }) {
  switch (block.type) {
    case "text":
      return <TextBlock text={block.text || ""} />;
    case "thinking":
      return <ThinkingBlock text={block.thinking || ""} />;
    case "tool_use":
      return <ToolUseBlock block={block} />;
    case "tool_result":
      return <ToolResultBlock block={block} />;
    default:
      return null;
  }
}

function TextBlock({ text }: { text: string }) {
  const cleaned = sanitizeText(text);
  if (!cleaned) return null;
  return (
    <div className="bg-cyan-700/30 text-zinc-100 rounded-2xl rounded-bl-md px-4 py-2.5 text-sm prose prose-invert prose-sm max-w-none break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({node, ...props}) => <a {...props} className="text-cyan-300 hover:underline" />,
          code: ({node, ...props}) => <code {...props} className="bg-zinc-800 px-1.5 py-0.5 rounded text-cyan-200 font-mono text-xs" />,
          pre: ({node, ...props}) => <pre {...props} className="bg-zinc-800 p-3 rounded overflow-x-auto" />,
        }}
      >
        {cleaned}
      </ReactMarkdown>
    </div>
  );
}

function ThinkingBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (!text.trim()) return null;
  return (
    <CollapsiblePill
      open={open}
      onToggle={() => setOpen(!open)}
      icon={<Brain className="w-3.5 h-3.5" />}
      label="Thinking"
      className="bg-amber-500/10 border-amber-500/20 text-amber-300"
    >
      <pre className="text-xs text-amber-200/80 whitespace-pre-wrap overflow-x-auto p-3">
        {text}
      </pre>
    </CollapsiblePill>
  );
}

function ToolUseBlock({ block }: { block: ContentBlock }) {
  const [open, setOpen] = useState(false);
  const name = block.name || "unknown";
  const icon = getToolIcon(name);
  const preview = getToolPreview(name, block.input);

  return (
    <CollapsiblePill
      open={open}
      onToggle={() => setOpen(!open)}
      icon={icon}
      label={name}
      preview={preview}
      className="bg-zinc-800 border-zinc-700 text-zinc-300"
    >
      <ToolInputRenderer name={name} input={block.input} />
    </CollapsiblePill>
  );
}

function ToolResultBlock({ block }: { block: ContentBlock }) {
  const [open, setOpen] = useState(false);
  const isError = block.is_error === true;
  const content = extractResultText(block.content);
  if (!content) return null;

  return (
    <CollapsiblePill
      open={open}
      onToggle={() => setOpen(!open)}
      icon={
        isError ? (
          <AlertCircle className="w-3.5 h-3.5" />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5" />
        )
      }
      label={isError ? "Error" : "Result"}
      className={
        isError
          ? "bg-rose-500/10 border-rose-500/20 text-rose-300"
          : "bg-teal-500/10 border-teal-500/20 text-teal-300"
      }
    >
      <ToolOutput text={content} isError={isError} />
    </CollapsiblePill>
  );
}

function CollapsiblePill({
  open,
  onToggle,
  icon,
  label,
  preview,
  className,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  icon: React.ReactNode;
  label: string;
  preview?: string;
  className: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`rounded-lg border ${className} overflow-hidden`}>
      <button
        onClick={onToggle}
        className="flex items-center gap-2 w-full px-3 py-2 text-xs hover:bg-white/5 transition-colors"
      >
        {open ? (
          <ChevronDown className="w-3 h-3 shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 shrink-0" />
        )}
        {icon}
        <span className="font-medium">{label}</span>
        {!open && preview && (
          <span className="text-zinc-500 truncate ml-1">{preview}</span>
        )}
      </button>
      {open && <div className="border-t border-inherit">{children}</div>}
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

  if (name === "Bash" || name === "bash") {
    return (
      <div className="p-3">
        <div className="bg-zinc-900 rounded p-2 font-mono text-xs text-green-400">
          <span className="text-zinc-500">$ </span>
          {String(data.command || "")}
        </div>
      </div>
    );
  }

  if (name === "Edit" || name === "edit") {
    return (
      <div className="p-3 space-y-1">
        <div className="text-xs text-zinc-400 font-mono">
          {String(data.file_path || "")}
        </div>
        {Boolean(data.old_string) && (
          <pre className="text-xs bg-rose-950/30 text-rose-300 rounded p-2 overflow-x-auto">
            {`- ${String(data.old_string)}`}
          </pre>
        )}
        {Boolean(data.new_string) && (
          <pre className="text-xs bg-green-950/30 text-green-300 rounded p-2 overflow-x-auto">
            {`+ ${String(data.new_string)}`}
          </pre>
        )}
      </div>
    );
  }

  if (name === "Read" || name === "read") {
    return (
      <div className="p-3">
        <div className="text-xs text-zinc-400 font-mono">
          {String(data.file_path || "")}
        </div>
      </div>
    );
  }

  if (name === "Write" || name === "write") {
    return (
      <div className="p-3 space-y-1">
        <div className="text-xs text-zinc-400 font-mono">
          {String(data.file_path || "")}
        </div>
        {Boolean(data.content) && (
          <pre className="text-xs bg-zinc-900 text-zinc-300 rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">
            {String(data.content)}
          </pre>
        )}
      </div>
    );
  }

  if (name === "Grep" || name === "grep" || name === "Glob" || name === "glob") {
    return (
      <div className="p-3">
        <div className="text-xs text-zinc-400 font-mono">
          {Boolean(data.pattern) && <span>pattern: {String(data.pattern)}</span>}
          {Boolean(data.path) && <span className="ml-2">in: {String(data.path)}</span>}
        </div>
      </div>
    );
  }

  return (
    <pre className="text-xs text-zinc-400 p-3 overflow-x-auto whitespace-pre-wrap">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function ToolOutput({ text, isError }: { text: string; isError: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const lines = text.split("\n");
  const shouldTruncate = lines.length > MAX_COLLAPSED_LINES;
  const displayed =
    !expanded && shouldTruncate
      ? lines.slice(0, MAX_COLLAPSED_LINES).join("\n") + "\n..."
      : text;

  return (
    <div className="relative">
      <pre
        className={`text-xs p-3 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto ${
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

function getToolIcon(name: string): React.ReactNode {
  const n = name.toLowerCase();
  if (n === "bash") return <Terminal className="w-3.5 h-3.5" />;
  if (n === "edit" || n === "write")
    return <FileEdit className="w-3.5 h-3.5" />;
  if (n === "read") return <FileText className="w-3.5 h-3.5" />;
  if (n === "grep" || n === "glob")
    return <Search className="w-3.5 h-3.5" />;
  return <Wrench className="w-3.5 h-3.5" />;
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

function extractResultText(content: unknown): string {
  if (!content) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === "string") return item;
        if (typeof item === "object" && item !== null && "text" in item)
          return String((item as { text: string }).text);
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return String(content);
}

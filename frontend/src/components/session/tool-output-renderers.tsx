import { Check, X, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { ObservationResult } from "../../types";
import { PREVIEW_LONG } from "../../constants";
import { MarkdownRenderer } from "../ui/markdown-renderer";
import { ContentRenderer } from "./content-renderer";
import { CopyButton } from "../ui/copy-button";

const ERROR_PREFIX = "[ERROR] ";
const AUTO_EXPAND_LINE_THRESHOLD = 20;
const MAX_COLLAPSED_LINES = 8;

export function ToolResultBlock({ result }: { result: ObservationResult }) {
  const rawContent = result.content;
  if (!rawContent) return null;

  // Handle multimodal content (images in tool results)
  if (Array.isArray(rawContent)) {
    return (
      <div className="max-w-[85%] mt-1 bg-panel/30 border border-default rounded-lg overflow-hidden p-3">
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
      <div className="max-w-[85%] mt-1 bg-panel/30 border border-default rounded-lg overflow-hidden">
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
        <div className="mt-1 bg-panel/30 border border-default rounded-lg overflow-hidden">
          <ToolOutput text={content} isError={isError} />
        </div>
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
        <div className="flex items-center justify-between px-3 py-1 bg-control/40 border-b border-card">
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
          isError ? "text-rose-800 dark:text-rose-200" : "text-teal-800 dark:text-teal-100"
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

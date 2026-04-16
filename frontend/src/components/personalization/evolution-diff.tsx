import { FileText } from "lucide-react";
import type { SkillEdit } from "../../types";

type DiffRow =
  | { type: "hunk-header"; index: number }
  | { type: "context"; lineNum: number; text: string }
  | { type: "removed"; lineNum: number; text: string }
  | { type: "added"; lineNum: number; text: string }
  | { type: "separator" };

interface EvolutionDiffViewProps {
  skillName: string;
  edits: SkillEdit[];
  /** Original SKILL.md content for computing real line numbers. */
  originalContent?: string;
}

export function EvolutionDiffView({ skillName, edits, originalContent }: EvolutionDiffViewProps) {
  const rows = buildDiffRows(edits, originalContent);

  return (
    <div className="rounded-lg border border-card overflow-hidden bg-panel/60">
      <DiffFileHeader skillName={skillName} editCount={edits.length} />
      <div className="font-mono text-xs">
        {rows.map((row, i) => {
          switch (row.type) {
            case "hunk-header":
              return <HunkHeader key={i} index={row.index} />;
            case "context":
              return <ContextLine key={i} lineNum={row.lineNum} text={row.text} />;
            case "removed":
              return <RemovedLine key={i} lineNum={row.lineNum} text={row.text} />;
            case "added":
              return <AddedLine key={i} lineNum={row.lineNum} text={row.text} />;
            case "separator":
              return <HunkSeparator key={i} />;
          }
        })}
      </div>
    </div>
  );
}

function DiffFileHeader({ skillName, editCount }: { skillName: string; editCount: number }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-control/80 border-b border-card text-xs">
      <FileText className="w-3.5 h-3.5 text-muted" />
      <span className="font-mono text-secondary">{skillName}/SKILL.md</span>
      <span className="text-dimmed ml-auto">
        {editCount} edit{editCount !== 1 ? "s" : ""}
      </span>
    </div>
  );
}

function HunkHeader({ index }: { index: number }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-subtle text-[10px] flex-wrap border-b border-default/40">
      <span className="text-dimmed ml-auto">hunk {index + 1}</span>
    </div>
  );
}

function ContextLine({ lineNum, text }: { lineNum: number; text: string }) {
  return (
    <div className="flex">
      <span className="w-10 shrink-0 text-right pr-1.5 text-[10px] leading-5 select-none text-faint">
        {lineNum}
      </span>
      <span className="w-5 shrink-0 leading-5 select-none" />
      <span className="flex-1 px-2 leading-5 whitespace-pre-wrap break-words text-muted">
        {text}
      </span>
    </div>
  );
}

function RemovedLine({ lineNum, text }: { lineNum: number; text: string }) {
  return (
    <div className="flex bg-red-50 dark:bg-red-950/30">
      <span className="w-10 shrink-0 text-right pr-1.5 text-[10px] leading-5 select-none bg-red-100 text-red-500/70 dark:bg-red-900/40 dark:text-red-400/70">
        {lineNum}
      </span>
      <span className="w-5 shrink-0 text-center leading-5 select-none text-red-500/70">-</span>
      <span className="flex-1 px-2 leading-5 whitespace-pre-wrap break-words text-red-700 dark:text-red-300/90">
        {text}
      </span>
    </div>
  );
}

function AddedLine({ lineNum, text }: { lineNum: number; text: string }) {
  return (
    <div className="flex bg-emerald-50 dark:bg-emerald-950/25">
      <span className="w-10 shrink-0 text-right pr-1.5 text-[10px] leading-5 select-none bg-emerald-100 text-emerald-500/70 dark:bg-emerald-900/35 dark:text-emerald-400/70">
        {lineNum}
      </span>
      <span className="w-5 shrink-0 text-center leading-5 select-none text-emerald-500/70">+</span>
      <span className="flex-1 px-2 leading-5 whitespace-pre-wrap break-words text-emerald-700 dark:text-emerald-300/90">
        {text}
      </span>
    </div>
  );
}

function HunkSeparator() {
  return (
    <div className="flex items-center py-0.5 bg-subtle text-faint text-[10px] select-none border-y border-default/40">
      <span className="w-10 shrink-0" />
      <span className="px-2">&middot;&middot;&middot;</span>
    </div>
  );
}

/**
 * Find the 1-based line number where `needle` starts in `haystack`.
 * Returns 0 if not found.
 */
function findLineNumber(haystack: string, needle: string): number {
  const idx = haystack.indexOf(needle);
  if (idx < 0) return 0;
  return haystack.substring(0, idx).split("\n").length;
}

/**
 * Compute the common prefix and suffix line counts between old and new lines.
 * These are the context lines the LLM embedded around the actual change.
 */
function computeContextBounds(oldLines: string[], newLines: string[]): { prefixLen: number; suffixLen: number } {
  let prefixLen = 0;
  const maxPrefix = Math.min(oldLines.length, newLines.length);
  while (prefixLen < maxPrefix && oldLines[prefixLen] === newLines[prefixLen]) {
    prefixLen++;
  }

  let suffixLen = 0;
  const maxSuffix = Math.min(oldLines.length - prefixLen, newLines.length - prefixLen);
  while (
    suffixLen < maxSuffix &&
    oldLines[oldLines.length - 1 - suffixLen] === newLines[newLines.length - 1 - suffixLen]
  ) {
    suffixLen++;
  }

  return { prefixLen, suffixLen };
}

function buildDiffRows(edits: SkillEdit[], originalContent?: string): DiffRow[] {
  const rows: DiffRow[] = [];

  edits.forEach((edit, idx) => {
    if (idx > 0) {
      rows.push({ type: "separator" });
    }
    rows.push({ type: "hunk-header", index: idx });

    // Compute the starting line number from the original file
    const startLine = originalContent && edit.old_string
      ? findLineNumber(originalContent, edit.old_string)
      : 0;

    const oldLines = splitText(edit.old_string);
    const newLines = splitText(edit.new_string);

    if (oldLines.length === 0 && newLines.length === 0) return;

    // For append edits (old_string is empty), just show added lines
    if (oldLines.length === 0) {
      const appendStart = originalContent ? originalContent.split("\n").length + 1 : 1;
      let addCursor = appendStart;
      for (const line of newLines) {
        rows.push({ type: "added", lineNum: addCursor++, text: line });
      }
      return;
    }

    // Find matching context prefix/suffix between old and new
    const { prefixLen, suffixLen } = computeContextBounds(oldLines, newLines);

    let oldCursor = startLine || 1;
    let newCursor = startLine || 1;

    // Leading context lines (identical in old and new)
    for (let i = 0; i < prefixLen; i++) {
      rows.push({ type: "context", lineNum: oldCursor, text: oldLines[i] });
      oldCursor++;
      newCursor++;
    }

    // Changed old lines (removed)
    const oldChangeEnd = oldLines.length - suffixLen;
    for (let i = prefixLen; i < oldChangeEnd; i++) {
      rows.push({ type: "removed", lineNum: oldCursor++, text: oldLines[i] });
    }

    // Changed new lines (added)
    const newChangeEnd = newLines.length - suffixLen;
    for (let i = prefixLen; i < newChangeEnd; i++) {
      rows.push({ type: "added", lineNum: newCursor++, text: newLines[i] });
    }

    // Sync cursors after changed region
    const maxCursor = Math.max(oldCursor, newCursor);
    oldCursor = maxCursor;
    newCursor = maxCursor;

    // Trailing context lines
    for (let i = oldLines.length - suffixLen; i < oldLines.length; i++) {
      rows.push({ type: "context", lineNum: oldCursor, text: oldLines[i] });
      oldCursor++;
      newCursor++;
    }
  });

  return rows;
}

function splitText(text: string): string[] {
  if (!text || text.trim().length === 0) return [];
  return text.split("\n");
}

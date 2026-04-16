import { Tag, Wrench } from "lucide-react";
import { Tooltip } from "../tooltip";
import {
  normalizeSourceType,
  SOURCE_COLORS,
  SOURCE_DESCRIPTIONS,
  SOURCE_LABELS,
  SUBDIR_DESCRIPTIONS,
  SUBDIR_LABELS,
  TAG_DESCRIPTIONS,
} from "./constants";

/** Colored pill showing which agent interface a skill comes from. */
export function SourceBadge({ sourceType, sourcePath }: { sourceType: string; sourcePath?: string }) {
  const key = normalizeSourceType(sourceType);
  const colorClass = SOURCE_COLORS[key] || "bg-control-hover text-muted border-hover";
  const label = SOURCE_LABELS[key] || key;
  const description = SOURCE_DESCRIPTIONS[key] || sourcePath || key;

  return (
    <Tooltip text={description}>
      <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${colorClass}`}>
        {label}
      </span>
    </Tooltip>
  );
}

/** Small pill for a skill tag with hover description. */
export function TagBadge({ tag }: { tag: string }) {
  return (
    <Tooltip text={TAG_DESCRIPTIONS[tag] || `Tag: ${tag}`}>
      <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700 cursor-default">
        {tag}
      </span>
    </Tooltip>
  );
}

/** Rounded pill variant of TagBadge used in detail popups. */
export function TagPill({ tag }: { tag: string }) {
  return (
    <Tooltip text={TAG_DESCRIPTIONS[tag] || `Tag: ${tag}`}>
      <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700 cursor-default hover:bg-slate-200 dark:hover:bg-slate-700 transition">
        {tag}
      </span>
    </Tooltip>
  );
}

/** Mono-spaced pill showing an allowed tool name. */
export function ToolBadge({ tool }: { tool: string }) {
  return (
    <Tooltip text={`Allowed tool: ${tool}`}>
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-50 text-cyan-700 border border-cyan-200 dark:bg-cyan-900/30 dark:text-cyan-300 dark:border-cyan-700/40 font-mono font-medium cursor-default">
        {tool}
      </span>
    </Tooltip>
  );
}

/** Mono-spaced pill showing a subdirectory name. */
export function SubdirBadge({ dir }: { dir: string }) {
  return (
    <Tooltip text={SUBDIR_DESCRIPTIONS[dir] || `Subdirectory: ${dir}`}>
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700 font-mono cursor-default hover:bg-slate-200 dark:hover:bg-slate-700 transition">
        {SUBDIR_LABELS[dir] || dir}
      </span>
    </Tooltip>
  );
}

/** Row of tag badges with overflow count, prefixed by a Tag icon. */
export function TagList({ tags, max = 5 }: { tags: string[]; max?: number }) {
  if (tags.length === 0) return null;
  return (
    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
      <Tag className="w-3.5 h-3.5 text-secondary shrink-0" />
      {tags.slice(0, max).map((tag) => (
        <TagBadge key={tag} tag={tag} />
      ))}
      {tags.length > max && (
        <span className="text-xs text-secondary font-medium">+{tags.length - max}</span>
      )}
    </div>
  );
}

/** Row of tool badges with overflow count, prefixed by a Wrench icon. */
export function ToolList({ tools, max = 3 }: { tools: string[]; max?: number }) {
  if (tools.length === 0) return null;
  return (
    <div className="flex items-center gap-1 mt-1 flex-wrap">
      <Wrench className="w-3 h-3 text-muted shrink-0" />
      {tools.slice(0, max).map((tool) => (
        <ToolBadge key={tool} tool={tool} />
      ))}
      {tools.length > max && (
        <span className="text-[10px] text-muted font-medium">+{tools.length - max}</span>
      )}
    </div>
  );
}

/**
 * FlowDiagram — DOM/CSS conversation flow visualization.
 *
 * Renders a vertical flow of user→agent→tool cards grouped by phase.
 * Tool calls are shown as compact colored chips inside agent cards,
 * eliminating messy fan-out arrows. Dependencies are revealed on hover
 * via highlight rings on related tools.
 */

import { useState, useMemo, useCallback } from "react";
import type { Step, FlowData } from "../../types";
import { useTooltip, Tooltip, type TooltipContent } from "../analysis/tooltip";
import {
  computeFlow,
  type FlowPhaseGroup,
  type FlowToolChip,
} from "./flow-layout";

interface FlowDiagramProps {
  steps: Step[];
  flowData: FlowData;
}

const CATEGORY_STYLE: Record<string, { bg: string; ring: string; text: string; label: string }> = {
  file_read: { bg: "bg-blue-500/20", ring: "ring-blue-400/60", text: "text-blue-300", label: "read" },
  file_write: { bg: "bg-emerald-500/20", ring: "ring-emerald-400/60", text: "text-emerald-300", label: "write" },
  shell: { bg: "bg-amber-500/20", ring: "ring-amber-400/60", text: "text-amber-300", label: "shell" },
  search: { bg: "bg-sky-500/20", ring: "ring-sky-400/60", text: "text-sky-300", label: "search" },
  web: { bg: "bg-orange-500/20", ring: "ring-orange-400/60", text: "text-orange-300", label: "web" },
  agent: { bg: "bg-violet-500/20", ring: "ring-violet-400/60", text: "text-violet-300", label: "agent" },
  task: { bg: "bg-rose-500/20", ring: "ring-rose-400/60", text: "text-rose-300", label: "task" },
  other: { bg: "bg-zinc-500/20", ring: "ring-zinc-400/60", text: "text-zinc-400", label: "other" },
};

const PHASE_STYLE: Record<string, { border: string; label: string; dot: string; bg: string }> = {
  exploration: { border: "border-l-blue-400", label: "text-blue-400", dot: "bg-blue-400", bg: "bg-blue-500/[0.03]" },
  implementation: { border: "border-l-emerald-400", label: "text-emerald-400", dot: "bg-emerald-400", bg: "bg-emerald-500/[0.03]" },
  debugging: { border: "border-l-red-400", label: "text-red-400", dot: "bg-red-400", bg: "bg-red-500/[0.03]" },
  verification: { border: "border-l-amber-400", label: "text-amber-400", dot: "bg-amber-400", bg: "bg-amber-500/[0.03]" },
  planning: { border: "border-l-violet-400", label: "text-violet-400", dot: "bg-violet-400", bg: "bg-violet-500/[0.03]" },
  mixed: { border: "border-l-zinc-500", label: "text-zinc-400", dot: "bg-zinc-500", bg: "bg-zinc-500/[0.02]" },
};

const RELATION_LABELS: Record<string, string> = {
  read_before_write: "read \u2192 write",
  search_then_read: "search \u2192 read",
  write_then_test: "edit \u2192 test",
  multi_edit: "re-edit",
  error_retry: "retry",
};

export function FlowDiagram({ steps, flowData }: FlowDiagramProps) {
  const { tip, show, move, hide } = useTooltip();
  const [hoveredToolId, setHoveredToolId] = useState<string | null>(null);

  const result = useMemo(
    () => computeFlow(steps, flowData.tool_graph, flowData.phase_segments),
    [steps, flowData]
  );

  // Bidirectional dependency lookup for hover highlighting
  const relatedTools = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const [sourceId, deps] of result.dependencies) {
      for (const dep of deps) {
        if (!map.has(sourceId)) map.set(sourceId, new Set());
        map.get(sourceId)!.add(dep.targetToolCallId);
        if (!map.has(dep.targetToolCallId)) map.set(dep.targetToolCallId, new Set());
        map.get(dep.targetToolCallId)!.add(sourceId);
      }
    }
    return map;
  }, [result.dependencies]);

  // Dependency label for a highlighted tool
  const depLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const [sourceId, deps] of result.dependencies) {
      for (const dep of deps) {
        const label = RELATION_LABELS[dep.relation] || dep.relation;
        map.set(`${sourceId}->${dep.targetToolCallId}`, label);
        map.set(`${dep.targetToolCallId}->${sourceId}`, label);
      }
    }
    return map;
  }, [result.dependencies]);

  const isHighlighted = useCallback(
    (toolCallId: string): boolean => {
      if (!hoveredToolId) return false;
      if (toolCallId === hoveredToolId) return true;
      return relatedTools.get(hoveredToolId)?.has(toolCallId) || false;
    },
    [hoveredToolId, relatedTools]
  );

  const getDepLabel = useCallback(
    (toolCallId: string): string | null => {
      if (!hoveredToolId || toolCallId === hoveredToolId) return null;
      return depLabels.get(`${hoveredToolId}->${toolCallId}`) || null;
    },
    [hoveredToolId, depLabels]
  );

  return (
    <div className="max-w-3xl mx-auto pb-8">
      {result.phases.map((phase, phaseIdx) => (
        <div key={phaseIdx} id={`flow-phase-${phaseIdx}`}>
          <PhaseSection phase={phase}>
            {phase.cards.map((card, cardIdx) => (
              <div key={card.data.id}>
                {cardIdx > 0 && <Connector />}
                {card.type === "user" ? (
                  <UserCard
                    label={card.data.label}
                    detail={card.data.detail}
                    onHover={show}
                    onMove={move}
                    onLeave={hide}
                  />
                ) : (
                  <AgentCard
                    label={card.data.label}
                    detail={card.data.detail}
                    tools={card.data.tools}
                    hoveredToolId={hoveredToolId}
                    onToolEnter={setHoveredToolId}
                    onToolLeave={() => setHoveredToolId(null)}
                    isHighlighted={isHighlighted}
                    getDepLabel={getDepLabel}
                    onHover={show}
                    onMove={move}
                    onLeave={hide}
                  />
                )}
              </div>
            ))}
          </PhaseSection>
          {/* Connector between phase sections */}
          {phaseIdx < result.phases.length - 1 && (
            <div className="flex items-center pl-6 py-1">
              <div className="flex flex-col items-center">
                <div className="w-px h-2 bg-zinc-700/30" />
                <div className="w-1 h-1 rounded-full bg-zinc-600/40" />
                <div className="w-px h-2 bg-zinc-700/30" />
              </div>
            </div>
          )}
        </div>
      ))}
      <Tooltip state={tip} />
    </div>
  );
}

function PhaseSection({
  phase,
  children,
}: {
  phase: FlowPhaseGroup;
  children: React.ReactNode;
}) {
  const style = PHASE_STYLE[phase.phase] || PHASE_STYLE.mixed;

  return (
    <div className={`rounded-lg ${style.bg}`}>
      <div className={`border-l-[3px] ${style.border} pl-5 pr-3 py-4`}>
        {/* Phase header */}
        <div className="flex items-center gap-2.5 mb-4">
          <span className={`w-2.5 h-2.5 rounded-full ${style.dot} ring-2 ring-current/10`} />
          <span className={`text-[11px] font-bold uppercase tracking-[0.14em] ${style.label}`}>
            {phase.phase}
          </span>
          <span className="text-[10px] text-zinc-500 font-medium">
            {phase.cards.length} step{phase.cards.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div>{children}</div>
      </div>
    </div>
  );
}

function Connector() {
  return (
    <div className="flex items-center justify-center py-1.5">
      <div className="flex flex-col items-center">
        <div className="w-px h-2.5 bg-zinc-700/40" />
        <div className="w-[5px] h-[5px] rounded-full border border-zinc-600/60 bg-zinc-800" />
        <div className="w-px h-2.5 bg-zinc-700/40" />
      </div>
    </div>
  );
}

function UserCard({
  label,
  detail,
  onHover,
  onMove,
  onLeave,
}: {
  label: string;
  detail: string;
  onHover: (e: React.MouseEvent, content: TooltipContent) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}) {
  return (
    <div
      className="group relative rounded-lg border border-indigo-500/30 bg-indigo-950/30 hover:border-indigo-400/50 hover:bg-indigo-950/40 transition-all"
      onMouseEnter={(e) => onHover(e, detail)}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      <div className="px-4 py-3 flex items-start gap-3">
        <span className="shrink-0 mt-0.5 w-6 h-6 rounded-md bg-indigo-500/25 border border-indigo-400/20 flex items-center justify-center">
          <svg className="w-3 h-3 text-indigo-300" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm2-3a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm4 8c0 1-1 1-1 1H3s-1 0-1-1 1-4 6-4 6 3 6 4zm-1-.004c-.001-.246-.154-.986-.832-1.664C11.516 10.68 10.289 10 8 10c-2.29 0-3.516.68-4.168 1.332-.678.678-.83 1.418-.832 1.664h10z"/>
          </svg>
        </span>
        <p className="text-[13px] leading-relaxed text-indigo-100 min-w-0 break-words">
          {label}
        </p>
      </div>
    </div>
  );
}

function AgentCard({
  label,
  detail,
  tools,
  hoveredToolId,
  onToolEnter,
  onToolLeave,
  isHighlighted,
  getDepLabel,
  onHover,
  onMove,
  onLeave,
}: {
  label: string;
  detail: string;
  tools: FlowToolChip[];
  hoveredToolId: string | null;
  onToolEnter: (id: string) => void;
  onToolLeave: () => void;
  isHighlighted: (toolCallId: string) => boolean;
  getDepLabel: (toolCallId: string) => string | null;
  onHover: (e: React.MouseEvent, content: TooltipContent) => void;
  onMove: (e: React.MouseEvent) => void;
  onLeave: () => void;
}) {
  // Group tools by category for summary display
  const grouped = useMemo(() => {
    const map = new Map<string, FlowToolChip[]>();
    for (const tool of tools) {
      const list = map.get(tool.category) || [];
      list.push(tool);
      map.set(tool.category, list);
    }
    const order = ["file_read", "search", "file_write", "shell", "web", "agent", "task", "other"];
    return [...map.entries()].sort(
      ([a], [b]) => (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) - (order.indexOf(b) === -1 ? 99 : order.indexOf(b))
    );
  }, [tools]);

  return (
    <div className="rounded-lg border border-cyan-500/20 bg-cyan-950/20 hover:border-cyan-400/35 transition-colors">
      {/* Agent message */}
      <div
        className="px-4 py-3 flex items-start gap-3"
        onMouseEnter={(e) => onHover(e, detail)}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
      >
        <span className="shrink-0 mt-0.5 w-6 h-6 rounded-md bg-cyan-500/20 border border-cyan-400/15 flex items-center justify-center">
          <svg className="w-3 h-3 text-cyan-300" viewBox="0 0 16 16" fill="currentColor">
            <path d="M6 12.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5zM3 8.062C3 6.76 4.235 5.765 5.53 5.886a26.58 26.58 0 0 0 4.94 0C11.765 5.765 13 6.76 13 8.062v1.157a.933.933 0 0 1-.765.935c-.845.147-2.34.346-4.235.346-1.895 0-3.39-.2-4.235-.346A.933.933 0 0 1 3 9.219V8.062zm4.542-.827a.25.25 0 0 0-.217.068l-.92.9a25.14 25.14 0 0 1-1.871-.183.25.25 0 0 0-.068.495c.55.076 1.232.149 2.02.193a.25.25 0 0 0 .189-.071l.754-.736.847 1.71a.25.25 0 0 0 .404.062l.932-.97a25.286 25.286 0 0 0 1.922-.188.25.25 0 0 0-.068-.495c-.538.074-1.207.145-1.98.189a.25.25 0 0 0-.166.076l-.754.785-.842-1.7a.25.25 0 0 0-.182-.135z"/>
            <path d="M8.5 1.866a1 1 0 1 0-1 0V3h-2A4.5 4.5 0 0 0 1 7.5V8a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1v1a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1v-.5A4.5 4.5 0 0 0 10.5 3h-2V1.866zM14 7.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7.5A3.5 3.5 0 0 1 5.5 4h5A3.5 3.5 0 0 1 14 7.5z"/>
          </svg>
        </span>
        <p className="text-[13px] leading-relaxed text-cyan-100 min-w-0 break-words">
          {label}
        </p>
      </div>

      {/* Tool calls section */}
      {tools.length > 0 && (
        <div className="border-t border-cyan-500/10 mx-3 px-1 py-2.5">
          {/* Header with count and category breakdown */}
          <div className="flex items-center gap-1.5 mb-2 px-1">
            <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
              {tools.length} tool{tools.length !== 1 ? "s" : ""}
            </span>
            <span className="text-zinc-700 text-[10px]">{"·"}</span>
            <div className="flex gap-1.5">
              {grouped.map(([cat, items]) => {
                const catStyle = CATEGORY_STYLE[cat] || CATEGORY_STYLE.other;
                return (
                  <span
                    key={cat}
                    className={`inline-flex items-center gap-1 text-[10px] ${catStyle.text}`}
                    title={`${items.length} ${cat.replace(/_/g, " ")}`}
                  >
                    <span className={`w-2 h-2 rounded-sm ${catStyle.bg} border border-current/20`} />
                    <span className="opacity-80">{catStyle.label}</span>
                    <span className="font-mono font-semibold">{items.length}</span>
                  </span>
                );
              })}
            </div>
          </div>
          {/* Tool pills */}
          <div className="flex flex-wrap gap-1.5 px-1">
            {tools.map((tool) => (
              <ToolChip
                key={tool.id}
                tool={tool}
                highlighted={isHighlighted(tool.toolCallId)}
                depLabel={getDepLabel(tool.toolCallId)}
                isAnyHovered={!!hoveredToolId}
                onEnter={() => onToolEnter(tool.toolCallId)}
                onLeave={onToolLeave}
                onHover={onHover}
                onMove={onMove}
                onHoverLeave={onLeave}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ToolChip({
  tool,
  highlighted,
  depLabel,
  isAnyHovered,
  onEnter,
  onLeave,
  onHover,
  onMove,
  onHoverLeave,
}: {
  tool: FlowToolChip;
  highlighted: boolean;
  depLabel: string | null;
  isAnyHovered: boolean;
  onEnter: () => void;
  onLeave: () => void;
  onHover: (e: React.MouseEvent, content: TooltipContent) => void;
  onMove: (e: React.MouseEvent) => void;
  onHoverLeave: () => void;
}) {
  const style = CATEGORY_STYLE[tool.category] || CATEGORY_STYLE.other;
  const dimmed = isAnyHovered && !highlighted;

  // Build rich tooltip with tool name header and formatted JSON body
  const richTooltip = useMemo(() => {
    const parts = tool.detail.split("\n");
    const toolName = parts[0] || tool.name;
    const argsText = parts.slice(1).join("\n").trim();
    if (!argsText) {
      return <span className="font-mono text-[12px] text-cyan-300">{toolName}</span>;
    }
    return (
      <div>
        <div className="font-mono text-[12px] font-semibold text-cyan-300 mb-1.5">{toolName}</div>
        <pre className="font-mono text-[11px] text-zinc-300 leading-snug whitespace-pre-wrap break-all m-0">
          {argsText}
        </pre>
      </div>
    );
  }, [tool.detail, tool.name]);

  return (
    <span
      className={`
        relative inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono
        border transition-all duration-150 cursor-default
        ${style.bg} ${style.text}
        ${highlighted ? `ring-2 ${style.ring} border-transparent brightness-125` : "border-transparent"}
        ${dimmed ? "opacity-25" : "opacity-100"}
        hover:opacity-100 hover:brightness-125
      `}
      onMouseEnter={(e) => {
        onEnter();
        onHover(e, richTooltip);
      }}
      onMouseMove={onMove}
      onMouseLeave={() => {
        onLeave();
        onHoverLeave();
      }}
    >
      {tool.name}
      {depLabel && (
        <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 px-1.5 py-px rounded-full text-[8px] font-sans font-bold bg-zinc-900 border border-zinc-500 text-zinc-200 whitespace-nowrap shadow-lg">
          {depLabel}
        </span>
      )}
    </span>
  );
}

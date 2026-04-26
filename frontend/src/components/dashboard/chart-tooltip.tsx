import { useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { TOOLTIP_OFFSET } from "./chart-constants";

export type TooltipContent = string | React.ReactNode;

export interface TooltipState {
  x: number;
  y: number;
  content: TooltipContent;
}

const MAX_WIDTH = 300;
const MAX_WIDTH_WIDE = 480;

/**
 * Tone vocabulary for ``MetricList`` rows. Maps semantic data categories
 * to a shared light/dark color palette so tooltips read the same across
 * every dashboard chart.
 */
export type MetricTone =
  | "input"
  | "output"
  | "cache_read"
  | "cache_write"
  | "tokens"
  | "total"
  | "cost"
  | "count"
  | "percent"
  | "muted"
  | "session_id"
  | "model";

const TONE_CLASSES: Record<MetricTone, string> = {
  input: "text-blue-600 dark:text-blue-400",
  output: "text-sky-600 dark:text-sky-400",
  cache_read: "text-emerald-600 dark:text-emerald-400",
  cache_write: "text-purple-600 dark:text-purple-400",
  tokens: "text-cyan-700 dark:text-cyan-400",
  total: "text-orange-600 dark:text-orange-400",
  cost: "text-emerald-700 dark:text-emerald-400",
  count: "text-secondary",
  percent: "text-muted",
  muted: "text-muted",
  session_id: "text-purple-600 dark:text-purple-400",
  model: "text-sky-700 dark:text-sky-400",
};

export interface MetricRow {
  label: string;
  value: string;
  tone?: MetricTone;
}

/**
 * Two-column ``label: value`` layout used inside chart tooltips.
 *
 * Renders an optional bold header line followed by N rows. Values are
 * tabular-num + monospace so digits line up. Pass a ``tone`` per row
 * to color the value semantically (e.g. ``cache_write`` -> purple).
 */
export function MetricList({
  header,
  rows,
}: {
  header?: React.ReactNode;
  rows: MetricRow[];
}) {
  return (
    <div className="font-mono text-[12px] leading-5">
      {header != null && (
        <div className="mb-1 pb-1 border-b border-card text-secondary font-semibold">
          {header}
        </div>
      )}
      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5">
        {rows.map((row, i) => (
          <div key={`${row.label}-${i}`} className="contents">
            <span className="text-secondary">{row.label}</span>
            <span className={`text-right tabular-nums ${TONE_CLASSES[row.tone ?? "count"]}`}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Tooltip({ state }: { state: TooltipState | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number }>({
    left: 0,
    top: 0,
  });

  const isRichContent = state != null && typeof state.content !== "string";
  const maxW = isRichContent ? MAX_WIDTH_WIDE : MAX_WIDTH;

  useEffect(() => {
    if (!state) return;
    const el = ref.current;
    const elW = el ? el.offsetWidth : maxW;
    const elH = el ? el.offsetHeight : 40;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = state.x + TOOLTIP_OFFSET;
    let top = state.y - 8;

    // Flip left if overflowing right edge
    if (left + elW > vw - 8) {
      left = state.x - elW - TOOLTIP_OFFSET;
    }
    // Clamp top to viewport
    if (top + elH > vh - 8) {
      top = vh - elH - 8;
    }
    if (top < 8) {
      top = 8;
    }

    setPos({ left, top });
  }, [state, maxW]);

  if (!state) return null;

  return createPortal(
    <div
      ref={ref}
      className={`fixed z-[9999] pointer-events-none px-3 py-2.5 rounded-lg bg-white dark:bg-control border border-default dark:border-hover text-[13px] leading-relaxed text-primary shadow-lg dark:shadow-2xl ${
        isRichContent ? "whitespace-pre-wrap" : "whitespace-pre-line"
      }`}
      style={{
        left: pos.left,
        top: pos.top,
        maxWidth: maxW,
      }}
    >
      {state.content}
    </div>,
    document.body
  );
}

export function useTooltip() {
  const [tip, setTip] = useState<TooltipState | null>(null);
  const show = useCallback((e: React.MouseEvent, content: TooltipContent) => {
    setTip({ x: e.clientX, y: e.clientY, content });
  }, []);
  const move = useCallback((e: React.MouseEvent) => {
    setTip((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : null));
  }, []);
  const hide = useCallback(() => setTip(null), []);
  return { tip, show, move, hide };
}

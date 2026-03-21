import { useState, useCallback } from "react";
import { TOOLTIP_OFFSET, TOOLTIP_MARGIN } from "./chart-constants";

export interface TooltipState {
  x: number;
  y: number;
  content: string;
}

export function Tooltip({ state }: { state: TooltipState | null }) {
  if (!state) return null;
  const maxX = window.innerWidth - TOOLTIP_MARGIN;
  const maxY = window.innerHeight - TOOLTIP_MARGIN;
  const x = Math.min(state.x + TOOLTIP_OFFSET, maxX - 260);
  const y = Math.min(state.y - 8, maxY - 80);

  return (
    <div
      className="fixed z-[9999] pointer-events-none px-3 py-2.5 rounded-lg bg-zinc-800/95 border border-zinc-600 text-[13px] leading-relaxed text-zinc-100 shadow-2xl whitespace-pre-line backdrop-blur-sm"
      style={{
        left: 0,
        top: 0,
        transform: `translate(${x}px, ${y}px)`,
        maxWidth: 300,
      }}
    >
      {state.content}
    </div>
  );
}

export function useTooltip() {
  const [tip, setTip] = useState<TooltipState | null>(null);
  const show = useCallback((e: React.MouseEvent, content: string) => {
    setTip({ x: e.clientX, y: e.clientY, content });
  }, []);
  const move = useCallback((e: React.MouseEvent) => {
    setTip((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : null));
  }, []);
  const hide = useCallback(() => setTip(null), []);
  return { tip, show, move, hide };
}

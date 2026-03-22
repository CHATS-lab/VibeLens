import { useState, useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { TOOLTIP_OFFSET } from "./chart-constants";

export interface TooltipState {
  x: number;
  y: number;
  content: string;
}

const MAX_WIDTH = 300;

export function Tooltip({ state }: { state: TooltipState | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number }>({
    left: 0,
    top: 0,
  });

  useEffect(() => {
    if (!state) return;
    const el = ref.current;
    const elW = el ? el.offsetWidth : MAX_WIDTH;
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
  }, [state]);

  if (!state) return null;

  return createPortal(
    <div
      ref={ref}
      className="fixed z-[9999] pointer-events-none px-3 py-2.5 rounded-lg bg-zinc-800/95 border border-zinc-600 text-[13px] leading-relaxed text-zinc-100 shadow-2xl whitespace-pre-line"
      style={{
        left: pos.left,
        top: pos.top,
        maxWidth: MAX_WIDTH,
      }}
    >
      {state.content}
    </div>,
    document.body
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

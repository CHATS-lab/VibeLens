import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface TooltipProps {
  text: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * Tooltip rendered via a React portal so it never clips against
 * parent overflow boundaries. Shows instantly on hover. Automatically
 * flips vertically when the tooltip would overflow the viewport top.
 */
export function Tooltip({ text, children, className }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number; flipped: boolean } | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!visible || !triggerRef.current) return;

    const rect = triggerRef.current.getBoundingClientRect();
    const tooltipHeight = tooltipRef.current?.offsetHeight ?? 32;
    const tooltipWidth = tooltipRef.current?.offsetWidth ?? 200;
    const GAP = 6;

    const fitsAbove = rect.top - tooltipHeight - GAP > 0;
    const top = fitsAbove
      ? rect.top - GAP + window.scrollY
      : rect.bottom + GAP + window.scrollY;

    // Clamp horizontal position so the tooltip stays within viewport
    const rawLeft = rect.left + rect.width / 2 + window.scrollX;
    const halfWidth = tooltipWidth / 2;
    const minLeft = halfWidth + 8;
    const maxLeft = window.innerWidth - halfWidth - 8;
    const left = Math.max(minLeft, Math.min(maxLeft, rawLeft));

    setCoords({ top, left, flipped: !fitsAbove });
  }, [visible]);

  return (
    <span
      ref={triggerRef}
      className={`inline-flex ${className ?? ""}`}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => { setVisible(false); setCoords(null); }}
    >
      {children}
      {visible && text &&
        createPortal(
          <span
            ref={tooltipRef}
            style={{
              position: "absolute",
              top: coords?.top ?? -9999,
              left: coords?.left ?? -9999,
              transform: coords?.flipped
                ? "translateX(-50%)"
                : "translateX(-50%) translateY(-100%)",
              visibility: coords ? "visible" : "hidden",
            }}
            className="z-[9999] px-3 py-2 text-xs leading-relaxed text-zinc-100 bg-zinc-800/95 border border-zinc-600 rounded-lg shadow-2xl max-w-[300px] text-center pointer-events-none break-words"
          >
            {text}
          </span>,
          document.body,
        )}
    </span>
  );
}

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface TooltipProps {
  text: React.ReactNode;
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
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!visible || !triggerRef.current) return;

    const rect = triggerRef.current.getBoundingClientRect();
    const tooltipWidth = tooltipRef.current?.offsetWidth ?? 200;
    const GAP = 6;

    const top = rect.bottom + GAP + window.scrollY;

    // Clamp horizontal position so the tooltip stays within viewport
    const rawLeft = rect.left + rect.width / 2 + window.scrollX;
    const halfWidth = tooltipWidth / 2;
    const minLeft = halfWidth + 8;
    const maxLeft = window.innerWidth - halfWidth - 8;
    const left = Math.max(minLeft, Math.min(maxLeft, rawLeft));

    setCoords({ top, left });
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
              transform: "translateX(-50%)",
              visibility: coords ? "visible" : "hidden",
            }}
            className="z-[9999] px-3 py-2 text-xs leading-relaxed text-primary bg-white dark:bg-control border border-default dark:border-hover rounded-lg shadow-lg dark:shadow-2xl max-w-[300px] w-max text-center pointer-events-none break-words"
          >
            {text}
          </span>,
          document.body,
        )}
    </span>
  );
}

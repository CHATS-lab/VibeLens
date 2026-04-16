import { useEffect, useRef, useState } from "react";

interface CollapsibleTextProps {
  /** Text content to render. */
  text: string;
  /** Optional leading label rendered before the text (e.g. "Description:"). */
  label?: string;
  /** Max lines shown when collapsed. Defaults to 3. */
  maxLines?: number;
  /** Extra classes for the text container. */
  className?: string;
  /** Tailwind text color class for the toggle button. Defaults to accent-teal. */
  toggleClassName?: string;
}

/**
 * Text block that clamps to `maxLines` and reveals a "Show more" toggle
 * only when the content actually overflows. Toggles show full text.
 */
export function CollapsibleText({
  text,
  label,
  maxLines = 3,
  className = "",
  toggleClassName = "text-accent-teal",
}: CollapsibleTextProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      setOverflowing(el.scrollHeight - 1 > el.clientHeight);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [text, maxLines]);

  const clampStyle = expanded
    ? undefined
    : ({
        display: "-webkit-box",
        WebkitLineClamp: maxLines,
        WebkitBoxOrient: "vertical" as const,
        overflow: "hidden",
      });

  return (
    <div className={className}>
      <span ref={ref} style={clampStyle} className="block">
        {label && <span className="font-semibold text-secondary">{label} </span>}
        {text}
      </span>
      {(overflowing || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className={`mt-1 text-xs font-medium hover:underline ${toggleClassName}`}
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

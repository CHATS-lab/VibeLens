import { useState } from "react";

interface TopicsRowProps {
  topics: string[];
  max?: number;
}

/** Flat row of topic pills with a "+N more" toggle when the list exceeds ``max``. */
export function TopicsRow({ topics, max = 5 }: TopicsRowProps) {
  const [expanded, setExpanded] = useState(false);
  if (topics.length === 0) return null;
  const visible = expanded ? topics : topics.slice(0, max);
  const overflow = topics.length - max;
  return (
    <div className="flex flex-wrap gap-1 items-center mt-2">
      {visible.map((topic) => (
        <span
          key={topic}
          className="text-[10px] px-2 py-0.5 rounded-full bg-control-hover/60 text-secondary border border-hover/30"
        >
          {topic}
        </span>
      ))}
      {overflow > 0 && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-[10px] text-muted hover:text-primary underline underline-offset-2 px-1"
        >
          {expanded ? "Show less" : `+${overflow} more`}
        </button>
      )}
    </div>
  );
}

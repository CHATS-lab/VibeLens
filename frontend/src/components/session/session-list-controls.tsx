import { Bot, ChevronDown, Check, Heart } from "lucide-react";
import { useRef, useState } from "react";
import { AgentIcon } from "../../agents";
import { useClickOutside } from "../../hooks/use-click-outside";
import { Tooltip } from "../ui/tooltip";

interface AgentFilterAgents {
  names: string[];
  counts: Record<string, number>;
  total: number;
}

export function AgentFilterDropdown({
  value,
  agents,
  onChange,
}: {
  value: string;
  agents: AgentFilterAgents;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, open, () => setOpen(false));

  const options = [
    { value: "all", label: "All agents", count: agents.total },
    ...agents.names.map((a) => ({ value: a, label: a, count: agents.counts[a] ?? 0 })),
  ];
  const active = options.find((o) => o.value === value);
  const activeLabel = active?.label ?? "All agents";
  const activeCount = active?.count;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 bg-control text-secondary text-sm rounded px-2.5 py-1.5 border border-card hover:border-hover transition cursor-pointer"
      >
        {value === "all" ? (
          <Bot className="w-4 h-4 text-dimmed shrink-0" />
        ) : (
          <AgentIcon agent={value} />
        )}
        <span className="flex-1 text-left truncate">{activeLabel}</span>
        {activeCount !== undefined && (
          <span className="text-[11px] tabular-nums text-dimmed shrink-0">{activeCount}</span>
        )}
        <ChevronDown className={`w-3.5 h-3.5 text-dimmed shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-control border border-card rounded-md shadow-xl overflow-hidden">
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full flex items-center gap-2 px-2.5 py-1.5 text-sm transition ${
                value === opt.value
                  ? "bg-accent-cyan-subtle text-cyan-700 dark:text-cyan-200"
                  : "text-secondary hover:bg-control-hover hover:text-primary"
              }`}
            >
              {value === opt.value ? (
                <Check className="w-3.5 h-3.5 text-accent-cyan shrink-0" />
              ) : (
                <span className="w-3.5 shrink-0" />
              )}
              {opt.value === "all" ? (
                <Bot className="w-4 h-4 text-dimmed shrink-0" />
              ) : (
                <AgentIcon agent={opt.value} />
              )}
              <span className="flex-1 truncate text-left">{opt.label}</span>
              <span className="text-[11px] tabular-nums text-dimmed shrink-0">{opt.count}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function DonateButton({ onClick, disabled, tooltip }: { onClick: () => void; disabled: boolean; tooltip?: string }) {
  const button = (
    <button
      onClick={disabled ? undefined : onClick}
      className={`w-full flex items-center justify-center gap-1.5 py-1.5 text-sm font-semibold rounded border transition ${
        disabled
          ? "bg-rose-600/40 text-rose-700 dark:text-rose-200 border-rose-500/30 cursor-not-allowed opacity-60"
          : "bg-rose-600 hover:bg-rose-500 text-white border-rose-500 shadow-sm shadow-rose-900/40"
      }`}
    >
      <Heart className="w-3.5 h-3.5" />
      Donate Data
    </button>
  );

  if (disabled && tooltip) {
    return <Tooltip text={tooltip} className="w-full">{button}</Tooltip>;
  }
  return button;
}

import { Filter, Search, X } from "lucide-react";
import { Tooltip } from "../tooltip";
import { normalizeSourceType, SOURCE_COLORS, SOURCE_LABELS } from "./skill-constants";

/** Search input with icon and clear button. */
export function SkillSearchBar({
  value,
  onChange,
  placeholder = "Search skills...",
  focusRingColor = "focus:ring-teal-500/30 focus:border-teal-600",
}: {
  value: string;
  onChange: (query: string) => void;
  placeholder?: string;
  focusRingColor?: string;
}) {
  return (
    <div className="relative mb-4">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dimmed" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full pl-9 pr-3 py-2 text-sm rounded-md bg-control border border-card text-primary placeholder:text-faint outline-none focus:ring-1 transition ${focusRingColor}`}
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-dimmed hover:text-secondary"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

/** Horizontal bar of filter chips with an "All" button and colored per-item buttons. */
export function SourceFilterBar({
  items,
  activeKey,
  onSelect,
  totalCount,
  countByKey,
  colorMap = SOURCE_COLORS,
  labelMap = SOURCE_LABELS,
}: {
  items: string[];
  activeKey: string | null;
  onSelect: (key: string | null) => void;
  totalCount: number;
  countByKey: (key: string) => number;
  colorMap?: Record<string, string>;
  labelMap?: Record<string, string>;
}) {
  if (items.length === 0) return null;

  return (
    <div className="flex items-center gap-2 mb-4">
      <Filter className="w-3.5 h-3.5 text-dimmed" />
      <button
        onClick={() => onSelect(null)}
        className={`px-2.5 py-1 text-[11px] font-medium rounded-md border transition ${
          activeKey === null
            ? "bg-control-hover text-secondary border-hover"
            : "text-secondary border-card hover:text-primary hover:border-hover"
        }`}
      >
        All ({totalCount})
      </button>
      {items.map((key) => {
        const normalized = normalizeSourceType(key);
        const count = countByKey(key);
        const colorClass = colorMap[normalized] || colorMap[key] || "bg-control text-muted border-card";
        return (
          <button
            key={key}
            onClick={() => onSelect(activeKey === key ? null : key)}
            className={`px-2.5 py-1 text-[11px] font-medium rounded-md border transition ${
              activeKey === key
                ? colorClass
                : "text-secondary border-card hover:text-primary hover:border-hover"
            }`}
          >
            {labelMap[normalized] || labelMap[key] || key} ({count})
          </button>
        );
      })}
    </div>
  );
}

/** Centered "no results" message for filtered/searched lists. */
export function NoResultsState() {
  return (
    <div className="text-center py-12">
      <Search className="w-8 h-8 text-faint mx-auto mb-2" />
      <p className="text-sm text-muted">No skills matching current filters</p>
    </div>
  );
}

/** Small counter showing "X of Y skills". */
export function SkillCount({ filtered, total }: { filtered: number; total: number }) {
  return (
    <div className="text-sm text-secondary mb-3">
      {filtered} of {total} skill{total !== 1 ? "s" : ""}
    </div>
  );
}

const CONFIDENCE_THRESHOLDS = { HIGH: 0.75, MEDIUM: 0.5 } as const;

/** Horizontal confidence bar with percentage label. accentColor controls the high-confidence color. */
export function ConfidenceBar({ confidence, accentColor = "emerald" }: { confidence: number; accentColor?: "emerald" | "amber" | "teal" }) {
  const pct = Math.round(confidence * 100);
  const isHigh = confidence >= CONFIDENCE_THRESHOLDS.HIGH;
  const isMedium = confidence >= CONFIDENCE_THRESHOLDS.MEDIUM;

  const HIGH_COLORS: Record<string, { bar: string; text: string }> = {
    emerald: { bar: "bg-emerald-500", text: "text-accent-emerald" },
    amber: { bar: "bg-amber-500", text: "text-accent-amber" },
    teal: { bar: "bg-teal-500", text: "text-accent-teal" },
  };
  const high = HIGH_COLORS[accentColor];
  const barColor = isHigh ? high.bar : isMedium ? "bg-amber-500" : "bg-control-hover";
  const textColor = isHigh ? high.text : isMedium ? "text-accent-amber" : "text-dimmed";

  return (
    <Tooltip text={`${pct}% confidence`}>
      <div className="flex items-center gap-2 cursor-help">
        <div className="w-16 h-1.5 rounded-full bg-control-hover/60 overflow-hidden">
          <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-xs font-semibold ${textColor} tabular-nums`}>{pct}%</span>
      </div>
    </Tooltip>
  );
}

/** Section header with icon, title, and hover tooltip. */
export function SectionHeader({
  icon,
  title,
  tooltip,
  accentColor = "text-accent-teal",
}: {
  icon: React.ReactNode;
  title: string;
  tooltip: string;
  accentColor?: string;
}) {
  return (
    <Tooltip text={tooltip}>
      <div className="flex items-center gap-2 mb-3 cursor-help">
        <span className={accentColor}>{icon}</span>
        <h3 className="text-xl font-semibold text-primary">{title}</h3>
      </div>
    </Tooltip>
  );
}

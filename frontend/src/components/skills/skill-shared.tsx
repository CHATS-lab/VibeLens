import { AlertCircle, Filter, Loader2, Search, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { SOURCE_COLORS, SOURCE_LABELS } from "./skill-constants";

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
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full pl-9 pr-3 py-2 text-sm rounded-md bg-zinc-800 border border-zinc-700 text-zinc-100 placeholder:text-zinc-600 outline-none focus:ring-1 transition ${focusRingColor}`}
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
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
      <Filter className="w-3.5 h-3.5 text-zinc-500" />
      <button
        onClick={() => onSelect(null)}
        className={`px-2.5 py-1 text-[11px] font-medium rounded-md border transition ${
          activeKey === null
            ? "bg-zinc-700 text-zinc-200 border-zinc-600"
            : "text-zinc-300 border-zinc-700/50 hover:text-zinc-100 hover:border-zinc-600"
        }`}
      >
        All ({totalCount})
      </button>
      {items.map((key) => {
        const count = countByKey(key);
        const colorClass = colorMap[key] || "bg-zinc-800 text-zinc-400 border-zinc-700/50";
        return (
          <button
            key={key}
            onClick={() => onSelect(activeKey === key ? null : key)}
            className={`px-2.5 py-1 text-[11px] font-medium rounded-md border transition ${
              activeKey === key
                ? colorClass
                : "text-zinc-300 border-zinc-700/50 hover:text-zinc-100 hover:border-zinc-600"
            }`}
          >
            {labelMap[key] || key} ({count})
          </button>
        );
      })}
    </div>
  );
}

/** Dismissible error banner with a red alert icon. */
export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-red-900/20 border border-red-800/30 mb-4">
      <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
      <p className="text-sm text-red-300">{message}</p>
      <button onClick={onDismiss} className="ml-auto shrink-0 text-red-400 hover:text-red-300">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

/** Centered spinner with a label, shown while data is loading. */
export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-16">
      <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
      <span className="ml-2 text-sm text-zinc-500">{label}</span>
    </div>
  );
}

/** Centered empty state with an icon and message. */
export function EmptyState({
  icon: Icon,
  title,
  subtitle,
  children,
}: {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="text-center py-16">
      <Icon className="w-10 h-10 text-zinc-600 mx-auto mb-3" />
      <p className="text-sm font-medium text-zinc-400 mb-1">{title}</p>
      {subtitle && <p className="text-xs text-zinc-600 mb-4">{subtitle}</p>}
      {children}
    </div>
  );
}

/** Centered "no results" message for filtered/searched lists. */
export function NoResultsState() {
  return (
    <div className="text-center py-12">
      <Search className="w-8 h-8 text-zinc-600 mx-auto mb-2" />
      <p className="text-sm text-zinc-400">No skills matching current filters</p>
    </div>
  );
}

/** Small counter showing "X of Y skills". */
export function SkillCount({ filtered, total }: { filtered: number; total: number }) {
  return (
    <div className="text-sm text-zinc-200 mb-3">
      {filtered} of {total} skill{total !== 1 ? "s" : ""}
    </div>
  );
}

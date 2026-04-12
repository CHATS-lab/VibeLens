// Text color tiers
export const TEXT_PRIMARY = "text-primary";
export const TEXT_SECONDARY = "text-secondary";
export const TEXT_MUTED = "text-muted";
export const TEXT_DIMMED = "text-dimmed";

// Segmented toggle
export const TOGGLE_CONTAINER = "flex gap-0.5 bg-control rounded p-0.5";
export const TOGGLE_BUTTON_BASE = "flex-1 flex items-center justify-center gap-1.5 text-xs py-1.5 rounded transition";
export const TOGGLE_ACTIVE = "bg-control-hover text-primary";
export const TOGGLE_INACTIVE = "text-dimmed hover:text-secondary";

// Stat card description
export const CARD_DESCRIPTION = "text-[11px] text-muted mt-0.5 leading-tight";

// Token metric label (session header)
export const METRIC_LABEL = "text-muted text-xs";

// Phase colors — shared between flow-diagram, prompt-nav-panel
export const PHASE_STYLE: Record<string, { border: string; label: string; dot: string; bg: string }> = {
  exploration: { border: "border-l-blue-400", label: "text-blue-600 dark:text-blue-400", dot: "bg-blue-400", bg: "" },
  implementation: { border: "border-l-emerald-400", label: "text-emerald-600 dark:text-emerald-400", dot: "bg-emerald-400", bg: "" },
  debugging: { border: "border-l-red-400", label: "text-red-600 dark:text-red-400", dot: "bg-red-400", bg: "" },
  verification: { border: "border-l-amber-400", label: "text-amber-600 dark:text-amber-400", dot: "bg-amber-400", bg: "" },
  planning: { border: "border-l-violet-400", label: "text-violet-600 dark:text-violet-400", dot: "bg-violet-400", bg: "" },
  mixed: { border: "border-l-indigo-400", label: "text-indigo-600 dark:text-indigo-400", dot: "bg-indigo-400", bg: "" },
};

// Tool category colors — shared between flow-diagram, flow-layout
export const CATEGORY_STYLE: Record<string, { bg: string; ring: string; text: string; label: string }> = {
  file_read: { bg: "bg-blue-500/20", ring: "ring-blue-400/60", text: "text-blue-600 dark:text-blue-300", label: "read" },
  file_write: { bg: "bg-emerald-500/20", ring: "ring-emerald-400/60", text: "text-emerald-600 dark:text-emerald-300", label: "write" },
  shell: { bg: "bg-amber-500/20", ring: "ring-amber-400/60", text: "text-amber-600 dark:text-amber-300", label: "shell" },
  search: { bg: "bg-sky-500/20", ring: "ring-sky-400/60", text: "text-sky-600 dark:text-sky-300", label: "search" },
  web: { bg: "bg-orange-500/20", ring: "ring-orange-400/60", text: "text-orange-600 dark:text-orange-300", label: "web" },
  agent: { bg: "bg-violet-500/20", ring: "ring-violet-400/60", text: "text-violet-600 dark:text-violet-300", label: "agent" },
  task: { bg: "bg-rose-500/20", ring: "ring-rose-400/60", text: "text-rose-600 dark:text-rose-300", label: "task" },
  interact: { bg: "bg-cyan-500/20", ring: "ring-cyan-400/60", text: "text-cyan-600 dark:text-cyan-300", label: "interact" },
  other: { bg: "bg-zinc-500/20", ring: "ring-zinc-400/60", text: "text-zinc-500 dark:text-zinc-400", label: "other" },
};

// Category short labels — shared between prompt-nav-panel, flow-diagram
export const CATEGORY_LABELS: Record<string, string> = {
  file_read: "read",
  file_write: "write",
  shell: "shell",
  search: "search",
  web: "web",
  agent: "agent",
  task: "task",
  interact: "interact",
  other: "other",
};

// Severity colors for friction analysis
export const SEVERITY_COLORS: Record<number, string> = {
  1: "bg-control-hover/50 text-secondary border-hover/60",
  2: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/40 dark:text-sky-300 dark:border-sky-700/30",
  3: "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/40 dark:text-yellow-300 dark:border-yellow-700/30",
  4: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/50 dark:text-orange-200 dark:border-orange-600/40",
  5: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/50 dark:text-rose-200 dark:border-rose-600/40",
};

// Right sidebar panel dimensions (shared across prompt nav, friction, skills)
export const SIDEBAR_DEFAULT_WIDTH = 252;
export const SIDEBAR_MIN_WIDTH = 180;
export const SIDEBAR_MAX_WIDTH = 400;

// SVG chart dimensions
export const CHART = {
  WIDTH: 800,
  HEIGHT: 200,
  MARGIN_LEFT: 55,
  MARGIN_RIGHT: 15,
  MARGIN_TOP: 12,
  MARGIN_BOTTOM: 28,
};

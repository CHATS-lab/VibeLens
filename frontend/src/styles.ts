// Text color tiers
export const TEXT_PRIMARY = "text-zinc-100";
export const TEXT_SECONDARY = "text-zinc-200";
export const TEXT_MUTED = "text-zinc-400";
export const TEXT_DIMMED = "text-zinc-500";

// Segmented toggle
export const TOGGLE_CONTAINER = "flex gap-0.5 bg-zinc-800 rounded p-0.5";
export const TOGGLE_BUTTON_BASE = "flex-1 flex items-center justify-center gap-1.5 text-xs py-1.5 rounded transition";
export const TOGGLE_ACTIVE = "bg-zinc-700 text-zinc-100";
export const TOGGLE_INACTIVE = "text-zinc-500 hover:text-zinc-300";

// Stat card description
export const CARD_DESCRIPTION = "text-[11px] text-zinc-400 mt-0.5 leading-tight";

// Token metric label (session header)
export const METRIC_LABEL = "text-zinc-400 text-xs";

// Phase colors — shared between flow-diagram, prompt-nav-panel
export const PHASE_STYLE: Record<string, { border: string; label: string; dot: string; bg: string }> = {
  exploration: { border: "border-l-blue-400", label: "text-blue-400", dot: "bg-blue-400", bg: "bg-blue-500/[0.03]" },
  implementation: { border: "border-l-emerald-400", label: "text-emerald-400", dot: "bg-emerald-400", bg: "bg-emerald-500/[0.03]" },
  debugging: { border: "border-l-red-400", label: "text-red-400", dot: "bg-red-400", bg: "bg-red-500/[0.03]" },
  verification: { border: "border-l-amber-400", label: "text-amber-400", dot: "bg-amber-400", bg: "bg-amber-500/[0.03]" },
  planning: { border: "border-l-violet-400", label: "text-violet-400", dot: "bg-violet-400", bg: "bg-violet-500/[0.03]" },
  mixed: { border: "border-l-zinc-500", label: "text-zinc-400", dot: "bg-zinc-500", bg: "bg-zinc-500/[0.02]" },
};

// Tool category colors — shared between flow-diagram, flow-layout
export const CATEGORY_STYLE: Record<string, { bg: string; ring: string; text: string; label: string }> = {
  file_read: { bg: "bg-blue-500/20", ring: "ring-blue-400/60", text: "text-blue-300", label: "read" },
  file_write: { bg: "bg-emerald-500/20", ring: "ring-emerald-400/60", text: "text-emerald-300", label: "write" },
  shell: { bg: "bg-amber-500/20", ring: "ring-amber-400/60", text: "text-amber-300", label: "shell" },
  search: { bg: "bg-sky-500/20", ring: "ring-sky-400/60", text: "text-sky-300", label: "search" },
  web: { bg: "bg-orange-500/20", ring: "ring-orange-400/60", text: "text-orange-300", label: "web" },
  agent: { bg: "bg-violet-500/20", ring: "ring-violet-400/60", text: "text-violet-300", label: "agent" },
  task: { bg: "bg-rose-500/20", ring: "ring-rose-400/60", text: "text-rose-300", label: "task" },
  other: { bg: "bg-zinc-500/20", ring: "ring-zinc-400/60", text: "text-zinc-400", label: "other" },
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
  other: "other",
};

// Severity colors for friction analysis
export const SEVERITY_COLORS: Record<number, string> = {
  1: "bg-zinc-700/50 text-zinc-300 border-zinc-600/40",
  2: "bg-sky-900/40 text-sky-300 border-sky-700/30",
  3: "bg-yellow-900/40 text-yellow-300 border-yellow-700/30",
  4: "bg-orange-900/50 text-orange-200 border-orange-600/40",
  5: "bg-rose-900/50 text-rose-200 border-rose-600/40",
};

// Display truncation lengths
export const SESSION_ID_SHORT = 8;
export const SESSION_ID_MEDIUM = 12;
export const PREVIEW_SHORT = 40;
export const PREVIEW_MEDIUM = 60;
export const PREVIEW_LONG = 150;
export const LABEL_MAX_LENGTH = 120;

// Timing constants
export const SHARE_STATUS_RESET_MS = 2000;
export const SCROLL_SUPPRESS_MS = 800;
export const SEARCH_DEBOUNCE_MS = 300;
export const SESSIONS_PER_PAGE = 100;

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

/** Badge colors for extension item types. */
export const ITEM_TYPE_COLORS: Record<string, string> = {
  skill: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-900/30 dark:text-teal-400 dark:border-teal-700/30",
  subagent: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-900/30 dark:text-violet-400 dark:border-violet-700/30",
  command: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/30 dark:text-sky-400 dark:border-sky-700/30",
  hook: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-700/30",
  repo: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-700/30",
};

/** Human-readable labels for item types. */
export const ITEM_TYPE_LABELS: Record<string, string> = {
  skill: "Skill",
  subagent: "Agent",
  command: "Command",
  hook: "Hook",
  repo: "MCP",
};

/** Icon container colors for item types. */
export const ITEM_TYPE_ICON_COLORS: Record<string, { bg: string; text: string }> = {
  skill: { bg: "bg-teal-50 dark:bg-teal-900/30", text: "text-teal-600 dark:text-teal-400" },
  subagent: { bg: "bg-violet-50 dark:bg-violet-900/30", text: "text-violet-600 dark:text-violet-400" },
  command: { bg: "bg-sky-50 dark:bg-sky-900/30", text: "text-sky-600 dark:text-sky-400" },
  hook: { bg: "bg-amber-50 dark:bg-amber-900/30", text: "text-amber-600 dark:text-amber-400" },
  repo: { bg: "bg-emerald-50 dark:bg-emerald-900/30", text: "text-emerald-600 dark:text-emerald-400" },
};

/** Platform display labels. */
export const PLATFORM_LABELS: Record<string, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
  gemini: "Gemini",
};

/** Items per page for extension browsing. */
export const EXTENSION_PAGE_SIZE = 50;

/** Sort options for extension browsing. */
export const SORT_OPTIONS: { value: string; label: string; needsProfile?: boolean }[] = [
  { value: "quality", label: "Quality" },
  { value: "name", label: "Name" },
  { value: "popularity", label: "Popularity" },
  { value: "recent", label: "Recent" },
  { value: "relevance", label: "For You", needsProfile: true },
];

/** View mode for extension list. */
export type ExtensionViewMode = "list" | "card";

/** Maximum tags shown in list view cards. */
export const LIST_VIEW_MAX_TAGS = 3;

/** Maximum tags shown in card grid view. */
export const CARD_VIEW_MAX_TAGS = 5;

/** Maximum page buttons shown in pagination. */
export const MAX_VISIBLE_PAGES = 7;

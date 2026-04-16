/**
 * Normalize a source_type value from the backend to a canonical key.
 *
 * Handles formats like "AgentType.CODEX", "SkillSource.CLAUDE", or plain "codex".
 * Maps legacy "claude_code" to "claude" for consistency with backend enum values.
 */
export function normalizeSourceType(raw: string): string {
  const dotMatch = raw.match(/\.(\w+)$/);
  const key = dotMatch ? dotMatch[1].toLowerCase() : raw;
  if (key === "claude_code") return "claude";
  if (key === "qwen_code") return "qwen";
  return key;
}

/** Color classes for skill source badges (agent interfaces). */
export const SOURCE_COLORS: Record<string, string> = {
  claude: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/30 dark:text-sky-400 dark:border-sky-700/30",
  codex: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-700/30",
  central: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-900/30 dark:text-teal-400 dark:border-teal-700/30",
  gemini: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-700/30",
  copilot: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-900/30 dark:text-violet-400 dark:border-violet-700/30",
  openclaw: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-700/30",
  cursor: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-700/30",
  opencode: "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-900/30 dark:text-cyan-400 dark:border-cyan-700/30",
  antigravity: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/30 dark:text-purple-400 dark:border-purple-700/30",
  kimi: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-700/30",
  openhands: "bg-lime-50 text-lime-700 border-lime-200 dark:bg-lime-900/30 dark:text-lime-400 dark:border-lime-700/30",
  qwen: "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-400 dark:border-indigo-700/30",
  aider: "bg-pink-50 text-pink-700 border-pink-200 dark:bg-pink-900/30 dark:text-pink-400 dark:border-pink-700/30",
};

/** Human-readable labels for agent interface source types. */
export const SOURCE_LABELS: Record<string, string> = {
  claude: "Claude",
  codex: "Codex",
  central: "Central",
  gemini: "Gemini",
  copilot: "Copilot",
  openclaw: "OpenClaw",
  cursor: "Cursor",
  opencode: "OpenCode",
  antigravity: "Antigravity",
  kimi: "Kimi",
  openhands: "OpenHands",
  qwen: "Qwen",
  aider: "Aider",
};

/** Tooltip descriptions for agent interface source types. */
export const SOURCE_DESCRIPTIONS: Record<string, string> = {
  claude: "Installed in ~/.claude/skills/",
  codex: "Installed in ~/.codex/skills/",
  central: "Central store in ~/.vibelens/skills/",
  gemini: "Installed for Gemini CLI",
  copilot: "Installed in ~/.copilot/skills/",
  openclaw: "Installed in ~/.openclaw/skills/",
  cursor: "Installed in ~/.cursor/skills/",
  opencode: "Installed in ~/.config/opencode/skills/",
  antigravity: "Installed for Antigravity",
  kimi: "Installed for Kimi",
  openhands: "Installed for OpenHands",
  qwen: "Installed for Qwen",
  aider: "Installed for Aider",
};

/** Tooltip descriptions for common skill tags. */
export const TAG_DESCRIPTIONS: Record<string, string> = {
  "agent-skills": "Official Anthropic registry skill",
  development: "Software development tools and workflows",
  "ai-assistant": "AI assistant capabilities",
  automation: "Task and workflow automation",
  testing: "Test writing and debugging",
  documentation: "Doc generation and maintenance",
  refactoring: "Code restructuring patterns",
  debugging: "Debugging and error resolution",
  deployment: "Build, deploy, and CI/CD",
  security: "Security scanning and auditing",
  database: "Database and schema management",
  frontend: "Frontend, UI, and styling",
  backend: "Backend services and APIs",
  devops: "Infrastructure and operations",
};

/** Display labels for skill subdirectories. */
export const SUBDIR_LABELS: Record<string, string> = {
  scripts: "scripts/",
  references: "references/",
  agents: "agents/",
  assets: "assets/",
};

/** Tooltip descriptions for skill subdirectories. */
export const SUBDIR_DESCRIPTIONS: Record<string, string> = {
  scripts: "Bundled executable scripts",
  references: "Reference docs and examples",
  agents: "Sub-agent definitions",
  assets: "Templates and config files",
};

/** All supported agent sync targets (key + label). */
export const ALL_SYNC_TARGETS: { key: string; label: string }[] = [
  { key: "claude", label: "Claude" },
  { key: "codex", label: "Codex" },
  { key: "copilot", label: "Copilot" },
  { key: "openclaw", label: "OpenClaw" },
];

/** Color classes for featured skill categories. */
export const CATEGORY_COLORS: Record<string, string> = {
  "ai-assistant": "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-400 dark:border-indigo-700/30",
  development: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-900/30 dark:text-teal-400 dark:border-teal-700/30",
};

/** Human-readable labels for featured skill categories. */
export const CATEGORY_LABELS: Record<string, string> = {
  "ai-assistant": "AI Assistant",
  development: "Development",
};


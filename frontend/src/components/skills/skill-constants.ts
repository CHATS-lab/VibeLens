/** Color classes for skill source badges (agent interfaces). */
export const SOURCE_COLORS: Record<string, string> = {
  claude_code: "bg-sky-900/30 text-sky-400 border-sky-700/30",
  codex: "bg-emerald-900/30 text-emerald-400 border-emerald-700/30",
  central: "bg-teal-900/30 text-teal-400 border-teal-700/30",
  gemini: "bg-amber-900/30 text-amber-400 border-amber-700/30",
  gemini_cli: "bg-amber-900/30 text-amber-400 border-amber-700/30",
  copilot: "bg-violet-900/30 text-violet-400 border-violet-700/30",
  openclaw: "bg-rose-900/30 text-rose-400 border-rose-700/30",
  cursor: "bg-blue-900/30 text-blue-400 border-blue-700/30",
  opencode: "bg-cyan-900/30 text-cyan-400 border-cyan-700/30",
  antigravity: "bg-purple-900/30 text-purple-400 border-purple-700/30",
  kimi_cli: "bg-orange-900/30 text-orange-400 border-orange-700/30",
  openhands: "bg-lime-900/30 text-lime-400 border-lime-700/30",
  qwen_code: "bg-indigo-900/30 text-indigo-400 border-indigo-700/30",
};

/** Human-readable labels for agent interface source types. */
export const SOURCE_LABELS: Record<string, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
  central: "Central",
  gemini: "Gemini",
  gemini_cli: "gemini_cli",
  copilot: "Copilot",
  openclaw: "OpenClaw",
};

/** Tooltip descriptions for agent interface source types. */
export const SOURCE_DESCRIPTIONS: Record<string, string> = {
  claude_code: "Installed in ~/.claude/skills/",
  codex: "Installed in ~/.codex/skills/",
  central: "Central store in ~/.vibelens/skills/",
  gemini: "Installed for Gemini CLI",
  gemini_cli: "Installed in ~/.gemini/skills/",
  copilot: "Installed in ~/.copilot/skills/",
  openclaw: "Installed in ~/.openclaw/skills/",
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
  { key: "claude_code", label: "Claude Code" },
  { key: "codex", label: "Codex" },
  { key: "gemini_cli", label: "gemini_cli" },
  { key: "copilot", label: "Copilot" },
  { key: "openclaw", label: "OpenClaw" },
];

/** Color classes for featured skill categories. */
export const CATEGORY_COLORS: Record<string, string> = {
  "ai-assistant": "bg-indigo-900/30 text-indigo-400 border-indigo-700/30",
  development: "bg-teal-900/30 text-teal-400 border-teal-700/30",
};

/** Human-readable labels for featured skill categories. */
export const CATEGORY_LABELS: Record<string, string> = {
  "ai-assistant": "AI Assistant",
  development: "Development",
};


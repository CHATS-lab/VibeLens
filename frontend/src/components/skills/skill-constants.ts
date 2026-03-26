/** Color classes for skill source badges (agent interfaces). */
export const SOURCE_COLORS: Record<string, string> = {
  claude_code: "bg-sky-900/30 text-sky-400 border-sky-700/30",
  codex: "bg-emerald-900/30 text-emerald-400 border-emerald-700/30",
  central: "bg-teal-900/30 text-teal-400 border-teal-700/30",
  gemini: "bg-amber-900/30 text-amber-400 border-amber-700/30",
};

/** Human-readable labels for agent interface source types. */
export const SOURCE_LABELS: Record<string, string> = {
  claude_code: "Claude Code",
  codex: "Codex",
  central: "Central",
  gemini: "Gemini",
};

/** Tooltip descriptions for agent interface source types. */
export const SOURCE_DESCRIPTIONS: Record<string, string> = {
  claude_code: "Skill is installed in ~/.claude/skills/ for Claude Code CLI",
  codex: "Skill is installed in ~/.codex/skills/ for OpenAI Codex CLI",
  central: "Managed copy in ~/.vibelens/skills/ central repository",
  gemini: "Skill is installed for Google Gemini CLI",
};

/** Tooltip descriptions for common skill tags. */
export const TAG_DESCRIPTIONS: Record<string, string> = {
  "agent-skills": "Official Anthropic skill from the skills hub registry",
  development: "Tools and workflows for software development",
  "ai-assistant": "AI-powered assistant capabilities and automation",
  automation: "Automates repetitive tasks and workflows",
  testing: "Test writing, running, and debugging utilities",
  documentation: "Documentation generation and maintenance",
  refactoring: "Code refactoring and restructuring patterns",
  debugging: "Systematic debugging and error resolution",
  deployment: "Build, deploy, and CI/CD pipeline management",
  security: "Security scanning, auditing, and best practices",
  database: "Database queries, migrations, and schema management",
  frontend: "Frontend development, UI components, and styling",
  backend: "Backend services, APIs, and server-side logic",
  devops: "Infrastructure, monitoring, and operations",
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
  scripts: "Executable scripts bundled with the skill",
  references: "Reference documents and examples",
  agents: "Sub-agent definitions for complex workflows",
  assets: "Static assets like templates and configs",
};

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

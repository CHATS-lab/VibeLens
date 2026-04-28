/**
 * Personalization-only display constants. Agent metadata (labels, colors,
 * icons, normalize helper) lives in ``frontend/src/agents`` and is
 * re-exported here for backwards-compatible imports — every existing
 * ``import { SOURCE_LABELS } from "../constants"`` keeps working.
 */

export {
  normalizeSourceType,
  SOURCE_COLORS,
  SOURCE_DESCRIPTIONS,
  SOURCE_LABELS,
} from "../../agents";

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

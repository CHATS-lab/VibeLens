/**
 * Single-source-of-truth metadata for every agent platform plus the legacy
 * grouping concept "central" (VibeLens's own store). One row per slug; the
 * historical ``SOURCE_LABELS`` / ``SOURCE_COLORS`` / ``SOURCE_DESCRIPTIONS``
 * records are derived views below for backwards-compatible imports.
 *
 * Add a new agent: append a row here and (optionally) drop a PNG into
 * ``src/assets/agents/<slug>.png``. ``AGENT_ICONS`` picks it up via the
 * Vite import.meta.glob below.
 *
 * This module is the *frontend* SoT for cosmetic agent data (label / color /
 * icon). Backend data — directories, supported_types, upload commands — lives
 * in ``services/extensions/platforms.py`` and ``services/upload/agents.py``
 * and reaches the frontend through API responses.
 */
import { normalizeSourceType } from "./normalize";

interface AgentMeta {
  /** Human-readable label shown in pills, badges, and dialogs. */
  label: string;
  /** Tailwind class string for an active badge background. */
  color: string;
  /** Tooltip line shown next to "Installed in ..." UI. */
  description: string;
}

const AGENTS: Record<string, AgentMeta> = {
  aider: {
    label: "Aider",
    color: "bg-pink-50 text-pink-700 border-pink-200 dark:bg-pink-900/30 dark:text-pink-400 dark:border-pink-700/30",
    description: "Installed for Aider",
  },
  amp: {
    label: "Amp",
    color: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-700/30",
    description: "Installed in ~/.config/amp/skills/",
  },
  antigravity: {
    label: "Antigravity",
    color: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/30 dark:text-purple-400 dark:border-purple-700/30",
    description: "Installed for Antigravity",
  },
  augment: {
    label: "Augment",
    color: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-700/30",
    description: "Installed in ~/.augment/skills/",
  },
  autoclaw: {
    label: "AutoClaw",
    color: "bg-stone-50 text-stone-700 border-stone-200 dark:bg-stone-900/30 dark:text-stone-400 dark:border-stone-700/30",
    description: "Installed in ~/.openclaw-autoclaw/skills/",
  },
  // VibeLens's own store; not a real agent.
  central: {
    label: "Central",
    color: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-900/30 dark:text-teal-400 dark:border-teal-700/30",
    description: "Central store in ~/.vibelens/skills/",
  },
  claude: {
    label: "Claude",
    color: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/30 dark:text-sky-400 dark:border-sky-700/30",
    description: "Installed in ~/.claude/skills/",
  },
  codebuddy: {
    label: "CodeBuddy",
    color: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-700/30",
    description: "Installed in ~/.codebuddy/skills/",
  },
  codex: {
    label: "Codex",
    color: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-400 dark:border-emerald-700/30",
    description: "Installed in ~/.agents/skills/",
  },
  copilot: {
    label: "Copilot",
    color: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-900/30 dark:text-violet-400 dark:border-violet-700/30",
    description: "Installed in ~/.copilot/skills/",
  },
  cursor: {
    label: "Cursor",
    color: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-700/30",
    description: "Installed in ~/.cursor/skills/",
  },
  easyclaw: {
    label: "EasyClaw",
    color: "bg-zinc-50 text-zinc-700 border-zinc-200 dark:bg-zinc-900/30 dark:text-zinc-400 dark:border-zinc-700/30",
    description: "Installed in ~/.easyclaw/skills/",
  },
  factory: {
    label: "Factory Droid",
    color: "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-700/30",
    description: "Installed in ~/.factory/skills/",
  },
  gemini: {
    label: "Gemini",
    color: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-700/30",
    description: "Installed for Gemini CLI",
  },
  hermes: {
    label: "Hermes",
    color: "bg-pink-50 text-pink-700 border-pink-200 dark:bg-pink-900/30 dark:text-pink-400 dark:border-pink-700/30",
    description: "Installed in ~/.hermes/skills/",
  },
  junie: {
    label: "Junie",
    color: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200 dark:bg-fuchsia-900/30 dark:text-fuchsia-400 dark:border-fuchsia-700/30",
    description: "Installed in ~/.junie/skills/",
  },
  kilo: {
    label: "Kilo",
    color: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-900/30 dark:text-teal-400 dark:border-teal-700/30",
    description: "Installed in ~/.kilocode/skills/",
  },
  kimi: {
    label: "Kimi",
    color: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-700/30",
    description: "Installed for Kimi",
  },
  kiro: {
    label: "Kiro",
    color: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-900/30 dark:text-sky-400 dark:border-sky-700/30",
    description: "Installed in ~/.kiro/skills/",
  },
  ob1: {
    label: "OB-1",
    color: "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-900/30 dark:text-slate-400 dark:border-slate-700/30",
    description: "Installed in ~/.ob1/skills/",
  },
  openclaw: {
    label: "OpenClaw",
    color: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-400 dark:border-rose-700/30",
    description: "Installed in ~/.openclaw/skills/",
  },
  opencode: {
    label: "OpenCode",
    color: "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-900/30 dark:text-cyan-400 dark:border-cyan-700/30",
    description: "Installed in ~/.config/opencode/skills/",
  },
  openhands: {
    label: "OpenHands",
    color: "bg-lime-50 text-lime-700 border-lime-200 dark:bg-lime-900/30 dark:text-lime-400 dark:border-lime-700/30",
    description: "Installed for OpenHands",
  },
  qclaw: {
    label: "QClaw",
    color: "bg-neutral-50 text-neutral-700 border-neutral-200 dark:bg-neutral-900/30 dark:text-neutral-400 dark:border-neutral-700/30",
    description: "Installed in ~/.qclaw/skills/",
  },
  qoder: {
    label: "Qoder",
    color: "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-700/30",
    description: "Installed in ~/.qoder/skills/",
  },
  qwen: {
    label: "Qwen",
    color: "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-400 dark:border-indigo-700/30",
    description: "Installed for Qwen",
  },
  trae: {
    label: "Trae",
    color: "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-700/30",
    description: "Installed in ~/.trae/skills/",
  },
  "trae-cn": {
    label: "Trae CN",
    color: "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-700/30",
    description: "Installed in ~/.trae-cn/skills/",
  },
  workbuddy: {
    label: "WorkBuddy",
    color: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-700/30",
    description: "Installed in ~/.workbuddy/skills/",
  },
};

// Vite eagerly inlines every PNG under assets/agents/ as a hashed URL.
// Module-private — consumers go through getAgentMeta(...).iconUrl.
const AGENT_ICON_URLS: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<{ default: string }>("../assets/agents/*.png", { eager: true }),
  ).map(([path, mod]) => [path.match(/\/([^/]+)\.png$/)?.[1] ?? "", mod.default]),
);

/** Single accessor: normalizes the slug and returns label / color / description /
 *  iconUrl with safe fallbacks for unknown agents. */
export function getAgentMeta(rawSlug: string): AgentMeta & { slug: string; iconUrl: string | null } {
  const slug = normalizeSourceType(rawSlug);
  const meta = AGENTS[slug];
  return {
    slug,
    label: meta?.label ?? rawSlug,
    color: meta?.color ?? "bg-control text-muted border-card",
    description: meta?.description ?? "",
    iconUrl: AGENT_ICON_URLS[slug] ?? null,
  };
}

// Derived field-only maps for callers that need a plain Record<slug, T>
// (e.g. the SourceFilterBar's color/label override props).
export const SOURCE_COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(AGENTS).map(([slug, m]) => [slug, m.color]),
);

export const SOURCE_LABELS: Record<string, string> = Object.fromEntries(
  Object.entries(AGENTS).map(([slug, m]) => [slug, m.label]),
);

export const SOURCE_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  Object.entries(AGENTS).map(([slug, m]) => [slug, m.description]),
);

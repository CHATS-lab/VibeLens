import type { ExtensionSyncTarget } from "../../../types";

/**
 * Maps a backend extension_type to its per-type REST endpoint base path.
 * Used by catalog-facing UI (InstallTargetDialog, extension-card) to dispatch
 * detail/uninstall requests to the correct typed handler instead of the
 * skills-only routes.
 */
const ENDPOINT_BY_TYPE: Record<string, string> = {
  skill: "/api/skills",
  subagent: "/api/subagents",
  command: "/api/commands",
  hook: "/api/hooks",
};

/** Returns the base API endpoint for an extension type, or null if unknown. */
export function extensionEndpoint(type: string): string | null {
  return ENDPOINT_BY_TYPE[type] ?? null;
}

/**
 * Extract `installed_in` from a detail response.
 *
 * Each /api/{type}/{name} endpoint nests the item under its type key
 * (e.g. `{skill: {...}}`, `{subagent: {...}}`). This helper handles both
 * nested and flat shapes.
 */
export function extractInstalledIn(type: string, data: unknown): string[] {
  const blob = data as
    & { [k: string]: { installed_in?: string[] } | undefined }
    & { installed_in?: string[] };
  return blob[type]?.installed_in ?? blob.installed_in ?? [];
}

/**
 * Normalize a per-type list response into ExtensionSyncTarget[].
 *
 * The skill/subagent/command list endpoints return `sync_targets: [{agent,
 * {type}_count, {type}s_dir}]`. Hooks return `{agent, hook_count,
 * settings_path}`. This helper converts both to `{agent, count, dir}`.
 */
export function normalizeSyncTargets(type: string, raw: unknown): ExtensionSyncTarget[] {
  const list = (raw as { sync_targets?: Array<Record<string, unknown>> })?.sync_targets ?? [];
  const countKey = `${type}_count`;
  const dirKey = `${type}s_dir`;
  return list.map((target) => ({
    agent: String(target.agent ?? ""),
    count: Number(target[countKey] ?? 0),
    dir: String(target[dirKey] ?? target.settings_path ?? ""),
  }));
}

/**
 * Central-store label used under the "always saved" row in InstallTargetDialog.
 * Hooks live at `~/.vibelens/hooks/` (no trailing 's'), others are pluralized.
 */
export function centralStoreLabel(type: string): string {
  if (type === "hook") return "~/.vibelens/hooks/";
  return `~/.vibelens/${type}s/`;
}

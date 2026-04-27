/**
 * Normalize a source_type value from the backend to a canonical key.
 *
 * Handles formats like "AgentType.CODEX", "SkillSource.CLAUDE", or plain "codex".
 * Maps legacy "claude_code" to "claude" for consistency with backend enum values.
 *
 * Lives in its own module so ``constants.ts`` can import it during its
 * own initialization without a circular import.
 */
export function normalizeSourceType(raw: string): string {
  const dotMatch = raw.match(/\.(\w+)$/);
  const key = dotMatch ? dotMatch[1].toLowerCase() : raw;
  if (key === "claude_code") return "claude";
  if (key === "qwen_code") return "qwen";
  return key;
}

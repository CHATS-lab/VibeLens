const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;

export function formatTime(timestamp: string | null): string {
  if (!timestamp) return "";
  const diff = Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000);
  if (diff < MINUTE) return "now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`;
  return `${Math.floor(diff / DAY)}d`;
}

const SYSTEM_TAG_RE = /<(?:system-reminder|command-name|user-prompt-submit-hook)[^>]*>[\s\S]*?<\/(?:system-reminder|command-name|user-prompt-submit-hook)>/g;

export function sanitizeText(text: string): string {
  return text.replace(SYSTEM_TAG_RE, "").trim();
}

export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "...";
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "0s";
  const hours = Math.floor(seconds / HOUR);
  const minutes = Math.floor((seconds % HOUR) / MINUTE);
  const secs = Math.floor(seconds % MINUTE);
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  if (secs > 0 || parts.length === 0) parts.push(`${secs}s`);
  return parts.join(" ");
}

export function extractUserText(message: {
  content: string | Array<{ type: string; text?: string }>;
}): string {
  if (typeof message.content === "string") {
    return sanitizeText(message.content);
  }
  return message.content
    .filter((b) => b.type === "text" && b.text)
    .map((b) => sanitizeText(b.text || ""))
    .join("\n")
    .trim();
}

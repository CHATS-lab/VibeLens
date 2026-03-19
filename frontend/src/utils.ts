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

export function extractUserText(step: { message: string }): string {
  return sanitizeText(step.message);
}

export function baseProjectName(path: string): string {
  if (!path) return "Unknown";
  const segments = path.replace(/\/+$/, "").split("/");
  return segments[segments.length - 1] || path;
}

export function formatElapsed(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / HOUR);
  const minutes = Math.floor((totalSeconds % HOUR) / MINUTE);
  const seconds = Math.floor(totalSeconds % MINUTE);
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

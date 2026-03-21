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

const SYSTEM_TAG_RE = /<(?:system-reminder|command-name|command-message|user-prompt-submit-hook|local-command-caveat|local-command-stdout|task-notification)[^>]*>[\s\S]*?<\/(?:system-reminder|command-name|command-message|user-prompt-submit-hook|local-command-caveat|local-command-stdout|task-notification)>/g;

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
  if (!seconds || seconds <= 0) return "0m";
  const hours = Math.floor(seconds / HOUR);
  const minutes = Math.floor((seconds % HOUR) / MINUTE);
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0 || parts.length === 0) parts.push(`${minutes}m`);
  return parts.join(" ");
}

export function extractUserText(step: { message: string }): string {
  return sanitizeText(step.message);
}

export function baseProjectName(path: string): string {
  if (!path) return "Unknown";
  const normalized = path.replace(/[\\/]+$/, "");
  const segments = normalized.split(/[\\/]/).filter(Boolean);
  const LAST_N_SEGMENTS = 2;
  if (segments.length === 0) return path;
  const tail = segments.slice(-LAST_N_SEGMENTS);
  return tail.join("/");
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

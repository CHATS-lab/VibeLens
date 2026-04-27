/**
 * Agent platform icon. Renders the per-slug PNG when available; otherwise a
 * colored letter-tile of the first label character. The slug is normalized
 * inside ``getAgentMeta`` so callers can pass raw backend values like
 * ``"AgentType.CODEX"`` directly.
 */
import { getAgentMeta } from "./meta";

interface AgentIconProps {
  /** Raw or normalized agent slug. */
  agent: string;
  /** Pixel size; default 16 (matches lucide w-4 h-4). */
  size?: number;
  className?: string;
}

export function AgentIcon({ agent, size = 16, className = "" }: AgentIconProps) {
  const { label, color, iconUrl } = getAgentMeta(agent);
  if (iconUrl) {
    return (
      <img
        src={iconUrl}
        alt={label}
        width={size}
        height={size}
        className={`shrink-0 rounded ${className}`}
        loading="lazy"
      />
    );
  }
  return (
    <span
      style={{ width: size, height: size, fontSize: Math.max(8, size * 0.55) }}
      className={`inline-flex items-center justify-center rounded border font-bold shrink-0 ${color} ${className}`}
      aria-label={label}
    >
      {label.charAt(0).toUpperCase()}
    </span>
  );
}

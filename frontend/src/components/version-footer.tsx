import type { UseVersionResult } from "../hooks/use-version";

interface VersionFooterProps {
  version: UseVersionResult;
  onOpenSettings: () => void;
}

export function VersionFooter({ version, onOpenSettings }: VersionFooterProps) {
  const { info, effectiveState } = version;
  if (!info) return null;
  const label = `v${info.current}`;

  if (effectiveState === "update_available") {
    return (
      <button
        onClick={onOpenSettings}
        className="text-xs text-muted hover:text-secondary px-2 py-0.5 rounded-full bg-control border border-card hover:border-hover transition-colors"
        title="Open settings to see the upgrade command"
      >
        {label} · Update available
      </button>
    );
  }

  return <span className="text-xs text-faint">{label}</span>;
}

import type { LinkType } from "../../../api/extensions";

interface LinkTypeToggleProps {
  value: LinkType;
  onChange: (next: LinkType) => void;
  /** Show the explanatory help text below the buttons. */
  withHelp?: boolean;
}

const ACTIVE = "bg-accent-teal-subtle border-accent-teal text-accent-teal";
const INACTIVE = "border-card text-muted hover:text-secondary";

export function LinkTypeToggle({
  value,
  onChange,
  withHelp = true,
}: LinkTypeToggleProps) {
  return (
    <div>
      <p className="text-xs font-medium text-secondary mb-2">Install method</p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onChange("symlink")}
          className={`px-3 py-1 text-xs rounded-md border ${
            value === "symlink" ? ACTIVE : INACTIVE
          }`}
        >
          Symlink {withHelp ? "(recommended)" : ""}
        </button>
        <button
          type="button"
          onClick={() => onChange("copy")}
          className={`px-3 py-1 text-xs rounded-md border ${
            value === "copy" ? ACTIVE : INACTIVE
          }`}
        >
          Copy
        </button>
      </div>
      {withHelp && (
        <p className="text-xs text-dimmed mt-1.5">
          Symlinks keep agent copies in sync with edits to the central store.
          Copy is used automatically when symlinks are not supported.
        </p>
      )}
    </div>
  );
}

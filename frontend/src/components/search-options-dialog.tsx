import { X } from "lucide-react";

interface SearchSource {
  key: string;
  label: string;
  description: string;
}

const SEARCH_SOURCES: SearchSource[] = [
  {
    key: "user_prompts",
    label: "User prompts",
    description: "All messages typed by the user",
  },
  {
    key: "agent_messages",
    label: "Agent messages",
    description: "Text responses from the agent",
  },
  {
    key: "tool_calls",
    label: "Tool calls",
    description: "Tool names, arguments, and results",
  },
  {
    key: "session_id",
    label: "Session ID",
    description: "Match against session identifiers",
  },
];

interface SearchOptionsDialogProps {
  sources: Set<string>;
  onApply: (sources: Set<string>) => void;
  onClose: () => void;
}

export function SearchOptionsDialog({
  sources,
  onApply,
  onClose,
}: SearchOptionsDialogProps) {
  const draft = new Set(sources);

  const handleToggle = (key: string) => {
    if (draft.has(key)) {
      draft.delete(key);
    } else {
      draft.add(key);
    }
    // Force re-render by applying immediately through onApply
    onApply(new Set(draft));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-overlay backdrop-blur-sm"
        onClick={onClose}
      />

      <div className="relative bg-panel border border-card rounded-lg shadow-2xl w-full max-w-sm mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-default">
          <h2 className="text-sm font-semibold text-primary">
            Search Options
          </h2>
          <button
            onClick={onClose}
            className="text-dimmed hover:text-secondary transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          {SEARCH_SOURCES.map((src) => (
            <label
              key={src.key}
              className="flex items-start gap-3 cursor-pointer group"
            >
              <input
                type="checkbox"
                checked={sources.has(src.key)}
                onChange={() => handleToggle(src.key)}
                className="mt-0.5 accent-cyan-500 w-4 h-4 rounded border-hover bg-control"
              />
              <div>
                <span className="text-sm text-secondary group-hover:text-primary transition">
                  {src.label}
                </span>
                <p className="text-xs text-dimmed">{src.description}</p>
              </div>
            </label>
          ))}
        </div>

        <div className="flex justify-end gap-2 px-5 py-3 border-t border-default">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-muted hover:text-secondary transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

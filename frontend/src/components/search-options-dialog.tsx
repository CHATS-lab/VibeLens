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
    key: "agent_content",
    label: "Agent responses & tool calls",
    description: "Agent messages, tool names, and arguments",
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
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      <div className="relative bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl w-full max-w-sm mx-4">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-100">
            Search Options
          </h2>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 transition"
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
                className="mt-0.5 accent-cyan-500 w-4 h-4 rounded border-zinc-600 bg-zinc-800"
              />
              <div>
                <span className="text-sm text-zinc-200 group-hover:text-zinc-100 transition">
                  {src.label}
                </span>
                <p className="text-xs text-zinc-500">{src.description}</p>
              </div>
            </label>
          ))}
        </div>

        <div className="flex justify-end gap-2 px-5 py-3 border-t border-zinc-800">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

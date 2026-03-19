import { useState } from "react";
import { X } from "lucide-react";

interface DonateConsentDialogProps {
  sessionCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}

const CONSENT_ITEMS = [
  "My donated sessions may contain code snippets, file paths, and conversation content from my coding agent interactions.",
  "Donated data will be used for academic research on coding agent behavior by CHATS-Lab at Northeastern University.",
  "I have reviewed the selected sessions and confirm they do not contain sensitive credentials, API keys, or private information I wish to keep confidential.",
  "Donated data may be shared in anonymized or aggregated form in research publications and datasets.",
];

export function DonateConsentDialog({
  sessionCount,
  onConfirm,
  onCancel,
}: DonateConsentDialogProps) {
  const [agreed, setAgreed] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />

      <div className="relative bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-100">
            Donate {sessionCount} Session{sessionCount !== 1 ? "s" : ""}
          </h2>
          <button
            onClick={onCancel}
            className="text-zinc-500 hover:text-zinc-300 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          <p className="text-sm text-zinc-300">
            Your sessions will be donated to{" "}
            <a
              href="https://github.com/CHATS-lab"
              target="_blank"
              rel="noopener noreferrer"
              className="text-cyan-400 hover:text-cyan-300 underline"
            >
              CHATS-Lab
            </a>{" "}
            at Northeastern University for research on coding agent behavior.
          </p>

          <div className="space-y-2 text-xs text-zinc-400">
            <p className="font-medium text-zinc-300">
              By donating, you acknowledge that:
            </p>
            <ul className="space-y-1.5 list-disc list-inside">
              {CONSENT_ITEMS.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>

          {/* Agreement checkbox */}
          <label className="flex items-start gap-2.5 cursor-pointer group">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 w-4 h-4 rounded border-zinc-600 bg-zinc-800 text-cyan-500 focus:ring-cyan-500 focus:ring-offset-0 cursor-pointer"
            />
            <span className="text-xs text-zinc-300 group-hover:text-zinc-100 transition select-none">
              I have read and agree to the above terms
            </span>
          </label>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-zinc-800">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!agreed}
            className="px-3 py-1.5 text-xs text-white bg-rose-600 hover:bg-rose-500 rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Donate
          </button>
        </div>
      </div>
    </div>
  );
}

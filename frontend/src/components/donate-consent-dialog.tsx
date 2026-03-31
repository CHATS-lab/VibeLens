import { useState } from "react";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "./modal";

interface DonateConsentDialogProps {
  sessionCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}

const CONSENT_ITEMS = [
  "Before sharing, please ensure you have the necessary permissions to share this data and that it does not belong to a project with confidentiality restrictions.",
  "My donated sessions may contain code snippets, file paths, and conversation content from my coding agent interactions.",
  "Donated data will be used solely for academic research and will not be sold or used for commercial purposes.",
  "Donated data may appear in anonymized or aggregated form in research publications and open datasets.",
  "I may request deletion of my donated data by contacting the research team.",
];

export function DonateConsentDialog({
  sessionCount,
  onConfirm,
  onCancel,
}: DonateConsentDialogProps) {
  const [agreed, setAgreed] = useState(false);

  return (
    <Modal onClose={onCancel} maxWidth="max-w-lg">
      <ModalHeader
        title={`Donate ${sessionCount} Session${sessionCount !== 1 ? "s" : ""}`}
        onClose={onCancel}
      />

      <ModalBody>
        <div className="space-y-4">
          <p className="text-sm text-zinc-100 leading-relaxed">
            Your sessions will be donated to{" "}
            <a
              href="https://github.com/CHATS-lab"
              target="_blank"
              rel="noopener noreferrer"
              className="text-cyan-400 hover:text-cyan-300 underline"
            >
              CHATS-Lab
            </a>{" "}
            at Northeastern University for academic research on coding agent
            behavior. All donated data will be post-processed with
            anonymization tools before use.
          </p>

          <div className="space-y-2">
            <p className="text-sm font-medium text-zinc-100">
              By donating, you acknowledge that:
            </p>
            <ul className="space-y-1.5 list-disc pl-4 text-sm text-zinc-200 leading-relaxed">
              {CONSENT_ITEMS.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>

          <label className="flex items-center gap-2.5 cursor-pointer group bg-zinc-800/50 rounded-md px-3 py-2.5">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="w-4 h-4 rounded border-zinc-600 bg-zinc-800 text-cyan-500 focus:ring-cyan-500 focus:ring-offset-0 cursor-pointer"
            />
            <span className="text-sm text-zinc-100 group-hover:text-white transition select-none">
              I have read and agree to the above terms
            </span>
          </label>
        </div>
      </ModalBody>

      <ModalFooter>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-zinc-400 hover:text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded transition"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={!agreed}
          className="px-3 py-1.5 text-sm text-white bg-rose-600 hover:bg-rose-500 rounded transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Donate
        </button>
      </ModalFooter>
    </Modal>
  );
}

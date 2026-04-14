import { Search } from "lucide-react";
import { useState } from "react";
import { ConsentSection } from "../consent-section";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "../modal";

export function RecommendConsentDialog({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [agreed, setAgreed] = useState(false);

  return (
    <Modal onClose={onCancel} maxWidth="max-w-md">
      <ModalHeader onClose={onCancel}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-teal-600/20">
            <Search className="w-5 h-5 text-teal-600 dark:text-teal-400" />
          </div>
          <h2 className="text-base font-semibold text-primary">
            Confirm Recommendation
          </h2>
        </div>
      </ModalHeader>
      <ModalBody>
        <div className="space-y-4">
          <div className="rounded-lg border border-teal-200 dark:border-teal-800/40 bg-teal-50 dark:bg-teal-950/10 px-4 py-3">
            <p className="text-sm text-secondary leading-relaxed">
              VibeLens will analyze all your sessions to build a profile, then
              match you with community skills that fit your workflow.
            </p>
          </div>
          <ConsentSection agreed={agreed} onAgreeChange={setAgreed} />
        </div>
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onCancel}
          className="px-4 py-2 text-xs text-muted hover:text-secondary hover:bg-control border border-card rounded-md transition"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={!agreed}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white text-xs font-medium rounded-md transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Search className="w-3 h-3" />
          Start
        </button>
      </ModalFooter>
    </Modal>
  );
}

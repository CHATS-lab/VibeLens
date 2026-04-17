import { Coins, Layers, Play, Sparkles } from "lucide-react";
import { useState } from "react";
import type { CostEstimate } from "../types";
import { ConsentSection } from "./consent-section";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "./ui/modal";

export function CostEstimateDialog({
  estimate,
  sessionCount,
  onConfirm,
  onCancel,
}: {
  estimate: CostEstimate;
  sessionCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [agreed, setAgreed] = useState(false);

  return (
    <Modal onClose={onCancel} maxWidth="max-w-lg">
      <ModalHeader onClose={onCancel}>
        <h2 className="text-base font-semibold text-primary">Confirm Analysis</h2>
      </ModalHeader>
      <ModalBody>
        <div className="space-y-4">
          <div className="flex items-center gap-4 px-4 py-3 bg-subtle rounded-lg">
            <div className="flex items-center gap-2.5">
              <Layers className="w-4 h-4 text-violet-600 dark:text-violet-400" />
              <div className="flex flex-col">
                <span className="text-[10px] text-dimmed">Sessions</span>
                <span className="text-sm font-semibold text-primary">{sessionCount}</span>
              </div>
            </div>
            <div className="w-px h-8 bg-control-hover" />
            <div className="flex items-center gap-2.5">
              <Sparkles className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              <div className="flex flex-col">
                <span className="text-[10px] text-dimmed">Model</span>
                <span className="text-sm font-medium text-secondary">{estimate.model}</span>
              </div>
            </div>
          </div>
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/30 rounded-lg px-4 py-3">
            <div className="flex items-center gap-2">
              <Coins className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              <span className="text-sm font-medium text-amber-800 dark:text-amber-200">
                Estimated cost: {estimate.formatted_cost}
              </span>
            </div>
            {!estimate.pricing_found && (
              <p className="mt-1 text-xs text-amber-600/70 dark:text-amber-400/70">
                Model not in pricing table -- actual cost may vary.
              </p>
            )}
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
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium rounded-md transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Play className="w-3 h-3" />
          Run Analysis
        </button>
      </ModalFooter>
    </Modal>
  );
}

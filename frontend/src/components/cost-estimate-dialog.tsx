import { Coins, Layers, Play, Sparkles } from "lucide-react";
import type { CostEstimate } from "../types";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "./modal";

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
  return (
    <Modal onClose={onCancel} maxWidth="max-w-md">
      <ModalHeader title="Confirm Analysis" onClose={onCancel} />
      <ModalBody>
        <div className="space-y-4">
          <div className="flex items-center gap-2 px-3 py-2 bg-zinc-800/50 rounded-lg">
            <Layers className="w-3.5 h-3.5 text-violet-400" />
            <div className="flex flex-col">
              <span className="text-[10px] text-zinc-500">Sessions</span>
              <span className="text-xs text-zinc-200">{sessionCount}</span>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Model: {estimate.model}</span>
          </div>
          <div className="bg-amber-900/20 border border-amber-700/30 rounded-lg px-4 py-3">
            <div className="flex items-center gap-2">
              <Coins className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-medium text-amber-200">
                Estimated cost: {estimate.formatted_cost}
              </span>
            </div>
            {!estimate.pricing_found && (
              <p className="mt-1 text-xs text-amber-400/70">
                Model not in pricing table -- actual cost may vary.
              </p>
            )}
          </div>
        </div>
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onCancel}
          className="px-4 py-2 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 border border-zinc-700 rounded-md transition"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium rounded-md transition"
        >
          <Play className="w-3 h-3" />
          Run Analysis
        </button>
      </ModalFooter>
    </Modal>
  );
}

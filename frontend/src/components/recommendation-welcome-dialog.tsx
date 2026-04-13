import { Search, Sparkles, X } from "lucide-react";
import { Modal, ModalBody } from "./modal";

interface RecommendationWelcomeDialogProps {
  onTryNow: () => void;
  onDismiss: () => void;
}

export function RecommendationWelcomeDialog({ onTryNow, onDismiss }: RecommendationWelcomeDialogProps) {
  return (
    <Modal onClose={onDismiss} maxWidth="max-w-md">
      <ModalBody>
        <div className="flex flex-col items-center text-center py-4 gap-5">
          <button
            onClick={onDismiss}
            className="absolute top-3 right-3 p-1 text-zinc-400 hover:text-zinc-200 transition"
          >
            <X className="w-4 h-4" />
          </button>

          <span className="text-sm font-semibold tracking-widest uppercase text-cyan-500">
            New Feature
          </span>

          <h2 className="text-lg font-semibold text-primary">
            Personalize your agent in one minute
          </h2>

          <div className="flex flex-col gap-3 w-full">
            <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-cyan-500/5 border border-cyan-500/10">
              <Search className="w-5 h-5 text-cyan-500 shrink-0" />
              <div className="text-left">
                <p className="text-sm font-medium text-primary">1,500+ tools scanned</p>
                <p className="text-xs text-muted">Skills, agents, commands, hooks, repos</p>
              </div>
            </div>
            <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-violet-500/5 border border-violet-500/10">
              <Sparkles className="w-5 h-5 text-violet-500 shrink-0" />
              <div className="text-left">
                <p className="text-sm font-medium text-primary">Matched to your workflow</p>
                <p className="text-xs text-muted">LLM-powered profile from your sessions</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={onTryNow}
              className="px-5 py-2 text-sm font-semibold text-white bg-gradient-to-r from-cyan-600 to-cyan-500 hover:from-cyan-500 hover:to-cyan-400 rounded-lg transition"
            >
              Try It Now
            </button>
            <button
              onClick={onDismiss}
              className="px-4 py-2 text-sm text-muted hover:text-secondary transition"
            >
              Skip
            </button>
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}

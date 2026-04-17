import { useState } from "react";
import { Search, Sparkles, X } from "lucide-react";
import { Modal, ModalBody } from "./ui/modal";

const DISMISS_KEY = "vibelens-rec-welcome-dismissed";

interface RecommendationWelcomeDialogProps {
  onTryNow: () => void;
  onDismiss: () => void;
}

export function shouldShowRecWelcome(): boolean {
  return localStorage.getItem(DISMISS_KEY) !== "1";
}

export function RecommendationWelcomeDialog({ onTryNow, onDismiss }: RecommendationWelcomeDialogProps) {
  const [dontShow, setDontShow] = useState(false);

  const dismiss = () => {
    if (dontShow) localStorage.setItem(DISMISS_KEY, "1");
    onDismiss();
  };

  const tryNow = () => {
    if (dontShow) localStorage.setItem(DISMISS_KEY, "1");
    onTryNow();
  };

  return (
    <Modal onClose={dismiss} maxWidth="max-w-md">
      <ModalBody>
        <div className="flex flex-col items-center text-center py-4 gap-5">
          <button
            onClick={dismiss}
            className="absolute top-3 right-3 p-1 text-muted hover:text-primary transition"
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

          <label className="flex items-center gap-2 text-xs text-muted cursor-pointer select-none">
            <input
              type="checkbox"
              checked={dontShow}
              onChange={(e) => setDontShow(e.target.checked)}
              className="rounded border-border text-cyan-600 focus:ring-cyan-500/30"
            />
            Don't show this again
          </label>

          <div className="flex items-center gap-3">
            <button
              onClick={tryNow}
              className="px-5 py-2 text-sm font-semibold text-white bg-gradient-to-r from-cyan-600 to-cyan-500 hover:from-cyan-500 hover:to-cyan-400 rounded-lg transition"
            >
              Try It Now
            </button>
            <button
              onClick={dismiss}
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

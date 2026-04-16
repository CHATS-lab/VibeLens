import { BookOpen, ExternalLink, Eye, FileText, Heart, History, Shield, Trash2 } from "lucide-react";
import { useState } from "react";
import { Modal, ModalHeader, ModalBody, ModalFooter } from "./modal";
import { WITHDRAW_FORM_URL } from "./donation-constants";

interface DonateConsentDialogProps {
  sessionCount: number;
  onConfirm: () => void;
  onCancel: () => void;
  onShowHistory: () => void;
}

const CONSENT_ITEMS: { icon: React.ReactNode; text: string }[] = [
  {
    icon: <Shield className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />,
    text: "Please ensure you have permission to share this data and it does not belong to a confidential project.",
  },
  {
    icon: <FileText className="w-4 h-4 text-cyan-600 dark:text-cyan-400 shrink-0 mt-0.5" />,
    text: "Sessions may contain code snippets, git bundles, file paths, and conversation content from your coding agent interactions.",
  },
  {
    icon: <BookOpen className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />,
    text: "Data will be used solely for academic research and will not be sold or used commercially.",
  },
  {
    icon: <Eye className="w-4 h-4 text-violet-600 dark:text-violet-400 shrink-0 mt-0.5" />,
    text: "Data may appear in anonymized or aggregated form in research publications and open datasets.",
  },
  {
    icon: <Trash2 className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />,
    text: "You may request deletion of your donated data by contacting the research team.",
  },
];

export function DonateConsentDialog({
  sessionCount,
  onConfirm,
  onCancel,
  onShowHistory,
}: DonateConsentDialogProps) {
  const [agreed, setAgreed] = useState(false);

  return (
    <Modal onClose={onCancel} maxWidth="max-w-2xl">
      <ModalHeader onClose={onCancel}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-rose-600/20">
            <Heart className="w-5 h-5 text-rose-600 dark:text-rose-400" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-primary">
              Donate {sessionCount} Session{sessionCount !== 1 ? "s" : ""}
            </h2>
            <p className="text-xs text-muted">Support open research on coding agents</p>
          </div>
        </div>
      </ModalHeader>

      <ModalBody>
        <div className="space-y-5">
          <div className="rounded-lg border border-cyan-200 dark:border-cyan-800/40 bg-cyan-50 dark:bg-cyan-950/10 px-4 py-3">
            <p className="text-sm text-secondary leading-relaxed">
              Your sessions will be donated to{" "}
              <a
                href="https://github.com/CHATS-lab"
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent-cyan hover:text-cyan-700 dark:hover:text-cyan-300 underline font-medium"
              >
                CHATS-Lab
              </a>{" "}
              at Northeastern University for academic research on coding agent
              behavior. All donated data will be post-processed with
              anonymization tools before use.
            </p>
          </div>

          <div>
            <p className="text-sm font-semibold text-primary mb-3">
              By donating, you acknowledge that:
            </p>
            <div className="space-y-2.5">
              {CONSENT_ITEMS.map((item, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 rounded-md bg-control/40 border border-card px-3.5 py-2.5"
                >
                  {item.icon}
                  <span className="text-sm text-secondary leading-relaxed">{item.text}</span>
                </div>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-3 cursor-pointer group rounded-lg border border-hover bg-control/60 px-4 py-3 hover:border-rose-600/40 hover:bg-control/80 transition">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="w-4 h-4 rounded border-hover bg-control text-rose-500 focus:ring-rose-500 focus:ring-offset-0 cursor-pointer"
            />
            <span className="text-sm font-medium text-primary transition select-none">
              I have read and agree to the above terms
            </span>
          </label>

          <p className="text-xs text-muted text-center">
            Already donated?{" "}
            <a
              href={WITHDRAW_FORM_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-rose-600 dark:text-rose-400 hover:underline"
            >
              Request withdrawal
              <ExternalLink className="w-3 h-3" />
            </a>
          </p>
        </div>
      </ModalBody>

      <ModalFooter>
        <button
          onClick={onShowHistory}
          className="mr-auto inline-flex items-center gap-1.5 px-3 py-2 text-sm text-muted hover:text-secondary hover:bg-control-hover border border-card hover:border-hover rounded-lg transition"
        >
          <History className="w-4 h-4" />
          View history
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm text-muted hover:text-secondary hover:bg-control-hover border border-card hover:border-hover rounded-lg transition"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={!agreed}
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-rose-600 hover:bg-rose-500 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Heart className="w-3.5 h-3.5" />
          Donate
        </button>
      </ModalFooter>
    </Modal>
  );
}

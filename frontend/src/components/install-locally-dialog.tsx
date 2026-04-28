import { ExternalLink, Package, Terminal } from "lucide-react";
import { useCopyFeedback } from "../hooks/use-copy-feedback";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "./ui/modal";

const INSTALL_COMMAND = "pip install vibelens && vibelens serve";

export function InstallLocallyDialog({ onClose }: { onClose: () => void }) {
  const { copied, copy } = useCopyFeedback();

  return (
    <Modal onClose={onClose} maxWidth="max-w-lg">
      <ModalHeader title="Install VibeLens Locally" onClose={onClose} />
      <ModalBody>
        <div className="flex items-center justify-center mb-2">
          <div className="p-3 rounded-full bg-cyan-50 dark:bg-cyan-900/30 border border-cyan-200 dark:border-cyan-800/40">
            <Package className="w-6 h-6 text-accent-cyan" />
          </div>
        </div>
        <p className="text-sm text-secondary text-center leading-relaxed">
          LLM-powered analysis is available when running VibeLens on your own machine. Install it with one command:
        </p>
        <button
          onClick={() => copy(INSTALL_COMMAND)}
          className="w-full group flex items-center gap-2 px-4 py-3 bg-control hover:bg-control-hover border border-card rounded-lg transition text-left"
        >
          <Terminal className="w-4 h-4 text-dimmed shrink-0" />
          <code className="text-sm text-accent-cyan flex-1 font-mono">{INSTALL_COMMAND}</code>
          <span className="text-xs text-dimmed group-hover:text-secondary transition shrink-0">
            {copied ? "Copied!" : "Copy"}
          </span>
        </button>
        <div className="flex justify-center">
          <a
            href="https://github.com/CHATS-lab/VibeLens"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-accent-cyan hover:text-accent-cyan transition"
          >
            <ExternalLink className="w-3 h-3" />
            View on GitHub
          </a>
        </div>
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-secondary hover:text-primary bg-control hover:bg-control-hover border border-card rounded-md transition"
        >
          Got it
        </button>
      </ModalFooter>
    </Modal>
  );
}

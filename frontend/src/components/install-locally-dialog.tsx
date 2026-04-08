import { ExternalLink, Package, Terminal } from "lucide-react";
import { useState } from "react";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "./modal";

export function InstallLocallyDialog({ onClose }: { onClose: () => void }) {
  const [copied, setCopied] = useState(false);

  const installCommand = "pip install vibelens && vibelens serve";

  const handleCopy = () => {
    navigator.clipboard.writeText(installCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Modal onClose={onClose} maxWidth="max-w-lg">
      <ModalHeader title="Install VibeLens Locally" onClose={onClose} />
      <ModalBody>
        <div className="flex items-center justify-center mb-2">
          <div className="p-3 rounded-full bg-cyan-900/30 border border-cyan-700/30">
            <Package className="w-6 h-6 text-cyan-400" />
          </div>
        </div>
        <p className="text-sm text-zinc-300 text-center leading-relaxed">
          LLM-powered analysis is available when running VibeLens on your own machine. Install it with one command:
        </p>
        <button
          onClick={handleCopy}
          className="w-full group flex items-center gap-2 px-4 py-3 bg-zinc-800 hover:bg-zinc-750 border border-zinc-700 rounded-lg transition text-left"
        >
          <Terminal className="w-4 h-4 text-zinc-500 shrink-0" />
          <code className="text-sm text-cyan-300 flex-1 font-mono">{installCommand}</code>
          <span className="text-xs text-zinc-500 group-hover:text-zinc-300 transition shrink-0">
            {copied ? "Copied!" : "Copy"}
          </span>
        </button>
        <div className="flex justify-center">
          <a
            href="https://github.com/yejh123/VibeLens"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 transition"
          >
            <ExternalLink className="w-3 h-3" />
            View on GitHub
          </a>
        </div>
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-md transition"
        >
          Got it
        </button>
      </ModalFooter>
    </Modal>
  );
}

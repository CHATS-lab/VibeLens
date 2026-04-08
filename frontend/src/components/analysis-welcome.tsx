import { ArrowLeft, ExternalLink, Package, Play, Settings, Terminal } from "lucide-react";
import { useState } from "react";
import type { LLMStatus } from "../types";
import { DemoBanner } from "./demo-banner";
import { LLMConfigForm } from "./llm-config";
import { Modal, ModalBody, ModalFooter, ModalHeader } from "./modal";
import { Tooltip } from "./tooltip";

type AccentColor = "amber" | "teal" | "cyan";

const ACCENT_BUTTON: Record<AccentColor, string> = {
  amber: "bg-amber-600 hover:bg-amber-500",
  teal: "bg-teal-600 hover:bg-teal-500",
  cyan: "bg-cyan-600 hover:bg-cyan-500",
};

const ACCENT_LINK: Record<AccentColor, string> = {
  amber: "text-amber-400 hover:text-amber-300",
  teal: "text-teal-400 hover:text-teal-300",
  cyan: "text-cyan-400 hover:text-cyan-300",
};

interface AnalysisWelcomePageProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  accentColor: AccentColor;
  llmStatus: LLMStatus | null;
  fetchWithToken: (url: string, init?: RequestInit) => Promise<Response>;
  onLlmConfigured: () => void;
  checkedCount: number;
  maxSessions: number;
  error: string | null;
  onRun: () => void;
  isDemo?: boolean;
}

export function AnalysisWelcomePage({
  icon,
  title,
  description,
  accentColor,
  llmStatus,
  fetchWithToken,
  onLlmConfigured,
  checkedCount,
  maxSessions,
  error,
  onRun,
  isDemo,
}: AnalysisWelcomePageProps) {
  const [view, setView] = useState<"intro" | "config">("intro");
  const [showInstallDialog, setShowInstallDialog] = useState(false);

  const isConnected = llmStatus?.available === true;
  const isMock = llmStatus?.backend_id === "mock";
  const overLimit = checkedCount > maxSessions;

  if (view === "config") {
    return (
      <div className="flex justify-center h-full pt-12">
        <div className="max-w-md w-full px-6">
          <button
            onClick={() => setView("intro")}
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition mb-6"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back
          </button>
          <h3 className="text-lg font-semibold text-zinc-200 mb-2">
            Configure LLM Backend
          </h3>
          <p className="text-xs text-zinc-400 mb-5">
            Provide an API key and model to enable LLM-powered analysis.
          </p>
          <LLMConfigForm
            fetchWithToken={fetchWithToken}
            llmStatus={llmStatus}
            accentColor={accentColor}
            onConfigured={() => {
              onLlmConfigured();
              setView("intro");
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center max-w-md px-6">
        <div className="flex justify-center mb-4">{icon}</div>
        <h3 className="text-lg font-semibold text-zinc-200 mb-2">{title}</h3>
        <p className="text-sm text-zinc-400 mb-6 leading-relaxed">
          {description}
        </p>

        {/* LLM status indicator */}
        {!isMock && (
          <div className="mb-6">
            {isConnected ? (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-zinc-800/60 border border-zinc-700/50 rounded-lg text-xs text-zinc-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <span>{llmStatus.backend_id} / {llmStatus.model}</span>
                <button
                  onClick={() => setView("config")}
                  className={`ml-1 ${ACCENT_LINK[accentColor]} transition`}
                >
                  Change
                </button>
              </div>
            ) : (
              <button
                onClick={() => setView("config")}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700/50 rounded-lg transition"
              >
                <Settings className="w-3.5 h-3.5" />
                Configure LLM
              </button>
            )}
          </div>
        )}

        {isDemo && isMock && (
          <div className="mb-6 text-left">
            <DemoBanner />
          </div>
        )}

        {error && (
          <div className="mb-4 px-4 py-2.5 bg-rose-900/20 border border-rose-800/50 rounded-lg text-xs text-rose-300 text-left">
            {error}
          </div>
        )}

        {overLimit && (
          <div className="mb-4 px-4 py-2.5 bg-amber-900/20 border border-amber-800/50 rounded-lg text-xs text-amber-300 text-left">
            Too many sessions selected ({checkedCount}). Maximum is {maxSessions}. Deselect some sessions to continue.
          </div>
        )}

        <Tooltip text={checkedCount === 0 ? "Use the checkboxes in the session list to select sessions for analysis." : ""}>
          <button
            onClick={isDemo ? () => setShowInstallDialog(true) : onRun}
            disabled={checkedCount === 0 || overLimit || (!isConnected && !isMock)}
            className={`inline-flex items-center gap-2 px-5 py-2.5 ${ACCENT_BUTTON[accentColor]} text-white text-sm font-medium rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            <Play className="w-4 h-4" />
            {checkedCount > 0
              ? `Analyze ${checkedCount} session${checkedCount !== 1 ? "s" : ""}`
              : "Select sessions first"}
          </button>
        </Tooltip>
      </div>

      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

function InstallLocallyDialog({ onClose }: { onClose: () => void }) {
  const [copied, setCopied] = useState(false);

  const installCommand = "pip install vibelens && vibelens serve";

  const handleCopy = () => {
    navigator.clipboard.writeText(installCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Modal onClose={onClose} maxWidth="max-w-md">
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

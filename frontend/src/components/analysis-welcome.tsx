import { ArrowLeft, Lightbulb, Play, Settings } from "lucide-react";
import { useState } from "react";
import type { LLMStatus } from "../types";
import { DemoBanner } from "./demo-banner";
import { InstallLocallyDialog } from "./install-locally-dialog";
import { LLMConfigForm } from "./llm-config";
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

const ACCENT_TUTORIAL: Record<AccentColor, {
  border: string;
  bg: string;
  radial: string;
  iconBg: string;
  iconColor: string;
  title: string;
  desc: string;
}> = {
  amber: {
    border: "border-amber-800/40",
    bg: "bg-gradient-to-r from-amber-950/40 via-amber-900/20 to-orange-950/40",
    radial: "bg-[radial-gradient(ellipse_at_top_right,rgba(234,88,12,0.08),transparent_60%)]",
    iconBg: "bg-amber-500/15 border border-amber-500/20",
    iconColor: "text-amber-400",
    title: "text-amber-300",
    desc: "text-amber-400/70",
  },
  teal: {
    border: "border-teal-800/40",
    bg: "bg-gradient-to-r from-teal-950/40 via-teal-900/20 to-indigo-950/40",
    radial: "bg-[radial-gradient(ellipse_at_top_right,rgba(139,92,246,0.08),transparent_60%)]",
    iconBg: "bg-teal-500/15 border border-teal-500/20",
    iconColor: "text-teal-400",
    title: "text-teal-300",
    desc: "text-teal-400/70",
  },
  cyan: {
    border: "border-cyan-800/40",
    bg: "bg-gradient-to-r from-cyan-950/40 via-cyan-900/20 to-blue-950/40",
    radial: "bg-[radial-gradient(ellipse_at_top_right,rgba(59,130,246,0.08),transparent_60%)]",
    iconBg: "bg-cyan-500/15 border border-cyan-500/20",
    iconColor: "text-cyan-400",
    title: "text-cyan-300",
    desc: "text-cyan-400/70",
  },
};

export interface Tutorial {
  title: string;
  description: string;
}

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
  tutorial?: Tutorial;
  tutorialAccentColor?: AccentColor;
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
  tutorial,
  tutorialAccentColor,
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

        {tutorial && <TutorialBanner tutorial={tutorial} accentColor={tutorialAccentColor ?? accentColor} />}

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

export function TutorialBanner({ tutorial, accentColor }: { tutorial: Tutorial; accentColor: AccentColor }) {
  const s = ACCENT_TUTORIAL[accentColor];
  return (
    <div className={`relative w-full px-4 py-3.5 rounded-lg ${s.border} ${s.bg} overflow-hidden text-left mb-6`}>
      <div className={`absolute inset-0 ${s.radial}`} />
      <div className="relative flex items-center gap-3">
        <div className={`shrink-0 p-2 rounded-lg ${s.iconBg}`}>
          <Lightbulb className={`w-4 h-4 ${s.iconColor}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${s.title}`}>{tutorial.title}</p>
          <p className={`text-sm ${s.desc} mt-0.5`}>{tutorial.description}</p>
        </div>
      </div>
    </div>
  );
}


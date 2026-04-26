import { ArrowLeft, Lightbulb, Play, Settings, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { LLMStatus } from "../types";
import { DemoBanner } from "./demo-banner";
import { InstallLocallyDialog } from "./install-locally-dialog";
import { LLMConfigForm } from "./llm/llm-config";
import { Tooltip } from "./ui/tooltip";

type AccentColor = "amber" | "teal" | "cyan";

const ACCENT_BUTTON: Record<AccentColor, string> = {
  amber: "bg-amber-600 hover:bg-amber-500",
  teal: "bg-teal-600 hover:bg-teal-500",
  cyan: "bg-cyan-600 hover:bg-cyan-500",
};

const ACCENT_BUTTON_OUTLINE: Record<AccentColor, string> = {
  amber: "border border-amber-500/50 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10",
  teal: "border border-teal-500/50 text-teal-600 dark:text-teal-400 hover:bg-teal-500/10",
  cyan: "border border-cyan-500/50 text-cyan-600 dark:text-cyan-400 hover:bg-cyan-500/10",
};

const ACCENT_LINK: Record<AccentColor, string> = {
  amber: "text-amber-600 hover:text-amber-500 dark:text-amber-400 dark:hover:text-amber-300",
  teal: "text-teal-600 hover:text-teal-500 dark:text-teal-400 dark:hover:text-teal-300",
  cyan: "text-cyan-600 hover:text-cyan-500 dark:text-cyan-400 dark:hover:text-cyan-300",
};

const ACCENT_TUTORIAL: Record<AccentColor, {
  border: string;
  bg: string;
  iconBg: string;
  iconColor: string;
  title: string;
  desc: string;
}> = {
  amber: {
    border: "border-amber-300 dark:border-tutorial-amber-border",
    bg: "bg-amber-50 dark:bg-tutorial-amber-bg",
    iconBg: "bg-amber-100 dark:bg-amber-500/15 border border-amber-200 dark:border-amber-500/20",
    iconColor: "text-amber-600 dark:text-amber-400",
    title: "text-primary",
    desc: "text-secondary",
  },
  teal: {
    border: "border-teal-300 dark:border-tutorial-teal-border",
    bg: "bg-teal-50 dark:bg-tutorial-teal-bg",
    iconBg: "bg-teal-100 dark:bg-teal-500/15 border border-teal-200 dark:border-teal-500/20",
    iconColor: "text-teal-600 dark:text-teal-400",
    title: "text-primary",
    desc: "text-secondary",
  },
  cyan: {
    border: "border-cyan-300 dark:border-tutorial-cyan-border",
    bg: "bg-cyan-50 dark:bg-tutorial-cyan-bg",
    iconBg: "bg-cyan-100 dark:bg-cyan-500/15 border border-cyan-200 dark:border-cyan-500/20",
    iconColor: "text-cyan-600 dark:text-cyan-400",
    title: "text-primary",
    desc: "text-secondary",
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
  onRunAll?: () => void;
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
  onRunAll,
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
            className="flex items-center gap-1.5 text-xs text-dimmed hover:text-secondary hover:bg-control/30 rounded px-1 -mx-1 transition mb-6"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back
          </button>
          <h3 className="text-lg font-semibold text-secondary mb-2">
            Configure LLM Backend
          </h3>
          <p className="text-xs text-muted mb-5">
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
    <div className="flex justify-center pt-8">
      <div className="text-center max-w-md px-6">
        <div className="flex justify-center mb-4">{icon}</div>
        <h3 className="text-xl font-bold text-primary mb-2">{title}</h3>
        <p className="text-sm text-secondary mb-6 leading-relaxed">
          {description}
        </p>

        {tutorial && <TutorialBanner tutorial={tutorial} accentColor={tutorialAccentColor ?? accentColor} />}

        {/* LLM status indicator */}
        {!isMock && (
          <div className="mb-6">
            {isConnected ? (
              <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-control/60 border border-card rounded-lg text-xs text-muted">
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
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted hover:text-secondary bg-control hover:bg-control-hover border border-card rounded-lg transition"
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
          <div className="mb-4 px-4 py-2.5 bg-accent-rose-subtle border border-rose-200 dark:border-rose-800/40 rounded-lg text-xs text-accent-rose text-left">
            {error}
          </div>
        )}

        {overLimit && (
          <div className="mb-4 px-4 py-2.5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 rounded-lg text-xs text-amber-700 dark:text-amber-300 text-left">
            Too many sessions selected ({checkedCount}). Maximum is {maxSessions}. Deselect some sessions to continue.
          </div>
        )}

        <div className="flex items-center justify-center gap-3">
          {onRunAll && (
            <button
              onClick={isDemo ? () => setShowInstallDialog(true) : onRunAll}
              disabled={!isConnected && !isMock}
              className={`inline-flex items-center gap-1.5 px-4 py-2 ${ACCENT_BUTTON[accentColor]} text-white text-sm font-medium rounded-lg transition disabled:opacity-60 disabled:cursor-not-allowed`}
            >
              <Play className="w-3.5 h-3.5" />
              Start with all sessions
            </button>
          )}
          <Tooltip text={checkedCount === 0 ? "Use the checkboxes in the session list to select sessions for analysis." : ""}>
            <button
              onClick={isDemo ? () => setShowInstallDialog(true) : onRun}
              disabled={checkedCount === 0 || overLimit || (!isConnected && !isMock)}
              className={`inline-flex items-center gap-1.5 px-4 py-2 ${ACCENT_BUTTON_OUTLINE[accentColor]} text-sm font-medium rounded-lg transition disabled:opacity-60 disabled:cursor-not-allowed`}
            >
              <Play className="w-3.5 h-3.5" />
              {checkedCount > 0
                ? `Analyze ${checkedCount} selected`
                : "Select sessions first"}
            </button>
          </Tooltip>
        </div>
      </div>

      {showInstallDialog && (
        <InstallLocallyDialog onClose={() => setShowInstallDialog(false)} />
      )}
    </div>
  );
}

export function TutorialBanner({
  tutorial,
  accentColor,
  dismissKey,
}: {
  tutorial: Tutorial;
  accentColor: AccentColor;
  dismissKey?: string;
}) {
  const [hidden, setHidden] = useState(() =>
    dismissKey ? localStorage.getItem(dismissKey) === "1" : false,
  );

  useEffect(() => {
    setHidden(dismissKey ? localStorage.getItem(dismissKey) === "1" : false);
  }, [dismissKey]);

  if (hidden) return null;

  const handleDismiss = () => {
    if (dismissKey) localStorage.setItem(dismissKey, "1");
    setHidden(true);
  };

  const s = ACCENT_TUTORIAL[accentColor];
  return (
    <div className={`relative w-full px-4 py-3.5 rounded-lg border ${s.border} ${s.bg} overflow-hidden text-left`}>
      <div className="flex items-center gap-3">
        <div className={`shrink-0 p-2 rounded-lg ${s.iconBg}`}>
          <Lightbulb className={`w-4 h-4 ${s.iconColor}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className={`text-base font-bold ${s.title}`}>{tutorial.title}</p>
          <p className={`text-sm ${s.desc} mt-0.5`}>{tutorial.description}</p>
        </div>
        {dismissKey && (
          <button
            type="button"
            onClick={handleDismiss}
            aria-label="Hide tutorial"
            className="shrink-0 p-1 -m-1 text-muted hover:text-primary hover:bg-control/40 rounded transition"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}


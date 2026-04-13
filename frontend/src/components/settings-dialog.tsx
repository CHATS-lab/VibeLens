import { X, Bug, Lightbulb, Sparkles, Compass } from "lucide-react";
import { TOUR_STORAGE_KEY } from "./tutorial/tour-steps";
import { useSettings } from "../settings-context";
import type { FontScale, ThemePreference, FontFamily } from "../settings-context";

const GITHUB_ISSUES_URL = "https://github.com/CHATS-lab/VibeLens/issues/new";

const FEEDBACK_TEMPLATES: Record<string, { title: string; body: string }> = {
  bug: {
    title: "[Bug] ",
    body: `## Description
Describe the bug clearly and concisely.

## Steps to Reproduce
1. Go to ...
2. Click on ...
3. See error

## Expected Behavior
What should have happened?

## Screenshots
If applicable, add screenshots.

## Environment
- Browser:
- OS:
- VibeLens version: `,
  },
  enhancement: {
    title: "[Feature] ",
    body: `## Feature Description
Describe the feature you'd like to see.

## Use Case
Why would this feature be useful?

## Proposed Solution
How do you envision this working?

## Alternatives Considered
Any alternative solutions or workarounds?`,
  },
  improvement: {
    title: "[Improvement] ",
    body: `## Current Behavior
What currently works but could be better?

## Suggested Improvement
How should it be improved?

## Motivation
Why would this improvement matter?`,
  },
};

const FONT_CARDS: { key: FontFamily; label: string; fontFamily: string }[] = [
  { key: "default", label: "Default", fontFamily: "Georgia, 'Times New Roman', Times, serif" },
  { key: "sans", label: "Sans", fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" },
  { key: "system", label: "System", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', system-ui, sans-serif" },
  { key: "dyslexic", label: "Dyslexic friendly", fontFamily: "'OpenDyslexic', sans-serif" },
];

interface SettingsDialogProps {
  onClose: () => void;
  onShowOnboarding?: () => void;
}

function openFeedback(label: string): void {
  const template = FEEDBACK_TEMPLATES[label];
  const params = new URLSearchParams({
    labels: label,
    title: template?.title ?? "",
    body: template?.body ?? "",
  });
  window.open(`${GITHUB_ISSUES_URL}?${params}`, "_blank", "noopener,noreferrer");
}

export function SettingsDialog({ onClose, onShowOnboarding }: SettingsDialogProps) {
  const { fontScale, setFontScale, fontScaleOptions, theme, setTheme, themeOptions, fontFamily, setFontFamily } = useSettings();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-overlay backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative bg-panel border border-card rounded-lg shadow-2xl w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-default">
          <h2 className="text-sm font-semibold text-primary">Settings</h2>
          <button
            onClick={onClose}
            className="text-dimmed hover:text-secondary transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-5">
          {/* Theme */}
          <div>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
              Theme
            </h3>
            <div className="flex gap-2">
              {themeOptions.map((option: ThemePreference) => (
                <button
                  key={option}
                  onClick={() => setTheme(option)}
                  className={`flex-1 py-2 text-sm font-medium rounded-md border transition ${
                    theme === option
                      ? "bg-accent-cyan-subtle text-accent-cyan border-cyan-200 dark:border-cyan-700/40"
                      : "text-muted border-card hover:text-secondary hover:border-hover"
                  }`}
                >
                  {option.charAt(0).toUpperCase() + option.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Chat font */}
          <div>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
              Chat font
            </h3>
            <div className="grid grid-cols-4 gap-2">
              {FONT_CARDS.map((card) => (
                <button
                  key={card.key}
                  onClick={() => setFontFamily(card.key)}
                  className={`flex flex-col items-center gap-1 py-3 px-1 rounded-lg border transition ${
                    fontFamily === card.key
                      ? "bg-accent-cyan-subtle border-cyan-200 dark:border-cyan-700/40"
                      : "border-card hover:border-hover"
                  }`}
                >
                  <span
                    className="text-2xl text-primary leading-none"
                    style={{ fontFamily: card.fontFamily }}
                  >
                    Aa
                  </span>
                  <span className="text-[10px] text-muted mt-1 truncate w-full text-center">
                    {card.label}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Display Scale */}
          <div>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
              Display Scale
            </h3>
            <div className="flex gap-2">
              {fontScaleOptions.map((scale: FontScale) => (
                <button
                  key={scale}
                  onClick={() => setFontScale(scale)}
                  className={`flex-1 py-2 text-sm font-medium rounded-md border transition ${
                    fontScale === scale
                      ? "bg-accent-cyan-subtle text-accent-cyan border-cyan-200 dark:border-cyan-700/40"
                      : "text-muted border-card hover:text-secondary hover:border-hover"
                  }`}
                >
                  {scale}
                </button>
              ))}
            </div>
          </div>

          {/* Send Feedback */}
          <div>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
              Send Feedback
            </h3>
            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => openFeedback("bug")}
                className="flex flex-col items-center gap-1.5 py-3 text-xs font-medium text-secondary hover:text-primary bg-control/80 hover:bg-control-hover rounded-lg border border-card transition"
              >
                <Bug className="w-4 h-4 text-red-600 dark:text-red-400" />
                Bug Report
              </button>
              <button
                onClick={() => openFeedback("enhancement")}
                className="flex flex-col items-center gap-1.5 py-3 text-xs font-medium text-secondary hover:text-primary bg-control/80 hover:bg-control-hover rounded-lg border border-card transition"
              >
                <Lightbulb className="w-4 h-4 text-yellow-400" />
                Feature Request
              </button>
              <button
                onClick={() => openFeedback("improvement")}
                className="flex flex-col items-center gap-1.5 py-3 text-xs font-medium text-secondary hover:text-primary bg-control/80 hover:bg-control-hover rounded-lg border border-card transition"
              >
                <Sparkles className="w-4 h-4 text-accent-cyan" />
                Improvement
              </button>
            </div>
          </div>

          {/* Help */}
          <div>
            <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
              Help
            </h3>
            <button
              onClick={() => {
                localStorage.removeItem(TOUR_STORAGE_KEY);
                onShowOnboarding?.();
              }}
              className="flex items-center gap-2 w-full py-2.5 px-3 text-xs font-medium text-secondary hover:text-primary bg-control/80 hover:bg-control-hover rounded-lg border border-card transition"
            >
              <Compass className="w-4 h-4 text-accent-cyan" />
              Start Tutorial
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

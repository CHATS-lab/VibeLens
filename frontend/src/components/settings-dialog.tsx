import { X, Bug, Lightbulb, Sparkles, Compass } from "lucide-react";
import { TOUR_STORAGE_KEY } from "./tutorial/tour-steps";
import { useSettings } from "../settings-context";
import type { FontScale, ThemePreference, FontFamily } from "../settings-context";
import type { UseVersionResult } from "../hooks/use-version";
import { VersionSection } from "./version-section";

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
  { key: "sans", label: "Sans", fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" },
  { key: "serif", label: "Serif", fontFamily: "Georgia, 'Times New Roman', Times, serif" },
  { key: "mono", label: "Mono", fontFamily: "'Geist Mono', 'SF Mono', 'Fira Code', monospace" },
  { key: "readable", label: "Readable", fontFamily: "'Atkinson Hyperlegible', sans-serif" },
];

interface SettingsDialogProps {
  version: UseVersionResult;
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

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-1.5">
      {children}
    </h3>
  );
}

function FeedbackButton({
  label,
  icon,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center justify-center gap-1.5 py-2 text-xs font-medium text-secondary hover:text-primary bg-control/80 hover:bg-control-hover rounded-lg border border-card transition"
    >
      {icon}
      {label}
    </button>
  );
}

export function SettingsDialog({ version, onClose, onShowOnboarding }: SettingsDialogProps) {
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
        <div className="px-5 py-4 space-y-4">
          <VersionSection version={version} />

          {/* Appearance — theme + display scale share one block since both are
              quick segmented pickers. The 5-column grid gives Scale's 5 buttons
              their own column each so the percentages don't crowd. */}
          <div className="grid grid-cols-5 gap-3">
            <div className="col-span-2">
              <SectionLabel>Theme</SectionLabel>
              <div className="flex gap-1.5">
                {themeOptions.map((option: ThemePreference) => (
                  <button
                    key={option}
                    onClick={() => setTheme(option)}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-md border transition ${
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
            <div className="col-span-3">
              <SectionLabel>Scale</SectionLabel>
              <div className="flex gap-1.5">
                {fontScaleOptions.map((scale: FontScale) => (
                  <button
                    key={scale}
                    onClick={() => setFontScale(scale)}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-md border transition ${
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
          </div>

          {/* Font */}
          <div>
            <SectionLabel>Font</SectionLabel>
            <div className="grid grid-cols-4 gap-2">
              {FONT_CARDS.map((card) => (
                <button
                  key={card.key}
                  onClick={() => setFontFamily(card.key)}
                  className={`flex flex-col items-center gap-0.5 py-2 px-1 rounded-lg border transition ${
                    fontFamily === card.key
                      ? "bg-accent-cyan-subtle border-cyan-200 dark:border-cyan-700/40"
                      : "border-card hover:border-hover"
                  }`}
                >
                  <span
                    className="text-lg text-primary leading-none"
                    style={{ fontFamily: card.fontFamily }}
                  >
                    Aa
                  </span>
                  <span className="text-[10px] text-muted truncate w-full text-center">
                    {card.label}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Send Feedback — compact icon-left buttons keep one row */}
          <div>
            <SectionLabel>Send Feedback</SectionLabel>
            <div className="grid grid-cols-3 gap-1.5">
              <FeedbackButton label="Bug" icon={<Bug className="w-3.5 h-3.5 text-red-600 dark:text-red-400" />} onClick={() => openFeedback("bug")} />
              <FeedbackButton label="Feature" icon={<Lightbulb className="w-3.5 h-3.5 text-yellow-500" />} onClick={() => openFeedback("enhancement")} />
              <FeedbackButton label="Improve" icon={<Sparkles className="w-3.5 h-3.5 text-accent-cyan" />} onClick={() => openFeedback("improvement")} />
            </div>
          </div>

          {/* Tutorial — quiet footer link, no dedicated section header */}
          <button
            onClick={() => {
              localStorage.removeItem(TOUR_STORAGE_KEY);
              onShowOnboarding?.();
            }}
            className="flex items-center justify-center gap-1.5 w-full py-1.5 text-xs font-medium text-accent-cyan hover:text-accent-cyan/80 hover:bg-accent-cyan-subtle rounded-md transition"
          >
            <Compass className="w-3.5 h-3.5" />
            Start Tutorial
          </button>
        </div>
      </div>
    </div>
  );
}

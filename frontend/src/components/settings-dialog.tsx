import { X, Bug, Lightbulb, Sparkles } from "lucide-react";
import { useSettings } from "../settings-context";
import type { FontScale } from "../settings-context";

const GITHUB_ISSUES_URL = "https://github.com/yejh123/VibeLens/issues/new";

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

interface SettingsDialogProps {
  onClose: () => void;
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

export function SettingsDialog({ onClose }: SettingsDialogProps) {
  const { fontScale, setFontScale, fontScaleOptions } = useSettings();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Dialog */}
      <div className="relative bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <h2 className="text-sm font-semibold text-zinc-100">Settings</h2>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-5">
          {/* Display Scale */}
          <div>
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
              Display Scale
            </h3>
            <div className="flex gap-2">
              {fontScaleOptions.map((scale: FontScale) => (
                <button
                  key={scale}
                  onClick={() => setFontScale(scale)}
                  className={`flex-1 py-2 text-sm font-medium rounded-md border transition ${
                    fontScale === scale
                      ? "bg-cyan-600/20 text-cyan-300 border-cyan-500/40"
                      : "text-zinc-400 border-zinc-700 hover:text-zinc-200 hover:border-zinc-600"
                  }`}
                >
                  {scale}
                </button>
              ))}
            </div>
          </div>

          {/* Send Feedback */}
          <div>
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
              Send Feedback
            </h3>
            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => openFeedback("bug")}
                className="flex flex-col items-center gap-1.5 py-3 text-xs font-medium text-zinc-300 hover:text-zinc-100 bg-zinc-800/80 hover:bg-zinc-700 rounded-lg border border-zinc-700/50 transition"
              >
                <Bug className="w-4 h-4 text-red-400" />
                Bug Report
              </button>
              <button
                onClick={() => openFeedback("enhancement")}
                className="flex flex-col items-center gap-1.5 py-3 text-xs font-medium text-zinc-300 hover:text-zinc-100 bg-zinc-800/80 hover:bg-zinc-700 rounded-lg border border-zinc-700/50 transition"
              >
                <Lightbulb className="w-4 h-4 text-yellow-400" />
                Feature Request
              </button>
              <button
                onClick={() => openFeedback("improvement")}
                className="flex flex-col items-center gap-1.5 py-3 text-xs font-medium text-zinc-300 hover:text-zinc-100 bg-zinc-800/80 hover:bg-zinc-700 rounded-lg border border-zinc-700/50 transition"
              >
                <Sparkles className="w-4 h-4 text-cyan-400" />
                Improvement
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

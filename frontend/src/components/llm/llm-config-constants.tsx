export const BACKEND_OPTIONS = [
  { value: "litellm", label: "LiteLLM" },
  { value: "aider", label: "Aider" },
  { value: "amp", label: "Amp" },
  { value: "claude_code", label: "Claude Code" },
  { value: "codex", label: "Codex" },
  { value: "cursor", label: "Cursor" },
  { value: "gemini", label: "Gemini CLI" },
  { value: "kimi", label: "Kimi" },
  { value: "opencode", label: "OpenCode" },
  { value: "openclaw", label: "OpenClaw" },
  { value: "disabled", label: "Disabled" },
];

export const CLI_BACKENDS = new Set([
  "aider",
  "amp",
  "claude_code",
  "codex",
  "cursor",
  "gemini",
  "kimi",
  "opencode",
  "openclaw",
]);

export type AccentColor = "amber" | "teal" | "cyan";

export const ACCENT_STYLES: Record<AccentColor, { focus: string; button: string; selected: string }> = {
  amber: {
    focus: "focus:border-amber-600",
    button: "bg-amber-600 hover:bg-amber-500",
    selected: "text-amber-700 dark:text-amber-400",
  },
  teal: {
    focus: "focus:border-teal-600",
    button: "bg-teal-600 hover:bg-teal-500",
    selected: "text-teal-700 dark:text-teal-400",
  },
  cyan: {
    focus: "focus:border-cyan-600",
    button: "bg-cyan-600 hover:bg-cyan-500",
    selected: "text-cyan-700 dark:text-cyan-400",
  },
};

export function formatPrice(price: number): string {
  return price < 0.01 ? price.toFixed(3) : price.toFixed(2);
}

export function PricingLine({ inputPrice, outputPrice }: { inputPrice: number; outputPrice: number }) {
  return (
    <p className="text-xs text-dimmed mt-1">
      ${formatPrice(inputPrice)} / ${formatPrice(outputPrice)} per MTok (in / out)
    </p>
  );
}

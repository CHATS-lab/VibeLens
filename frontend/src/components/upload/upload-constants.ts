import type { AgentType, OSPlatform } from "../../types";

export type UploadStep = "select" | "upload" | "confirm" | "result";

export const AGENT_OPTIONS: { type: AgentType; label: string }[] = [
  { type: "claude", label: "Claude Code" },
  { type: "claude_web", label: "Claude Web" },
  { type: "codex", label: "Codex CLI" },
  { type: "gemini", label: "Gemini CLI" },
];

export const OS_OPTIONS: { platform: OSPlatform; label: string }[] = [
  { platform: "macos", label: "macOS" },
  { platform: "linux", label: "Linux" },
  { platform: "windows", label: "Windows" },
];

export const AGENT_LABELS: Record<AgentType, string> = {
  claude: "Claude Code",
  claude_web: "Claude Web",
  codex: "Codex CLI",
  gemini: "Gemini CLI",
};

export const DEFAULT_AGENT: AgentType = "claude";
export const DEFAULT_OS: OSPlatform = "macos";

export const WEB_EXPORT_STEPS = [
  { num: "1", text: "Open claude.ai and go to Settings" },
  { num: "2", text: 'Scroll to "Export Data" and click Export' },
  { num: "3", text: "Wait for the email, then download the zip" },
  { num: "4", text: "Upload the downloaded zip below" },
];
